"""Phase-scoped output compatibility matrix tests."""

from __future__ import annotations

import json

from light_engine.mapping.physical import PhysicalFrame
from light_engine.models import (
    DigitalStrip,
    PixelFrame,
    RGBCCTColor,
    RoutedFrame,
    ZoneOutput,
)
from light_engine.outputs import JsonOutput, NullOutput, SimulatorOutput, send_all
from light_engine.outputs.serial_output import SerialOutput, SerialStreamParser
from light_engine.outputs.udp_output import UdpOutput


class RecordingSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def sendto(self, data: bytes, address: tuple[str, int]) -> int:
        self.sent.append((data, address))
        return len(data)


def _memory_serial_output() -> SerialOutput:
    output = SerialOutput()
    output._open = True
    output._running = True
    output._use_memory = True
    output._memory_transport = bytearray()
    output._parser = SerialStreamParser()
    return output


def test_phase_3_legacy_outputs_continue_to_use_logical_frame(tmp_path) -> None:
    logical = PixelFrame(
        timestamp=0.5,
        sequence=21,
        strips=[
            DigitalStrip(
                strip_id="strip_a",
                pixel_count=1,
                pixels=[(0.1, 0.2, 0.3)],
            )
        ],
        zones=[
            ZoneOutput(
                zone_id="zone_a",
                color=RGBCCTColor(r=0.1, g=0.2, b=0.3, warm_white=0.4),
            )
        ],
    )
    routed = RoutedFrame(
        logical=logical,
        physical=PhysicalFrame(sequence=21, timestamp=0.5),
    )
    json_path = tmp_path / "frames.jsonl"
    null_output = NullOutput()
    simulator_output = SimulatorOutput()
    json_output = JsonOutput(str(json_path))
    serial_output = _memory_serial_output()
    udp_socket = RecordingSocket()
    udp_output = UdpOutput(host="127.0.0.1", port=9001)
    udp_output._open = True
    udp_output._enabled = True
    udp_output._socket = udp_socket

    for output in (null_output, simulator_output, json_output):
        output.open()

    try:
        send_all(
            {
                "null": null_output,
                "simulator": simulator_output,
                "json": json_output,
                "serial": serial_output,
                "udp": udp_output,
            },
            routed,
        )

        assert null_output.health().frames_sent == 1
        assert simulator_output.pop_latest() is logical
        assert serial_output.health().frames_sent == 1
        assert serial_output.health().packets_sent == 0
        assert len(serial_output._write_queue) == 1
        assert udp_output.health().frames_sent == 1
        assert udp_output.health().packets_sent == 1
        assert len(udp_socket.sent) == 1

        data = json.loads(json_path.read_text(encoding="utf-8").strip())
        assert data["sequence"] == 21
        assert data["strips"][0]["strip_id"] == "strip_a"
        assert "physical" not in data
    finally:
        for output in (
            null_output,
            simulator_output,
            json_output,
            serial_output,
            udp_output,
        ):
            output.close()
