"""Pure UDP v2 WS2811 physical-node protocol codec."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Optional


MAGIC = 0x4C45
VERSION = 0x02
MESSAGE_TYPE_FRAME = 0x01
FLAG_SAFE_STATE = 0x01
FLAG_KEY_FRAME = 0x02
ALLOWED_FLAGS = FLAG_SAFE_STATE | FLAG_KEY_FRAME
HEADER_FORMAT = ">HBBBBIHH"
HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)
CRC_LENGTH = 4
MAX_UDP_PAYLOAD = 65507
MAX_UINT8 = 0xFF
MAX_UINT16 = 0xFFFF
MAX_UINT32 = 0xFFFFFFFF


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & MAX_UINT32


def _require_uint(name: str, value: int, maximum: int) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}], got {value!r}")


def _pixels_to_payload(pixels: list[tuple[int, int, int]]) -> bytes:
    payload = bytearray()
    for pixel in pixels:
        if len(pixel) != 3:
            raise ValueError(f"pixel must contain exactly 3 channels, got {pixel!r}")
        for channel in pixel:
            _require_uint("pixel channel", channel, MAX_UINT8)
        payload.extend(pixel)
    return bytes(payload)


@dataclass(frozen=True)
class UdpV2Packet:
    """One complete physical RGB frame for one ESP32 node."""

    digital_node_id: int
    sequence: int
    pixels: list[tuple[int, int, int]]
    flags: int = 0
    message_type: int = MESSAGE_TYPE_FRAME

    def __post_init__(self) -> None:
        _require_uint("digital_node_id", self.digital_node_id, MAX_UINT8)
        if self.digital_node_id == 0:
            raise ValueError("digital_node_id must be non-zero")
        _require_uint("sequence", self.sequence, MAX_UINT32)
        _require_uint("message_type", self.message_type, MAX_UINT8)
        _require_uint("flags", self.flags, MAX_UINT8)
        if self.flags & ~ALLOWED_FLAGS:
            raise ValueError(f"reserved flags must be zero, got 0x{self.flags:02X}")
        if len(self.pixels) > MAX_UINT16:
            raise ValueError(f"pixel count must fit uint16, got {len(self.pixels)}")
        payload = _pixels_to_payload(self.pixels)
        if len(payload) > MAX_UINT16:
            raise ValueError(f"payload length must fit uint16, got {len(payload)}")

    def encode(self) -> bytes:
        payload = _pixels_to_payload(self.pixels)
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            self.message_type,
            self.digital_node_id,
            self.flags,
            self.sequence,
            len(self.pixels),
            len(payload),
        )
        checksum = crc32(header + payload)
        return header + payload + struct.pack(">I", checksum)

    @classmethod
    def decode(
        cls,
        data: bytes,
        *,
        expected_node_id: Optional[int] = None,
        min_sequence: Optional[int] = None,
        max_udp_payload: int = MAX_UDP_PAYLOAD,
    ) -> Optional["UdpV2Packet"]:
        if len(data) < HEADER_LENGTH + CRC_LENGTH:
            return None
        if len(data) > max_udp_payload:
            return None
        header = data[:HEADER_LENGTH]
        try:
            magic, version, message_type, node_id, flags, sequence, pixel_count, payload_length = struct.unpack(
                HEADER_FORMAT, header
            )
        except struct.error:
            return None
        if magic != MAGIC or version != VERSION:
            return None
        if flags & ~ALLOWED_FLAGS:
            return None
        if expected_node_id is not None and node_id != expected_node_id:
            return None
        if min_sequence is not None and sequence < min_sequence:
            return None
        if payload_length != pixel_count * 3:
            return None
        expected_length = HEADER_LENGTH + payload_length + CRC_LENGTH
        if len(data) != expected_length:
            return None
        payload = data[HEADER_LENGTH : HEADER_LENGTH + payload_length]
        received_crc = struct.unpack(">I", data[-CRC_LENGTH:])[0]
        if crc32(data[:-CRC_LENGTH]) != received_crc:
            return None
        pixels = [
            (payload[idx], payload[idx + 1], payload[idx + 2])
            for idx in range(0, payload_length, 3)
        ]
        try:
            return cls(
                message_type=message_type,
                digital_node_id=node_id,
                flags=flags,
                sequence=sequence,
                pixels=pixels,
            )
        except ValueError:
            return None
