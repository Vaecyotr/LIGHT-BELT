"""Phase 6 UDP output module tests."""

from __future__ import annotations

import pytest

from light_engine.mapping.physical import DigitalNodeFrame, PhysicalFrame
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import UdpV2Packet, crc32


def test_legacy_udp_output_class_is_removed() -> None:
    import light_engine.outputs.udp_output as udp_output

    assert not hasattr(udp_output, "UdpOutput")


def test_udp_v2_packet_roundtrip() -> None:
    pixels = [(255, 128, 0), (0, 255, 100), (50, 50, 200)]
    packet = UdpV2Packet(digital_node_id=3, sequence=42, pixels=pixels)

    raw = packet.encode()
    decoded = UdpV2Packet.decode(raw)

    assert decoded is not None
    assert decoded.digital_node_id == 3
    assert decoded.sequence == 42
    assert decoded.pixels == pixels


def test_udp_v2_rejects_crc_corruption() -> None:
    raw = bytearray(
        UdpV2Packet(digital_node_id=1, sequence=1, pixels=[(255, 0, 0)]).encode()
    )
    raw[-1] ^= 0x01

    assert UdpV2Packet.decode(bytes(raw)) is None


def test_udp_v2_rejects_bad_magic_and_reserved_flags() -> None:
    raw = bytearray(UdpV2Packet(digital_node_id=1, sequence=1, pixels=[]).encode())
    raw[0] = 0x00
    assert UdpV2Packet.decode(bytes(raw)) is None

    with pytest.raises(ValueError, match="reserved flags"):
        UdpV2Packet(digital_node_id=1, sequence=1, flags=0x80, pixels=[])


def test_udp_v2_rejects_stale_sequence_and_oversize_datagram() -> None:
    raw = UdpV2Packet(digital_node_id=1, sequence=9, pixels=[]).encode()

    assert UdpV2Packet.decode(raw, min_sequence=10) is None
    assert UdpV2Packet.decode(raw, min_sequence=9) is not None
    assert UdpV2Packet.decode(raw, max_udp_payload=len(raw) - 1) is None


def test_udp_output_v2_uses_physical_frame_sequence() -> None:
    output = UdpOutputV2()
    output.open()
    frame = PhysicalFrame(
        timestamp=0.0,
        sequence=1234,
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="192.0.2.7",
                port=9001,
                pixels=[(1.0, 0.0, 0.0)],
            )
        ],
    )

    output.send_frame(frame)

    sent = output.get_sent_datagrams()
    assert len(sent) == 1
    decoded = UdpV2Packet.decode(sent[0][0])
    assert decoded is not None
    assert decoded.sequence == 1234
    assert decoded.digital_node_id == 7


def test_udp_output_v2_does_not_generate_independent_sequence() -> None:
    output = UdpOutputV2()
    output.open()
    frame = PhysicalFrame(
        timestamp=0.0,
        sequence=77,
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="192.0.2.7",
                port=9001,
                pixels=[(0.0, 1.0, 0.0)],
            )
        ],
    )

    output.send_frame(frame)
    output.send_frame(frame)

    packets = [UdpV2Packet.decode(data) for data, _ in output.get_sent_datagrams()]
    assert [packet.sequence for packet in packets if packet is not None] == [77, 77]


def test_crc32_known_value() -> None:
    assert crc32(b"123456789") == 0xCBF43926
