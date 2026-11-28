"""Read-only Modbus RTU to HTTP bridge for the chamber PLC."""
import argparse
import fcntl
import json
import logging
import math
import os
import select
import struct
import termios
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit

POINTS = (
    ["exhaust_valve_1","\u6392\u6c14\u96001","0X1","BOOL"],
    ["exhaust_valve_2","\u6392\u6c14\u96002","0X2","BOOL"],
    ["oxygen_generator","\u5236\u6c27\u673a","0X3","BOOL"],
    ["air_compressor","\u7a7a\u538b\u673a","0X4","BOOL"],
    ["aux_exhaust_valve","\u8f85\u52a9\u6392\u6c14\u9600","0X5","BOOL"],
    ["lighting","\u706f\u5149","0X6","BOOL"],
    ["alarm","\u62a5\u8b66","0X7","BOOL"],
    ["tv","\u7535\u89c6","0X8","BOOL"],
    ["air_compressor_status","\u7a7a\u538b\u673a\u8fd0\u884c\u72b6\u6001","0X1025","BOOL"],
    ["oxygen_generator_status","\u5236\u6c27\u673a\u8fd0\u884c\u72b6\u6001","0X1026","BOOL"],
    ["equipment_running","\u8bbe\u5907\u5de5\u4f5c\u72b6\u6001","0X1027","BOOL"],
    ["exhaust_valve_1_status","\u6392\u6c14\u96001\u72b6\u6001","0X1028","BOOL"],
    ["exhaust_valve_2_status","\u6392\u6c14\u96002\u72b6\u6001","0X1029","BOOL"],
    ["aux_exhaust_valve_status","\u8f85\u52a9\u6392\u6c14\u9600\u72b6\u6001","0X1030","BOOL"],
    ["equipment_alarm","\u8bbe\u5907\u62a5\u8b66","0X1031","BOOL"],
    ["air_inlet_valve_status","\u7a7a\u6c14\u8fdb\u6c14\u9600\u72b6\u6001","0X1032","BOOL"],
    ["help_button","\u6c42\u52a9\u6309\u94ae","1X1","BOOL"],
    ["oxygen_concentration","\u8231\u5185\u6c27\u6d53\u5ea6","4X2561","REAL"],
    ["temperature","\u8231\u5185\u6e29\u5ea6","4X2563","REAL"],
    ["humidity","\u8231\u5185\u6e7f\u5ea6","4X2565","REAL"],
    ["co2_concentration","\u8231\u5185\u4e8c\u6c27\u5316\u78b3\u6d53\u5ea6","4X2567","REAL"],
    ["pressure","\u8231\u5185\u538b\u529b","4X2569","REAL"],
    ["runtime","\u8bbe\u5907\u8fd0\u884c\u65f6\u95f4","4X2571","REAL"],
    ["mode","\u8bbe\u5907\u6a21\u5f0f","4X2573","INT"],
)
READ_GROUPS = ((1, 0, 8), (1, 1024, 8), (2, 0, 1), (3, 2560, 13))
ROUTE = "/api/v1/plc/status"
PORT = 8081


class PlcReadError(Exception):
    """The PLC did not provide a valid, complete snapshot."""


def crc_word(data):
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return struct.pack("<H", crc)


def read_group(fd, station, function, offset, count, timeout):
    header = struct.pack(">BBHH", station, function, offset, count)
    request = header + crc_word(header)
    payload_size = count * 2 if function == 3 else (count + 7) // 8
    # 3.5 character intervals at 9600 baud and 8N1 are under 4 ms.
    time.sleep(0.008)
    termios.tcflush(fd, termios.TCIFLUSH)
    if os.write(fd, request) != len(request):
        raise PlcReadError("short serial write")
    deadline = time.monotonic() + timeout
    response = bytearray()

    while (remaining := deadline - time.monotonic()) > 0:
        if not select.select([fd], [], [], remaining)[0]:
            break
        response.extend(os.read(fd, 256))
        if response.startswith(request):
            del response[:len(request)]
        if len(response) >= 5 and response[:2] == bytes((station, function | 0x80)):
            if len(response) == 5 and response[-2:] == crc_word(response[:-2]):
                raise PlcReadError(f"Modbus exception {response[2]} at offset {offset}")
            raise PlcReadError(f"invalid exception frame at offset {offset}")
        if len(response) >= payload_size + 5:
            break

    if not response:
        raise PlcReadError(f"response timeout at offset {offset}")
    if (len(response) != payload_size + 5
            or response[:3] != bytes((station, function, payload_size))
            or response[-2:] != crc_word(response[:-2])):
        raise PlcReadError(f"invalid response at offset {offset}")
    return bytes(response[3:-2])


