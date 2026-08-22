"""Phase 34 motion-clock contracts for stateful/complex moving effects."""

from __future__ import annotations

import pytest

from light_engine.effects.comet import CometEffect
from light_engine.effects.heat_fire import HeatFireEffect
from light_engine.effects.history_stream import HistoryStreamEffect
from light_engine.effects.onset_ripple import OnsetRippleEffect
from light_engine.models import AudioFeatures, EffectContext
from light_engine.motion import MotionInterval


def _context(
    *,
    cue_time: float,
    previous_cue_time: float,
    motion_time: float,
    previous_motion_time: float,
    params: dict[str, object],
    speed: float = 1.0,
    delta_time: float = 1.0,
    audio: AudioFeatures | None = None,
    pixel_count: int = 12,
) -> EffectContext:
    return EffectContext(
        timestamp=cue_time,
        delta_time=delta_time,
        sequence=1,
        speed=speed,
        audio_features=audio,
        motion=MotionInterval(
            previous_motion_time=previous_motion_time,
            motion_time=motion_time,
            previous_cue_time=previous_cue_time,
            cue_time=cue_time,
        ),
        mode_parameters={
            "cue_local_time": cue_time,
            "strip_defs": ({"id": "path", "pixel_count": pixel_count},),
            "zone_defs": (),
            **params,
        },
    )


def _lit_indices(frame) -> list[int]:
    return [
        index
        for index, pixel in enumerate(frame.strips[0].pixels)
        if max(pixel) > 0.0
    ]


def _direct_context(
    cue_time: float,
    *,
    params: dict[str, object],
    speed: float = 2.0,
    audio: AudioFeatures | None = None,
    pixel_count: int = 12,
) -> EffectContext:
    return EffectContext(
        timestamp=cue_time,
        delta_time=max(cue_time, 0.1),
        sequence=1,
        speed=speed,
        audio_features=audio,
        mode_parameters={
            "cue_local_time": cue_time,
            "strip_defs": ({"id": "path", "pixel_count": pixel_count},),
            "zone_defs": (),
            **params,
        },
    )


def test_constant_motion_matches_preclock_absolute_time_equivalence() -> None:
    cue_time = 1.5
    motion_ctx = lambda params, audio=None: _context(
        cue_time=cue_time,
        previous_cue_time=0.0,
        motion_time=cue_time * 2.0,
        previous_motion_time=0.0,
        params=params,
        speed=2.0,
        delta_time=cue_time,
        audio=audio,
    )

    history_params = {"steps_per_second": 3.0, "color": (0.4, 0.2, 0.1)}
    assert HistoryStreamEffect().process(motion_ctx(history_params)) == (
        HistoryStreamEffect().process(
            _direct_context(cue_time, params=history_params)
        )
    )

    heat_params = {
        "cooling_per_second": 0.4,
        "spark_rate": 30.0,
        "spark_strength": 0.7,
        "diffusion": 0.25,
    }
    assert HeatFireEffect(seed=9).process(motion_ctx(heat_params)) == (
        HeatFireEffect(seed=9).process(
            _direct_context(cue_time, params=heat_params)
        )
    )

    comet_params = {
        "speed": 1.7,
        "tail_length": 0.0,
        "decay": 0.0,
        "count": 3,
        "phase_spacing": 0.2,
        "color": (0.5, 0.2, 0.1),
    }
    assert CometEffect().process(motion_ctx(comet_params)) == (
        CometEffect().process(_direct_context(cue_time, params=comet_params))
    )

    ripple_params = {
        "wave_speed_pps": 1.2,
        "wave_width_px": 2.0,
        "decay_seconds": 5.0,
    }
    trigger = AudioFeatures(timestamp=0.0, peak=True, loudness=1.0, silence=False)
    quiet = AudioFeatures(timestamp=cue_time, peak=False)
    motion_ripple = OnsetRippleEffect(seed=4)
    direct_ripple = OnsetRippleEffect(seed=4)
    motion_ripple.process(
        _context(
            cue_time=0.0,
            previous_cue_time=0.0,
            motion_time=0.0,
            previous_motion_time=0.0,
            params=ripple_params,
            speed=2.0,
            audio=trigger,
        )
    )
    direct_ripple.process(
        _direct_context(0.0, params=ripple_params, audio=trigger)
    )
    assert motion_ripple.process(motion_ctx(ripple_params, quiet)) == (
        direct_ripple.process(
            _direct_context(cue_time, params=ripple_params, audio=quiet)
        )
    )


