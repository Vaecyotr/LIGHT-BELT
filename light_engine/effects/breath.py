"""BREATH effect - slow periodic brightness oscillation."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_rgb,
    runtime_str,
)
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)


class BreathEffect(BaseEffect):
    """Slow sinusoidal brightness breathing."""

    def __init__(self, name: str = "breath"):
        super().__init__(name)
        config = Config.get_instance()
        self._period = config.get("effects.breath.period", 4.0)
        c = config.get("effects.breath.color", [0.4, 0.2, 0.6])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )
        self._min = config.get(
            "effects.breath.min_brightness",
            config.get("system.smoothing.min_brightness", 0.01),
        )
        self._phase = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        period = max(0.001, runtime_float(ctx, "period", self._period))
        minimum = runtime_float(ctx, "min_brightness", self._min)
        waveform = runtime_str(ctx, "waveform", "sine")
        r, g, b = runtime_rgb(ctx, "color", self._color)

        self._phase += ctx.delta_time
        phase = float(ctx.mode_parameters.get("cue_local_time", self._phase))
        cycle = (phase / period) % 1.0
        if waveform == "sine":
            # Keep the historical phase and arithmetic exactly for the default.
            t = (math.sin(2 * math.pi * phase / period) + 1) / 2
        else:
            triangle = 1.0 - abs(2.0 * ((cycle + 0.25) % 1.0) - 1.0)
            t = triangle if waveform == "triangle" else triangle * triangle * (3.0 - 2.0 * triangle)
        brightness = minimum + (1.0 - minimum) * t

        r, g, b = r * brightness, g * brightness, b * brightness

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            pixels = [(r, g, b)] * sd["pixel_count"]
            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=rgb_to_rgbcct(r, g, b),
            ))

        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
            ),
            ctx.intensity,
        )

    def reset(self) -> None:
        self._phase = 0.0


def validate_breath_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    waveform = values.get("waveform")
    if waveform is not None and (
        not isinstance(waveform, str)
        or waveform not in {"sine", "triangle", "smoothstep"}
    ):
        raise ValueError("waveform must be one of: sine, triangle, smoothstep")
    return dict(values)
