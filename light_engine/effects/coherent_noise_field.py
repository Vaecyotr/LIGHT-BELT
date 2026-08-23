"""Native moving one-dimensional coherent-noise brightness field."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_motion_time,
    runtime_rgb,
)
from light_engine.effects.coherent_noise import coherent_noise_2d, derive_coherent_seed
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput


def _bounded_number(
    values: Mapping[str, Any], key: str, lower: float, upper: float
) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    if not lower <= float(value) <= upper:
        raise ValueError(f"{key} must be in [{lower}, {upper}]")


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


def validate_coherent_noise_field_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the intentionally small authored field contract."""

    _bounded_number(values, "feature_size_px", 0.01, 10000.0)
    _bounded_number(values, "drift_rate", 0.0, 1000.0)
    _bounded_number(values, "contrast", 0.0, 4.0)
    _bounded_number(values, "floor_gain", 0.0, 1.0)
    _bounded_number(values, "ceiling_gain", 0.0, 1.0)
    floor = float(values.get("floor_gain", 0.10))
    ceiling = float(values.get("ceiling_gain", 0.85))
    if ceiling < floor:
        raise ValueError("ceiling_gain must be >= floor_gain")
    _validate_color(values)
    return dict(values)


class CoherentNoiseFieldEffect(BaseEffect):
    """Render one smoothly drifting logical brightness field per target path.

    Spatial origin is deliberately not interpreted here: the Show compositor
    remaps the finished logical frame, and virtual paths arrive as one complete
    path buffer before they are split back into physical logical strips.
    """

    def __init__(self, name: str = "coherent_noise_field", *, seed: int = 0):
        super().__init__(name)
        if type(seed) is not int:
            raise TypeError("seed must be an integer")
        self._seed = seed

    @staticmethod
    def _gain(noise: float, *, contrast: float, floor: float, ceiling: float) -> float:
        centered = 0.5 + (noise - 0.5) * contrast
        shaped = min(1.0, max(0.0, centered))
        return floor + (ceiling - floor) * shaped

    def process(self, ctx: EffectContext) -> PixelFrame:
        feature_size = runtime_float(ctx, "feature_size_px", 8.0)
        drift_rate = runtime_float(ctx, "drift_rate", 0.25)
        contrast = runtime_float(ctx, "contrast", 1.0)
        floor = runtime_float(ctx, "floor_gain", 0.10)
        ceiling = runtime_float(ctx, "ceiling_gain", 0.85)
        color = runtime_rgb(ctx, "color", (0.20, 0.55, 1.0))
        validate_coherent_noise_field_params(
            {
                "feature_size_px": feature_size,
                "drift_rate": drift_rate,
                "contrast": contrast,
                "floor_gain": floor,
                "ceiling_gain": ceiling,
                "color": color,
            }
        )
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", ctx.timestamp)))
        motion_time = runtime_motion_time(ctx, cue_time)
        temporal_coordinate = motion_time * drift_rate
        if not math.isfinite(temporal_coordinate):
            raise ValueError("coherent noise temporal coordinate must be finite")
        seed = derive_coherent_seed(self._seed, str(ctx.mode_parameters.get("cue_id", "")))

        def sample(position: float) -> tuple[float, float, float]:
            noise = coherent_noise_2d(
                position / feature_size, temporal_coordinate, seed=seed
            )
            gain = self._gain(noise, contrast=contrast, floor=floor, ceiling=ceiling)
            return tuple(channel * gain for channel in color)

        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", ()):
            pixel_count = int(strip_def["pixel_count"])
            pixels = [sample(index + 0.5) for index in range(pixel_count)]
            strips.append(DigitalStrip(str(strip_def["id"]), pixel_count, pixels))

        # Analog zones have no pixel coordinate.  A fixed logical half-pixel
        # sample gives every zone a deterministic, visible fallback without
        # inventing topology, physical positions, or a second origin system.
        zone_rgb = sample(0.5)
        zones = [
            ZoneOutput(zone_id=str(zone_def["id"]), color=rgb_to_rgbcct(*zone_rgb))
            for zone_def in ctx.mode_parameters.get("zone_defs", ())
        ]
        return apply_common_intensity(
            PixelFrame(ctx.timestamp, ctx.sequence, strips, zones), ctx.intensity
        )
