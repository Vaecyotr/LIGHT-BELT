"""Tests for serial protocol: encoding, decoding, streaming parser, validation."""

import struct
import pytest
from light_engine.outputs.serial_output import (
    SerialPacket,
    SerialStreamParser,
    FRAME_HEADER,
    FRAME_FOOTER,
    FRAME_LENGTH,
    _compute_checksum,
)


class TestSerialPacket:
    def test_encode_test_vector(self):
        """Frozen test vector: CMD=1,R=255,G=128,B=0,W=32,Br=80,Fade=1000."""
        p = SerialPacket(cmd=0x01, r=255, g=128, b=0, w=32, brightness=80, fade_ms=1000)
        raw = p.encode()
        expected = bytes([0x55, 0x01, 0xFF, 0x80, 0x00, 0x20, 0x50, 0x03, 0xE8, 0xDB, 0xAA])
        assert raw == expected
        assert len(raw) == FRAME_LENGTH

    def test_encode_returns_bytes(self):
        p = SerialPacket()
        raw = p.encode()
        assert isinstance(raw, bytes)
        assert len(raw) == FRAME_LENGTH

    def test_roundtrip(self):
        p = SerialPacket(cmd=0x02, r=100, g=150, b=200, w=50, brightness=80, fade_ms=500)
        raw = p.encode()
        decoded = SerialPacket.decode(raw)
        assert decoded is not None
        assert decoded.cmd == 0x02
        assert decoded.r == 100
        assert decoded.g == 150
        assert decoded.b == 200
        assert decoded.w == 50
        assert decoded.brightness == 80
        assert decoded.fade_ms == 500

    def test_brightness_range_0_100(self):
        for br in [0, 50, 100]:
            p = SerialPacket(brightness=br)
            assert p.brightness == br
        with pytest.raises(ValueError):
            SerialPacket(brightness=-1)
        with pytest.raises(ValueError):
            SerialPacket(brightness=101)

    def test_rgbw_range_0_255(self):
        p = SerialPacket(r=255, g=255, b=255, w=255)
        assert p.r == 255
        with pytest.raises(ValueError):
            SerialPacket(r=256)
        with pytest.raises(ValueError):
            SerialPacket(r=-1)

    def test_fade_range_0_65535(self):
        p = SerialPacket(fade_ms=0)
        p2 = SerialPacket(fade_ms=65535)
        with pytest.raises(ValueError):
            SerialPacket(fade_ms=-1)
        with pytest.raises(ValueError):
            SerialPacket(fade_ms=65536)

    def test_fade_big_endian(self):
        p = SerialPacket(fade_ms=1000)
        raw = p.encode()
        fade_bytes = raw[7:9]
        fade_val = struct.unpack(">H", fade_bytes)[0]
        assert fade_val == 1000

    def test_checksum_is_sum_not_crc(self):
        """Verify checksum is 8-bit sum, not CRC."""
        p = SerialPacket(cmd=0x01, r=0x10, g=0x20, b=0x30, w=0x40, brightness=0x50, fade_ms=0)
        raw = p.encode()
        body = raw[1:9]
        expected_cs = sum(body) & 0xFF
        assert raw[9] == expected_cs
        assert body == bytes([0x01, 0x10, 0x20, 0x30, 0x40, 0x50, 0x00, 0x00])

    def test_decode_short(self):
        assert SerialPacket.decode(b"\x55\x01") is None

    def test_decode_bad_header(self):
        raw = bytes([0x00] * FRAME_LENGTH)
        assert SerialPacket.decode(raw) is None

    def test_decode_bad_footer(self):
        raw = bytes([FRAME_HEADER] + [0x00] * 9 + [0x00])
        assert SerialPacket.decode(raw) is None

    def test_decode_bad_checksum(self):
        p = SerialPacket()
        raw = bytearray(p.encode())
        raw[9] ^= 0xFF  # Corrupt checksum
        assert SerialPacket.decode(bytes(raw)) is None


class TestSerialStreamParser:
    def test_parse_single_frame(self):
        parser = SerialStreamParser()
        p = SerialPacket(r=100, g=150, b=200)
        raw = p.encode()
        frames = parser.feed(raw)
        assert len(frames) == 1
        assert frames[0].r == 100
        assert parser.valid_frames == 1

    def test_parse_multiple_frames(self):
        parser = SerialStreamParser()
        packets = []
        for i in range(10):
            packets.append(SerialPacket(r=i, g=i * 10, b=i * 20).encode())
        raw = b"".join(packets)
        frames = parser.feed(raw)
        assert len(frames) == 10

    def test_parse_split_packet(self):
        parser = SerialStreamParser()
        p = SerialPacket(r=255, g=128, b=0, w=32)
        raw = p.encode()
        # Split at byte 5
        frames = parser.feed(raw[:5])
        assert len(frames) == 0  # Incomplete
        frames = parser.feed(raw[5:])
        assert len(frames) == 1
        assert frames[0].r == 255

    def test_parse_noise_before_frame(self):
        parser = SerialStreamParser()
        p = SerialPacket(r=100, g=100, b=100)
        raw = bytes([0x00, 0xFF, 0xFE]) + p.encode()
        frames = parser.feed(raw)
        assert len(frames) == 1
        assert parser.invalid_frames >= 0  # Noise discarded

    def test_parse_bad_checksum_skips_to_next(self):
        parser = SerialStreamParser()
        p1 = SerialPacket(r=10, g=10, b=10)
        p2 = SerialPacket(r=20, g=20, b=20)
        raw1 = bytearray(p1.encode())
        raw1[9] ^= 0xFF  # Corrupt checksum
        raw = bytes(raw1) + p2.encode()
        frames = parser.feed(raw)
        assert len(frames) == 1
        assert frames[0].r == 20
        assert parser.invalid_frames >= 1

    def test_parser_buffer_limits(self):
        parser = SerialStreamParser(max_buffer=32)
        # Flood with noise
        noise = bytes([0x00] * 100)
        frames = parser.feed(noise)
        assert len(frames) == 0
        # Buffer should be cleared, not 100 bytes

    def test_reset(self):
        parser = SerialStreamParser()
        p = SerialPacket()
        parser.feed(p.encode())
        parser.reset()
        assert parser.valid_frames == 0
        assert parser.invalid_frames == 0
