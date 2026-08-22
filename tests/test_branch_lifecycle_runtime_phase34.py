"""Phase 34 branch-lifecycle runtime scheduling contracts."""

from __future__ import annotations

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import DigitalStrip, EffectContext, PixelFrame
from light_engine.show import (
    Cue,
    CueBranchSpec,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
    black_base_frame,
)


class _CountingEffect(BaseEffect):
    """Stateful probe whose current render count is directly observable."""

    def __init__(self) -> None:
        super().__init__("counting")
        self.contexts: list[EffectContext] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contexts.append(ctx)
        value = min(1.0, len(self.contexts) / 10.0)
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=definition["id"],
                    pixel_count=definition["pixel_count"],
                    pixels=[(value, 0.0, 0.0)] * definition["pixel_count"],
                )
                for definition in ctx.mode_parameters["strip_defs"]
            ],
        )


def _runtime(
    *lifecycles: str | None,
    release_after: str = "a",
) -> tuple[ShowRuntime, tuple[ZoneDef, ...], list[_CountingEffect]]:
    path = VirtualPathSpec(
        id="path",
        targets=(
            TargetSelector("digital_strip", id="a"),
            TargetSelector("digital_strip", id="b"),
        ),
    )
    branches = tuple(
        CueBranchSpec(
            path_id="path",
            after_target_id=release_after,
            target=TargetSelector("digital_strip", id=f"branch_{index}"),
            **({} if lifecycle is None else {"lifecycle": lifecycle}),
        )
        for index, lifecycle in enumerate(lifecycles)
    )
    cue = Cue(
        id="branched",
        start=0.0,
        end=4.0,
        target=TargetSelector("virtual_path", id="path"),
        effect=EffectSpec(mode="fixed", id="counting"),
        branches=branches,
    )
    show = ShowDefinition(
        schema_version=2,
        id="branch-lifecycle-runtime",
        duration=4.0,
        cues=(cue,),
        virtual_paths=(path,),
    )
    strips = (
        ZoneDef(id="a", pixel_count=1),
        ZoneDef(id="b", pixel_count=1),
        *(ZoneDef(id=f"branch_{index}", pixel_count=1) for index in range(len(lifecycles))),
    )
    effects: list[_CountingEffect] = []

    def factory(_name: str) -> _CountingEffect:
        effect = _CountingEffect()
        effects.append(effect)
        return effect

    return ShowRuntime(show, TargetResolver((), strips), effect_factory=factory), strips, effects


def _render(runtime: ShowRuntime, strips: tuple[ZoneDef, ...], timestamp: float, sequence: int) -> PixelFrame:
    base = black_base_frame(
        timestamp=timestamp,
        sequence=sequence,
        analog_zones=(),
        digital_strips=strips,
    )
    return runtime.render(
        EffectContext(timestamp=timestamp, delta_time=1.0, sequence=sequence),
        base,
    )


def _pixel(frame: PixelFrame, strip_id: str) -> tuple[float, float, float]:
    return next(strip for strip in frame.strips if strip.strip_id == strip_id).pixels[0]


def test_pre_roll_advances_while_hidden_and_shares_parent_motion_interval() -> None:
    runtime, strips, effects = _runtime("pre_roll")

    frame = _render(runtime, strips, 0.0, 1)
    frame = _render(runtime, strips, 1.0, 2)

    assert len(effects) == 2
    parent, branch = effects
    assert len(branch.contexts) == 2
    assert branch.contexts[-1].motion is parent.contexts[-1].motion
    assert _pixel(frame, "branch_0") == (0.0, 0.0, 0.0)


def test_omitted_lifecycle_defaults_to_no_processing_before_release() -> None:
    runtime, strips, effects = _runtime(None)

    _render(runtime, strips, 0.0, 1)
    frame = _render(runtime, strips, 1.0, 2)

    assert len(effects[1].contexts) == 0
    assert _pixel(frame, "branch_0") == (0.0, 0.0, 0.0)

    released = _render(runtime, strips, 2.0, 3)
    assert len(effects[1].contexts) == 1
    assert _pixel(released, "branch_0") == pytest.approx((0.1, 0.0, 0.0))


def test_pre_roll_release_frame_processes_once_and_reveals_current_state() -> None:
    runtime, strips, effects = _runtime("pre_roll")
    _render(runtime, strips, 0.0, 1)
    _render(runtime, strips, 1.0, 2)

    released = _render(runtime, strips, 2.0, 3)

    assert len(effects[1].contexts) == 3
    assert _pixel(released, "branch_0") == pytest.approx((0.3, 0.0, 0.0))


def test_pre_roll_reset_and_replay_reconstructs_hidden_state() -> None:
    runtime, strips, effects = _runtime("pre_roll")
    schedule = (0.0, 1.0, 2.0)
    first = [_pixel(_render(runtime, strips, timestamp, index), "branch_0") for index, timestamp in enumerate(schedule, 1)]
    first_branch = effects[1]

    runtime.reset()
    replay = [_pixel(_render(runtime, strips, timestamp, index), "branch_0") for index, timestamp in enumerate(schedule, 1)]

    assert effects[3] is not first_branch
    assert len(effects[3].contexts) == 3
    assert replay == pytest.approx(first)


def test_pre_roll_branch_that_never_releases_stays_hidden_but_advances() -> None:
    runtime, strips, effects = _runtime("pre_roll", release_after="b")

    frames = [
        _render(runtime, strips, timestamp, index)
        for index, timestamp in enumerate((0.0, 1.0, 2.0, 3.0), 1)
    ]

    assert len(effects[1].contexts) == 4
    assert all(_pixel(frame, "branch_0") == (0.0, 0.0, 0.0) for frame in frames)


def test_multiple_pre_roll_branches_advance_hidden_and_reveal_once_each() -> None:
    runtime, strips, effects = _runtime("pre_roll", "pre_roll")
    _render(runtime, strips, 0.0, 1)
    hidden = _render(runtime, strips, 1.0, 2)

    assert [len(effect.contexts) for effect in effects[1:]] == [2, 2]
    assert _pixel(hidden, "branch_0") == _pixel(hidden, "branch_1") == (0.0, 0.0, 0.0)

    released = _render(runtime, strips, 2.0, 3)
    assert [len(effect.contexts) for effect in effects[1:]] == [3, 3]
    assert _pixel(released, "branch_0") == pytest.approx((0.3, 0.0, 0.0))
    assert _pixel(released, "branch_1") == pytest.approx((0.3, 0.0, 0.0))


def test_mixed_branch_lifecycles_reveal_continuous_and_fresh_state_together() -> None:
    runtime, strips, effects = _runtime("pre_roll", "start_on_release")
    _render(runtime, strips, 0.0, 1)
    _render(runtime, strips, 1.0, 2)

    assert [len(effect.contexts) for effect in effects[1:]] == [2, 0]

    released = _render(runtime, strips, 2.0, 3)
    assert [len(effect.contexts) for effect in effects[1:]] == [3, 1]
    assert _pixel(released, "branch_0") == pytest.approx((0.3, 0.0, 0.0))
    assert _pixel(released, "branch_1") == pytest.approx((0.1, 0.0, 0.0))
