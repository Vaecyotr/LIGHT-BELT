"""Pure RS-485 v2 RGB+CCT protocol codec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


SYNC = b"\xA5\x5A"
VERSION = 0x02
DEFAULT_COMMAND = 0x01
FRAME_LENGTH = 16
MIN_NODE_ID = 1
MAX_NODE_ID = 6
MAX_UINT8 = 0xFF
MAX_UINT16 = 0xFFFF
MAX_UINT32 = 0xFFFFFFFF


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _require_uint(name: str, value: int, maximum: int) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}], got {value!r}")


@dataclass(frozen=True)
class RS485v2Packet:
    """Fixed 16-byte RS-485 v2 analog node command."""

    node_id: int
    sequence: int
    r: int = 0
    g: int = 0
    b: int = 0
    warm_white: int = 0
    cool_white: int = 0
    fade_ms: int = 0
    flags: int = 0
    command: int = DEFAULT_COMMAND

    def __post_init__(self) -> None:
        if type(self.node_id) is not int or not (MIN_NODE_ID <= self.node_id <= MAX_NODE_ID):
            raise ValueError(f"node_id must be in [{MIN_NODE_ID}, {MAX_NODE_ID}], got {self.node_id!r}")
        _require_uint("sequence", self.sequence, MAX_UINT32)
        for name in ("r", "g", "b", "warm_white", "cool_white", "flags", "command"):
            _require_uint(name, getattr(self, name), MAX_UINT8)
        _require_uint("fade_ms", self.fade_ms, MAX_UINT16)

    def encode(self) -> bytes:
        body = bytes(
            [
                SYNC[0],
                SYNC[1],
                VERSION,
                self.command,
                self.node_id,
                self.sequence & 0xFF,
                self.r,
                self.g,
                self.b,
                self.warm_white,
                self.cool_white,
                (self.fade_ms >> 8) & 0xFF,
                self.fade_ms & 0xFF,
                self.flags,
            ]
        )
        crc = crc16_ccitt_false(body)
        return body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    @classmethod
    def decode(
        cls,
        data: bytes,
        *,
        expected_node_id: Optional[int] = None,
        expected_command: Optional[int] = None,
    ) -> Optional["RS485v2Packet"]:
        if len(data) != FRAME_LENGTH:
            return None
        if data[:2] != SYNC or data[2] != VERSION:
            return None
        received_crc = (data[14] << 8) | data[15]
        if crc16_ccitt_false(data[:14]) != received_crc:
            return None
        command = data[3]
        node_id = data[4]
        if expected_command is not None and command != expected_command:
            return None
        if expected_node_id is not None and node_id != expected_node_id:
            return None
        if not (MIN_NODE_ID <= node_id <= MAX_NODE_ID):
            return None
        return cls(
            command=command,
            node_id=node_id,
            sequence=data[5],
            r=data[6],
            g=data[7],
            b=data[8],
            warm_white=data[9],
            cool_white=data[10],
            fade_ms=(data[11] << 8) | data[12],
            flags=data[13],
        )


class RS485v2StreamParser:
    """Streaming parser for noisy or fragmented fixed-length v2 frames."""

    def __init__(self, *, expected_node_id: Optional[int] = None, max_buffer: int = 4096):
        self._buffer = bytearray()
        self._expected_node_id = expected_node_id
        self._max_buffer = max_buffer
        self.valid_frames = 0
        self.invalid_frames = 0

    def feed(self, data: bytes) -> list[RS485v2Packet]:
        self._buffer.extend(data)
        if len(self._buffer) > self._max_buffer:
            self._buffer = self._buffer[-self._max_buffer :]

        packets: list[RS485v2Packet] = []
        while len(self._buffer) >= FRAME_LENGTH:
            sync_index = self._buffer.find(SYNC)
            if sync_index < 0:
                self._buffer.clear()
                break
            if sync_index:
                del self._buffer[:sync_index]
            if len(self._buffer) < FRAME_LENGTH:
                break
            candidate = bytes(self._buffer[:FRAME_LENGTH])
            packet = RS485v2Packet.decode(candidate, expected_node_id=self._expected_node_id)
            if packet is None:
                del self._buffer[0]
                self.invalid_frames += 1
                continue
            packets.append(packet)
            self.valid_frames += 1
            del self._buffer[:FRAME_LENGTH]
        return packets
