"""Tests for UDP binary protocol encoding and decoding."""

import struct
from light_engine.models import DigitalStrip, PixelFrame
from light_engine.outputs.udp_output import UdpOutput, UdpPacket, _compute_checksum


class RecordingSocket:
    def __init__(self):
        self.sent = []

    def sendto(self, data, address):
        self.sent.append((data, address))
        return len(data)


class TestUdpPacket:
    def test_encode_decode_roundtrip(self):
        pixels = [(255, 128, 0), (0, 255, 100), (50, 50, 200)]
        p = UdpPacket(
            sequence=42, strip_id=3, pixel_offset=0,
            pixel_count=len(pixels), pixels=pixels,
        )
        raw = p.encode()
        decoded = UdpPacket.decode(raw)
        assert decoded is not None
        assert decoded.sequence == 42
        assert decoded.strip_id == 3
        assert decoded.pixel_offset == 0
        assert decoded.pixel_count == 3
        assert decoded.pixels == pixels

    def test_decode_short(self):
        assert UdpPacket.decode(b"\x00\x01") is None

    def test_decode_bad_checksum(self):
        p = UdpPacket(sequence=1, strip_id=2, pixel_offset=0,
                       pixel_count=1, pixels=[(255, 0, 0)])
        raw = bytearray(p.encode())
        raw[-2] ^= 0xFF
        assert UdpPacket.decode(bytes(raw)) is None

    def test_decode_bad_magic(self):
        p = UdpPacket(sequence=1, strip_id=2, pixel_offset=0,
                       pixel_count=1, pixels=[(255, 0, 0)])
        raw = bytearray(p.encode())
        raw[0] = 0x00
        assert UdpPacket.decode(bytes(raw)) is None

    def test_checksum_detection(self):
        """Verify checksum detects single-bit errors."""
        pixels = [(100, 150, 200)]
        p = UdpPacket(sequence=1, strip_id=1, pixel_offset=0,
                       pixel_count=1, pixels=pixels)
        raw = p.encode()
        # Corrupt one payload bit
        mutated = bytearray(raw)
        mutated[14] ^= 0x01
        assert UdpPacket.decode(bytes(mutated)) is None

    def test_empty_pixels(self):
        p = UdpPacket(sequence=0, strip_id=0, pixel_offset=0,
                       pixel_count=0, pixels=[])
        raw = p.encode()
        decoded = UdpPacket.decode(raw)
        assert decoded is not None
        assert decoded.pixel_count == 0


class TestUdpOutputSequence:
    def test_send_frame_uses_pixel_frame_sequence(self):
        socket = RecordingSocket()
        output = UdpOutput(host="127.0.0.1", port=9001)
        output._open = True
        output._enabled = True
        output._socket = socket
        frame = PixelFrame(
            timestamp=0.0,
            sequence=1234,
            strips=[
                DigitalStrip(
                    strip_id="s1",
                    pixel_count=1,
                    pixels=[(1.0, 0.0, 0.0)],
                )
            ],
        )

        output.send_frame(frame)

        assert len(socket.sent) == 1
        packet = UdpPacket.decode(socket.sent[0][0])
        assert packet is not None
        assert packet.sequence == 1234

    def test_send_frame_does_not_generate_independent_sequence(self):
        socket = RecordingSocket()
        output = UdpOutput(host="127.0.0.1", port=9001)
        output._open = True
        output._enabled = True
        output._socket = socket
        frame = PixelFrame(
            timestamp=0.0,
            sequence=77,
            strips=[
                DigitalStrip(
                    strip_id="s1",
                    pixel_count=1,
                    pixels=[(0.0, 1.0, 0.0)],
                )
            ],
        )

        output.send_frame(frame)
        output.send_frame(frame)

        packets = [UdpPacket.decode(data) for data, _ in socket.sent]
        assert [packet.sequence for packet in packets if packet is not None] == [77, 77]


class TestChecksum:
    def test_xor_checksum(self):
        data = bytes([0x00, 0x01, 0x02, 0x03])
        cs = _compute_checksum(data)
        # (0x0001 ^ 0x0203) = 0x0202
        assert cs == 0x0202
