"""Reusable runtime sampling for explicit Show v2 ColorSource blocks."""

from __future__ import annotations

import hashlib
import math
from typing import Literal

from light_engine.color import rgb_to_rgbcct
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput
from light_engine.show.models import ColorSourceSpec


ColorSourceSupport = Literal["GLOBAL", "POSITIONAL", "EVENT", "NOT_APPLICABLE"]


def color_source_support(effect_id: str) -> ColorSourceSupport:
    # Lazy import avoids a registry/show import cycle during built-in setup.
    from light_engine.effects import get_effect_registration

    return get_effect_registration(effect_id).color_source_support


class ColorSampler:
    """Sample one validated ColorSource using global, position, or event semantics."""

    def __init__(self, spec: ColorSourceSpec, *, cue_seed: int = 0):
        self.spec = spec
        self._cue_seed = int(cue_seed)

    def sample_current(self, ctx: EffectContext) -> tuple[float, float, float]:
        source_type = self.spec.type
        if source_type == "timeline":
            return self._timeline(float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        if source_type == "spatial_palette":
            return interpolate_palette(self.spec.palette, 0.5)
        if source_type == "video_average":
            return self._video(ctx, dominant=False)
        if source_type == "video_dominant":
            return self._video(ctx, dominant=True)
        if source_type == "audio_spectrum_palette":
            audio = ctx.audio_features
            if audio is None:
                return self._fallback()
            return interpolate_palette(self.spec.palette, sum(audio.spectrum or ()) / 16.0)
        if source_type == "dominant_frequency_palette":
            return self._dominant_frequency(ctx)
        raise RuntimeError(f"unsupported ColorSource type {source_type!r}")

    def sample_position(
        self, ctx: EffectContext, normalized_position: float
    ) -> tuple[float, float, float]:
        position = _clamp01(normalized_position)
        if self.spec.type == "spatial_palette":
            return interpolate_palette(self.spec.palette, position)
        if self.spec.type == "audio_spectrum_palette":
            audio = ctx.audio_features
            if audio is None:
                return self._fallback()
            spectrum = audio.spectrum or (0.0,) * 16
            band = _sample_scalar(spectrum, position)
            return interpolate_palette(self.spec.palette, band)
        return self.sample_current(ctx)

    def sample_event(
        self, ctx: EffectContext, event_identity: object
    ) -> tuple[float, float, float]:
        logical_identity = _stable_event_identity(event_identity)
        digest = hashlib.sha256(
            f"color-source-event-v1:{self._cue_seed}:{logical_identity}".encode("utf-8")
        ).digest()
        coordinate = int.from_bytes(digest[:8], "big") / float((1 << 64) - 1)
        return self.sample_position(ctx, coordinate)

    def apply_to_frame(
        self,
        ctx: EffectContext,
        frame: PixelFrame,
        support: ColorSourceSupport,
    ) -> PixelFrame:
        """Replace hue while preserving each renderer's existing RGB envelope."""

        if support not in {"GLOBAL", "POSITIONAL"}:
            return frame
        global_color = self.sample_current(ctx)
        strips: list[DigitalStrip] = []
        for strip in frame.strips:
            pixels = []
            for index, pixel in enumerate(strip.pixels):
                position = normalized_pixel_position(index, strip.pixel_count)
                sampled = (
                    self.sample_position(ctx, position)
                    if support == "POSITIONAL"
                    else global_color
                )
                gain = max(pixel)
                pixels.append(tuple(_clamp01(channel * gain) for channel in sampled))
            strips.append(DigitalStrip(strip.strip_id, strip.pixel_count, pixels))

        zones = []
        for zone in frame.zones:
            gain = max(
                zone.color.r,
                zone.color.g,
                zone.color.b,
                zone.color.warm_white,
                zone.color.cool_white,
            )
            zones.append(
                ZoneOutput(
                    zone.zone_id,
                    rgb_to_rgbcct(*(channel * gain for channel in global_color)),
                )
            )
        return PixelFrame(
            frame.timestamp,
            frame.sequence,
            strips,
            zones,
            metadata=dict(frame.metadata),
        )

    def _timeline(self, cue_time: float) -> tuple[float, float, float]:
        frames = self.spec.keyframes
        if cue_time <= frames[0].time:
            return frames[0].color
        for index, current in enumerate(frames[1:], start=1):
            if cue_time <= current.time:
                previous = frames[index - 1]
                amount = (cue_time - previous.time) / (current.time - previous.time)
                return tuple(
                    previous.color[channel]
                    + (current.color[channel] - previous.color[channel]) * amount
                    for channel in range(3)
                )
        return frames[-1].color

    def _video(self, ctx: EffectContext, *, dominant: bool) -> tuple[float, float, float]:
        video = ctx.video_features
        if video is None:
            return self._fallback()
        return tuple(video.dominant_rgb if dominant else video.average_rgb)

    def _dominant_frequency(self, ctx: EffectContext) -> tuple[float, float, float]:
        audio = ctx.audio_features
        if audio is None:
            return self._fallback()
        lower = self.spec.frequency_min_hz
        upper = self.spec.frequency_max_hz
        if lower is None or upper is None:
            raise RuntimeError("validated dominant-frequency ColorSource lacks bounds")
        coordinate = (audio.dominant_frequency - lower) / (upper - lower)
        return interpolate_palette(self.spec.palette, coordinate)

    def _fallback(self) -> tuple[float, float, float]:
        if self.spec.fallback is None:
            raise RuntimeError("validated input ColorSource lacks fallback")
        return self.spec.fallback


def interpolate_palette(
    palette: tuple[tuple[float, float, float], ...], coordinate: float
) -> tuple[float, float, float]:
    value = _clamp01(coordinate)
    if len(palette) == 1:
        return palette[0]
    scaled = value * (len(palette) - 1)
    left = min(int(math.floor(scaled)), len(palette) - 1)
    right = min(left + 1, len(palette) - 1)
    amount = scaled - left
    return tuple(
        palette[left][channel]
        + (palette[right][channel] - palette[left][channel]) * amount
        for channel in range(3)
    )


def normalized_pixel_position(index: int, pixel_count: int) -> float:
    """Map a finite logical path to [0,1]; a one-pixel path uses its midpoint."""

    if pixel_count <= 0 or index < 0 or index >= pixel_count:
        raise ValueError("pixel index must address a non-empty logical path")
    return 0.5 if pixel_count == 1 else index / (pixel_count - 1)


def _sample_scalar(values: tuple[float, ...], coordinate: float) -> float:
    value = _clamp01(coordinate)
    scaled = value * (len(values) - 1)
    left = min(int(math.floor(scaled)), len(values) - 1)
    right = min(left + 1, len(values) - 1)
    amount = scaled - left
    return _clamp01(values[left] + (values[right] - values[left]) * amount)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _stable_event_identity(value: object) -> str:
    """Encode only logical primitives; reject address-bearing object reprs."""

    if isinstance(value, str):
        return f"s{len(value)}:{value}"
    if type(value) is int:
        return f"i:{value}"
    if isinstance(value, tuple):
        return "t:[" + ",".join(_stable_event_identity(item) for item in value) + "]"
    raise TypeError("ColorSource event identity must contain only str/int/tuple values")
