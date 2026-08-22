"""Phase 34 isolated cue-level common-motion clock contracts."""

from __future__ import annotations

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import (
    AudioFeatures,
    DigitalStrip,
    EffectContext,
    MusicControlState,
    PixelFrame,
)
from light_engine.motion import CueMotionClock, MotionInterval
from light_engine.show import (
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    CueBranchSpec,
    CueRenderJob,
    EffectSpec,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
)


class _CaptureEffect(BaseEffect):
    def __init__(self, name: str = "capture") -> None:
        super().__init__(name)
        self.contexts: list[EffectContext] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contexts.append(ctx)
        strips = [
            DigitalStrip(
                strip_id=definition["id"],
                pixel_count=definition["pixel_count"],
                pixels=[(0.0, 0.0, 0.0)] * definition["pixel_count"],
            )
            for definition in ctx.mode_parameters["strip_defs"]
        ]
        return PixelFrame(timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips)


def _resolver() -> TargetResolver:
    return TargetResolver((), (ZoneDef(id="strip", pixel_count=2),))


def _cue(
    *,
    effect: EffectSpec | None = None,
    audio_modulation: AudioModulationSpec | None = None,
    start: float = 0.0,
    end: float = 20.0,
) -> Cue:
    return Cue(
        id="motion",
        start=start,
        end=end,
        target=TargetSelector("digital_strip", id="strip"),
        effect=effect or EffectSpec(mode="fixed", id="capture"),
        audio_modulation=audio_modulation,
    )


def _ctx(
    timestamp: float,
    speed: float,
    *,
    sequence: int = 1,
    delta_time: float = 1.0,
    rms: float | None = None,
    music_state: MusicControlState | None = None,
) -> EffectContext:
    audio = None
    if rms is not None:
        audio = AudioFeatures(timestamp=timestamp, rms=rms, silence=False)
    return EffectContext(
        timestamp=timestamp,
        delta_time=delta_time,
        sequence=sequence,
        speed=speed,
        audio_features=audio,
        music_control_state=music_state,
    )


def _rendered_motion(job: CueRenderJob, capture: _CaptureEffect, ctx: EffectContext) -> MotionInterval:
    job.render(ctx)
    motion = capture.contexts[-1].motion
    assert motion is not None
    return motion


@pytest.mark.parametrize("speed", [0.0, 0.5, 1.0, 2.0])
def test_constant_speed_equals_cue_local_time_times_speed(speed: float) -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(_cue(), 0, _resolver(), effect=capture)

    for sequence, timestamp in enumerate((0.0, 0.25, 1.0, 3.0), start=1):
        motion = _rendered_motion(
            job,
            capture,
            _ctx(timestamp, speed, sequence=sequence, delta_time=0.25),
        )
        assert motion.motion_time == pytest.approx(timestamp * speed)


def test_speed_downshift_changes_slope_without_recomputing_phase() -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(_cue(), 0, _resolver(), effect=capture)

    samples = [
        _rendered_motion(job, capture, _ctx(0.0, 2.0)),
        _rendered_motion(job, capture, _ctx(1.0, 2.0)),
        _rendered_motion(job, capture, _ctx(2.0, 0.5)),
        _rendered_motion(job, capture, _ctx(3.0, 0.5)),
    ]

    assert [sample.motion_time for sample in samples] == pytest.approx([0.0, 2.0, 2.5, 3.0])
    assert all(a.motion_time <= b.motion_time for a, b in zip(samples, samples[1:]))


def test_zero_speed_freezes_then_resume_continues_from_frozen_phase() -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(_cue(), 0, _resolver(), effect=capture)

    motions = [
        _rendered_motion(job, capture, _ctx(timestamp, speed)).motion_time
        for timestamp, speed in ((0.0, 1.0), (1.0, 1.0), (2.0, 0.0), (4.0, 0.0), (5.0, 1.0))
    ]

    assert motions == pytest.approx([0.0, 1.0, 1.0, 1.0, 2.0])


def _audio_speed_modulation(*, smoothing_seconds: float) -> AudioModulationSpec:
    return AudioModulationSpec(
        speed=AudioModulationChannelSpec(
            source="audio.rms",
            amount=1.0,
            min_multiplier=0.0,
            max_multiplier=2.0,
            smoothing_seconds=smoothing_seconds,
        )
    )


def test_audio_speed_modulation_changes_motion_slope_only() -> None:
    capture = _CaptureEffect()
    cue = _cue(
        effect=EffectSpec(mode="fixed", id="capture", speed=0.5),
        audio_modulation=_audio_speed_modulation(smoothing_seconds=0.0),
    )
    job = CueRenderJob(cue, 0, _resolver(), effect=capture)

    motions = [
        _rendered_motion(job, capture, _ctx(timestamp, 2.0, rms=rms)).motion_time
        for timestamp, rms in ((0.0, 1.0), (1.0, 1.0), (2.0, 0.5), (3.0, 0.0))
    ]

    assert [ctx.speed for ctx in capture.contexts] == pytest.approx([2.0, 2.0, 1.0, 0.0])
    assert motions == pytest.approx([0.0, 2.0, 3.0, 3.0])


def test_smoothed_audio_speed_is_integrated_without_changing_smoothing_formula() -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(
        _cue(audio_modulation=_audio_speed_modulation(smoothing_seconds=2.0)),
        0,
        _resolver(),
        effect=capture,
    )

    first = _rendered_motion(job, capture, _ctx(0.0, 1.0, rms=1.0))
    second = _rendered_motion(job, capture, _ctx(1.0, 1.0, rms=1.0))
    third = _rendered_motion(job, capture, _ctx(2.0, 1.0, rms=0.0))

    assert [ctx.speed for ctx in capture.contexts] == pytest.approx([1.5, 1.75, 0.875])
    assert [first.motion_time, second.motion_time, third.motion_time] == pytest.approx(
        [0.0, 1.75, 2.625]
    )


