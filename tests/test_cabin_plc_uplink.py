"""PLC read-only API (Modbus RTU over a pseudo-terminal) and U01 uplink."""

import json
import os
import pty
import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace

import pytest

if sys.platform != "linux":
    pytest.skip("PLC serial API is Linux only", allow_module_level=True)

from host_services import plc_status_api as plc
from host_services import uplink

STATION = 10
REALS = (55.0, 67.25, 77.0, 88.0, 99.0, 1260.5)
MODE = 2
# 0X1..0X8: exhaust_valve_1 and tv on; 0X1025..0X1032: air compressor and air inlet on.
OUTPUTS, STATUS, HELP = 0b1000_0001, 0b1000_0001, 1


def _registers():
    raw = b""
    for value in REALS:
        packed = struct.pack(">f", value)
        raw += packed[2:] + packed[:2]  # PLC stores the low word first
    return raw + struct.pack(">h", MODE)


def _reply(request):
    station, function, offset, count = struct.unpack(">BBHH", request[:6])
    payload = {(1, 0): bytes([OUTPUTS]), (1, 1024): bytes([STATUS]),
               (2, 0): bytes([HELP]), (3, 2560): _registers()}[(function, offset)]
    assert len(payload) == (count * 2 if function == 3 else (count + 7) // 8)
    frame = bytes([station, function, len(payload)]) + payload
    return frame + plc.crc_word(frame)


@pytest.fixture
def fake_plc():
    master, slave = pty.openpty()
    stop = threading.Event()

    def serve():
        buffer = b""
        while not stop.is_set():
            try:
                buffer += os.read(master, 64)
            except OSError:
                return
            while len(buffer) >= 8:
                request, buffer = buffer[:8], buffer[8:]
                assert request[6:] == plc.crc_word(request[:6])
                os.write(master, _reply(request))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield os.ttyname(slave)
    stop.set()
    os.close(slave)
    os.close(master)


def test_snapshot_decodes_every_point_from_the_serial_line(fake_plc):
    points = plc.snapshot(SimpleNamespace(serial=fake_plc, station=STATION, timeout=1.0))
    assert len(points) == 24
    on = {key for key, point in points.items() if point["type"] == "BOOL" and point["value"]}
    assert on == {"exhaust_valve_1", "tv", "air_compressor_status", "air_inlet_valve_status",
                  "help_button"}
    assert [points[key]["value"] for key in ("oxygen_concentration", "temperature", "humidity",
            "co2_concentration", "pressure", "runtime")] == list(REALS)
    assert points["mode"]["value"] == MODE


def test_api_exits_quietly_without_a_configured_serial(monkeypatch):
    monkeypatch.delenv("LIGHT_BELT_PLC_SERIAL", raising=False)
    monkeypatch.setattr(sys, "argv", ["plc_status_api"])
    plc.main()  # returns instead of serving


class _Recorder(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self._send(*self.server.plc_reply)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append((dict(self.headers), body))
        status, reply = self.server.app_reply(body)
        self._send(status, reply)

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), _Recorder)
    httpd.requests = []
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def _snapshot():
    points = {key: {"value": False} for key, *_ in plc.POINTS}
    points.update({"oxygen_concentration": {"value": 23.5}, "temperature": {"value": 24.1},
                   "humidity": {"value": 45.0}, "co2_concentration": {"value": 600.0},
                   "pressure": {"value": 12.3}, "runtime": {"value": 1260.0}, "mode": {"value": 2},
                   "air_compressor_status": {"value": True}, "equipment_alarm": {"value": True},
                   "air_compressor": {"value": False}, "alarm": {"value": False}})
    return {"status": "ok", "read_at": "2026-11-28T12:51:42.374+00:00", "points": points}


def _uplink(server, tmp_path):
    base = f"http://127.0.0.1:{server.server_port}"
    store = uplink.EventStore(tmp_path / "events.sqlite3")
    return uplink.Uplink(base + uplink.EVENTS_PATH, "SN1", "tok", store,
                         plc_url=base + plc.ROUTE)


