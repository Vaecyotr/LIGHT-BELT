"""Pure receiver for WLED Audio Sync V2 datagrams.

The 44-byte wire layout is defined by WLED's packed ``audioSyncPacket``:
https://github.com/wled/WLED/blob/v16.0.1/usermods/audioreactive/audio_reactive.cpp

This module implements only that public wire contract. It does not copy or
embed WLED runtime code.
"""

from __future__ import annotations

import math
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, Tuple

from light_engine.models import AudioFeatures


WLED_AUDIO_SYNC_V2_HEADER = b"00002\x00"
WLED_AUDIO_SYNC_V2_PACKET_SIZE = 44
WLED_AUDIO_SYNC_V2_FFT_MAX = 254
WLED_AUDIO_SYNC_DEFAULT_PORT = 11988
WLED_AUDIO_SYNC_MULTICAST_GROUP = "239.0.0.1"
_PACKET = struct.Struct("<6s2sffBB16sHff")


class WledAudioSyncV2DecodeError(ValueError):
    """Raised when a datagram is not a legal WLED Audio Sync V2 packet."""


@dataclass(frozen=True)
class WledAudioSyncV2Packet:
    """Validated, host-independent representation of one V2 datagram."""

    sample_raw: float
    loudness: float
    peak: bool
    spectrum: Tuple[float, ...]
    dominant_magnitude: float
    dominant_frequency: float


def decode_wled_audio_sync_v2(data: bytes) -> WledAudioSyncV2Packet:
    """Decode and validate one exact-size WLED Audio Sync V2 datagram."""

    if len(data) != WLED_AUDIO_SYNC_V2_PACKET_SIZE:
        raise WledAudioSyncV2DecodeError(
            f"packet must be exactly {WLED_AUDIO_SYNC_V2_PACKET_SIZE} bytes, got {len(data)}"
        )
    header, _, sample_raw, sample_smoothed, peak, _, bands, _, magnitude, frequency = (
        _PACKET.unpack(data)
    )
    if header != WLED_AUDIO_SYNC_V2_HEADER:
        raise WledAudioSyncV2DecodeError(f"invalid Audio Sync V2 header: {header!r}")
    values = {
        "sample_raw": sample_raw,
        "sample_smoothed": sample_smoothed,
        "dominant_magnitude": magnitude,
        "dominant_frequency": frequency,
    }
    for name, value in values.items():
        if not math.isfinite(value) or value < 0.0:
            raise WledAudioSyncV2DecodeError(
                f"{name} must be finite and non-negative, got {value}"
            )
    if any(value > WLED_AUDIO_SYNC_V2_FFT_MAX for value in bands):
        raise WledAudioSyncV2DecodeError(
            "fftResult bands must be in the transmitted WLED v16.0.1 range "
            f"[0, {WLED_AUDIO_SYNC_V2_FFT_MAX}]"
        )
    return WledAudioSyncV2Packet(
        sample_raw=sample_raw,
        loudness=min(sample_smoothed / 255.0, 1.0),
        peak=bool(peak),
        spectrum=tuple(value / WLED_AUDIO_SYNC_V2_FFT_MAX for value in bands),
        dominant_magnitude=magnitude,
        dominant_frequency=frequency,
    )


class DatagramSocket(Protocol):
    """Small socket surface used by the receiver and test doubles."""

    def setsockopt(self, level: int, option: int, value: Any) -> None: ...
    def bind(self, address: tuple[str, int]) -> None: ...
    def setblocking(self, flag: bool) -> None: ...
    def recvfrom(self, size: int) -> tuple[bytes, Any]: ...
    def close(self) -> None: ...


