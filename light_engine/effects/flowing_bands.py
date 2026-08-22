"""Fixed alternating bands with a cue-local, discrete moving highlight."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.effects.base import (
    BaseEffect,
    runtime_float,
    runtime_int,
    runtime_motion_time,
    runtime_rgb,
    runtime_str,
)
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput


def _finite_number(values: Mapping[str, Any], key: str, lower: float, upper: float) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    if not lower <= float(value) <= upper:
        raise ValueError(f"{key} must be in [{lower}, {upper}]")


def _integer(values: Mapping[str, Any], key: str, lower: int, upper: int) -> None:
    value = values.get(key)
    if value is not None and (type(value) is not int or not lower <= value <= upper):
        raise ValueError(f"{key} must be an integer in [{lower}, {upper}]")


def validate_flowing_bands_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    _integer(values, "band_width_px", 1, 10000)
    _integer(values, "gap_width_px", 1, 10000)
    _integer(values, "phase_offset_steps", 0, 10000)
    _finite_number(values, "base_gain", 0.0, 1.0)
    _finite_number(values, "highlight_gain", 0.0, 1.0)
    _finite_number(values, "steps_per_second", 0.0, 1000.0)
    direction = values.get("direction")
    if direction is not None and direction not in {"forward", "reverse"}:
        raise ValueError("direction must be 'forward' or 'reverse'")
    base = float(values.get("base_gain", 0.125))
    highlight = float(values.get("highlight_gain", 0.625))
    if highlight < base:
        raise ValueError("highlight_gain must be >= base_gain")
    _validate_color(values)
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


class FlowingBandsEffect(BaseEffect):
    """Keep the A/B pattern fixed and advance which A band is highlighted."""

    def process(self, ctx: EffectContext) -> PixelFrame:
        band_width = runtime_int(ctx, "band_width_px", 1)
        gap_width = runtime_int(ctx, "gap_width_px", 1)
        base_gain = runtime_float(ctx, "base_gain", 0.125)
        highlight_gain = runtime_float(ctx, "highlight_gain", 0.625)
        steps_per_second = runtime_float(ctx, "steps_per_second", 1.0)
        direction = runtime_str(ctx, "direction", "forward")
        phase_offset = runtime_int(ctx, "phase_offset_steps", 0)
        color = runtime_rgb(ctx, "color", (1.0, 1.0, 1.0))
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        motion_time = runtime_motion_time(ctx, cue_time)
        step = math.floor(motion_time * steps_per_second) + phase_offset
        period = band_width + gap_width

        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", ()):
            pixel_count = strip_def["pixel_count"]
            band_count = (pixel_count + period - 1) // period
            highlighted_band: int | None = None
            if step > 0 and band_count:
                highlighted_band = (step - 1) % band_count
                if direction == "reverse":
                    highlighted_band = band_count - 1 - highlighted_band

            pixels = []
            for index in range(pixel_count):
                position = index % period
                if position >= band_width:
                    pixels.append((0.0, 0.0, 0.0))
                    continue
                band_index = index // period
                gain = highlight_gain if band_index == highlighted_band else base_gain
                gain *= ctx.intensity
                pixels.append(
                    tuple(max(0.0, min(1.0, channel * gain)) for channel in color)
                )
            strips.append(DigitalStrip(strip_def["id"], pixel_count, pixels))
        zones = [ZoneOutput(zone["id"], RGBCCTColor()) for zone in ctx.mode_parameters.get("zone_defs", ())]
        return PixelFrame(ctx.timestamp, ctx.sequence, strips, zones)
