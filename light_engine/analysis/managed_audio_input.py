"""One managed entry point for file, PulseAudio PCM, and WLED audio inputs."""

from __future__ import annotations

import time
import ipaddress
from dataclasses import replace
from typing import Callable

import numpy as np

from light_engine.analysis.audio import AudioAnalyzer
from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.analysis.pulse_capture import ParecCapture
from light_engine.analysis.source_selector import AudioSourceSelector
from light_engine.analysis.wled_audio_sync import WledAudioSyncV2Source
from light_engine.config import Config
from light_engine.media import AudioReader
from light_engine.models import AudioFeatures, AudioObservation, MusicControlState


class ManagedAudioInput:
    """Select and analyze one source while preserving legacy feature outputs.

    ``target`` accepts ``{"kind": "file", "path": ...}``, PulseAudio
    targets (``phone_pcm``, ``program_pcm``, or ``monitor``) with ``device``
    and a required ``monitor_stream`` index, WLED targets with a required
    ``source_id`` (IPv4 sender), or ``{"kind": "none"}``.
    """

    def __init__(
        self,
        config: Config | None = None,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        capture_factory: Callable[..., ParecCapture] = ParecCapture,
        wled_factory: Callable[..., WledAudioSyncV2Source] = WledAudioSyncV2Source,
    ) -> None:
        self._config = config or Config.get_instance()
        self._clock_ns = clock_ns
        self._capture_factory = capture_factory
        self._wled_factory = wled_factory
        stale_ms = self._config.get("system.audio.source.stale_after_ms", 250)
        self._selector = AudioSourceSelector(stale_after_ms=stale_ms, clock_ns=clock_ns)
        self._music = MusicControlAnalyzer(timing_resolution=1 / max(
            1.0, self._config.get("system.output_fps", 30.0)))
        self._audio_analyzer: AudioAnalyzer | None = None
        self._reader: AudioReader | None = None
        self._capture: ParecCapture | None = None
        self._wled: WledAudioSyncV2Source | None = None
        self._kind = "none"
        self._source_id: str | None = None
        self._epoch = 0
        self._seq = 0
        self._last_quality = "unavailable"
        self._last_music_state: MusicControlState | None = None
        self._target: dict = {"kind": "none"}
        self._mode = "none"
        self._last_wled_valid_count = 0
        self._configured_key: tuple[str, dict] | None = None
        self._fault: str | None = None
        self._retry_after_ns = 0
        self._retry_delay_ns = 250_000_000
        self._last_features: AudioFeatures | None = None
        self._pcm_buffer = np.zeros((0, 2), dtype=np.float32)
        self._pcm_music_state: MusicControlState | None = None
        self._last_observation: AudioObservation | None = None
        self._last_file_media_time: float | None = None
        self._last_file_state_time: float | None = None

    def configure(self, mode: str, target: dict | None) -> int:
        """Replace the selected source and return its new source epoch."""
        target = dict(target or {"kind": "none"})
        mode = "auto" if mode == "device" else mode
        if self._configured_key == (mode, target):
            return self._epoch
        self._close_source()
        self._music.reset()
        self._last_music_state = None
        if self._audio_analyzer is not None:
            self._audio_analyzer.reset()
        self._target = target
        self._mode = mode
        self._kind = self._target.get("kind", "none")
        self._source_id = self._target.get("source_id")
        self._seq = 0
        self._last_features = None
        self._can_emit = False
        self._pcm_timestamp = None
        self._pcm_buffer = np.zeros((0, 2), dtype=np.float32)
        self._pcm_music_state = None
        self._last_observation = None
        self._last_file_media_time = None
        self._last_file_state_time = None
        self._fault = None
        self._configured_key = (mode, target)
        try:
            self._epoch = self._selector.select(
                "program_pcm" if self._kind == "monitor" else self._kind,
                self._source_id,
            )
        except Exception as exc:
            self._record_fault(exc)
            return self._epoch
        self._last_quality = "warming"
        self._start_source()
        return self._epoch

    def _start_source(self) -> None:
        try:
            if self._mode not in {"auto", "device", "mic", "none"}:
                raise ValueError("mode must be auto, device, mic, or none")
            if (self._mode == "mic") != (self._kind == "wled"):
                raise ValueError("microphone selection requires the configured WLED source")
            if self._kind == "file":
                path = self._target.get("path")
                if not path:
                    raise ValueError("file target requires path")
                self._reader = AudioReader(str(path)).open()
                self._audio_analyzer = AudioAnalyzer(
                    self._config, managed_spectrum=True
                )
            elif self._kind in {"phone_pcm", "program_pcm", "monitor"}:
                device = self._target.get("device") or self._target.get("monitor")
                if not device:
                    raise ValueError("PCM target requires device")
                monitor_stream = self._target.get("monitor_stream")
                if not isinstance(monitor_stream, int) or monitor_stream < 0:
                    raise ValueError(
                        "monitor PCM target requires a valid monitor_stream index"
                    )
                self._capture = self._capture_factory(
                    device=str(device),
                    monitor_stream=monitor_stream,
                    sample_rate=int(self._target.get("sample_rate", 48_000)),
                    channels=int(self._target.get("channels", 2)),
                    block_ms=int(self._target.get("block_ms", 20)),
                ).start()
                self._audio_analyzer = AudioAnalyzer(
                    self._config, managed_spectrum=True
                )
            elif self._kind == "wled":
                sender = self._target.get("source_id")
                try:
                    ipaddress.IPv4Address(sender)
                except (ipaddress.AddressValueError, TypeError):
                    raise ValueError(
                        "WLED target requires a valid IPv4 source_id"
                    ) from None
                cfg = self._config.get("system.audio.source", {})
                self._wled = self._wled_factory(
                    multicast_group=cfg.get("multicast_group", "239.0.0.1"),
                    port=cfg.get("port", 11988),
                    interface=cfg.get("interface_ipv4", "0.0.0.0"),
                    stale_after=cfg.get("stale_after_ms", 250) / 1000.0,
                    expected_sender=sender,
                    drain_budget=64,
                ).open()
                self._last_wled_valid_count = 0
            elif self._kind != "none":
                raise ValueError(f"unsupported audio target kind: {self._kind!r}")
            self._fault = None
            self._retry_delay_ns = 250_000_000
        except Exception as exc:
            self._close_source()
            self._record_fault(exc)

    def _record_fault(self, exc: Exception) -> None:
        self._music.reset()
        self._can_emit = False
        self._last_observation = None
        self._pcm_timestamp = None
        self._pcm_buffer = np.empty((0, 2), dtype=np.float32)
        self._fault = f"{type(exc).__name__}: {exc}"
        self._last_quality = "fault"
        self._retry_after_ns = self._clock_ns() + self._retry_delay_ns
        self._retry_delay_ns = min(self._retry_delay_ns * 2, 8_000_000_000)

    def poll(
        self, media_time_s: float
    ) -> tuple[AudioFeatures | None, MusicControlState | None]:
        """Poll one selected source and derive music state from fresh windows."""
        if self._fault is not None:
            if self._clock_ns() >= self._retry_after_ns:
                self._fault = None
                self._last_file_state_time = self._last_file_media_time = None
                self._last_features = self._last_music_state = None
                try:
                    self._epoch = self._selector.select(
                        "program_pcm" if self._kind == "monitor" else self._kind, self._source_id
                    )
                except ValueError as exc:
                    self._record_fault(exc)
                    return None, None
                self._start_source()
            if self._fault is not None:
                return None, None
        observation: AudioObservation | None = None
        accepted_beat = False
        try:
            if self._kind == "file" and self._reader is not None:
                window = self._config.get("system.audio.window_size", 0.05)
                start = max(0.0, media_time_s - window / 2)
                samples = self._reader.get_window_at(start, window)
                if samples is not None and len(samples):
                    self._seq += 1
                    repeated = self._last_file_media_time == media_time_s
                    if repeated and self._last_features is not None:
                        features = replace(
                            self._last_features,
                            beat=False,
                            peak=False,
                            spectral_flux=0.0,
                            onset=0.0,
                        )
                    else:
                        features = self._audio_analyzer.analyze(
                            samples, media_time_s, self._reader.sample_rate
                        )
                        self._last_file_media_time = media_time_s
                        self._last_features = features
                    now = self._clock_ns()
                    observation = AudioObservation(
                        features=features,
                        source_kind="file",
                        source_id=self._source_id,
                        source_epoch=self._epoch,
                        sample_seq=self._seq,
                        clock_domain="media",
                        analysis_time_s=media_time_s,
                        media_time_s=media_time_s,
                        received_ns=now,
                        quality="fresh",
                        capabilities=(
                            "loudness",
                            "pcm_rms",
                            "bass_mid_treble",
                            "spectrum16",
                            "dominant_frequency",
                            "beat_event",
                        ),
                        beat_event=features.beat,
                        event_id=f"{self._epoch}:{self._seq}"
                        if features.beat
                        else None,
                    )
            elif (
                self._kind in {"phone_pcm", "program_pcm", "monitor"} and self._capture
            ):
                chunk = self._capture.read_latest()
                if chunk is None and not self._capture.status()["running"]:
                    raise RuntimeError(
                        self._capture.status().get("error") or "parec exited"
                    )
                if chunk is not None:
                    if chunk.discontinuity:
                        self._pcm_buffer = np.zeros((0, 2), dtype=np.float32)
                        self._audio_analyzer.reset()
                        self._music.reset()
                        self._last_music_state = None
                        self._can_emit = False
                        self._pcm_timestamp = None
                    self._pcm_buffer = np.concatenate(
                        (self._pcm_buffer, chunk.samples), axis=0
                    )
                    win = max(1, round(0.05 * self._capture.sample_rate))
                    hop = max(1, round(0.025 * self._capture.sample_rate))
                    windows = []
                    while len(self._pcm_buffer) >= win:
                        window_samples = self._pcm_buffer[:win]
                        if self._pcm_timestamp is None:
                            timestamp = (
                                chunk.received_ns / 1e9
                                - (len(self._pcm_buffer) - win / 2)
                                / self._capture.sample_rate
                            )
                        else:
                            timestamp = (
                                self._pcm_timestamp + hop / self._capture.sample_rate
                            )
                        self._pcm_timestamp = timestamp
                        features = self._audio_analyzer.analyze_stereo(
                            window_samples, timestamp, self._capture.sample_rate
                        )
                        allowed = self._can_emit and not features.silence
                        if not allowed:
                            features.beat = features.peak = False
                            features.onset = features.spectral_flux = 0.0
                        self._pcm_music_state = self._music.update(
                            features, allow_beat=allowed
                        )
                        accepted_beat |= (
                            allowed and self._music.last_event_time == timestamp
                        )
                        self._can_emit = True
                        windows.append(features)
                        self._pcm_buffer = self._pcm_buffer[hop:]
                    if windows:
                        self._seq += 1
                        features = windows[-1]
                        features.beat = any(item.beat for item in windows)
                        features.peak = features.beat
                        features.spectral_flux = max(
                            item.spectral_flux for item in windows
                        )
                        features.onset = max(item.onset for item in windows)
                        observation = AudioObservation(
                            features=features,
                            source_kind="program_pcm"
                            if self._kind == "monitor"
                            else self._kind,
                            source_id=self._source_id,
                            source_epoch=self._epoch,
                            sample_seq=self._seq,
                            clock_domain="monotonic",
                            analysis_time_s=timestamp,
                            captured_ns=round(timestamp * 1e9),
                            received_ns=chunk.received_ns,
                            discontinuity=chunk.discontinuity,
                            quality="fresh",
                            capabilities=(
                                "loudness",
                                "pcm_rms",
                                "bass_mid_treble",
                                "spectrum16",
                                "dominant_frequency",
                                "beat_event",
                            ),
                            beat_event=features.beat,
                            event_id=f"{self._epoch}:{self._seq}"
                            if features.beat
                            else None,
                        )
            elif self._kind == "wled" and self._wled:
                features = self._wled.poll(self._clock_ns() / 1e9)
                diagnostics = self._wled.diagnostics()
                valid_count = int(diagnostics["packets_valid"])
                if (
                    not diagnostics["stale"]
                    and valid_count > self._last_wled_valid_count
                ):
                    self._last_wled_valid_count = valid_count
                    self._seq = valid_count
                    now = self._clock_ns()
                    age_ms = diagnostics.get("packet_age_seconds")
                    received_ns = (
                        now - int(age_ms * 1_000_000_000) if age_ms is not None else now
                    )
                    observation = AudioObservation(
                        features=features,
                        source_kind="wled",
                        source_id=self._source_id,
                        source_epoch=self._epoch,
                        sample_seq=self._seq,
                        clock_domain="monotonic",
                        analysis_time_s=features.timestamp,
                        received_ns=received_ns,
                        age_ms=age_ms * 1000 if age_ms is not None else None,
                        quality="fresh",
                        capabilities=(
                            "loudness",
                            "raw_level",
                            "spectrum16",
                            "dominant_frequency",
                            "beat_event",
                        ),
                        beat_event=features.beat,
                        event_id=f"{self._epoch}:{self._seq}"
                        if features.beat
                        else None,
                    )
        except Exception as exc:
            self._close_source()
            self._record_fault(exc)
            return None, None

        if observation is not None:
            if self._kind not in {"phone_pcm", "program_pcm", "monitor"}:
                f = observation.features
                repeated = (
                    self._kind == "file" and f.timestamp == self._last_file_state_time
                )
                allowed = self._can_emit and not repeated and not f.silence
                if not allowed:
                    f.beat = f.peak = False
                    f.onset = f.spectral_flux = 0.0
                self._last_music_state = self._music.update(f, allow_beat=allowed)
                accepted_beat = allowed and self._music.last_event_time == f.timestamp
                self._can_emit = True
                if self._kind == "file":
                    self._last_file_state_time = f.timestamp
            observation = replace(
                observation,
                beat_event=bool(accepted_beat),
                event_id=f"{self._epoch}:{self._seq}" if accepted_beat else None,
            )
            self._selector.publish(observation)
            self._last_observation = observation
        selected = self._selector.poll()
        self._last_observation = selected
        self._last_quality = selected.quality
        if selected.quality == "stale":
            self._can_emit = False
            self._pcm_timestamp = None
            self._pcm_buffer = np.empty((0, 2), dtype=np.float32)
            self._last_music_state = None
            self._music.reset()
            if self._audio_analyzer is not None:
                self._audio_analyzer.reset()
            return None, None
        if selected.quality == "fresh":
            if self._kind in {"phone_pcm", "program_pcm", "monitor"}:
                self._last_music_state = self._pcm_music_state
            return selected.features, self._last_music_state
        if selected.quality == "held":
            return selected.features, self._last_music_state
        return None, None

    def status(self) -> dict[str, object]:
        result = self._selector.status()
        obs = self._last_observation
        music = self._last_music_state
        tempo_valid = bool(music and music.tempo_confidence >= 0.18 and music.tempo_bpm > 0
                           and self._last_quality in {"fresh", "held"})
        result.update(
            {
                "age_ms": obs.age_ms if obs else None,
                "clock_domain": obs.clock_domain if obs else None,
                "analysis_time_s": obs.analysis_time_s if obs else None,
                "beat_confidence": None,
                "tempo_bpm": music.tempo_bpm if tempo_valid else None,
                "beat_phase": music.beat_phase if tempo_valid else None,
                "tempo_confidence": music.tempo_confidence if tempo_valid else 0.0,
                "mode": self._mode,
                "target": dict(self._target),
                "quality": self._last_quality,
                "silent": (
                    self._last_observation.features.silence
                    if self._last_observation
                    and self._last_quality in {"held", "fresh"}
                    else None
                ),
                "band_layout": "wled_v2_native_unknown"
                if self._kind == "wled"
                else "pcm_wled16_ref",
                "level_scale": "wled_wire" if self._kind == "wled" else "dbfs_display",
                "phase": {"fresh":"applied","held":"applied","warming":"preparing",
                          "stale":"fault","fault":"fault"}.get(self._last_quality,"waiting"),
                "effective": self._kind
                if self._last_quality in {"fresh", "held"}
                else None,
                "reason": self._fault,
                "sample_seq": self._last_observation.sample_seq
                if self._last_observation
                else None,
                "event_id": self._last_observation.event_id
                if self._last_observation
                else None,
                "capabilities": list(self._last_observation.capabilities)
                if self._last_observation
                else [],
            }
        )
        if self._capture is not None:
            result["capture"] = self._capture.status()
        if self._wled is not None:
            result["receiver"] = self._wled.diagnostics()
        return result

    def close(self) -> None:
        self._close_source()
        self._selector.select("none")
        self._kind = "none"
        self._source_id = None
        self._configured_key = None
        self._fault = None

    def _close_source(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._capture is not None:
            self._capture.close()
            self._capture = None
        if self._wled is not None:
            self._wled.close()
            self._wled = None
