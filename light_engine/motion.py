"""Internal cue-scoped integrated motion-time contract.

The Show runtime owns one :class:`CueMotionClock` per authored cue.  Effects
consume the immutable :class:`MotionInterval` attached to their
``EffectContext``; neither type is part of authored Show syntax.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _finite_non_negative(value: float, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite number >= 0")
    return number


@dataclass(frozen=True)
class MotionInterval:
    """One immutable cue-motion sample and its wall-time correspondence.

    ``previous_*`` and current values delimit the most recently integrated
    interval.  A repeated timestamp returns the same object, so consumers can
    safely detect fixed-step crossings without advancing twice.
    """

    previous_motion_time: float
    motion_time: float
    previous_cue_time: float
    cue_time: float

    def __post_init__(self) -> None:
        previous_motion = _finite_non_negative(
            self.previous_motion_time, "previous_motion_time"
        )
        motion = _finite_non_negative(self.motion_time, "motion_time")
        previous_cue = _finite_non_negative(self.previous_cue_time, "previous_cue_time")
        cue = _finite_non_negative(self.cue_time, "cue_time")
        if motion < previous_motion:
            raise ValueError("motion_time must not precede previous_motion_time")
        if cue < previous_cue:
            raise ValueError("cue_time must not precede previous_cue_time")
        object.__setattr__(self, "previous_motion_time", previous_motion)
        object.__setattr__(self, "motion_time", motion)
        object.__setattr__(self, "previous_cue_time", previous_cue)
        object.__setattr__(self, "cue_time", cue)

    @property
    def motion_delta(self) -> float:
        return self.motion_time - self.previous_motion_time

    @property
    def cue_delta(self) -> float:
        return self.cue_time - self.previous_cue_time


class CueMotionClock:
    """Integrate final composed common speed for exactly one cue.

    The current render's final speed applies to the wall-time interval since
    the previous render, matching the engine's existing ``delta_time * speed``
    convention.  On a first late render the speed is treated as constant from
    cue start, preserving ``motion_time == cue_time * speed`` without
    inventing historical live-audio samples.
    """

    def __init__(self) -> None:
        self.reset()

    @property
    def current(self) -> MotionInterval | None:
        return self._current

    def reset(self) -> None:
        self._motion_time = 0.0
        self._last_cue_time: float | None = None
        self._current: MotionInterval | None = None

    def advance(self, cue_time: float, speed: float) -> MotionInterval:
        cue_time = _finite_non_negative(cue_time, "cue_time")
        speed = _finite_non_negative(speed, "common motion speed")
        self._validate_internal_state()

        if self._last_cue_time is not None:
            if cue_time < self._last_cue_time:
                raise RuntimeError(
                    "cue motion clock received backward timestamp; reset and replay from the beginning"
                )
            if cue_time == self._last_cue_time:
                assert self._current is not None
                return self._current
            previous_cue_time = self._last_cue_time
        else:
            previous_cue_time = 0.0

        previous_motion_time = self._motion_time
        increment = (cue_time - previous_cue_time) * speed
        motion_time = previous_motion_time + increment
        if not math.isfinite(increment) or not math.isfinite(motion_time):
            raise ValueError("integrated motion clock state must remain finite")
        if motion_time < previous_motion_time:
            raise ValueError("integrated motion clock must not decrease")

        current = MotionInterval(
            previous_motion_time=previous_motion_time,
            motion_time=motion_time,
            previous_cue_time=previous_cue_time,
            cue_time=cue_time,
        )
        self._motion_time = motion_time
        self._last_cue_time = cue_time
        self._current = current
        return current

    def _validate_internal_state(self) -> None:
        _finite_non_negative(self._motion_time, "integrated motion clock state")
        if self._last_cue_time is not None:
            _finite_non_negative(self._last_cue_time, "motion clock cue time")
            if self._current is None:
                raise ValueError("motion clock state is incomplete")
        elif self._current is not None:
            raise ValueError("motion clock state is incomplete")


def constant_speed_motion_interval(cue_time: float, speed: float) -> MotionInterval:
    """Build the cue-start interval used by constant-speed direct callers.

    Show rendering never uses this compatibility constructor; its intervals
    are always produced by ``CueMotionClock``.  This keeps non-Show unit and
    library calls compatible without duplicating phase formulas in effects.
    """

    cue_time = _finite_non_negative(cue_time, "cue_time")
    speed = _finite_non_negative(speed, "common motion speed")
    motion_time = cue_time * speed
    if not math.isfinite(motion_time):
        raise ValueError("integrated motion clock state must remain finite")
    return MotionInterval(0.0, motion_time, 0.0, cue_time)