def decode_points(blocks):
    outputs, signals, discrete, registers = blocks
    values = [bool(block[0] & (1 << bit))
              for block in (outputs, signals) for bit in range(8)]
    values.append(bool(discrete[0] & 1))
    for i in range(0, 24, 4):
        raw = registers[i + 2:i + 4] + registers[i:i + 2]
        number = struct.unpack(">f", raw)[0]
        if not math.isfinite(number):
            raise PlcReadError(f"non-finite PLC float at offset {2560 + i // 2}")
        values.append(number)
    values.append(struct.unpack(">h", registers[24:26])[0])

    return {
        key: {"row": index, "name": name, "address": address, "type": kind, "value": value}
        for index, ((key, name, address, kind), value)
        in enumerate(zip(POINTS, values, strict=True), start=1)
    }


def snapshot(config):
    with_serial = os.open(config.serial, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = None
    try:
        fcntl.ioctl(with_serial, termios.TIOCEXCL)
        saved = termios.tcgetattr(with_serial)
        settings = termios.tcgetattr(with_serial)
        settings[:6] = [0, 0, termios.CLOCAL | termios.CREAD | termios.CS8,
                        0, termios.B9600, termios.B9600]
        settings[6][termios.VMIN] = settings[6][termios.VTIME] = 0
        termios.tcsetattr(with_serial, termios.TCSANOW, settings)
        blocks = [read_group(with_serial, config.station, function, offset, count, config.timeout)
                  for function, offset, count in READ_GROUPS]
        return decode_points(blocks)
    finally:
        try:
            if saved is not None:
                termios.tcsetattr(with_serial, termios.TCSANOW, saved)
        finally:
            os.close(with_serial)


class StatusHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(3)
        super().setup()

    def send_json(self, status, payload, *, allow_get=False):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if allow_get:
            self.send_header("Allow", "GET")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (OSError, TimeoutError):
                pass

    def do_GET(self):
        if urlsplit(self.path).path != ROUTE:
            self.send_json(404, {"status": "error", "error": "not_found"})
            return
        try:
            points = snapshot(self.server.plc_config)
        except (OSError, termios.error, PlcReadError) as exc:
            logging.warning("PLC read failed: %s", exc)
            self.send_json(503, {"status": "error", "error": "plc_unavailable"})
            return
        read_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        self.send_json(200, {"status": "ok", "read_at": read_at, "points": points})

    def read_only(self):
        self.send_json(405, {"status": "error", "error": "method_not_allowed"}, allow_get=True)

    do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = read_only


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    # Per-device values come from ~/.config/light-belt/host.env, like the Host.
    parser.add_argument("--serial", default=os.environ.get("LIGHT_BELT_PLC_SERIAL"))
    parser.add_argument("--station", type=int, choices=range(1, 248), metavar="1..247",
                        default=int(os.environ.get("LIGHT_BELT_PLC_STATION", "10")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--timeout", type=float, default=0.45)
    config = parser.parse_args()
    if not 0 < config.timeout <= 5:
        parser.error("--timeout must be greater than 0 and no more than 5 seconds")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if not config.serial:
        logging.info("LIGHT_BELT_PLC_SERIAL is not set; PLC API not started")
        return
    with HTTPServer((config.host, config.port), StatusHandler) as server:
        server.plc_config = config
        logging.info("Serving %s on %s:%s", ROUTE, config.host, config.port)
        server.serve_forever()


if __name__ == "__main__":
    main()

