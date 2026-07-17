import json
import struct
from pathlib import Path

import pytest

from light_engine.mapping.physical import DigitalNodeFrame, PhysicalFrame
from light_engine.outputs.udp_output import UdpOutputV2
from light_engine.outputs.udp_v2 import HEADER_LENGTH, UdpV2Packet


GOLDEN = Path("firmware/shared/udp_v2_golden.json")


def test_golden_vector_roundtrip():
    vector = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"][0]
    packet = UdpV2Packet(
        message_type=vector["message_type"],
        digital_node_id=vector["digital_node_id"],
        flags=vector["flags"],
        sequence=vector["sequence"],
        pixels=[tuple(pixel) for pixel in vector["pixels"]],
    )
    encoded = packet.encode()
    assert encoded.hex() == vector["encoded_hex"]
    assert UdpV2Packet.decode(encoded) == packet


def test_crc_corruption_rejected():
    encoded = bytearray(UdpV2Packet(digital_node_id=1, sequence=1, pixels=[(1, 2, 3)]).encode())
    encoded[-1] ^= 0x01
    assert UdpV2Packet.decode(bytes(encoded)) is None


def test_length_mismatch_rejected():
    encoded = bytearray(UdpV2Packet(digital_node_id=1, sequence=1, pixels=[(1, 2, 3)]).encode())
    encoded[HEADER_LENGTH - 1] = 4
    assert UdpV2Packet.decode(bytes(encoded)) is None


def test_reserved_flags_rejected():
    with pytest.raises(ValueError):
        UdpV2Packet(digital_node_id=1, sequence=1, flags=0x80, pixels=[])
    encoded = bytearray(UdpV2Packet(digital_node_id=1, sequence=1, pixels=[]).encode())
    encoded[5] = 0x80
    crc = struct.pack(">I", __import__("zlib").crc32(bytes(encoded[:-4])) & 0xFFFFFFFF)
    encoded[-4:] = crc
    assert UdpV2Packet.decode(bytes(encoded)) is None


def test_stale_sequence_rejected():
    encoded = UdpV2Packet(digital_node_id=1, sequence=9, pixels=[]).encode()
    assert UdpV2Packet.decode(encoded, min_sequence=10) is None
    assert UdpV2Packet.decode(encoded, min_sequence=9) is not None


def test_oversize_datagram_rejected_by_configured_limit():
    encoded = UdpV2Packet(digital_node_id=1, sequence=1, pixels=[(1, 2, 3)]).encode()
    assert UdpV2Packet.decode(encoded, max_udp_payload=len(encoded) - 1) is None


def test_udp_output_v2_sends_one_complete_datagram_per_node():
    frame = PhysicalFrame(
        sequence=42,
        timestamp=3.5,
        digital_frames=[
            DigitalNodeFrame(
                node_id=7,
                host="192.0.2.7",
                port=9001,
                pixels=[(0.0, 0.5, 1.0), (1.0, 0.0, 0.25)],
            )
        ],
    )
    output = UdpOutputV2()
    output.open()
    output.send_frame(frame)
    sent = output.get_sent_datagrams()
    assert len(sent) == 1
    payload, address = sent[0]
    assert address == ("192.0.2.7", 9001)
    decoded = UdpV2Packet.decode(payload)
    assert decoded is not None
    assert decoded.digital_node_id == 7
    assert decoded.sequence == 42
    assert decoded.pixels == [(0, 128, 255), (255, 0, 64)]
    assert output.health().logical_frames_sent == 1
    assert output.health().packets_sent == 1
