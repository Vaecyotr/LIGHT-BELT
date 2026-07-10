"""Cue-local continuous modulation from existing audio analysis values."""

from __future__ import annotations

from dataclasses import dataclass

from light_engine.models import EffectContext
from light_engine.show.models import AudioModulationChannelSpec, AudioModulationSpec


SOURCE_FIELDS = {
    "music.energy": ("music_control_state", "energy", False),
    "music.energy_trend": ("music_control_state", "energy_trend", True),
    "music.beat_strength": ("music_control_state", "beat_strength", False),
    "music.bass_pulse": ("music_control_state", "bass_pulse", False),
    "music.bass_ambient": ("music_control_state", "bass_ambient", False),
    "music.transient": ("music_control_state", "transient", False),
    "music.spectral_motion": ("music_control_state", "spectral_motion", False),
    "music.tempo_confidence": ("music_control_state", "tempo_confidence", False),
    "music.beat_regularity": ("music_control_state", "beat_regularity", False),
    "audio.rms": ("audio_features", "rms", False),
    "audio.bass": ("audio_features", "bass", False),
    "audio.mid": ("audio_features", "mid", False),
    "audio.treble": ("audio_features", "treble", False),
    "audio.spectral_flux": ("audio_features", "spectral_flux", False),
    "audio.onset": ("audio_features", "onset", False),
}


@dataclass(frozen=True)
class AudioModulationMultipliers:
    """The three bounded multipliers applied during one cue render."""

    brightness: float = 1.0
    speed: float = 1.0
    intensity: float = 1.0


class CueAudioModulator:
    """Maintain deterministic smoothing state for one cue only.

    For [0, 1] feature values, the signed modulation signal is ``2v - 1``;
    ``music.energy_trend`` is already signed in [-1, 1].  The target is
    ``clamp(1 + amount * signal, min_multiplier, max_multiplier)``.  A
    missing source always returns the neutral multiplier 1.0 and clears that
    channel's smoothing history.
    """

    def __init__(self, spec: AudioModulationSpec | None):
        self._spec = spec
        self._previous: dict[str, float] = {}

    def reset(self) -> None:
        self._previous.clear()

    def multipliers(self, ctx: EffectContext) -> AudioModulationMultipliers:
        if self._spec is None or not self._spec.enabled:
            self.reset()
            return AudioModulationMultipliers()
        return AudioModulationMultipliers(
            brightness=self._multiplier("brightness", self._spec.brightness, ctx),
            speed=self._multiplier("speed", self._spec.speed, ctx),
            intensity=self._multiplier("intensity", self._spec.intensity, ctx),
        )

    def _multiplier(
        self,
        channel_name: str,
        channel: AudioModulationChannelSpec | None,
        ctx: EffectContext,
    ) -> float:
        if channel is None:
            return 1.0
        source_value = _source_value(channel.source, ctx)
        if source_value is None:
            self._previous.pop(channel_name, None)
            return 1.0
        target = _target_multiplier(channel, source_value)
        previous = self._previous.get(channel_name, 1.0)
        alpha = 1.0 if channel.smoothing_seconds == 0.0 else min(
            1.0, ctx.delta_time / channel.smoothing_seconds
        )
        smoothed = previous + alpha * (target - previous)
        bounded = _clamp(smoothed, channel.min_multiplier, channel.max_multiplier)
        self._previous[channel_name] = bounded
        return bounded


def _source_value(source: str, ctx: EffectContext) -> float | None:
    context_field, source_field, signed = SOURCE_FIELDS[source]
    state = getattr(ctx, context_field)
    if state is None:
        return None
    value = float(getattr(state, source_field))
    return value if signed else 2.0 * value - 1.0


def _target_multiplier(channel: AudioModulationChannelSpec, signal: float) -> float:
    return _clamp(
        1.0 + channel.amount * signal,
        channel.min_multiplier,
        channel.max_multiplier,
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