def test_history_dynamic_down_up_pause_and_resume_advance_motion_steps_only() -> None:
    effect = HistoryStreamEffect()
    params = {"steps_per_second": 2.0, "color": (0.2, 0.0, 0.0)}
    effect.process(
        _context(
            cue_time=0.0,
            previous_cue_time=0.0,
            motion_time=0.0,
            previous_motion_time=0.0,
            params=params,
            speed=9.0,
            pixel_count=7,
        )
    )
    fast = effect.process(
        _context(
            cue_time=1.0,
            previous_cue_time=0.0,
            motion_time=2.0,
            previous_motion_time=0.0,
            params={**params, "color": (0.4, 0.0, 0.0)},
            speed=0.01,
            pixel_count=7,
        )
    )
    paused = effect.process(
        _context(
            cue_time=3.0,
            previous_cue_time=1.0,
            motion_time=2.0,
            previous_motion_time=2.0,
            params={**params, "color": (0.8, 0.0, 0.0)},
            speed=5.0,
            pixel_count=7,
        )
    )
    resumed = effect.process(
        _context(
            cue_time=4.0,
            previous_cue_time=3.0,
            motion_time=2.5,
            previous_motion_time=2.0,
            params={**params, "color": (1.0, 0.0, 0.0)},
            speed=5.0,
            pixel_count=7,
        )
    )

    assert effect._last_steps["path"] == 5
    assert paused.strips[0].pixels == fast.strips[0].pixels
    assert resumed.strips[0].pixels[0] == (1.0, 0.0, 0.0)
    assert resumed.strips[0].pixels[1:5] == [(0.4, 0.0, 0.0)] * 4


def test_history_timeline_samples_real_wall_crossings_and_is_vfr_equivalent() -> None:
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (0.0, 0.0, 0.0)},
            {"time": 2.0, "color": (1.0, 0.0, 0.0)},
        ),
    }
    params = {
        "steps_per_second": 2.0,
        "color": (0.0, 0.0, 0.0),
        "color_timeline": timeline,
    }

    def render(intervals: list[tuple[float, float, float, float]]):
        effect = HistoryStreamEffect()
        frame = None
        for previous_cue, cue, previous_motion, motion in intervals:
            frame = effect.process(
                _context(
                    cue_time=cue,
                    previous_cue_time=previous_cue,
                    motion_time=motion,
                    previous_motion_time=previous_motion,
                    params=params,
                    pixel_count=5,
                )
            )
        assert frame is not None
        return frame

    coarse = render([(0.0, 0.0, 0.0, 0.0), (0.0, 2.0, 0.0, 1.0)])
    fine = render(
        [
            (0.0, 0.0, 0.0, 0.0),
            (0.0, 0.5, 0.0, 0.25),
            (0.5, 1.0, 0.25, 0.5),
            (1.0, 1.5, 0.5, 0.75),
            (1.5, 2.0, 0.75, 1.0),
        ]
    )

    assert coarse == fine
    assert coarse.strips[0].pixels[:3] == pytest.approx(
        [(1.0, 0.0, 0.0), (0.5, 0.0, 0.0), (0.0, 0.0, 0.0)]
    )


def test_history_live_scalar_uses_current_sample_for_all_crossed_steps() -> None:
    effect = HistoryStreamEffect()
    params = {
        "steps_per_second": 2.0,
        "color": (1.0, 0.0, 0.0),
        "sample_gain_source": "audio.loudness",
    }
    frame = effect.process(
        _context(
            cue_time=2.0,
            previous_cue_time=0.0,
            motion_time=1.0,
            previous_motion_time=0.0,
            params=params,
            audio=AudioFeatures(timestamp=2.0, loudness=0.25),
            pixel_count=3,
        )
    )
    assert frame.strips[0].pixels == [(0.25, 0.0, 0.0)] * 3


def test_heat_uses_integrated_motion_ticks_without_rollback_and_replays() -> None:
    params = {
        "cooling_per_second": 0.3,
        "spark_rate": 60.0,
        "spark_strength": 0.8,
        "diffusion": 0.4,
    }
    schedule = (
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 2.0),
        (1.0, 2.0, 2.0, 2.25),
        (2.0, 4.0, 2.25, 2.25),
        (4.0, 5.0, 2.25, 3.25),
    )

    def play(effect: HeatFireEffect):
        frames = []
        for previous_cue, cue, previous_motion, motion in schedule:
            frames.append(
                effect.process(
                    _context(
                        cue_time=cue,
                        previous_cue_time=previous_cue,
                        motion_time=motion,
                        previous_motion_time=previous_motion,
                        params=params,
                        speed=10.0,
                        pixel_count=8,
                    )
                )
            )
        return frames

    effect = HeatFireEffect(seed=73)
    first = play(effect)
    assert first[3].strips == first[2].strips
    assert effect._last_target_tick == int(3.25 * effect.STEP_HZ)
    effect.reset()
    assert play(effect) == first


