import json
from pathlib import Path

from light_engine.mapping.physical import AnalogNodeCommand, PhysicalFrame
from light_engine.models import RGBCCTColor
from light_engine.outputs.rs485_v2 import (
    FRAME_LENGTH,
    RS485v2Packet,
    RS485v2StreamParser,
)
from light_engine.outputs.serial_output import SerialOutputV2


GOLDEN = Path("firmware/shared/rs485_v2_golden.json")


def test_golden_vector_roundtrip():
    vector = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"][0]
    packet = RS485v2Packet(
        command=vector["command"],
        node_id=vector["node_id"],
        sequence=vector["sequence"],
        r=vector["r"],
        g=vector["g"],
        b=vector["b"],
        warm_white=vector["warm_white"],
        cool_white=vector["cool_white"],
        fade_ms=vector["fade_ms"],
        flags=vector["flags"],
    )
    encoded = packet.encode()
    assert len(encoded) == FRAME_LENGTH
    assert encoded.hex() == vector["encoded_hex"]
    assert RS485v2Packet.decode(encoded) == packet


def test_crc_corruption_rejected():
    packet = RS485v2Packet(node_id=1, sequence=1, r=1).encode()
    corrupted = bytearray(packet)
    corrupted[-1] ^= 0x01
    assert RS485v2Packet.decode(bytes(corrupted)) is None


def test_noise_and_split_stream_recovery():
    first = RS485v2Packet(node_id=1, sequence=1, r=10).encode()
    second = RS485v2Packet(node_id=2, sequence=2, g=20).encode()
    parser = RS485v2StreamParser()
    assert parser.feed(b"\x00bad" + first[:5]) == []
    packets = parser.feed(first[5:] + b"\x99" + second)
    assert [packet.node_id for packet in packets] == [1, 2]
    assert parser.valid_frames == 2


def test_wrong_address_rejected():
    packet = RS485v2Packet(node_id=4, sequence=7).encode()
    assert RS485v2Packet.decode(packet, expected_node_id=5) is None
    assert RS485v2Packet.decode(packet, expected_node_id=4) is not None


def test_sequence_wrap_uses_low_byte():
    packet = RS485v2Packet(node_id=1, sequence=256, b=3)
    decoded = RS485v2Packet.decode(packet.encode())
    assert decoded is not None
    assert decoded.sequence == 0


def test_serial_output_v2_encodes_one_physical_frame_with_shared_sequence():
    frame = PhysicalFrame(
        sequence=513,
        timestamp=1.25,
        analog_commands=[
            AnalogNodeCommand(
                node_id=node_id,
                zone_id=f"zone_{node_id}",
                color=RGBCCTColor(r=node_id / 10, warm_white=0.1),
                fade_ms=25,
            )
            for node_id in range(1, 7)
        ],
    )
    output = SerialOutputV2()
    output.open()
    output.send_frame(frame)
    raw = output.get_memory_bytes()
    assert len(raw) == FRAME_LENGTH * 6
    packets = [
        RS485v2Packet.decode(raw[offset : offset + FRAME_LENGTH])
        for offset in range(0, len(raw), FRAME_LENGTH)
    ]
    assert [packet.node_id for packet in packets if packet is not None] == [1, 2, 3, 4, 5, 6]
    assert {packet.sequence for packet in packets if packet is not None} == {1}
    assert output.health().logical_frames_sent == 1
    assert output.health().packets_sent == 6
