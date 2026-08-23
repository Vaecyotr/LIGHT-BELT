"""Two-level pulse with discrete, deterministic state changes."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_rgb,
)
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput


class StepPulseEffect(BaseEffect):
    """Alternate between two exact colors without interpolation."""

    def process(self, ctx: EffectContext) -> PixelFrame:
        period = max(0.001, runtime_float(ctx, "period", 4.0))
        duty_cycle = runtime_float(ctx, "duty_cycle", 0.5)
        low = runtime_rgb(ctx, "low_color", (0.125, 0.03125, 0.0))
        high = runtime_rgb(ctx, "high_color", (0.125, 0.0625, 0.0))
        cue_time = float(ctx.mode_parameters.get("cue_local_time", 0.0))
        # Keep the historical low-first phase while using conventional duty
        # semantics: duty_cycle is the fraction of each period spent HIGH.
        color = low if cue_time % period < period * (1.0 - duty_cycle) else high

        strips = [
            DigitalStrip(
                strip_id=strip["id"],
                pixel_count=strip["pixel_count"],
                pixels=[color] * strip["pixel_count"],
            )
            for strip in ctx.mode_parameters.get("strip_defs", [])
        ]
        zones = [
            ZoneOutput(zone_id=zone["id"], color=rgb_to_rgbcct(*color))
            for zone in ctx.mode_parameters.get("zone_defs", [])
        ]
        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp,
                sequence=ctx.sequence,
                strips=strips,
                zones=zones,
            ),
            ctx.intensity,
        )


def validate_step_pulse_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    duty_cycle = values.get("duty_cycle")
    if duty_cycle is not None:
        if type(duty_cycle) not in {int, float} or not math.isfinite(float(duty_cycle)):
            raise ValueError("duty_cycle must be a finite number")
        if not 0.0 <= float(duty_cycle) <= 1.0:
            raise ValueError("duty_cycle must be in [0, 1]")
    return dict(values)
