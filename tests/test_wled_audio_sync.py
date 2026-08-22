"""Contract tests for the pure WLED Audio Sync V2 receiver."""

import socket
import struct

import pytest

from light_engine.analysis.wled_audio_sync import (
    WLED_AUDIO_SYNC_V2_FFT_MAX,
    WLED_AUDIO_SYNC_V2_PACKET_SIZE,
    WledAudioSyncV2DecodeError,
    WledAudioSyncV2Source,
    decode_wled_audio_sync_v2,
)


PACKET = struct.Struct("<6s2sffBB16sHff")


def packet(
    *,
    sample_raw=64.0,
    sample_smoothed=127.5,
    peak=0,
    bands=bytes(range(16)),
    magnitude=42.0,
    frequency=440.0,
    header=b"00002\x00",
):
    return PACKET.pack(
        header,
        b"ab",
        sample_raw,
        sample_smoothed,
        peak,
        99,
        bands,
        1234,
        magnitude,
        frequency,
    )


class FakeSocket:
    def __init__(self):
        self.datagrams = []
        self.options = []
        self.bound = None
        self.blocking = None
        self.closed = False

    def setsockopt(self, level, option, value):
        self.options.append((level, option, value))

    def bind(self, address):
        self.bound = address

    def setblocking(self, flag):
        self.blocking = flag

    def recvfrom(self, _size):
        if not self.datagrams:
            raise BlockingIOError
        return self.datagrams.pop(0)

    def close(self):
        self.closed = True


class Clock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_decoder_freezes_exact_44_byte_v2_layout_and_normalization():
    decoded = decode_wled_audio_sync_v2(
        packet(peak=7, bands=bytes([0, 1, 128, 254] + [128] * 12))
    )

    assert PACKET.size == WLED_AUDIO_SYNC_V2_PACKET_SIZE == 44
    assert decoded.sample_raw == 64.0
    assert decoded.loudness == 0.5
    assert decoded.peak is True
    assert WLED_AUDIO_SYNC_V2_FFT_MAX == 254
    assert decoded.spectrum[:4] == pytest.approx(
        (0.0, 1.0 / 254.0, 128.0 / 254.0, 1.0)
    )
    assert decoded.dominant_magnitude == 42.0
    assert decoded.dominant_frequency == 440.0


@pytest.mark.parametrize(
    "payload",
    [
        b"too short",
        packet(header=b"00001\x00"),
        packet(sample_smoothed=float("nan")),
        packet(bands=bytes([255] + [0] * 15)),
        packet(magnitude=-1.0),
        packet(frequency=float("inf")),
    ],
)
def test_decoder_rejects_malformed_packets(payload):
    with pytest.raises(WledAudioSyncV2DecodeError):
        decode_wled_audio_sync_v2(payload)


def test_source_opens_multicast_socket_nonblocking_and_closes_idempotently():
    udp_socket = FakeSocket()
    source = WledAudioSyncV2Source(udp_socket=udp_socket)

    assert source.open() is source
    assert udp_socket.bound == ("0.0.0.0", 11988)
    assert udp_socket.blocking is False
    assert any(option == socket.IP_ADD_MEMBERSHIP for _, option, _ in udp_socket.options)

    source.close()
    source.close()
    assert udp_socket.closed is True
    assert any(option == socket.IP_DROP_MEMBERSHIP for _, option, _ in udp_socket.options)


def test_source_rejects_port_zero_before_opening_socket():
    with pytest.raises(ValueError, match=r"port must be in \[1, 65535\]"):
        WledAudioSyncV2Source(port=0)


def test_source_drains_in_receive_order_and_preserves_transients():
    udp_socket = FakeSocket()
    clock = Clock(10.0)
    source = WledAudioSyncV2Source(udp_socket=udp_socket, clock=clock).open()
    udp_socket.datagrams.extend(
        [
            (
                packet(sample_raw=10.0, sample_smoothed=10.0, bands=bytes([0] * 16)),
                ("one", 1),
            ),
            (
                packet(
                    sample_raw=20.0,
                    sample_smoothed=20.0,
                    peak=1,
                    bands=bytes([254] * 16),
                ),
                ("two", 2),
            ),
            (
                packet(
                    sample_raw=30.0,
                    sample_smoothed=30.0,
                    bands=bytes([128] * 16),
                    frequency=880.0,
                ),
                ("three", 3),
            ),
        ]
    )

    features = source.poll(timestamp=2.0)

    assert features.raw_level == 30.0
    assert features.loudness == pytest.approx(30.0 / 255.0)
    assert features.spectrum == pytest.approx((128.0 / 254.0,) * 16)
    assert features.dominant_frequency == 880.0
    assert features.peak is features.beat is True
    assert features.spectral_flux == pytest.approx(1.0)
    assert features.onset == pytest.approx(1.0)
    assert source.diagnostics()["last_sender"] == ("three", 3)


