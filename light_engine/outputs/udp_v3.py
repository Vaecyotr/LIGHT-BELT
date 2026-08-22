"""Pure UDP v3 codec for one complete multi-output ESP32 node frame.

Wire order is big-endian and deliberately self-describing::

    magic:u16 version:u8 type:u8 node:u8 flags:u8 sequence:u32
    media_timestamp_us:u64 apply_at_us:u64 output_count:u8 payload_length:u16
    repeated (output_id:u8 gpio:u8 pixel_count:u16 output_length:u16 payload)
    crc32:u32

``apply_at_us == 0`` means immediate application.  A non-zero value is valid
only when ``SCHEDULED_APPLY`` is set, so old immediate frames remain
unambiguous.  The codec contains no sockets, clocks, GPIO drivers, or mutable
sequence state.
The transport marks sequence 1 of a newly opened Host output as `KEY_FRAME`;
stateful firmware, not this pure codec, owns the exact session-reset rule.

Clock synchronization uses a separate, broadcast-safe fixed-length message::

    magic:u16 version:u8 type:u8 sequence:u32 host_monotonic_us:u64 crc32:u32
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from light_engine.outputs.udp_v2 import (
    CRC_LENGTH,
    FLAG_KEY_FRAME,
    FLAG_SAFE_STATE,
    MAX_UINT8,
    MAX_UINT16,
    MAX_UINT32,
    crc32,
)


MAGIC = 0x4C45
VERSION = 0x03
MESSAGE_TYPE_FRAME = 0x01
MESSAGE_TYPE_CLOCK_BEACON = 0x02
MESSAGE_TYPE_FRAME_CHUNK = 0x03
FLAG_SCHEDULED_APPLY = 0x04
ALLOWED_FLAGS = FLAG_SAFE_STATE | FLAG_KEY_FRAME | FLAG_SCHEDULED_APPLY
HEADER_FORMAT = ">HBBBBIQQBH"
HEADER_LENGTH = struct.calcsize(HEADER_FORMAT)
OUTPUT_FORMAT = ">BBHH"
OUTPUT_LENGTH = struct.calcsize(OUTPUT_FORMAT)
CHUNK_FORMAT = ">BBHHHH"
CHUNK_LENGTH = struct.calcsize(CHUNK_FORMAT)
CLOCK_BEACON_FORMAT = ">HBBIQ"
CLOCK_BEACON_BODY_LENGTH = struct.calcsize(CLOCK_BEACON_FORMAT)
CLOCK_BEACON_LENGTH = CLOCK_BEACON_BODY_LENGTH + CRC_LENGTH
MAX_UINT64 = 0xFFFFFFFFFFFFFFFF
MAX_UDP_PAYLOAD = 65507


def _require_uint(name: str, value: int, maximum: int) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"{name} must be an integer in [0, {maximum}], got {value!r}")


def _pixels_to_payload(pixels: Sequence[tuple[int, int, int]]) -> bytes:
    payload = bytearray()
    for pixel in pixels:
        if len(pixel) != 3:
            raise ValueError(f"pixel must contain exactly 3 channels, got {pixel!r}")
        for channel in pixel:
            _require_uint("pixel channel", channel, MAX_UINT8)
        payload.extend(pixel)
    return bytes(payload)


@dataclass(frozen=True)
class UdpV3Output:
    output_id: int
    gpio: int
    pixels: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        _require_uint("output_id", self.output_id, MAX_UINT8)
        if self.output_id == 0:
            raise ValueError("output_id must be non-zero")
        _require_uint("gpio", self.gpio, MAX_UINT8)
        if len(self.pixels) > MAX_UINT16:
            raise ValueError("pixel count must fit uint16")
        _pixels_to_payload(self.pixels)


@dataclass(frozen=True)
class UdpV3Packet:
    """One atomic node frame; output boundaries are preserved in the packet."""

    digital_node_id: int
    sequence: int
    media_timestamp_us: int
    outputs: tuple[UdpV3Output, ...]
    apply_at_us: Optional[int] = None
    flags: int = 0
    message_type: int = MESSAGE_TYPE_FRAME

    def __post_init__(self) -> None:
        _require_uint("digital_node_id", self.digital_node_id, MAX_UINT8)
        if self.digital_node_id == 0:
            raise ValueError("digital_node_id must be non-zero")
        _require_uint("sequence", self.sequence, MAX_UINT32)
        _require_uint("media_timestamp_us", self.media_timestamp_us, MAX_UINT64)
        if self.apply_at_us is not None:
            _require_uint("apply_at_us", self.apply_at_us, MAX_UINT64)
            if self.apply_at_us == 0:
                raise ValueError("apply_at_us must be non-zero when scheduled")
        _require_uint("flags", self.flags, MAX_UINT8)
        if self.flags & ~ALLOWED_FLAGS:
            raise ValueError(f"reserved flags must be zero, got 0x{self.flags:02X}")
        is_scheduled = bool(self.flags & FLAG_SCHEDULED_APPLY)
        if is_scheduled != (self.apply_at_us is not None):
            raise ValueError(
                "FLAG_SCHEDULED_APPLY and apply_at_us must be present together"
            )
        _require_uint("message_type", self.message_type, MAX_UINT8)
        if self.message_type != MESSAGE_TYPE_FRAME:
            raise ValueError(f"unsupported message_type {self.message_type!r}")
        if not self.outputs or len(self.outputs) > 3:
            raise ValueError("a UDP v3 node frame must contain one to three outputs")
        output_ids = [output.output_id for output in self.outputs]
        gpios = [output.gpio for output in self.outputs]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("output IDs must be unique within one node frame")
        if len(gpios) != len(set(gpios)):
            raise ValueError("GPIO assignments must be unique within one node frame")

    def encode(self) -> bytes:
        payload = bytearray()
        for output in self.outputs:
            rgb = _pixels_to_payload(output.pixels)
            payload.extend(struct.pack(OUTPUT_FORMAT, output.output_id, output.gpio, len(output.pixels), len(rgb)))
            payload.extend(rgb)
        if len(payload) > MAX_UINT16:
            raise ValueError(
                "complete-frame payload does not fit uint16; use frame chunking"
            )
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            self.message_type,
            self.digital_node_id,
            self.flags,
            self.sequence,
            self.media_timestamp_us,
            0 if self.apply_at_us is None else self.apply_at_us,
            len(self.outputs),
            len(payload),
        )
        raw = header + bytes(payload)
        return raw + struct.pack(">I", crc32(raw))

    @classmethod
    def decode(
        cls,
        data: bytes,
        *,
        expected_node_id: Optional[int] = None,
        expected_outputs: Optional[Mapping[int, tuple[int, int]]] = None,
        min_sequence: Optional[int] = None,
        max_udp_payload: int = MAX_UDP_PAYLOAD,
    ) -> Optional["UdpV3Packet"]:
        if len(data) < HEADER_LENGTH + CRC_LENGTH or len(data) > max_udp_payload:
            return None
        try:
            (magic, version, message_type, node_id, flags, sequence, media_timestamp_us,
             apply_at_raw, output_count, payload_length) = struct.unpack(HEADER_FORMAT, data[:HEADER_LENGTH])
        except struct.error:
            return None
        if (
            magic != MAGIC
            or version != VERSION
            or message_type != MESSAGE_TYPE_FRAME
            or flags & ~ALLOWED_FLAGS
        ):
            return None
        if bool(flags & FLAG_SCHEDULED_APPLY) != (apply_at_raw != 0):
            return None
        if output_count == 0 or output_count > 3:
            return None
        if expected_node_id is not None and node_id != expected_node_id:
            return None
        if min_sequence is not None and sequence < min_sequence:
            return None
        if len(data) != HEADER_LENGTH + payload_length + CRC_LENGTH:
            return None
        if crc32(data[:-CRC_LENGTH]) != struct.unpack(">I", data[-CRC_LENGTH:])[0]:
            return None
        cursor = HEADER_LENGTH
        payload_end = cursor + payload_length
        outputs: list[UdpV3Output] = []
        seen_ids: set[int] = set()
        seen_gpios: set[int] = set()
        for _ in range(output_count):
            if cursor + OUTPUT_LENGTH > payload_end:
                return None
            output_id, gpio, pixel_count, output_length = struct.unpack(
                OUTPUT_FORMAT, data[cursor : cursor + OUTPUT_LENGTH]
            )
            cursor += OUTPUT_LENGTH
            if output_id == 0 or output_id in seen_ids or gpio in seen_gpios:
                return None
            if output_length != pixel_count * 3:
                return None
            if cursor + output_length > payload_end:
                return None
            if expected_outputs is not None:
                expected = expected_outputs.get(output_id)
                if expected != (gpio, pixel_count):
                    return None
            raw_pixels = data[cursor : cursor + output_length]
            cursor += output_length
            seen_ids.add(output_id)
            seen_gpios.add(gpio)
            try:
                outputs.append(UdpV3Output(
                    output_id=output_id,
                    gpio=gpio,
                    pixels=tuple(
                        (raw_pixels[index], raw_pixels[index + 1], raw_pixels[index + 2])
                        for index in range(0, output_length, 3)
                    ),
                ))
            except ValueError:
                return None
        if cursor != payload_end:
            return None
        if expected_outputs is not None and seen_ids != set(expected_outputs):
            return None
        try:
            return cls(
                message_type=message_type,
                digital_node_id=node_id,
                flags=flags,
                sequence=sequence,
                media_timestamp_us=media_timestamp_us,
                apply_at_us=None if apply_at_raw == 0 else apply_at_raw,
                outputs=tuple(outputs),
            )
        except ValueError:
            return None


@dataclass(frozen=True)
class UdpV3Chunk:
    """One validated RGB range within a complete logical output."""

    output_id: int
    gpio: int
    total_pixel_count: int
    chunk_offset: int
    pixels: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        _require_uint("output_id", self.output_id, MAX_UINT8)
        if self.output_id == 0:
            raise ValueError("output_id must be non-zero")
        _require_uint("gpio", self.gpio, MAX_UINT8)
        _require_uint("total_pixel_count", self.total_pixel_count, MAX_UINT16)
        if self.total_pixel_count == 0:
            raise ValueError("total_pixel_count must be non-zero")
        _require_uint("chunk_offset", self.chunk_offset, MAX_UINT16)
        if not self.pixels:
            raise ValueError("a chunk must contain at least one RGB pixel")
        if len(self.pixels) > MAX_UINT16:
            raise ValueError("chunk pixel count must fit uint16")
        if self.chunk_offset + len(self.pixels) > self.total_pixel_count:
            raise ValueError("chunk range must fit within total_pixel_count")
        payload = _pixels_to_payload(self.pixels)
        if len(payload) > MAX_UINT16:
            raise ValueError("chunk payload length must fit uint16")


@dataclass(frozen=True)
class UdpV3ChunkPacket:
    """One or more ranges belonging to one UDP v3 logical node frame."""

    digital_node_id: int
    sequence: int
    media_timestamp_us: int
    chunks: tuple[UdpV3Chunk, ...]
    apply_at_us: Optional[int] = None
    flags: int = 0
    message_type: int = MESSAGE_TYPE_FRAME_CHUNK

    def __post_init__(self) -> None:
        _require_uint("digital_node_id", self.digital_node_id, MAX_UINT8)
        if self.digital_node_id == 0:
            raise ValueError("digital_node_id must be non-zero")
        _require_uint("sequence", self.sequence, MAX_UINT32)
        _require_uint("media_timestamp_us", self.media_timestamp_us, MAX_UINT64)
        if self.apply_at_us is not None:
            _require_uint("apply_at_us", self.apply_at_us, MAX_UINT64)
            if self.apply_at_us == 0:
                raise ValueError("apply_at_us must be non-zero when scheduled")
        _require_uint("flags", self.flags, MAX_UINT8)
        if self.flags & ~ALLOWED_FLAGS:
            raise ValueError(f"reserved flags must be zero, got 0x{self.flags:02X}")
        if bool(self.flags & FLAG_SCHEDULED_APPLY) != (self.apply_at_us is not None):
            raise ValueError(
                "FLAG_SCHEDULED_APPLY and apply_at_us must be present together"
            )
        _require_uint("message_type", self.message_type, MAX_UINT8)
        if self.message_type != MESSAGE_TYPE_FRAME_CHUNK:
            raise ValueError(f"unsupported message_type {self.message_type!r}")
        if not self.chunks or len(self.chunks) > 3:
            raise ValueError("a UDP v3 chunk packet must contain one to three chunks")
        output_ids = [chunk.output_id for chunk in self.chunks]
        gpios = [chunk.gpio for chunk in self.chunks]
        if len(output_ids) != len(set(output_ids)):
            raise ValueError("chunk output IDs must be unique within one datagram")
        if len(gpios) != len(set(gpios)):
            raise ValueError("chunk GPIO assignments must be unique within one datagram")
        payload_length = sum(
            CHUNK_LENGTH + len(chunk.pixels) * 3 for chunk in self.chunks
        )
        if payload_length > MAX_UINT16:
            raise ValueError("chunk packet payload length must fit uint16")

    def encode(self) -> bytes:
        payload = bytearray()
        for chunk in self.chunks:
            rgb = _pixels_to_payload(chunk.pixels)
            payload.extend(
                struct.pack(
                    CHUNK_FORMAT,
                    chunk.output_id,
                    chunk.gpio,
                    chunk.total_pixel_count,
                    chunk.chunk_offset,
                    len(chunk.pixels),
                    len(rgb),
                )
            )
            payload.extend(rgb)
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            VERSION,
            self.message_type,
            self.digital_node_id,
            self.flags,
            self.sequence,
            self.media_timestamp_us,
            0 if self.apply_at_us is None else self.apply_at_us,
            len(self.chunks),
            len(payload),
        )
        raw = header + bytes(payload)
        return raw + struct.pack(">I", crc32(raw))

    @classmethod
    def decode(
        cls,
        data: bytes,
        *,
        expected_node_id: Optional[int] = None,
        max_udp_payload: int = MAX_UDP_PAYLOAD,
    ) -> Optional["UdpV3ChunkPacket"]:
        if len(data) < HEADER_LENGTH + CHUNK_LENGTH + CRC_LENGTH or len(data) > max_udp_payload:
            return None
        try:
            (
                magic,
                version,
                message_type,
                node_id,
                flags,
                sequence,
                media_timestamp_us,
                apply_at_raw,
                chunk_count,
                payload_length,
            ) = struct.unpack(HEADER_FORMAT, data[:HEADER_LENGTH])
        except struct.error:
            return None
        if (
            magic != MAGIC
            or version != VERSION
            or message_type != MESSAGE_TYPE_FRAME_CHUNK
            or flags & ~ALLOWED_FLAGS
            or bool(flags & FLAG_SCHEDULED_APPLY) != (apply_at_raw != 0)
            or chunk_count == 0
            or chunk_count > 3
            or (expected_node_id is not None and node_id != expected_node_id)
            or len(data) != HEADER_LENGTH + payload_length + CRC_LENGTH
            or crc32(data[:-CRC_LENGTH]) != struct.unpack(">I", data[-CRC_LENGTH:])[0]
        ):
            return None
        cursor = HEADER_LENGTH
        payload_end = cursor + payload_length
        chunks: list[UdpV3Chunk] = []
        seen_ids: set[int] = set()
        seen_gpios: set[int] = set()
        for _ in range(chunk_count):
            if cursor + CHUNK_LENGTH > payload_end:
                return None
            (
                output_id,
                gpio,
                total_pixel_count,
                chunk_offset,
                chunk_pixel_count,
                chunk_payload_length,
            ) = struct.unpack(CHUNK_FORMAT, data[cursor : cursor + CHUNK_LENGTH])
            cursor += CHUNK_LENGTH
            if (
                output_id == 0
                or output_id in seen_ids
                or gpio in seen_gpios
                or total_pixel_count == 0
                or chunk_pixel_count == 0
                or chunk_payload_length != chunk_pixel_count * 3
                or chunk_offset + chunk_pixel_count > total_pixel_count
                or cursor + chunk_payload_length > payload_end
            ):
                return None
            raw_pixels = data[cursor : cursor + chunk_payload_length]
            cursor += chunk_payload_length
            try:
                chunks.append(
                    UdpV3Chunk(
                        output_id=output_id,
                        gpio=gpio,
                        total_pixel_count=total_pixel_count,
                        chunk_offset=chunk_offset,
                        pixels=tuple(
                            (
                                raw_pixels[index],
                                raw_pixels[index + 1],
                                raw_pixels[index + 2],
                            )
                            for index in range(0, chunk_payload_length, 3)
                        ),
                    )
                )
            except ValueError:
                return None
            seen_ids.add(output_id)
            seen_gpios.add(gpio)
        if cursor != payload_end:
            return None
        try:
            return cls(
                digital_node_id=node_id,
                sequence=sequence,
                media_timestamp_us=media_timestamp_us,
                apply_at_us=None if apply_at_raw == 0 else apply_at_raw,
                flags=flags,
                chunks=tuple(chunks),
            )
        except ValueError:
            return None


def encode_udp_v3_frame_datagrams(
    packet: UdpV3Packet,
    *,
    max_udp_payload: int = MAX_UDP_PAYLOAD,
) -> list[bytes]:
    """Encode one logical frame, chunking only when one datagram cannot fit."""

    if type(max_udp_payload) is not int or not 1 <= max_udp_payload <= MAX_UDP_PAYLOAD:
        raise ValueError(
            f"max_udp_payload must be an integer in [1, {MAX_UDP_PAYLOAD}]"
        )
    complete_payload_length = sum(
        OUTPUT_LENGTH + len(output.pixels) * 3 for output in packet.outputs
    )
    if complete_payload_length <= MAX_UINT16:
        complete = packet.encode()
        if len(complete) <= max_udp_payload:
            return [complete]
    available_rgb_bytes = max_udp_payload - HEADER_LENGTH - CHUNK_LENGTH - CRC_LENGTH
    pixels_per_chunk = available_rgb_bytes // 3
    if pixels_per_chunk < 1:
        raise ValueError("max_udp_payload must allow at least one RGB pixel chunk")
    datagrams: list[bytes] = []
    for output in packet.outputs:
        total = len(output.pixels)
        for offset in range(0, total, pixels_per_chunk):
            chunk_packet = UdpV3ChunkPacket(
                digital_node_id=packet.digital_node_id,
                sequence=packet.sequence,
                media_timestamp_us=packet.media_timestamp_us,
                apply_at_us=packet.apply_at_us,
                flags=packet.flags,
                chunks=(
                    UdpV3Chunk(
                        output_id=output.output_id,
                        gpio=output.gpio,
                        total_pixel_count=total,
                        chunk_offset=offset,
                        pixels=output.pixels[offset : offset + pixels_per_chunk],
                    ),
                ),
            )
            encoded = chunk_packet.encode()
            if len(encoded) > max_udp_payload:
                raise AssertionError("UDP v3 chunk packetizer exceeded max_udp_payload")
            datagrams.append(encoded)
    return datagrams


def is_newer_sequence(candidate: int, previous: int) -> bool:
    """Return whether candidate is strictly newer under uint32 wrap semantics."""

    _require_uint("candidate sequence", candidate, MAX_UINT32)
    _require_uint("previous sequence", previous, MAX_UINT32)
    distance = (candidate - previous) & MAX_UINT32
    return 0 < distance < 0x80000000


class UdpV3FrameReassembler:
    """Pure one-incomplete-frame receiver mirroring the firmware contract."""

    def __init__(
        self,
        expected_node_id: int,
        expected_outputs: Mapping[int, tuple[int, int]],
    ) -> None:
        _require_uint("expected_node_id", expected_node_id, MAX_UINT8)
        if expected_node_id == 0:
            raise ValueError("expected_node_id must be non-zero")
        if not expected_outputs or len(expected_outputs) > 3:
            raise ValueError("expected_outputs must contain one to three outputs")
        normalized: dict[int, tuple[int, int]] = {}
        seen_gpios: set[int] = set()
        for output_id, expected in expected_outputs.items():
            _require_uint("expected output_id", output_id, MAX_UINT8)
            if output_id == 0 or output_id in normalized:
                raise ValueError("expected output IDs must be unique and non-zero")
            if not isinstance(expected, tuple) or len(expected) != 2:
                raise ValueError("expected output must be a (gpio, pixel_count) tuple")
            gpio, pixel_count = expected
            _require_uint("expected gpio", gpio, MAX_UINT8)
            _require_uint("expected pixel_count", pixel_count, MAX_UINT16)
            if pixel_count == 0:
                raise ValueError("expected pixel_count must be non-zero")
            if gpio in seen_gpios:
                raise ValueError("expected GPIO assignments must be unique")
            normalized[output_id] = (gpio, pixel_count)
            seen_gpios.add(gpio)
        self.expected_node_id = expected_node_id
        self.expected_outputs = normalized
        self._active_identity: tuple[int, int, int | None, int] | None = None
        self._buffers: dict[int, list[tuple[int, int, int] | None]] = {}
        self._last_completed_identity: tuple[int, int, int | None, int] | None = None
        self._last_completed_sequence: int | None = None

    @staticmethod
    def _identity(
        sequence: int,
        media_timestamp_us: int,
        apply_at_us: int | None,
        flags: int,
    ) -> tuple[int, int, int | None, int]:
        return (sequence, media_timestamp_us, apply_at_us, flags)

    @staticmethod
    def _is_session_start(sequence: int, flags: int) -> bool:
        return sequence == 1 and bool(flags & FLAG_KEY_FRAME)

    def _can_start_identity(
        self, identity: tuple[int, int, int | None, int]
    ) -> bool:
        sequence, _media, _apply, flags = identity
        if identity == self._last_completed_identity:
            return False
        reference_sequence = (
            self._active_identity[0]
            if self._active_identity is not None
            else self._last_completed_sequence
        )
        if reference_sequence is None:
            return True
        if self._active_identity is not None and sequence == reference_sequence:
            return identity == self._active_identity
        if self._is_session_start(sequence, flags):
            return True
        return is_newer_sequence(sequence, reference_sequence)

    def _begin(self, identity: tuple[int, int, int | None, int]) -> None:
        self._active_identity = identity
        self._buffers = {
            output_id: [None] * pixel_count
            for output_id, (_gpio, pixel_count) in self.expected_outputs.items()
        }

    def _mark_complete(
        self,
        packet: UdpV3Packet,
        identity: tuple[int, int, int | None, int],
    ) -> UdpV3Packet:
        self._last_completed_identity = identity
        self._last_completed_sequence = packet.sequence
        self._active_identity = None
        self._buffers = {}
        return packet

    def accept(self, data: bytes) -> Optional[UdpV3Packet]:
        complete = UdpV3Packet.decode(
            data,
            expected_node_id=self.expected_node_id,
            expected_outputs=self.expected_outputs,
        )
        if complete is not None:
            identity = self._identity(
                complete.sequence,
                complete.media_timestamp_us,
                complete.apply_at_us,
                complete.flags,
            )
            if not self._can_start_identity(identity):
                return None
            return self._mark_complete(complete, identity)

        packet = UdpV3ChunkPacket.decode(
            data,
            expected_node_id=self.expected_node_id,
        )
        if packet is None:
            return None
        identity = self._identity(
            packet.sequence,
            packet.media_timestamp_us,
            packet.apply_at_us,
            packet.flags,
        )
        if not self._can_start_identity(identity):
            return None
        if identity != self._active_identity:
            self._begin(identity)

        staged: list[tuple[list[tuple[int, int, int] | None], int, tuple[tuple[int, int, int], ...]]] = []
        for chunk in packet.chunks:
            expected = self.expected_outputs.get(chunk.output_id)
            if expected != (chunk.gpio, chunk.total_pixel_count):
                return None
            target = self._buffers[chunk.output_id]
            for relative, pixel in enumerate(chunk.pixels):
                existing = target[chunk.chunk_offset + relative]
                if existing is not None and existing != pixel:
                    return None
            staged.append((target, chunk.chunk_offset, chunk.pixels))
        for target, offset, pixels in staged:
            target[offset : offset + len(pixels)] = pixels

        if not all(all(pixel is not None for pixel in values) for values in self._buffers.values()):
            return None
        outputs = tuple(
            UdpV3Output(
                output_id=output_id,
                gpio=gpio,
                pixels=tuple(pixel for pixel in self._buffers[output_id] if pixel is not None),
            )
            for output_id, (gpio, _pixel_count) in self.expected_outputs.items()
        )
        result = UdpV3Packet(
            digital_node_id=self.expected_node_id,
            sequence=packet.sequence,
            media_timestamp_us=packet.media_timestamp_us,
            apply_at_us=packet.apply_at_us,
            flags=packet.flags,
            outputs=outputs,
        )
        return self._mark_complete(result, identity)


@dataclass(frozen=True)
class UdpV3ClockBeacon:
    """One Host-clock sample that can be sent to every node unchanged."""

    sequence: int
    host_monotonic_us: int
    message_type: int = MESSAGE_TYPE_CLOCK_BEACON

    def __post_init__(self) -> None:
        _require_uint("sequence", self.sequence, MAX_UINT32)
        _require_uint("host_monotonic_us", self.host_monotonic_us, MAX_UINT64)
        _require_uint("message_type", self.message_type, MAX_UINT8)
        if self.message_type != MESSAGE_TYPE_CLOCK_BEACON:
            raise ValueError(f"unsupported message_type {self.message_type!r}")

    def encode(self) -> bytes:
        body = struct.pack(
            CLOCK_BEACON_FORMAT,
            MAGIC,
            VERSION,
            self.message_type,
            self.sequence,
            self.host_monotonic_us,
        )
        return body + struct.pack(">I", crc32(body))

    @classmethod
    def decode(cls, data: bytes) -> Optional["UdpV3ClockBeacon"]:
        if len(data) != CLOCK_BEACON_LENGTH:
            return None
        try:
            magic, version, message_type, sequence, host_monotonic_us = struct.unpack(
                CLOCK_BEACON_FORMAT, data[:CLOCK_BEACON_BODY_LENGTH]
            )
            expected_crc = struct.unpack(">I", data[-CRC_LENGTH:])[0]
        except struct.error:
            return None
        if (
            magic != MAGIC
            or version != VERSION
            or message_type != MESSAGE_TYPE_CLOCK_BEACON
            or crc32(data[:-CRC_LENGTH]) != expected_crc
        ):
            return None
        try:
            return cls(
                sequence=sequence,
                host_monotonic_us=host_monotonic_us,
                message_type=message_type,
            )
        except ValueError:
            return None


__all__ = [
    "CHUNK_LENGTH", "CLOCK_BEACON_LENGTH", "FLAG_KEY_FRAME",
    "FLAG_SAFE_STATE", "FLAG_SCHEDULED_APPLY", "HEADER_LENGTH", "MAGIC",
    "MESSAGE_TYPE_CLOCK_BEACON", "MESSAGE_TYPE_FRAME",
    "MESSAGE_TYPE_FRAME_CHUNK", "VERSION", "UdpV3Chunk",
    "UdpV3ChunkPacket", "UdpV3ClockBeacon", "UdpV3FrameReassembler",
    "UdpV3Output", "UdpV3Packet", "encode_udp_v3_frame_datagrams",
    "is_newer_sequence",
]