class WledAudioSyncV2Source:
    """Nonblocking, drain-to-latest source for WLED Audio Sync V2 packets.

    Continuous values come from the last legal packet in a drain. Peak is
    OR-reduced and positive spectral flux is evaluated in receive order, with
    the maximum transition retained for the returned frame. A fresh poll with
    no packet retains continuous values but clears transients. Staleness clears
    all values and flux history exactly once per stale transition.
    """

    def __init__(
        self,
        *,
        bind_host: str = "0.0.0.0",
        port: int = WLED_AUDIO_SYNC_DEFAULT_PORT,
        multicast_group: str = WLED_AUDIO_SYNC_MULTICAST_GROUP,
        interface: str = "0.0.0.0",
        stale_after: float = 1.0,
        silence_threshold: float = 1.0 / WLED_AUDIO_SYNC_V2_FFT_MAX,
        udp_socket: Optional[DatagramSocket] = None,
        socket_factory: Optional[Callable[[], DatagramSocket]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if stale_after <= 0.0 or not math.isfinite(stale_after):
            raise ValueError("stale_after must be finite and positive")
        if not math.isfinite(silence_threshold) or not 0.0 <= silence_threshold <= 1.0:
            raise ValueError("silence_threshold must be finite and in [0, 1]")
        if not 1 <= port <= 65535:
            raise ValueError("port must be in [1, 65535]")
        if udp_socket is not None and socket_factory is not None:
            raise ValueError("provide udp_socket or socket_factory, not both")
        self.bind_host = bind_host
        self.port = port
        self.multicast_group = multicast_group
        self.interface = interface
        self.stale_after = stale_after
        self.silence_threshold = silence_threshold
        self._socket = udp_socket
        self._socket_factory = socket_factory or self._new_socket
        self._clock = clock
        self._membership = socket.inet_aton(multicast_group) + socket.inet_aton(interface)
        self._open = False
        self._latest: Optional[WledAudioSyncV2Packet] = None
        self._previous_spectrum: Optional[Tuple[float, ...]] = None
        self._last_packet_time: Optional[float] = None
        self._stale = True
        self._packets_received = 0
        self._packets_valid = 0
        self._packets_invalid = 0
        self._stale_transitions = 0
        self._reset_count = 0
        self._last_error: Optional[str] = None
        self._last_sender: Any = None

    @staticmethod
    def _new_socket() -> DatagramSocket:
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    def open(self) -> "WledAudioSyncV2Source":
        """Bind, join the multicast group, and switch to nonblocking I/O."""

        if self._open:
            return self
        udp_socket = self._socket or self._socket_factory()
        try:
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.bind((self.bind_host, self.port))
            udp_socket.setsockopt(
                socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, self._membership
            )
            udp_socket.setblocking(False)
        except Exception:
            udp_socket.close()
            self._socket = None
            raise
        self._socket = udp_socket
        self._open = True
        return self

    def poll(self, timestamp: float) -> AudioFeatures:
        """Drain available datagrams and return one deterministic feature set."""

        if not self._open or self._socket is None:
            raise RuntimeError("WledAudioSyncV2Source is not open")
        now = self._clock()
        latest: Optional[WledAudioSyncV2Packet] = None
        peak = False
        max_flux = 0.0
        while True:
            try:
                data, sender = self._socket.recvfrom(65535)
            except BlockingIOError:
                break
            self._packets_received += 1
            try:
                packet = decode_wled_audio_sync_v2(data)
            except WledAudioSyncV2DecodeError as exc:
                self._packets_invalid += 1
                self._last_error = str(exc)
                continue
            self._packets_valid += 1
            self._last_error = None
            self._last_sender = sender
            if self._previous_spectrum is not None:
                flux = sum(
                    max(current - previous, 0.0)
                    for current, previous in zip(packet.spectrum, self._previous_spectrum)
                ) / 16.0
                max_flux = max(max_flux, flux)
            self._previous_spectrum = packet.spectrum
            latest = packet
            peak = peak or packet.peak

        if latest is not None:
            self._latest = latest
            self._last_packet_time = now
            self._stale = False
            return self._features(timestamp, latest, peak=peak, flux=max_flux)

        if self._last_packet_time is None or now - self._last_packet_time >= self.stale_after:
            if not self._stale:
                self._stale_transitions += 1
                self._previous_spectrum = None
                self._latest = None
            self._stale = True
            return AudioFeatures(timestamp=timestamp)

        assert self._latest is not None
        return self._features(timestamp, self._latest, peak=False, flux=0.0)

    def _features(
        self,
        timestamp: float,
        packet: WledAudioSyncV2Packet,
        *,
        peak: bool,
        flux: float,
    ) -> AudioFeatures:
        silence = (
            packet.loudness <= self.silence_threshold
            and max(packet.spectrum) <= self.silence_threshold
        )
        return AudioFeatures(
            timestamp=timestamp,
            raw_level=packet.sample_raw,
            loudness=packet.loudness,
            spectrum=packet.spectrum,
            peak=peak,
            spectral_flux=flux,
            onset=flux,
            silence=silence,
            dominant_frequency=packet.dominant_frequency,
            dominant_magnitude=packet.dominant_magnitude,
        )

    def reset(self) -> None:
        """Clear retained features and flux history without closing the socket."""

        self._latest = None
        self._previous_spectrum = None
        self._last_packet_time = None
        self._stale = True
        self._reset_count += 1

    def close(self) -> None:
        """Leave multicast and close the socket; repeated calls are harmless."""

        if self._socket is None:
            return
        if self._open:
            try:
                self._socket.setsockopt(
                    socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, self._membership
                )
            except OSError:
                pass
        self._socket.close()
        self._socket = None
        self._open = False
        self.reset()

    @property
    def packet_age(self) -> Optional[float]:
        """Age in seconds of the last legal packet, or ``None`` before one."""

        if self._last_packet_time is not None:
            return max(0.0, self._clock() - self._last_packet_time)
        return None

    @property
    def stale(self) -> bool:
        """Whether the source currently has no fresh legal packet."""

        return self._stale

    def diagnostics(self) -> dict[str, Any]:
        """Return a snapshot of receiver health and packet counters."""

        return {
            "open": self._open,
            "stale": self._stale,
            "packet_age_seconds": self.packet_age,
            "packets_received": self._packets_received,
            "packets_valid": self._packets_valid,
            "packets_invalid": self._packets_invalid,
            "stale_transitions": self._stale_transitions,
            "reset_count": self._reset_count,
            "last_error": self._last_error,
            "last_sender": self._last_sender,
        }

    def __enter__(self) -> "WledAudioSyncV2Source":
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()