def test_no_new_fresh_packet_retains_continuous_and_clears_transient():
    udp_socket = FakeSocket()
    clock = Clock(1.0)
    source = WledAudioSyncV2Source(
        udp_socket=udp_socket, clock=clock, stale_after=1.0
    ).open()
    udp_socket.datagrams.append(
        (
            packet(
                sample_raw=91.25,
                sample_smoothed=200.0,
                peak=1,
                bands=bytes([64] * 16),
            ),
            ("sender", 1),
        )
    )
    first = source.poll(timestamp=4.0)

    clock.now = 1.5
    retained = source.poll(timestamp=4.5)

    assert retained.raw_level == first.raw_level == 91.25
    assert retained.loudness == first.loudness
    assert retained.spectrum == first.spectrum
    assert retained.dominant_frequency == first.dominant_frequency
    assert retained.peak is retained.beat is False
    assert retained.spectral_flux == retained.onset == 0.0
    assert source.packet_age == pytest.approx(0.5)
    assert source.diagnostics()["packet_age_seconds"] == pytest.approx(0.5)


def test_stale_zeros_once_and_first_recovery_has_no_pre_stale_flux():
    udp_socket = FakeSocket()
    clock = Clock(1.0)
    source = WledAudioSyncV2Source(
        udp_socket=udp_socket, clock=clock, stale_after=1.0
    ).open()
    udp_socket.datagrams.append((packet(bands=bytes([254] * 16)), ("sender", 1)))
    source.poll(timestamp=1.0)

    clock.now = 2.0
    stale = source.poll(timestamp=2.0)
    stale_again = source.poll(timestamp=2.1)

    assert stale.raw_level == 0.0
    assert stale.loudness == stale.rms == 0.0
    assert stale.spectrum == (0.0,) * 16
    assert stale.dominant_frequency == stale.dominant_magnitude == 0.0
    assert stale.peak is stale.beat is False
    assert stale_again.spectral_flux == 0.0
    assert source.stale is True
    assert source.diagnostics()["stale_transitions"] == 1

    clock.now = 2.2
    udp_socket.datagrams.append((packet(bands=bytes([128] * 16)), ("sender", 1)))
    recovered = source.poll(timestamp=2.2)
    assert recovered.spectral_flux == recovered.onset == 0.0


def test_invalid_packets_are_counted_and_do_not_hide_a_later_legal_packet():
    udp_socket = FakeSocket()
    source = WledAudioSyncV2Source(udp_socket=udp_socket, clock=Clock()).open()
    udp_socket.datagrams.extend(
        [
            (b"invalid", ("bad-length", 1)),
            (packet(bands=bytes([255] + [0] * 15)), ("bad-band", 2)),
            (packet(), ("good", 3)),
        ]
    )

    features = source.poll(timestamp=0.0)
    diagnostics = source.diagnostics()

    assert features.loudness == 0.5
    assert diagnostics["packets_received"] == 3
    assert diagnostics["packets_valid"] == 1
    assert diagnostics["packets_invalid"] == 2
    assert diagnostics["last_error"] is None


def test_reset_clears_retained_state_and_flux_history_without_closing():
    udp_socket = FakeSocket()
    source = WledAudioSyncV2Source(udp_socket=udp_socket, clock=Clock()).open()
    udp_socket.datagrams.append((packet(bands=bytes([254] * 16)), ("sender", 1)))
    source.poll(timestamp=0.0)

    source.reset()
    empty = source.poll(timestamp=1.0)

    assert empty.spectrum == (0.0,) * 16
    assert source.diagnostics()["open"] is True
    assert source.diagnostics()["reset_count"] == 1


def test_source_requires_open_and_valid_configuration():
    with pytest.raises(RuntimeError):
        WledAudioSyncV2Source(udp_socket=FakeSocket()).poll(timestamp=0.0)
    with pytest.raises(ValueError):
        WledAudioSyncV2Source(stale_after=0.0)
    with pytest.raises(ValueError):
        WledAudioSyncV2Source(port=65536)
    with pytest.raises(ValueError):
        WledAudioSyncV2Source(silence_threshold=float("nan"))
    with pytest.raises(ValueError):
        WledAudioSyncV2Source(
            udp_socket=FakeSocket(), socket_factory=lambda: FakeSocket()
        )
