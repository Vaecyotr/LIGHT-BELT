"""COLOR_WIPE effect - progressively fill each logical strip."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.color import rgb_to_rgbcct
from light_engine.config import Config
from light_engine.effects.base import BaseEffect, runtime_float, runtime_rgb
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput


def validate_color_wipe_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    unknown = set(values) - {"speed", "color", "color_timeline"}
    if unknown:
        raise ValueError(f"unknown effect parameters: {sorted(unknown)}")
    speed = values.get("speed")
    if speed is not None:
        if type(speed) not in {int, float} or not math.isfinite(float(speed)):
            raise ValueError("speed must be a finite number")
        if not 0.0 <= float(speed) <= 1000.0:
            raise ValueError("speed must be in [0, 1000] pixels per second")
    color = values.get("color")
    if color is not None:
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            raise ValueError("color must contain exactly 3 RGB channels")
        if any(
            type(channel) not in {int, float}
            or not math.isfinite(float(channel))
            or not 0.0 <= float(channel) <= 1.0
            for channel in color
        ):
            raise ValueError("color channels must be finite numbers in [0, 1]")
    return dict(values)


class ColorWipeEffect(BaseEffect):
    """Fill pixels cumulatively at a frame-rate-independent speed."""

    def __init__(self, name: str = "color_wipe"):
        super().__init__(name)
        config = Config.get_instance()
        self._speed = config.get("effects.color_wipe.speed", 20.0)
        color = config.get("effects.color_wipe.color", [0.2, 0.6, 1.0])
        self._color = (float(color[0]), float(color[1]), float(color[2]))
        self._elapsed = 0.0

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = runtime_float(ctx, "speed", self._speed)
        r, g, b = runtime_rgb(ctx, "color", self._color)
        self._elapsed += ctx.delta_time
        elapsed = max(
            0.0,
            float(ctx.mode_parameters.get("cue_local_time", self._elapsed)),
        )

        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            pixel_count = strip_def["pixel_count"]
            lit_count = min(pixel_count, max(0, int(elapsed * speed) + 1))
            pixels = [(r, g, b)] * lit_count
            pixels.extend([(0.0, 0.0, 0.0)] * (pixel_count - lit_count))
            strips.append(
                DigitalStrip(
                    strip_id=strip_def["id"],
                    pixel_count=pixel_count,
                    pixels=pixels,
                )
            )

        zones = [
            ZoneOutput(zone_id=zone_def["id"], color=rgb_to_rgbcct(r, g, b))
            for zone_def in ctx.mode_parameters.get("zone_defs", [])
        ]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
        )

    def reset(self) -> None:
        self._elapsed = 0.0
