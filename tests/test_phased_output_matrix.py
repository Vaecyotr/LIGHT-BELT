"""Phase 6 output matrix tests."""

from __future__ import annotations

import json

from light_engine.mapping.physical import (
    AnalogNodeCommand,
    DigitalNodeFrame,
    PhysicalFrame,
)
from light_engine.models import RGBCCTColor
from light_engine.outputs import JsonOutput, NullOutput, OutputMode, SimulatorOutput, send_all
from light_engine.outputs.rs485_v2 import FRAME_LENGTH
from light_engine.outputs.serial_output import SerialOutputV2
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import UdpV2Packet


def _physical_frame() -> PhysicalFrame:
    return PhysicalFrame(
        timestamp=0.5,
        sequence=21,
        analog_commands=[
            AnalogNodeCommand(
                node_id=node_id,
                zone_id=f"zone_{node_id}",
                color=RGBCCTColor(r=0.1, g=0.2, b=0.3, warm_white=0.4),
            )
            for node_id in range(1, 7)
        ],
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="127.0.0.1",
                port=9001,
                pixels=[(0.1, 0.2, 0.3)],
            )
        ],
    )


def test_phase_6_outputs_consume_physical_frame_directly(tmp_path) -> None:
    frame = _physical_frame()
    json_path = tmp_path / "frames.jsonl"
    null_output = NullOutput()
    simulator_output = SimulatorOutput()
    json_output = JsonOutput(str(json_path))
    serial_output = SerialOutputV2(mode=OutputMode.MEMORY)
    udp_output = UdpOutputV2(mode=OutputMode.MEMORY)

    for output in (
        null_output,
        simulator_output,
        json_output,
        serial_output,
        udp_output,
    ):
        output.open()

    try:
        send_all(
            {
                "null": null_output,
                "simulator": simulator_output,
                "json": json_output,
                "rs485_v2": serial_output,
                "udp_v2": udp_output,
            },
            frame,
        )

        assert null_output.health().frames_sent == 1
        assert simulator_output.pop_latest() is frame
        assert serial_output.health().logical_frames_sent == 1
        assert serial_output.health().packets_sent == 6
        assert len(serial_output.get_memory_bytes()) == FRAME_LENGTH * 6
        assert udp_output.health().logical_frames_sent == 1
        assert udp_output.health().packets_sent == 1

        decoded_udp = UdpV2Packet.decode(udp_output.get_sent_datagrams()[0][0])
        assert decoded_udp is not None
        assert decoded_udp.sequence == 21

        data = json.loads(json_path.read_text(encoding="utf-8").strip())
        assert data["sequence"] == 21
        assert data["analog_commands"][0]["node_id"] == 1
        assert data["digital_frames"][0]["node_id"] == 7
    finally:
        for output in (
            null_output,
            simulator_output,
            json_output,
            serial_output,
            udp_output,
        ):
            output.close()
