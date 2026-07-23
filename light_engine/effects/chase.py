"""CHASE effect - running light with multiple chase patterns.

Uses delta_time for frame-rate-independent animation.
Supports: single, multi, bounce, rainbow, video-color chase.
"""

from __future__ import annotations

import colorsys
import math
from typing import Optional

from light_engine.config import Config
from light_engine.effects.base import (
    BaseEffect,
    runtime_bool,
    runtime_float,
    runtime_int,
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


class ChaseEffect(BaseEffect):
    """Configurable chase/running-light effect.

    Uses delta_time for consistent speed across different frame rates.
    """

    def __init__(self, name: str = "chase"):
        super().__init__(name)
        config = Config.get_instance()
        self._speed_pps = config.get("effects.chase.speed", 2.0)  # pixels per second at speed=1
        self._width = config.get("effects.chase.width", 5)
        self._gap = config.get("effects.chase.gap", 10)
        self._direction = config.get("effects.chase.direction", "forward")
        self._trail = config.get("effects.chase.trail", 0.3)
        self._color_source = config.get("effects.chase.color_source", "rainbow")
        self._beat_boost = config.get("effects.chase.beat_boost", 2.0)
        self._position: float = 0.0
        self._bounce_phases: dict[str, float] = {}
        self._hue_offset: float = 0.0

    def _chase_color(
        self,
        pos: float,
        pixel_count: int,
        base_rgb: Optional[tuple[float, float, float]],
        color_source: str,
    ) -> tuple[float, float, float]:
        """Get the color for a chase position."""
        if color_source == "rainbow":
            hue = (pos / max(1, pixel_count) * 360 + self._hue_offset) % 360
            return colorsys.hsv_to_rgb(hue / 360, 1.0, 1.0)
        elif color_source in {"video", "static"} and base_rgb:
            return base_rgb
        else:
            return (1.0, 0.6, 0.0)  # default orange

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed_pps = runtime_float(ctx, "speed", self._speed_pps)
        width = runtime_int(ctx, "width", self._width)
        gap = runtime_int(ctx, "gap", self._gap)
        direction = runtime_str(ctx, "direction", self._direction)
        trail = runtime_float(ctx, "trail", self._trail)
        color_source = runtime_str(ctx, "color_source", self._color_source)
        beat_boost = runtime_float(ctx, "beat_boost", self._beat_boost)

        speed = speed_pps * ctx.speed
        if runtime_bool(ctx, "beat_boost", False) and ctx.audio_features:
            if ctx.audio_features.beat:
                speed *= beat_boost

        if direction == "reverse":
            dir_sign = -1
            self._position += dir_sign * speed * ctx.delta_time
        elif direction != "bounce":
            dir_sign = 1
            self._position += dir_sign * speed * ctx.delta_time
        self._hue_offset = (self._hue_offset + ctx.delta_time * 30) % 360

        # Get video color if available
        video_rgb = None
        if ctx.video_features:
            video_rgb = ctx.video_features.average_rgb
        authored_rgb = runtime_rgb(ctx, "color", (1.0, 0.6, 0.0))
        base_rgb = video_rgb if color_source == "video" else authored_rgb

        strips = []

        active_bounce_ids = set()
        for strip_index, sd in enumerate(
            ctx.mode_parameters.get("strip_defs", [])
        ):
            strip_id = sd["id"]
            n = sd["pixel_count"]
            if n == 0:
                continue
            period = width + gap
            if period <= 0:
                period = 1
            pixels = []
            if direction == "bounce":
                active_bounce_ids.add(strip_id)
                phase = (
                    self._bounce_phases.get(strip_id, 0.0)
                    + speed * ctx.delta_time
                )
                self._bounce_phases[strip_id] = phase
                max_position = n - 1
                if max_position <= 0:
                    pos = 0.0
                else:
                    span = float(max_position * 2)
                    folded = phase % span
                    pos = folded if folded <= max_position else span - folded
                if strip_index == 0:
                    self._position = pos
            else:
                pos = self._position
            for i in range(n):
                # Compute distance from nearest chase dot
                if direction == "bounce":
                    dist = (i - pos) % period
                else:
                    if dir_sign > 0:
                        dist = (i - pos) % period
                    else:
                        reverse_index = n - 1 - i
                        dist = (reverse_index + pos) % period

                if width > 0 and dist <= width:
                    intensity = 1.0 - (dist / width) * (1.0 - trail)
                    r, g, b = self._chase_color(i, n, base_rgb, color_source)
                    pixels.append((r * intensity, g * intensity, b * intensity))
                else:
                    pixels.append((0.0, 0.0, 0.0))

            strips.append(DigitalStrip(
                strip_id=strip_id, pixel_count=n, pixels=pixels
            ))

        for stale_id in set(self._bounce_phases) - active_bounce_ids:
            self._bounce_phases.pop(stale_id, None)

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=RGBCCTColor(),
            ))

        return PixelFrame(
            timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
        )

    def reset(self) -> None:
        self._position = 0.0
        self._bounce_phases.clear()
        self._hue_offset = 0.0

    def get_parameters(self) -> dict:
        return {
            "name": self.name,
            "position": round(self._position, 1),
            "speed_pps": self._speed_pps,
            "direction": self._direction,
        }
