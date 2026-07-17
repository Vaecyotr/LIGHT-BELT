"""Phase 6 RS-485 output module tests."""

from __future__ import annotations

import pytest

from light_engine.outputs.rs485_v2 import (
    FRAME_LENGTH,
    RS485v2Packet,
    RS485v2StreamParser,
    crc16_ccitt_false,
)
from light_engine.outputs.serial_output import SerialOutputV2


def test_legacy_serial_output_class_is_removed() -> None:
    import light_engine.outputs.serial_output as serial_output

    assert not hasattr(serial_output, "SerialOutput")


def test_rs485_v2_packet_roundtrip() -> None:
    packet = RS485v2Packet(
        node_id=3,
        sequence=513,
        r=255,
        g=128,
        b=64,
        warm_white=32,
        cool_white=16,
        fade_ms=1000,
        flags=1,
    )

    raw = packet.encode()
    decoded = RS485v2Packet.decode(raw)

    assert len(raw) == FRAME_LENGTH
    assert decoded is not None
    assert decoded.node_id == 3
    assert decoded.sequence == 1
    assert decoded.r == 255
    assert decoded.cool_white == 16


def test_rs485_v2_rejects_crc_corruption() -> None:
    raw = bytearray(RS485v2Packet(node_id=1, sequence=1).encode())
    raw[-1] ^= 0x01

    assert RS485v2Packet.decode(bytes(raw)) is None


def test_rs485_v2_rejects_wrong_address() -> None:
    raw = RS485v2Packet(node_id=4, sequence=9).encode()

    assert RS485v2Packet.decode(raw, expected_node_id=5) is None
    assert RS485v2Packet.decode(raw, expected_node_id=4) is not None


def test_rs485_v2_stream_parser_handles_noise_and_split_frames() -> None:
    first = RS485v2Packet(node_id=1, sequence=1, r=10).encode()
    second = RS485v2Packet(node_id=2, sequence=2, g=20).encode()
    parser = RS485v2StreamParser()

    assert parser.feed(b"\x00noise" + first[:4]) == []
    packets = parser.feed(first[4:] + b"\x99" + second)

    assert [packet.node_id for packet in packets] == [1, 2]
    assert parser.valid_frames == 2


def test_rs485_v2_validates_uint_ranges() -> None:
    with pytest.raises(ValueError, match="node_id"):
        RS485v2Packet(node_id=0, sequence=1)
    with pytest.raises(ValueError, match="r"):
        RS485v2Packet(node_id=1, sequence=1, r=256)
    with pytest.raises(ValueError, match="fade_ms"):
        RS485v2Packet(node_id=1, sequence=1, fade_ms=65536)


def test_crc16_ccitt_false_known_value() -> None:
    assert crc16_ccitt_false(b"123456789") == 0x29B1


def test_serial_output_v2_defaults_to_explicit_memory_mode() -> None:
    output = SerialOutputV2()
    output.open()

    assert output.capabilities()["mode"] == "memory"
