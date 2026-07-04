"""Utility functions: smoothing, normalization, limiting."""

from __future__ import annotations

import math
from collections import deque
from typing import Tuple

import numpy as np


class EMASmoother:
    """Exponential Moving Average smoother for scalar or vector values.

    Args:
        alpha: Smoothing factor. 0 = instant response, 1 = no change.
    """

    def __init__(self, alpha: float = 0.15):
        self.alpha = max(0.0, min(1.0, alpha))
        self._value: float = 0.0

    def update(self, value: float) -> float:
        """Update smoother with new value, return smoothed result."""
        self._value = self.alpha * self._value + (1 - self.alpha) * value
        return self._value

    def reset(self, value: float = 0.0) -> None:
        """Reset smoother state."""
        self._value = value

    @property
    def value(self) -> float:
        return self._value


class ColorSmoother:
    """EMA smoother for RGB tuples."""

    def __init__(self, alpha: float = 0.15):
        self._r = EMASmoother(alpha)
        self._g = EMASmoother(alpha)
        self._b = EMASmoother(alpha)

    def update(
        self, r: float, g: float, b: float
    ) -> Tuple[float, float, float]:
        """Update smoother with new color, return smoothed result."""
        return (
            self._r.update(r),
            self._g.update(g),
            self._b.update(b),
        )

    def reset(self, r: float = 0.0, g: float = 0.0, b: float = 0.0) -> None:
        self._r.reset(r)
        self._g.reset(g)
        self._b.reset(b)

    @property
    def value(self) -> Tuple[float, float, float]:
        return (self._r.value, self._g.value, self._b.value)


class AttackReleaseEnvelope:
    """Attack/Release envelope for smooth brightness transitions.

    Args:
        attack: Rate of increase per second (higher = faster attack).
        release: Rate of decrease per second (lower = slower release).
    """

    def __init__(self, attack: float = 0.3, release: float = 0.08):
        self.attack = max(0.001, attack)
        self.release = max(0.001, release)
        self._value: float = 0.0

    def update(self, target: float, delta_time: float) -> float:
        """Update envelope towards target.

        Args:
            target: Target value in [0, 1].
            delta_time: Time since last update in seconds.

        Returns:
            Current envelope value.
        """
        if target > self._value:
            self._value += (target - self._value) * min(1.0, self.attack * delta_time * 60)
        else:
            self._value += (target - self._value) * min(1.0, self.release * delta_time * 60)
        return self._value

    def reset(self, value: float = 0.0) -> None:
        self._value = value

    @property
    def value(self) -> float:
        return self._value


class RollingHistory:
    """Fixed-capacity rolling history for dynamic normalization.

    Args:
        capacity: Maximum number of values to store.
    """

    def __init__(self, capacity: int = 200):
        self._buffer: deque[float] = deque(maxlen=capacity)

    def push(self, value: float) -> None:
        """Add a value to the history."""
        if not math.isnan(value) and not math.isinf(value):
            self._buffer.append(value)

    def percentile(self, pct: float) -> float:
        """Get the pct-th percentile (0-100) of stored values."""
        if not self._buffer:
            return 0.0
        return float(np.percentile(list(self._buffer), pct))

    def max(self) -> float:
        """Get the maximum stored value."""
        if not self._buffer:
            return 0.0
        return max(self._buffer)

    def mean(self) -> float:
        """Get the mean stored value."""
        if not self._buffer:
            return 0.0
        return sum(self._buffer) / len(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


def noise_gate(
    value: float, threshold: float = 0.01, floor: float = 0.0
) -> float:
    """Apply noise gate: values below threshold are clamped to floor."""
    return floor if value < threshold else value


def limit_delta(
    current: float, target: float, max_delta: float
) -> float:
    """Limit the change between current and target to max_delta."""
    delta = target - current
    if abs(delta) <= max_delta:
        return target
    return current + math.copysign(max_delta, delta)


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp a value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    """Safe division: returns default if denominator is zero or NaN."""
    if b == 0 or math.isnan(b) or math.isinf(b):
        return default
    return a / b
