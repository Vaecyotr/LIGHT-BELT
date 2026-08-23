"""Audio-feature-driven bounded ripple waves."""

from __future__ import annotations

import math
import hashlib
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from light_engine.effects.base import BaseEffect, runtime_float, runtime_motion_time, runtime_rgb
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput


def _bounded(values: Mapping[str, Any], key: str, lower: float, upper: float) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    if not lower <= float(value) <= upper:
        raise ValueError(f"{key} must be in [{lower}, {upper}]")


def validate_onset_ripple_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    for key, lower, upper in (
        ("onset_threshold", 0.0, 1.0),
        ("wave_speed_pps", 0.0, 1000.0),
        ("wave_width_px", 0.1, 1000.0),
        ("decay_seconds", 0.01, 60.0),
        ("floor_gain", 0.0, 1.0),
    ):
        _bounded(values, key, lower, upper)
    _validate_color(values)
    event_origin = values.get("event_origin")
    if event_origin is not None and event_origin not in {"fixed", "random"}:
        raise ValueError("event_origin must be 'fixed' or 'random'")
    propagation = values.get("propagation")
    if propagation is not None and propagation not in {"one_way", "bidirectional"}:
        raise ValueError("propagation must be 'one_way' or 'bidirectional'")
    wrap = values.get("wrap")
    if wrap is not None and type(wrap) is not bool:
        raise ValueError("wrap must be a boolean")
    return dict(values)


def _validate_color(values: Mapping[str, Any]) -> None:
    color = values.get("color")
    if color is None:
        return
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        raise ValueError("color must contain exactly 3 RGB channels")
    if any(
        type(channel) not in {int, float}
        or not math.isfinite(float(channel))
        or not 0.0 <= float(channel) <= 1.0
        for channel in color
    ):
        raise ValueError("color channels must be finite numbers in [0, 1]")


@dataclass(frozen=True)
class _Wave:
    born: float
    born_motion: float
    strength: float
    origin: float
    bass: float
    high: float
    loudness: float
    color: tuple[float, float, float]


