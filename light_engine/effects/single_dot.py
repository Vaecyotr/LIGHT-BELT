"""Discrete single-pixel flow with deterministic positions."""

import math

from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_motion_time,
    runtime_rgb,
    runtime_str,
)
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput


class SingleDotEffect(BaseEffect):
    """Move one exact-color pixel at integer positions without a trail."""

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = max(0.0, runtime_float(ctx, "speed", 5.0))
        direction = runtime_str(ctx, "direction", "forward")
        if direction not in {"forward", "reverse", "bounce"}:
            raise ValueError(
                "single_dot direction must be 'forward', 'reverse', or 'bounce'"
            )
        color = runtime_rgb(ctx, "color", (0.0, 0.0, 0.125))
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        motion_time = runtime_motion_time(ctx, cue_time)

        strips = []
        for strip in ctx.mode_parameters.get("strip_defs", []):
            count = strip["pixel_count"]
            pixels = [(0.0, 0.0, 0.0)] * count
            if count:
                position = int(math.floor(motion_time * speed + 1e-9)) % count
                if direction == "reverse":
                    position = count - 1 - position
                elif direction == "bounce" and count > 1:
                    period = 2 * (count - 1)
                    phase = int(math.floor(motion_time * speed + 1e-9)) % period
                    position = phase if phase < count else period - phase
                pixels[position] = color
            strips.append(
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=count,
                    pixels=pixels,
                )
            )

        zones = [
            ZoneOutput(zone_id=zone["id"], color=RGBCCTColor())
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
