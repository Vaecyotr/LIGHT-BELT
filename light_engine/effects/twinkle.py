"""TWINKLE effect - randomly positioned, controllably colored sparks."""

from __future__ import annotations

import colorsys
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

from light_engine.config import Config
from light_engine.effects.base import (
    BaseEffect,
    runtime_float,
    runtime_param,
    runtime_rgb,
    runtime_str,
)
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


def validate_twinkle_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    unknown = set(values) - {
        "density",
        "fade_time",
        "color_source",
        "color",
        "color_timeline",
    }
    if unknown:
        raise ValueError(f"unknown effect parameters: {sorted(unknown)}")
    for key, lower, upper in (
        ("density", 0.0, 100.0),
        ("fade_time", 0.01, 60.0),
    ):
        value = values.get(key)
        if value is not None:
            if type(value) not in {int, float} or not math.isfinite(float(value)):
                raise ValueError(f"{key} must be a finite number")
            if not lower <= float(value) <= upper:
                raise ValueError(f"{key} must be in [{lower}, {upper}]")
    color_source = values.get("color_source")
    if color_source is not None and color_source not in {"solid", "palette", "random"}:
            raise ValueError(
                "color_source must be one of ['palette', 'random', 'solid']"
            )
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


class TwinkleEffect(BaseEffect):
    """Spawn sparks at random valid coordinates, scaled by strip length."""

    def __init__(self, name: str = "twinkle"):
        super().__init__(name)
        config = Config.get_instance()
        self._density = config.get("effects.twinkle.density", 0.12)
        self._fade_time = config.get("effects.twinkle.fade_time", 0.7)
        self._color_source = config.get("effects.twinkle.color_source", "random")
        color = config.get("effects.twinkle.color", [1.0, 1.0, 1.0])
        self._color = (float(color[0]), float(color[1]), float(color[2]))
        self._pixels: dict[str, list[tuple[float, float, float]]] = {}
        self._spawn_remainders: dict[str, float] = {}

    @staticmethod
    def _random_color() -> tuple[float, float, float]:
        return colorsys.hsv_to_rgb(random.random(), 0.7, 1.0)

    def _spark_color(
        self,
        ctx: EffectContext,
        color_source: str,
        solid: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        if color_source == "random":
            return self._random_color()
        if color_source == "palette":
            palette = runtime_param(ctx, "palette", ())
            if isinstance(palette, Sequence) and palette:
                selected = random.choice(palette)
                return (float(selected[0]), float(selected[1]), float(selected[2]))
        return solid

    def process(self, ctx: EffectContext) -> PixelFrame:
        density = runtime_float(ctx, "density", self._density)
        fade_time = runtime_float(ctx, "fade_time", self._fade_time)
        color_source = runtime_str(ctx, "color_source", self._color_source)
        solid = runtime_rgb(ctx, "color", self._color)
        decay = math.exp(-ctx.delta_time / fade_time)

        strips = []
        active_ids = set()
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            strip_id = strip_def["id"]
            pixel_count = strip_def["pixel_count"]
            active_ids.add(strip_id)
            current = self._pixels.get(strip_id)
            if current is None or len(current) != pixel_count:
                current = [(0.0, 0.0, 0.0)] * pixel_count
                self._spawn_remainders[strip_id] = 0.0
            current = [
                (
                    (r * decay, g * decay, b * decay)
                    if max(r, g, b) * decay >= 0.01
                    else (0.0, 0.0, 0.0)
                )
                for r, g, b in current
            ]

            expected = density * pixel_count * ctx.delta_time
            total = expected + self._spawn_remainders.get(strip_id, 0.0)
            spawn_count = int(total)
            self._spawn_remainders[strip_id] = total - spawn_count
            for _ in range(spawn_count):
                if pixel_count == 0:
                    break
                position = random.randrange(pixel_count)
                current[position] = self._spark_color(ctx, color_source, solid)

            self._pixels[strip_id] = current
            strips.append(
                DigitalStrip(
                    strip_id=strip_id,
                    pixel_count=pixel_count,
                    pixels=current,
                )
            )

        for stale_id in set(self._pixels) - active_ids:
            self._pixels.pop(stale_id, None)
            self._spawn_remainders.pop(stale_id, None)

        zones = [
            ZoneOutput(zone_id=zone_def["id"], color=RGBCCTColor())
            for zone_def in ctx.mode_parameters.get("zone_defs", [])
        ]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=strips,
            zones=zones,
        )

    def reset(self) -> None:
        self._pixels.clear()
        self._spawn_remainders.clear()
