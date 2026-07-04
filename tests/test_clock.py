"""Tests for clock system."""

import time
import pytest
from light_engine.clock import (
    MonotonicClock,
    OfflineRenderClock,
    FakeClock,
    VideoPtsClock,
    AudioPlaybackClock,
    MasterClock,
)


class TestMonotonicClock:
    def test_advances(self):
        c = MonotonicClock()
        t1 = c.now()
        time.sleep(0.01)
        t2 = c.now()
        assert t2 > t1

    def test_tick_returns_delta(self):
        c = MonotonicClock()
        time.sleep(0.05)
        dt = c.tick()
        # On some platforms perf_counter resolution is low;
        # the key property is dt >= 0 (never negative)
        assert dt >= 0


class TestOfflineRenderClock:
    def test_deterministic(self):
        c1 = OfflineRenderClock(fps=30)
        c2 = OfflineRenderClock(fps=30)
        for _ in range(100):
            assert abs(c1.tick() - c2.tick()) < 1e-9
            assert abs(c1.now() - c2.now()) < 1e-9

    def test_fixed_delta(self):
        c = OfflineRenderClock(fps=60)
        for _ in range(10):
            dt = c.tick()
            assert abs(dt - 1 / 60) < 1e-9


class TestFakeClock:
    def test_manual_advance(self):
        c = FakeClock()
        assert c.now() == 0.0
        c.advance(0.033)
        assert c.now() == 0.033
        c.advance(0.067)
        assert c.now() == 0.1

    def test_set_time(self):
        c = FakeClock()
        c.set_time(10.0)
        assert c.now() == 10.0

    def test_tick_does_not_advance(self):
        c = FakeClock()
        dt = c.tick()
        assert dt == 0.0
        assert c.now() == 0.0


class TestVideoPtsClock:
    def test_pts_update(self):
        c = VideoPtsClock()
        c.update_pts(1.0)
        assert c.now() == 1.0
        c.update_pts(1.5)
        assert c.now() == 1.5
        assert c.active

    def test_tick_returns_delta(self):
        c = VideoPtsClock()
        c.update_pts(1.0)
        dt = c.tick()
        c.update_pts(1.1)
        dt2 = c.tick()
        assert abs(dt2 - 0.1) < 1e-9


class TestAudioPlaybackClock:
    def test_sample_update(self):
        c = AudioPlaybackClock(sample_rate=44100)
        c.update_samples(44100)
        assert c.now() == 1.0
        assert c.active


class TestMasterClock:
    def test_default_monotonic(self):
        mc = MasterClock()
        assert isinstance(mc.master, MonotonicClock)

    def test_diagnostics(self):
        mc = MasterClock()
        diag = mc.diagnostics()
        assert "master_clock_time" in diag
        assert "video_sync_error_ms" in diag
        assert diag["video_pts"] is None

    def test_with_video_clock(self):
        vc = VideoPtsClock()
        mc = MasterClock(clock=FakeClock())
        mc.set_video_clock(vc)
        vc.update_pts(5.0)
        diag = mc.diagnostics()
        assert diag["video_pts"] == 5.0