def test_adaptive_selector_speed_changes_slope_without_resetting_clock() -> None:
    capture = _CaptureEffect()
    cue = _cue(
        effect=EffectSpec(
            mode="adaptive",
            speed=0.5,
            allowed={
                "silence": "capture",
                "transition": "capture",
                "flowing": "capture",
            },
            fallback="capture",
        )
    )
    job = CueRenderJob(cue, 0, _resolver(), effect=capture)
    states = (
        MusicControlState(timestamp=0.0, energy=0.02),
        MusicControlState(timestamp=1.0, energy=0.35, energy_trend=1.0),
        MusicControlState(timestamp=2.0, energy=0.35, energy_trend=-1.0),
    )

    motions = [
        _rendered_motion(
            job,
            capture,
            _ctx(state.timestamp, 9.0, music_state=state),
        ).motion_time
        for state in states
    ]

    assert [ctx.speed for ctx in capture.contexts] == pytest.approx([0.5, 0.75, 0.25])
    assert motions == pytest.approx([0.0, 0.75, 1.0])


def test_same_timestamp_returns_same_interval_and_does_not_advance_twice() -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(_cue(), 0, _resolver(), effect=capture)

    first = _rendered_motion(job, capture, _ctx(1.0, 1.0, sequence=1))
    repeated = _rendered_motion(job, capture, _ctx(1.0, 10.0, sequence=2))
    resumed = _rendered_motion(job, capture, _ctx(2.0, 1.0, sequence=3))

    assert repeated is first
    assert first.motion_time == pytest.approx(1.0)
    assert resumed.motion_time == pytest.approx(2.0)


def test_reset_and_replay_reconstructs_motion_clock() -> None:
    capture = _CaptureEffect()
    job = CueRenderJob(_cue(), 0, _resolver(), effect=capture)
    schedule = ((0.0, 1.0), (1.0, 2.0), (2.0, 0.0), (3.0, 0.5))

    first = [
        _rendered_motion(job, capture, _ctx(timestamp, speed)).motion_time
        for timestamp, speed in schedule
    ]
    job.reset()
    replay = [
        _rendered_motion(job, capture, _ctx(timestamp, speed)).motion_time
        for timestamp, speed in schedule
    ]

    assert replay == pytest.approx(first)


def test_late_released_branch_receives_parent_dynamic_motion_phase() -> None:
    path = VirtualPathSpec(
        id="path",
        targets=(
            TargetSelector("digital_strip", id="a"),
            TargetSelector("digital_strip", id="b"),
        ),
    )
    resolver = TargetResolver(
        (),
        (ZoneDef(id="a", pixel_count=1), ZoneDef(id="b", pixel_count=1), ZoneDef(id="release", pixel_count=1)),
    )
    resolver.register_authored_paths((path,))
    cue = Cue(
        id="branched",
        start=0.0,
        end=4.0,
        target=TargetSelector("virtual_path", id="path"),
        effect=EffectSpec(mode="fixed", id="capture"),
        branches=(
            CueBranchSpec(
                path_id="path",
                after_target_id="a",
                target=TargetSelector("digital_strip", id="release"),
            ),
        ),
    )
    parent_capture = _CaptureEffect()
    branch_captures: list[_CaptureEffect] = []

    def factory(name: str) -> _CaptureEffect:
        effect = _CaptureEffect(name)
        branch_captures.append(effect)
        return effect

    job = CueRenderJob(cue, 0, resolver, effect=parent_capture, effect_factory=factory)
    for timestamp, speed in ((0.0, 1.0), (1.0, 2.0)):
        job.render(_ctx(timestamp, speed))
        assert job.render_branches(_ctx(timestamp, speed)) == ()

    release_ctx = _ctx(2.0, 0.5)
    parent_motion = _rendered_motion(job, parent_capture, release_ctx)
    contributions = job.render_branches(release_ctx)

    assert len(contributions) == 1
    assert len(branch_captures) == 1
    branch_motion = branch_captures[0].contexts[-1].motion
    assert branch_motion is parent_motion
    assert branch_motion.motion_time == pytest.approx(2.5)
    assert branch_motion.motion_time != pytest.approx(2.0 * 0.5)


def test_fixed_cue_first_rendered_late_preserves_constant_speed_equivalence() -> None:
    capture = _CaptureEffect()
    cue = _cue(
        effect=EffectSpec(mode="fixed", id="capture", speed=0.5),
        start=5.0,
        end=20.0,
    )
    job = CueRenderJob(cue, 0, _resolver(), effect=capture)

    motion = _rendered_motion(job, capture, _ctx(8.0, 2.0))

    assert motion.previous_cue_time == 0.0
    assert motion.cue_time == 3.0
    assert motion.motion_time == pytest.approx(3.0)


@pytest.mark.parametrize(
    ("cue_time", "speed"),
    [(float("nan"), 1.0), (float("inf"), 1.0), (1.0, float("nan")), (1.0, float("inf")), (1.0, -0.1)],
)
def test_invalid_or_nonfinite_clock_inputs_fail_explicitly(cue_time: float, speed: float) -> None:
    with pytest.raises(ValueError, match="finite number >= 0"):
        CueMotionClock().advance(cue_time, speed)


def test_nonfinite_integrated_result_and_backward_time_fail_explicitly() -> None:
    clock = CueMotionClock()
    with pytest.raises(ValueError, match="remain finite"):
        clock.advance(1e308, 1e308)

    clock = CueMotionClock()
    clock.advance(1.0, 1.0)
    with pytest.raises(RuntimeError, match="reset and replay"):
        clock.advance(0.5, 1.0)