def test_ripple_propagates_on_motion_age_but_decays_on_real_age() -> None:
    params = {
        "wave_speed_pps": 1.0,
        "wave_width_px": 2.0,
        "decay_seconds": 10.0,
        "color": (1.0, 0.0, 0.0),
    }
    effect = OnsetRippleEffect(seed=5)
    born = effect.process(
        _context(
            cue_time=0.0,
            previous_cue_time=0.0,
            motion_time=0.0,
            previous_motion_time=0.0,
            params=params,
            audio=AudioFeatures(timestamp=0.0, peak=True, loudness=1.0, silence=False),
            pixel_count=8,
        )
    )
    paused = effect.process(
        _context(
            cue_time=2.0,
            previous_cue_time=0.0,
            motion_time=0.0,
            previous_motion_time=0.0,
            params=params,
            speed=10.0,
            audio=AudioFeatures(timestamp=2.0, peak=False, loudness=0.0),
            pixel_count=8,
        )
    )
    resumed = effect.process(
        _context(
            cue_time=3.0,
            previous_cue_time=2.0,
            motion_time=1.0,
            previous_motion_time=0.0,
            params=params,
            speed=0.01,
            audio=AudioFeatures(timestamp=3.0, peak=False, loudness=0.0),
            pixel_count=8,
        )
    )

    assert effect._waves[0].born == 0.0
    assert effect._waves[0].born_motion == 0.0
    assert _lit_indices(paused) == _lit_indices(born)
    assert max(paused.strips[0].pixels[0]) < max(born.strips[0].pixels[0])
    assert resumed.strips[0].pixels[2][0] > born.strips[0].pixels[2][0]


def test_ripple_random_bidirectional_wrap_replays_with_motion_clock() -> None:
    params = {
        "event_origin": "random",
        "propagation": "bidirectional",
        "wrap": True,
        "wave_speed_pps": 2.0,
        "wave_width_px": 1.5,
    }

    def render(effect: OnsetRippleEffect):
        effect.process(
            _context(
                cue_time=0.0,
                previous_cue_time=0.0,
                motion_time=0.0,
                previous_motion_time=0.0,
                params={**params, "cue_id": "random-wave"},
                    audio=AudioFeatures(
                        timestamp=0.0,
                        peak=True,
                        loudness=1.0,
                        silence=False,
                    ),
                pixel_count=9,
            )
        )
        return effect.process(
            _context(
                cue_time=1.0,
                previous_cue_time=0.0,
                motion_time=0.5,
                previous_motion_time=0.0,
                params={**params, "cue_id": "random-wave"},
                audio=AudioFeatures(timestamp=1.0, peak=False),
                pixel_count=9,
            )
        )

    left = OnsetRippleEffect(seed=88)
    right = OnsetRippleEffect(seed=88)
    assert render(left) == render(right)
    assert left._waves[0].origin == right._waves[0].origin
    assert len(left._waves) <= left.MAX_WAVES


def test_comet_multi_emitters_follow_motion_distance_without_speed_teleport() -> None:
    params = {
        "speed": 1.0,
        "tail_length": 0.0,
        "decay": 0.0,
        "count": 2,
        "phase_spacing": 0.0,
        "trajectory": "wrap",
        "color": (1.0, 0.0, 0.0),
    }
    effect = CometEffect()
    positions = []
    for previous_cue, cue, previous_motion, motion, common_speed in (
        (0.0, 1.0, 0.0, 2.0, 2.0),
        (1.0, 2.0, 2.0, 2.5, 0.5),
        (2.0, 3.0, 2.5, 2.5, 0.0),
        (3.0, 4.0, 2.5, 3.5, 1.0),
    ):
        frame = effect.process(
            _context(
                cue_time=cue,
                previous_cue_time=previous_cue,
                motion_time=motion,
                previous_motion_time=previous_motion,
                params=params,
                speed=common_speed,
            )
        )
        positions.append(_lit_indices(frame))

    assert positions == [[2], [2], [2], [3]]


def test_comet_legacy_single_emitter_ignores_motion_interval() -> None:
    params = {
        "speed": 2.0,
        "tail_length": 0.4,
        "decay": 0.8,
        "count": 1,
        "trajectory": "wrap",
        "color": (1.0, 0.0, 0.0),
    }
    effect = CometEffect()
    effect.process(
        _context(
            cue_time=1.0,
            previous_cue_time=0.0,
            motion_time=50.0,
            previous_motion_time=0.0,
            params=params,
            speed=1.5,
            delta_time=0.25,
        )
    )
    assert effect._positions["path"] == pytest.approx(0.75)
