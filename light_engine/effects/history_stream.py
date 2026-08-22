"""Fixed-rate color samples advected through one-dimensional logical paths."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from light_engine.color import evaluate_rgb_linear_timeline
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_motion_interval,
    runtime_param,
    runtime_rgb,
    runtime_str,
)
from light_engine.effects.scalar_source import ScalarSource, validate_scalar_source
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.motion import MotionInterval


_BLACK = (0.0, 0.0, 0.0)


def _finite_number(
    values: Mapping[str, Any],
    key: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    if not minimum <= float(value) <= maximum:
        raise ValueError(f"{key} must be in [{minimum}, {maximum}]")


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


def validate_history_stream_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the small authored contract of the native history primitive."""

    _finite_number(values, "steps_per_second", minimum=0.001, maximum=1000.0)
    direction = values.get("direction")
    if direction is not None and direction not in {"forward", "reverse"}:
        raise ValueError("direction must be 'forward' or 'reverse'")
    source = values.get("sample_gain_source")
    if source is not None:
        validate_scalar_source(source, field_name="sample_gain_source")
    _validate_color(values)
    return dict(values)


class HistoryStreamEffect(BaseEffect):
    """Insert fixed-rate color samples and move older ones through a path.

    At cue-local time zero, sampling step zero is inserted immediately.  At a
    later render call all due fixed steps through
    ``floor(motion_time * steps_per_second)`` are inserted.  When an
    authored ``color_timeline`` is present, its deterministic color function
    is evaluated at each retained exact fixed-step time.  Otherwise a renderer
    sees only its current context, so a call spanning unrendered steps inserts
    that current color/gain once for every due step.  Live scalar gain always
    remains current-context data; historical audio is never synthesized.
    """

    def __init__(self, name: str = "history_stream"):
        super().__init__(name)
        self._histories: dict[str, list[tuple[float, float, float]]] = {}
        self._last_steps: dict[str, int] = {}
        self._last_cue_time: float | None = None

    def process(self, ctx: EffectContext) -> PixelFrame:
        steps_per_second = runtime_float(ctx, "steps_per_second", 10.0)
        direction = runtime_str(ctx, "direction", "forward")
        sample_gain_source = runtime_param(ctx, "sample_gain_source", None)
        color_timeline = runtime_param(ctx, "color_timeline", None)
        color = runtime_rgb(ctx, "color", (1.0, 1.0, 1.0))
        validate_history_stream_params(
            {
                "steps_per_second": steps_per_second,
                "direction": direction,
                "sample_gain_source": sample_gain_source,
                "color": color,
            }
        )
        cue_time = float(ctx.mode_parameters.get("cue_local_time", ctx.timestamp))
        if not math.isfinite(cue_time):
            raise ValueError("history_stream cue_local_time must be finite")
        cue_time = max(0.0, cue_time)
        if self._last_cue_time is not None and cue_time < self._last_cue_time:
            self.reset()

        motion = runtime_motion_interval(ctx, cue_time)
        motion_time = motion.motion_time
        step_position = motion_time * steps_per_second
        if not math.isfinite(step_position):
            raise ValueError("history_stream step position must be finite")
        # The tolerance only neutralizes binary representation error at a
        # mathematically exact fixed-step boundary (for example 0.3 * 10).
        current_step = math.floor(step_position + 1e-12)
        gain = (
            1.0
            if sample_gain_source is None
            else ScalarSource(sample_gain_source).sample(ctx)
        )
        sample = tuple(channel * gain for channel in color)

        strips = []
        active_ids = set()
        for strip_def in ctx.mode_parameters.get("strip_defs", ()):
            strip_id = str(strip_def["id"])
            pixel_count = int(strip_def["pixel_count"])
            if pixel_count <= 0:
                raise ValueError("history_stream requires every logical path to be non-empty")
            active_ids.add(strip_id)
            history = self._resize_history(
                self._histories.get(strip_id, []),
                pixel_count,
                direction,
            )
            last_step = self._last_steps.get(strip_id, -1)
            due_steps = max(0, current_step - last_step)
            if due_steps:
                if color_timeline is None or (
                    ctx.motion is None and ctx.speed == 0.0
                ):
                    # With no timeline, and while speed is paused, no past
                    # color can be reconstructed.  Retain the documented
                    # current-sample insertion behavior.
                    history = self._advance(history, sample, due_steps, direction)
                else:
                    timeline_samples = self._timeline_samples(
                        color_timeline,
                        gain=gain,
                        last_step=last_step,
                        current_step=current_step,
                        steps_per_second=steps_per_second,
                        motion=motion,
                        capacity=pixel_count,
                    )
                    history = self._advance_samples(
                        history,
                        timeline_samples,
                        direction,
                    )
                self._last_steps[strip_id] = current_step
            self._histories[strip_id] = history
            strips.append(DigitalStrip(strip_id, pixel_count, list(history)))

        for stale_id in set(self._histories) - active_ids:
            self._histories.pop(stale_id, None)
            self._last_steps.pop(stale_id, None)
        self._last_cue_time = cue_time

        zones = [
            ZoneOutput(zone_id=zone_def["id"], color=RGBCCTColor())
            for zone_def in ctx.mode_parameters.get("zone_defs", ())
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

    @staticmethod
    def _resize_history(
        history: list[tuple[float, float, float]],
        pixel_count: int,
        direction: str,
    ) -> list[tuple[float, float, float]]:
        """Resize while retaining the newest edge of the logical stream."""

        if len(history) == pixel_count:
            return list(history)
        if direction == "forward":
            return (history[:pixel_count] + [_BLACK] * pixel_count)[:pixel_count]
        return ([_BLACK] * pixel_count + history[-pixel_count:])[-pixel_count:]

    @staticmethod
    def _advance(
        history: list[tuple[float, float, float]],
        sample: tuple[float, float, float],
        due_steps: int,
        direction: str,
    ) -> list[tuple[float, float, float]]:
        """Advance a bounded spatial history without allocating unbounded work."""

        length = len(history)
        if due_steps >= length:
            return [sample] * length
        if direction == "forward":
            return [sample] * due_steps + history[: length - due_steps]
        return history[due_steps:] + [sample] * due_steps

    @staticmethod
    def _timeline_samples(
        timeline: Any,
        *,
        gain: float,
        last_step: int,
        current_step: int,
        steps_per_second: float,
        motion: MotionInterval,
        capacity: int,
    ) -> list[tuple[float, float, float]]:
        """Rebuild only the retained fixed-step colors from a timeline.

        The timeline is a deterministic authored function, unlike live audio.
        It is therefore safe to evaluate it at the exact due step times.  The
        current scalar gain remains deliberately shared across those samples:
        no unavailable historical audio is invented.
        """

        first_step = max(last_step + 1, current_step - capacity + 1)
        samples = []
        for step in range(first_step, current_step + 1):
            boundary_motion = step / steps_per_second
            if motion.motion_delta > 0.0:
                fraction = (
                    (boundary_motion - motion.previous_motion_time)
                    / motion.motion_delta
                )
                # Normally every due boundary lies in the current interval.
                # Clamping only covers a newly introduced/resized logical path,
                # for which earlier wall-time correspondence is unavailable.
                fraction = min(1.0, max(0.0, fraction))
                cue_time = (
                    motion.previous_cue_time
                    + fraction * motion.cue_delta
                )
            else:
                cue_time = motion.previous_cue_time
            samples.append(
                tuple(
                    channel * gain
                    for channel in evaluate_rgb_linear_timeline(timeline, cue_time)
                )
            )
        return samples

    @staticmethod
    def _advance_samples(
        history: list[tuple[float, float, float]],
        samples: list[tuple[float, float, float]],
        direction: str,
    ) -> list[tuple[float, float, float]]:
        """Insert chronological timeline samples while retaining bounded work."""

        length = len(history)
        count = len(samples)
        if count >= length:
            return list(reversed(samples)) if direction == "forward" else list(samples)
        if direction == "forward":
            return list(reversed(samples)) + history[: length - count]
        return history[count:] + list(samples)

    def reset(self) -> None:
        self._histories.clear()
        self._last_steps.clear()
        self._last_cue_time = None
