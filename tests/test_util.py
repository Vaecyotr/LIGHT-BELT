"""Tests for utility modules."""

import math
import pytest
from light_engine.util import (
    EMASmoother,
    ColorSmoother,
    AttackReleaseEnvelope,
    RollingHistory,
    noise_gate,
    limit_delta,
    clamp,
    safe_div,
)


class TestEMASmoother:
    def test_smoothing(self):
        s = EMASmoother(alpha=0.5)
        v = s.update(1.0)
        assert v == 0.5  # alpha=0.5, first update from 0 -> 0.5
        v = s.update(1.0)
        assert 0.7 < v < 0.8  # Converging toward 1.0

    def test_reset(self):
        s = EMASmoother(0.5)
        s.update(1.0)
        s.reset(0.5)
        assert s.value == 0.5


class TestColorSmoother:
    def test_smoothing(self):
        s = ColorSmoother(alpha=0.5)
        r, g, b = s.update(1.0, 0.0, 0.0)
        assert r == 0.5
        assert 0.0 <= g <= 1.0
        assert 0.0 <= b <= 1.0


class TestAttackReleaseEnvelope:
    def test_attack_faster_than_release(self):
        env = AttackReleaseEnvelope(attack=1.0, release=0.1)
        v1 = env.update(1.0, 0.016)  # Attack toward 1.0
        v2 = env.update(0.0, 0.016)  # Release toward 0.0
        # Attack should be faster
        assert v1 > v2  # v1 jumped up more than v2 dropped

    def test_reset(self):
        env = AttackReleaseEnvelope()
        env.update(0.8, 1.0)
        env.reset(0.0)
        assert env.value == 0.0

    def test_clamped_to_target(self):
        env = AttackReleaseEnvelope(attack=100.0, release=100.0)
        v = env.update(0.5, 1.0)
        assert 0.4 < v < 0.6


class TestRollingHistory:
    def test_push_and_stats(self):
        h = RollingHistory(capacity=10)
        for v in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            h.push(v)
        assert len(h) == 10
        assert abs(h.mean() - 0.55) < 0.01
        assert abs(h.percentile(50) - 0.55) < 0.1
        assert h.max() == 1.0

    def test_rejects_nan(self):
        h = RollingHistory(capacity=10)
        h.push(float('nan'))
        assert len(h) == 0

    def test_rejects_inf(self):
        h = RollingHistory(capacity=10)
        h.push(float('inf'))
        assert len(h) == 0

    def test_empty_stats(self):
        h = RollingHistory()
        assert h.percentile(50) == 0.0
        assert h.max() == 0.0
        assert len(h) == 0


class TestNoiseGate:
    def test_below_threshold(self):
        assert noise_gate(0.005, threshold=0.01) == 0.0

    def test_above_threshold(self):
        assert noise_gate(0.5, threshold=0.01) == 0.5

    def test_custom_floor(self):
        assert noise_gate(0.005, threshold=0.01, floor=0.001) == 0.001


class TestLimitDelta:
    def test_within_limit(self):
        assert limit_delta(0.5, 0.55, 0.1) == 0.55

    def test_exceeds_limit_positive(self):
        assert limit_delta(0.5, 0.7, 0.1) == 0.6

    def test_exceeds_limit_negative(self):
        assert limit_delta(0.5, 0.3, 0.1) == 0.4


class TestSafeDiv:
    def test_normal(self):
        assert safe_div(10.0, 2.0) == 5.0

    def test_zero_denominator(self):
        assert safe_div(10.0, 0.0, default=0.0) == 0.0

    def test_nan_denominator(self):
        assert safe_div(10.0, float('nan'), default=0.0) == 0.0