def test_plc_snapshot_becomes_one_u01_event_with_the_15_fields(server, tmp_path):
    server.plc_reply = (200, _snapshot())
    link = _uplink(server, tmp_path)
    link.sample_once()
    [event] = link.store.oldest()
    assert set(event) == {"id", "source", "device_id", "ts", "user_id", "username", "data"}
    assert len(event["id"]) == 32 and int(event["id"], 16) >= 0
    assert (event["source"], event["device_id"], event["ts"]) == ("plc", "plc", 1795870302374)
    assert event["user_id"] is None and event["username"] is None
    assert event["data"] == {
        "oxygen_concentration": 23.5, "temperature": 24.1, "humidity": 45.0,
        "co2_concentration": 600.0, "pressure": 12.3, "air_compressor_on": True,
        "oxygen_generator_on": False, "cabin_running": False, "run_time": 1260.0, "mode": 2,
        "exhaust_valve_1_on": False, "exhaust_valve_2_on": False,
        "aux_exhaust_valve_on": False, "alarm": True, "air_inlet_valve_on": False}


def test_unavailable_plc_produces_no_event(server, tmp_path):
    server.plc_reply = (503, {"status": "error", "error": "plc_unavailable"})
    link = _uplink(server, tmp_path)
    link.sample_once()
    assert link.store.count() == 0


def test_only_accepted_events_are_deleted_and_batches_hold_100(server, tmp_path):
    server.plc_reply = (200, _snapshot())
    link = _uplink(server, tmp_path)
    for _ in range(150):
        link.sample_once()
    ids = [event["id"] for event in link.store.oldest(200)]
    server.app_reply = lambda body: (200, {"ok": True, "data": {
        "accepted": [e["id"] for e in body["events"][:60]]}})
    link.send_once()
    headers, body = server.requests[0]
    assert headers["Authorization"] == "Bearer tok"
    assert body["cabin_id"] == "SN1"
    assert [e["id"] for e in body["events"]] == ids[:100]
    assert [e["id"] for e in link.store.oldest(200)] == ids[60:]


@pytest.mark.parametrize("status, kept", [(401, 3), (500, 3), (400, 0)])
def test_error_responses_keep_or_drop_the_batch(server, tmp_path, status, kept):
    server.plc_reply = (200, _snapshot())
    link = _uplink(server, tmp_path)
    for _ in range(3):
        link.sample_once()
    server.app_reply = lambda body: (status, {"ok": False, "error": {"code": "X", "message": ""}})
    link.send_once()
    assert link.store.count() == kept


def test_unreachable_server_keeps_events(tmp_path):
    store = uplink.EventStore(tmp_path / "events.sqlite3")
    store.add(uplink.plc_event(_snapshot()))
    link = uplink.Uplink("http://127.0.0.1:9/api/v1/cabin/events", "SN1", "tok", store)
    link.send_once()
    assert store.count() == 1


def test_events_survive_a_restart(tmp_path):
    path = tmp_path / "events.sqlite3"
    store = uplink.EventStore(path)
    store.add(uplink.plc_event(_snapshot()))
    store.close()
    assert uplink.EventStore(path).count() == 1


@pytest.mark.parametrize("values", [{}, {"LIGHT_BELT_UPLINK_SERVER": "https://app.example"}])
def test_uplink_needs_server_cabin_and_token(monkeypatch, values):
    for name in ("LIGHT_BELT_UPLINK_SERVER", "LIGHT_BELT_CABIN_ID", "LIGHT_BELT_DEVICE_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    assert uplink.settings_from_environment() is None


def test_configured_uplink_posts_to_the_events_path(monkeypatch):
    monkeypatch.setenv("LIGHT_BELT_UPLINK_SERVER", "https://app.example/")
    monkeypatch.setenv("LIGHT_BELT_CABIN_ID", "SN1")
    monkeypatch.setenv("LIGHT_BELT_DEVICE_TOKEN", "tok")
    assert uplink.settings_from_environment() == (
        "https://app.example/api/v1/cabin/events", "SN1", "tok")
