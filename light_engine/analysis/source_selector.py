"""Bounded, epoch-aware selection of the active audio feature source."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable

from light_engine.models import AudioFeatures, AudioObservation


class AudioSourceSelector:
    """Accept only current-source windows and expose freshness explicitly."""

    def __init__(
        self,
        *,
        stale_after_ms: float = 250.0,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if stale_after_ms <= 0 or not float(stale_after_ms) < float("inf"):
            raise ValueError("stale_after_ms must be finite and positive")
        self.stale_after_ns = int(stale_after_ms * 1_000_000)
        self._clock_ns = clock_ns
        self._epoch = 0
        self._kind = "unknown"
        self._source_id: str | None = None
        self._latest: AudioObservation | None = None
        self._last_seq = -1
        self._last_delivered_seq = -1
        self._quality = "unavailable"

    def select(self, source_kind: str, source_id: str | None = None) -> int:
        """Select a source, incrementing epoch and discarding old windows."""
        if source_kind not in {
            "none",
            "file",
            "phone_pcm",
            "program_pcm",
            "wled",
            "synthetic",
        }:
            raise ValueError(f"unsupported audio source kind: {source_kind!r}")
        self._epoch += 1
        self._kind = "unknown" if source_kind == "none" else source_kind
        self._source_id = source_id
        self._latest = None
        self._last_seq = -1
        self._last_delivered_seq = -1
        self._quality = "unavailable" if source_kind == "none" else "warming"
        return self._epoch

    def publish(self, observation: AudioObservation) -> bool:
        """Publish a window only if source, epoch and sequence are current."""
        if observation.source_epoch != self._epoch:
            return False
        if (
            observation.source_kind != self._kind
            or observation.source_id != self._source_id
        ):
            return False
        if observation.sample_seq <= self._last_seq:
            return False
        self._latest = observation
        self._last_seq = observation.sample_seq
        return True

    def poll(self, now_ns: int | None = None) -> AudioObservation:
        """Return newest window, a transient-free hold, or a stale zero window."""
        now_ns = self._clock_ns() if now_ns is None else now_ns
        if self._latest is None:
            return AudioObservation(
                features=AudioFeatures(timestamp=0.0),
                source_kind=self._kind,
                source_id=self._source_id,
                source_epoch=self._epoch,
                clock_domain="monotonic",
                quality=self._quality,
            )

        received_ns = self._latest.received_ns
        age_ms = (
            max(0.0, (now_ns - received_ns) / 1_000_000)
            if received_ns is not None
            else None
        )
        stale = age_ms is not None and age_ms * 1_000_000 >= self.stale_after_ns
        if stale:
            self._latest = None
            self._last_delivered_seq = -1
            self._quality = "stale"
            return AudioObservation(
                features=AudioFeatures(timestamp=0.0),
                source_kind=self._kind,
                source_id=self._source_id,
                source_epoch=self._epoch,
                sample_seq=self._last_seq,
                clock_domain="monotonic",
                age_ms=age_ms,
                quality="stale",
            )

        fresh = self._latest.sample_seq != self._last_delivered_seq
        self._last_delivered_seq = self._latest.sample_seq
        self._quality = "fresh" if fresh else "held"
        features = self._latest.features
        if not fresh:
            features = replace(
                features,
                beat=False,
                peak=False,
                spectral_flux=0.0,
                onset=0.0,
            )
        return replace(
            self._latest,
            features=features,
            age_ms=age_ms,
            quality=self._quality,
            beat_event=self._latest.beat_event if fresh else False,
            event_id=self._latest.event_id if fresh else None,
        )

    def status(self) -> dict[str, object]:
        return {
            "source_kind": self._kind,
            "source_id": self._source_id,
            "source_epoch": self._epoch,
            "quality": self._quality,
            "sample_seq": self._last_seq if self._latest is not None else None,
        }
