"""Phase 32 UDP v3 long-frame packetization and reassembly contract."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from light_engine.mapping.physical import (
    DigitalNodeFrame,
    DigitalOutputFrame,
    PhysicalFrame,
)
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import (
    FLAG_KEY_FRAME,
    FLAG_SCHEDULED_APPLY,
    MESSAGE_TYPE_FRAME_CHUNK,
    UdpV3Chunk,
    UdpV3ChunkPacket,
    UdpV3FrameReassembler,
    UdpV3Output,
    UdpV3Packet,
    encode_udp_v3_frame_datagrams,
)


GOLDEN = Path("firmware/shared/udp_v3_chunk_golden.json")


def _pixels(count: int, seed: int = 0) -> tuple[tuple[int, int, int], ...]:
    return tuple(
        ((seed + index) & 0xFF, (seed + index * 3) & 0xFF, (255 - index) & 0xFF)
        for index in range(count)
    )


def _long_packet(*, sequence: int = 7, count: int = 481) -> UdpV3Packet:
    return UdpV3Packet(
        digital_node_id=9,
        sequence=sequence,
        media_timestamp_us=123_456,
        apply_at_us=999_000,
        flags=FLAG_SCHEDULED_APPLY,
        outputs=(UdpV3Output(1, 4, _pixels(count)),),
    )


@pytest.mark.parametrize("count", [17, 100, 101, 200, 481])
def test_logical_output_length_is_not_a_one_datagram_product_limit(count: int) -> None:
    packet = _long_packet(count=count)

    datagrams = encode_udp_v3_frame_datagrams(packet, max_udp_payload=1400)

    assert datagrams
    assert all(len(datagram) <= 1400 for datagram in datagrams)
    expected = {1: (4, count)}
    reassembler = UdpV3FrameReassembler(9, expected)
    complete = [frame for raw in datagrams if (frame := reassembler.accept(raw))]
    assert complete == [packet]


def test_481_pixel_frame_has_explicit_total_offsets_and_shared_identity() -> None:
    packet = _long_packet()

    datagrams = encode_udp_v3_frame_datagrams(packet, max_udp_payload=1400)
    chunks = [UdpV3ChunkPacket.decode(raw) for raw in datagrams]

    assert len(chunks) == 2
    assert all(item is not None for item in chunks)
    assert all(item.message_type == MESSAGE_TYPE_FRAME_CHUNK for item in chunks)
    assert {(item.sequence, item.media_timestamp_us, item.apply_at_us, item.flags) for item in chunks} == {
        (packet.sequence, packet.media_timestamp_us, packet.apply_at_us, packet.flags)
    }
    entries = [item.chunks[0] for item in chunks]
    assert [entry.total_pixel_count for entry in entries] == [481, 481]
    assert [entry.chunk_offset for entry in entries] == [0, len(entries[0].pixels)]
    assert sum(len(entry.pixels) for entry in entries) == 481


def test_out_of_order_and_identical_duplicates_refresh_exactly_once() -> None:
    packet = _long_packet()
    datagrams = encode_udp_v3_frame_datagrams(packet, max_udp_payload=1400)
    receiver = UdpV3FrameReassembler(9, {1: (4, 481)})

    assert receiver.accept(datagrams[-1]) is None
    assert receiver.accept(datagrams[-1]) is None
    assert receiver.accept(datagrams[0]) == packet
    assert all(receiver.accept(raw) is None for raw in datagrams)


def test_corrupt_missing_old_and_superseded_chunks_never_complete_partial_frame() -> None:
    first = _long_packet(sequence=7)
    first_datagrams = encode_udp_v3_frame_datagrams(first, max_udp_payload=1400)
    next_packet = replace(first, sequence=8, outputs=(UdpV3Output(1, 4, _pixels(481, 91)),))
    next_datagrams = encode_udp_v3_frame_datagrams(next_packet, max_udp_payload=1400)
    receiver = UdpV3FrameReassembler(9, {1: (4, 481)})

    corrupt = bytearray(first_datagrams[0])
    corrupt[-1] ^= 1
    assert receiver.accept(bytes(corrupt)) is None
    assert receiver.accept(first_datagrams[0]) is None
    assert receiver.accept(next_datagrams[0]) is None  # supersedes incomplete seq 7
    assert receiver.accept(first_datagrams[1]) is None  # old traffic cannot revive it
    assert receiver.accept(next_datagrams[1]) == next_packet


def test_conflicting_overlap_is_rejected_without_destroying_valid_progress() -> None:
    packet = _long_packet()
    datagrams = encode_udp_v3_frame_datagrams(packet, max_udp_payload=1400)
    first = UdpV3ChunkPacket.decode(datagrams[0])
    assert first is not None
    entry = first.chunks[0]
    conflict = replace(
        first,
        chunks=(
            UdpV3Chunk(
                output_id=entry.output_id,
                gpio=entry.gpio,
                total_pixel_count=entry.total_pixel_count,
                chunk_offset=entry.chunk_offset,
                pixels=((255, 0, 0),) + entry.pixels[1:],
            ),
        ),
    ).encode()
    receiver = UdpV3FrameReassembler(9, {1: (4, 481)})

    assert receiver.accept(datagrams[0]) is None
    assert receiver.accept(conflict) is None
    assert receiver.accept(datagrams[1]) == packet


def test_multiple_outputs_reassemble_in_configured_identity_order() -> None:
    packet = UdpV3Packet(
        digital_node_id=2,
        sequence=1,
        media_timestamp_us=0,
        flags=FLAG_KEY_FRAME,
        outputs=(
            UdpV3Output(1, 4, _pixels(101, 1)),
            UdpV3Output(2, 5, _pixels(200, 2)),
            UdpV3Output(3, 6, _pixels(17, 3)),
        ),
    )
    datagrams = encode_udp_v3_frame_datagrams(packet, max_udp_payload=220)
    receiver = UdpV3FrameReassembler(
        2,
        {1: (4, 101), 2: (5, 200), 3: (6, 17)},
    )

    result = None
    for raw in reversed(datagrams):
        result = receiver.accept(raw) or result
    assert result == packet


def test_sequence_order_is_uint32_wrap_aware() -> None:
    receiver = UdpV3FrameReassembler(9, {1: (4, 481)})
    before_wrap = _long_packet(sequence=0xFFFFFFFF)
    after_wrap = _long_packet(sequence=0)

    for raw in encode_udp_v3_frame_datagrams(before_wrap, max_udp_payload=1400):
        completed = receiver.accept(raw)
    assert completed == before_wrap
    for raw in encode_udp_v3_frame_datagrams(after_wrap, max_udp_payload=1400):
        completed = receiver.accept(raw)
    assert completed == after_wrap


def test_packetizer_rejects_payload_budget_that_cannot_hold_one_rgb_chunk() -> None:
    with pytest.raises(ValueError, match="one RGB pixel"):
        encode_udp_v3_frame_datagrams(_long_packet(count=101), max_udp_payload=45)


def _golden_pixels(chunk: dict[str, object]) -> tuple[tuple[int, int, int], ...]:
    pixels = tuple(tuple(pixel) for pixel in chunk["pixels"])
    repeat = chunk.get("pixel_repeat", 1)
    assert type(repeat) is int and repeat >= 1
    if repeat != 1:
        assert len(pixels) == 1
        pixels *= repeat
    return pixels


def _golden_bytes(vector: dict[str, object]) -> bytes:
    encoded = vector.get("encoded_hex")
    if isinstance(encoded, str):
        return bytes.fromhex(encoded)
    segments = vector["encoded_hex_segments"]
    expanded = "".join(
        segment
        if isinstance(segment, str)
        else segment["hex"] * segment["repeat"]
        for segment in segments
    )
    return bytes.fromhex(expanded)


def _golden_chunk_packet(vector: dict[str, object]) -> UdpV3ChunkPacket:
    chunks = tuple(
        UdpV3Chunk(
            output_id=chunk["output_id"],
            gpio=chunk["gpio"],
            total_pixel_count=chunk["total_pixel_count"],
            chunk_offset=chunk["chunk_offset"],
            pixels=_golden_pixels(chunk),
        )
        for chunk in vector["chunks"]
    )
    return UdpV3ChunkPacket(
        digital_node_id=vector["digital_node_id"],
        sequence=vector["sequence"],
        media_timestamp_us=vector["media_timestamp_us"],
        apply_at_us=vector["apply_at_us"],
        flags=vector["flags"],
        chunks=chunks,
    )


def test_all_chunk_golden_vectors_are_authoritative_wire_contracts() -> None:
    vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]

    for vector in vectors:
        packet = _golden_chunk_packet(vector)
        encoded = _golden_bytes(vector)
        assert packet.encode() == encoded
        assert UdpV3ChunkPacket.decode(encoded) == packet


def test_chunk_golden_packet_set_is_generated_by_python_packetizer() -> None:
    vectors = json.loads(GOLDEN.read_text(encoding="utf-8"))["vectors"]
    packet_vectors = sorted(
        (item for item in vectors if item.get("packet_set")),
        key=lambda item: item["packet_index"],
    )
    assert [item["packet_index"] for item in packet_vectors] == [0, 1]
    assert all(item["packet_count"] == 2 for item in packet_vectors)
    first = packet_vectors[0]
    pixels: list[tuple[int, int, int]] = []
    for vector in packet_vectors:
        pixels.extend(_golden_pixels(vector["chunks"][0]))
    logical = UdpV3Packet(
        digital_node_id=first["digital_node_id"],
        sequence=first["sequence"],
        media_timestamp_us=first["media_timestamp_us"],
        apply_at_us=first["apply_at_us"],
        flags=first["flags"],
        outputs=(UdpV3Output(1, 4, tuple(pixels)),),
    )

    encoded = encode_udp_v3_frame_datagrams(
        logical, max_udp_payload=first["max_udp_payload"]
    )
    assert encoded == [_golden_bytes(vector) for vector in packet_vectors]
    assert [len(datagram) for datagram in encoded] == [1480, 49]


def _physical_long_frame(*, max_udp_payload: int = 1400) -> PhysicalFrame:
    pixels = [(channel / 255, 0.0, 1.0) for channel in range(256)] + [
        (channel / 255, 1.0, 0.0) for channel in range(225)
    ]
    return PhysicalFrame(
        sequence=7,
        timestamp=0.123456,
        digital_frames=[
            DigitalNodeFrame(
                node_id=9,
                host="192.0.2.9",
                port=9001,
                outputs=[DigitalOutputFrame(1, 4, "strip_9", pixels)],
                max_udp_payload=max_udp_payload,
            )
        ],
    )


def test_udp_transport_sends_all_chunks_for_one_complete_logical_frame() -> None:
    output = UdpOutputV3()
    output.open()

    output.send_frame(_physical_long_frame())

    sent = output.get_sent_datagrams()
    assert len(sent) == 2
    assert {address for _raw, address in sent} == {("192.0.2.9", 9001)}
    assert all(len(raw) <= 1400 for raw, _address in sent)
    receiver = UdpV3FrameReassembler(9, {1: (4, 481)})
    completed = [
        frame for raw, _address in sent if (frame := receiver.accept(raw)) is not None
    ]
    assert len(completed) == 1
    assert len(completed[0].outputs[0].pixels) == 481
    assert output.health().logical_frames_sent == 1
    assert output.health().packets_sent == 2


def test_transport_preencodes_every_node_before_sending_any_chunk() -> None:
    good = _physical_long_frame().digital_frames[0]
    impossible = replace(good, node_id=8, max_udp_payload=45)
    frame = replace(_physical_long_frame(), digital_frames=[good, impossible])
    output = UdpOutputV3()
    output.open()

    output.send_frame(frame)

    assert output.get_sent_datagrams() == []
    assert output.health().logical_frames_sent == 0
    assert output.health().frames_dropped == 1