class OnsetRippleEffect(BaseEffect):
    """Birth bounded waves on generic peak/onset rising edges.

    ``origin`` here is the birth point of an individual event in the logical
    path.  It is deliberately separate from the cue/compositor ``origin``
    transform, which remains responsible for orienting the completed frame.
    """

    MAX_WAVES = 16

    def __init__(self, name: str = "onset_ripple", *, seed: int | None = None):
        super().__init__(name)
        # CueRenderJob seeds Python's module RNG while constructing a cue.  A
        # private seed sampled here therefore becomes cue-local and stable,
        # while direct callers can opt into an explicit seed for replay tests.
        self._seed = random.getrandbits(64) if seed is None else int(seed)
        self._waves: list[_Wave] = []
        self._previous_peak = False
        self._previous_onset = 0.0
        self._last_time: float | None = None
        self._event_index = 0

    @staticmethod
    def _bands(audio: AudioFeatures) -> tuple[float, float]:
        spectrum = audio.spectrum or (0.0,) * 16
        bass = max(audio.bass, sum(spectrum[:3]) / 3.0)
        high = max(audio.treble, sum(spectrum[10:]) / 6.0)
        return bass, high

    def _event_origin(
        self,
        ctx: EffectContext,
        event_index: int,
    ) -> float:
        """Return a deterministic event-local origin normalized to ``[0, 1)``."""

        event_origin = str(ctx.mode_parameters.get("event_origin", "fixed"))
        if event_origin == "fixed":
            return 0.0
        if event_origin != "random":
            # Validation normally catches this for authored parameters.  Keep
            # direct runtime contexts explicit rather than silently changing
            # the visual recipe.
            raise ValueError("event_origin must be 'fixed' or 'random'")
        cue_id = str(ctx.mode_parameters.get("cue_id", ""))
        digest = hashlib.sha256(
            f"{self._seed}:{cue_id}:{event_index}".encode("utf-8")
        ).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64)

    @staticmethod
    def _distance(
        position: float,
        front: float,
        length: int,
        wrap: bool,
    ) -> float:
        distance = abs(position - front)
        if wrap and length > 0:
            remainder = distance % length
            distance = min(remainder, length - remainder)
        return distance

    @classmethod
    def _wave_distance(
        cls,
        position: float,
        wave: _Wave,
        age: float,
        speed: float,
        length: int,
        propagation: str,
        wrap: bool,
        origin: float | None = None,
    ) -> float:
        travel = age * speed
        wave_origin = wave.origin if origin is None else origin
        distance = cls._distance(position, wave_origin + travel, length, wrap)
        if propagation == "bidirectional":
            distance = min(
                distance,
                cls._distance(position, wave_origin - travel, length, wrap),
            )
        elif propagation != "one_way":
            raise ValueError("propagation must be 'one_way' or 'bidirectional'")
        return distance

    def process(self, ctx: EffectContext) -> PixelFrame:
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        motion_time = runtime_motion_time(ctx, cue_time)
        if self._last_time is not None and cue_time < self._last_time:
            self.reset()
        self._last_time = cue_time
        threshold = runtime_float(ctx, "onset_threshold", 0.35)
        speed = runtime_float(ctx, "wave_speed_pps", 18.0)
        width = runtime_float(ctx, "wave_width_px", 2.0)
        decay = runtime_float(ctx, "decay_seconds", 1.5)
        floor = runtime_float(ctx, "floor_gain", 0.0)
        event_origin = str(ctx.mode_parameters.get("event_origin", "fixed"))
        propagation = str(ctx.mode_parameters.get("propagation", "one_way"))
        wrap = ctx.mode_parameters.get("wrap", False)
        if event_origin not in {"fixed", "random"}:
            raise ValueError("event_origin must be 'fixed' or 'random'")
        if propagation not in {"one_way", "bidirectional"}:
            raise ValueError("propagation must be 'one_way' or 'bidirectional'")
        if type(wrap) is not bool:
            raise ValueError("wrap must be a boolean")
        color = runtime_rgb(ctx, "color", (1.0, 0.35, 0.08))
        sampler = ctx.mode_parameters.get("color_sampler")
        floor_color = color if sampler is None else sampler.sample_current(ctx)
        audio = ctx.audio_features
        silent = audio is None or audio.silence
        if audio is None:
            peak = False
            onset = loudness = bass = high = 0.0
        else:
            peak = bool(audio.peak)
            onset = audio.onset
            loudness = audio.loudness or 0.0
            bass, high = self._bands(audio)
        trigger = not silent and (
            (peak and not self._previous_peak)
            or (onset >= threshold and self._previous_onset < threshold)
        )
        if trigger:
            event = max(onset, 1.0 if peak else 0.0)
            strength = min(1.0, event * (0.35 + 0.35 * loudness + 0.2 * bass + 0.1 * high))
            self._event_index += 1
            origin = self._event_origin(ctx, self._event_index)
            event_color = (
                color
                if sampler is None
                else sampler.sample_event(ctx, ("onset_ripple", self._event_index))
            )
            self._waves.append(
                _Wave(
                    cue_time,
                    motion_time,
                    strength,
                    origin,
                    bass,
                    high,
                    loudness,
                    event_color,
                )
            )
            del self._waves[:-self.MAX_WAVES]
        self._previous_peak = peak
        self._previous_onset = onset
        self._waves = [wave for wave in self._waves if cue_time - wave.born <= decay * 8.0]
        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", ()):
            pixels = []
            for index in range(strip_def["pixel_count"]):
                value = [channel * floor for channel in floor_color]
                x = index + 0.5
                for wave in self._waves:
                    # ``wave.origin`` is a shared normalized event location.
                    # Independent paths map it to their own valid logical
                    # pixel coordinate, while a virtual path is still passed
                    # here as its one continuous logical strip.
                    path_origin = wave.origin * strip_def["pixel_count"]
                    real_age = max(0.0, cue_time - wave.born)
                    motion_age = max(0.0, motion_time - wave.born_motion)
                    distance = self._wave_distance(
                        x,
                        wave,
                        motion_age,
                        speed,
                        strip_def["pixel_count"],
                        propagation,
                        wrap,
                        path_origin,
                    )
                    shape = max(0.0, 1.0 - distance / width)
                    fade = math.exp(-real_age / decay)
                    gains = (
                        0.5 + 0.5 * wave.bass,
                        0.5 + 0.5 * wave.loudness,
                        0.5 + 0.5 * wave.high,
                    )
                    for channel in range(3):
                        value[channel] += wave.color[channel] * wave.strength * shape * fade * gains[channel]
                pixels.append(tuple(min(1.0, channel * ctx.intensity) for channel in value))
            strips.append(DigitalStrip(strip_def["id"], strip_def["pixel_count"], pixels))
        zones = [ZoneOutput(zone["id"], RGBCCTColor()) for zone in ctx.mode_parameters.get("zone_defs", ())]
        return PixelFrame(ctx.timestamp, ctx.sequence, strips, zones)

    def reset(self) -> None:
        self._waves.clear()
        self._previous_peak = False
        self._previous_onset = 0.0
        self._last_time = None
        self._event_index = 0
