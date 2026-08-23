"""COLOR_WIPE effect - progressively fill each logical strip."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.color import rgb_to_rgbcct
from light_engine.config import Config
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_param,
    runtime_float,
    runtime_motion_time,
    runtime_rgb,
)
from light_engine.effects.scalar_source import ScalarSource, validate_scalar_source
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, ZoneOutput


def validate_color_wipe_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
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
    progress_source = values.get("progress_source")
    if progress_source is not None:
        validate_scalar_source(progress_source, field_name="progress_source")
    slew_seconds = values.get("slew_seconds")
    if slew_seconds is not None:
        if type(slew_seconds) not in {int, float} or not math.isfinite(
            float(slew_seconds)
        ):
            raise ValueError("slew_seconds must be a finite number")
        if float(slew_seconds) < 0.0:
            raise ValueError("slew_seconds must be >= 0")
    edge_softness = values.get("edge_softness_px")
    if edge_softness is not None:
        if type(edge_softness) not in {int, float} or not math.isfinite(
            float(edge_softness)
        ):
            raise ValueError("edge_softness_px must be a finite number")
        if not 0.0 <= float(edge_softness) <= 10000.0:
            raise ValueError("edge_softness_px must be in [0, 10000]")
    progress_curve = values.get("progress_curve")
    if progress_curve is not None and (
        not isinstance(progress_curve, str)
        or progress_curve not in {"linear", "smoothstep"}
    ):
        raise ValueError("progress_curve must be one of: linear, smoothstep")
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
        self._external_progress: float | None = None
        self._external_source_name: str | None = None
        self._last_time_marker: float | None = None

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = runtime_float(ctx, "speed", self._speed)
        r, g, b = runtime_rgb(ctx, "color", self._color)
        self._elapsed += ctx.delta_time
        cue_time = max(
            0.0,
            float(ctx.mode_parameters.get("cue_local_time", self._elapsed)),
        )
        progress_source = runtime_param(ctx, "progress_source", None)
        external_progress = (
            None
            if progress_source is None
            else self._sample_external_progress(ctx, progress_source)
        )
        edge_softness = runtime_float(ctx, "edge_softness_px", 0.0)
        progress_curve = str(runtime_param(ctx, "progress_curve", "linear"))

        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            pixel_count = strip_def["pixel_count"]
            if external_progress is None:
                # Preserve the legacy time-driven default exactly, including
                # its first illuminated pixel at cue-local time zero.
                elapsed = runtime_motion_time(ctx, cue_time)
                lit_count = min(
                    pixel_count,
                    max(0, int(elapsed * speed) + 1),
                )
                front_px = min(pixel_count, max(0.0, elapsed * speed + 1.0))
            else:
                curved_progress = _apply_progress_curve(
                    external_progress,
                    progress_curve,
                )
                lit_count = min(
                    pixel_count,
                    max(
                        0,
                        math.floor(curved_progress * pixel_count + 1e-12),
                    ),
                )
                front_px = curved_progress * pixel_count
            if external_progress is None and progress_curve == "smoothstep":
                normalized = front_px / max(1, pixel_count)
                front_px = _apply_progress_curve(normalized, progress_curve) * pixel_count
                lit_count = min(pixel_count, max(0, math.floor(front_px + 1e-12)))
            if edge_softness == 0.0:
                # Exact legacy behavior for the default hard edge.
                pixels = [(r, g, b)] * lit_count
                pixels.extend([(0.0, 0.0, 0.0)] * (pixel_count - lit_count))
            elif front_px >= pixel_count:
                pixels = [(r, g, b)] * pixel_count
            else:
                pixels = [
                    (
                        r * gain,
                        g * gain,
                        b * gain,
                    )
                    for index in range(pixel_count)
                    for gain in (
                        max(0.0, min(1.0, (front_px - index) / edge_softness)),
                    )
                ]
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
        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp,
                sequence=ctx.sequence,
                strips=strips,
                zones=zones,
            ),
            ctx.intensity,
        )

    def reset(self) -> None:
        self._elapsed = 0.0
        self._external_progress = None
        self._external_source_name = None
        self._last_time_marker = None

    def _sample_external_progress(
        self,
        ctx: EffectContext,
        source_name: Any,
    ) -> float:
        source_name = validate_scalar_source(
            source_name,
            field_name="progress_source",
        )
        target = ScalarSource(source_name).sample(ctx)
        slew_seconds = runtime_float(ctx, "slew_seconds", 0.0)
        if not math.isfinite(slew_seconds) or slew_seconds < 0.0:
            raise ValueError("slew_seconds must be finite and >= 0")
        marker = float(ctx.mode_parameters.get("cue_local_time", ctx.timestamp))
        if not math.isfinite(marker):
            raise ValueError("external progress time marker must be finite")
        source_changed = source_name != self._external_source_name
        sought_backwards = (
            self._last_time_marker is not None
            and marker < self._last_time_marker
            and not math.isclose(marker, self._last_time_marker, abs_tol=1e-12)
        )
        if (
            self._external_progress is None
            or source_changed
            or sought_backwards
            or slew_seconds == 0.0
        ):
            progress = target
        else:
            maximum_change = ctx.delta_time / slew_seconds
            delta = target - self._external_progress
            progress = self._external_progress + max(
                -maximum_change,
                min(maximum_change, delta),
            )
        self._external_progress = progress
        self._external_source_name = source_name
        self._last_time_marker = marker
        return progress


def _apply_progress_curve(progress: float, curve: str) -> float:
    bounded = max(0.0, min(1.0, progress))
    if curve == "smoothstep":
        return bounded * bounded * (3.0 - 2.0 * bounded)
    return bounded
