"""Phase 34 pre-roll output, release, and virtual-path isolation contracts."""

from __future__ import annotations

import pytest

from light_engine.clock import Clock
from light_engine.config import Config
from light_engine.effects.base import BaseEffect
from light_engine.engine import Engine
from light_engine.mapping import ZoneDef
from light_engine.mapping.physical import PhysicalFrame
from light_engine.models import DigitalStrip, EffectContext, PixelFrame
from light_engine.outputs import NullOutput
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


class _SolidCountingEffect(BaseEffect):
    """Observable stateful effect that paints only its resolved target."""

    def __init__(self) -> None:
        super().__init__("solid-counting")
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


def _show(
    *,
    path_targets: tuple[str, str] = ("path_a", "path_b"),
    branch_targets: tuple[tuple[str, ...], ...] = (("branch_a",),),
    lifecycle: str = "pre_roll",
    duration: float = 4.0,
) -> ShowDefinition:
    path = VirtualPathSpec(
        id="flow",
        targets=tuple(
            TargetSelector("digital_strip", id=strip_id)
            for strip_id in path_targets
        ),
        origin="start",
    )
    cue = Cue(
        id="branched",
        start=0.0,
        end=duration,
        target=TargetSelector("virtual_path", id="flow"),
        effect=EffectSpec(mode="fixed", id="solid-counting"),
        branches=tuple(
            CueBranchSpec(
                path_id="flow",
                after_target_id=path_targets[0],
                target=TargetSelector("digital_set", ids=target_ids),
                origin="end",
                lifecycle=lifecycle,
            )
            for target_ids in branch_targets
        ),
    )
    return ShowDefinition(
        schema_version=2,
        id=f"branch-output-isolation-{lifecycle}",
        duration=duration,
        cues=(cue,),
        virtual_paths=(path,),
    )


def _runtime(
    show: ShowDefinition,
    strips: tuple[ZoneDef, ...],
) -> tuple[ShowRuntime, list[_SolidCountingEffect]]:
    effects: list[_SolidCountingEffect] = []

    def factory(_name: str) -> _SolidCountingEffect:
        effect = _SolidCountingEffect()
        effects.append(effect)
        return effect

    return ShowRuntime(show, TargetResolver((), strips), effect_factory=factory), effects


def _render(
    runtime: ShowRuntime,
    strips: tuple[ZoneDef, ...],
    *,
    timestamp: float,
    sequence: int,
) -> PixelFrame:
    return runtime.render(
        EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence),
        black_base_frame(
            timestamp=timestamp,
            sequence=sequence,
            analog_zones=(),
            digital_strips=strips,
        ),
    )


def _logical_pixels(frame: PixelFrame, strip_id: str) -> list[tuple[float, float, float]]:
    return next(strip.pixels for strip in frame.strips if strip.strip_id == strip_id)


def test_multiple_pre_roll_targets_advance_without_leaking_into_composition() -> None:
    strips = tuple(
        ZoneDef(id=strip_id, pixel_count=1)
        for strip_id in ("path_a", "path_b", "branch_a", "branch_b", "branch_c")
    )
    show = _show(branch_targets=(("branch_a", "branch_b"), ("branch_c",)))
    runtime, effects = _runtime(show, strips)

    first = _render(runtime, strips, timestamp=0.0, sequence=1)
    hidden = _render(runtime, strips, timestamp=1.0, sequence=2)

    assert [len(effect.contexts) for effect in effects] == [2, 2, 2]
    assert any(pixel != (0.0, 0.0, 0.0) for pixel in _logical_pixels(hidden, "path_a"))
    for frame in (first, hidden):
        for strip_id in ("branch_a", "branch_b", "branch_c"):
            assert _logical_pixels(frame, strip_id) == [(0.0, 0.0, 0.0)]

    released = _render(runtime, strips, timestamp=2.0, sequence=3)

    # Each branch processes exactly once on the release frame, and only that
    # one current contribution becomes visible for every target in its set.
    assert [len(effect.contexts) for effect in effects] == [3, 3, 3]
    for strip_id in ("branch_a", "branch_b", "branch_c"):
        assert _logical_pixels(released, strip_id) == pytest.approx([(0.3, 0.0, 0.0)])


def test_lifecycle_is_orthogonal_to_virtual_path_and_release_predicate() -> None:
    strips = tuple(
        ZoneDef(id=strip_id, pixel_count=1)
        for strip_id in ("path_a", "path_b", "branch_a")
    )
    pre_show = _show(lifecycle="pre_roll")
    fresh_show = _show(lifecycle="start_on_release")
    pre_runtime, pre_effects = _runtime(pre_show, strips)
    fresh_runtime, fresh_effects = _runtime(fresh_show, strips)

    pre_parent = pre_runtime.jobs[0]
    fresh_parent = fresh_runtime.jobs[0]
    pre_branch = pre_parent._branch_jobs[0]
    fresh_branch = fresh_parent._branch_jobs[0]

    assert pre_show.virtual_paths[0] == fresh_show.virtual_paths[0]
    assert pre_parent.resolved.authored_path == fresh_parent.resolved.authored_path
    assert pre_branch.release_progress == fresh_branch.release_progress == 0.5
    assert pre_branch.job.resolved.selector == fresh_branch.job.resolved.selector
    assert pre_branch.job.origin == fresh_branch.job.origin == "end"

    before_pre = _render(pre_runtime, strips, timestamp=2.0 - 1e-6, sequence=1)
    before_fresh = _render(fresh_runtime, strips, timestamp=2.0 - 1e-6, sequence=1)
    assert _logical_pixels(before_pre, "branch_a") == [(0.0, 0.0, 0.0)]
    assert _logical_pixels(before_fresh, "branch_a") == [(0.0, 0.0, 0.0)]

    at_pre = _render(pre_runtime, strips, timestamp=2.0, sequence=2)
    at_fresh = _render(fresh_runtime, strips, timestamp=2.0, sequence=2)

    # The existing >= threshold predicate releases both lifecycles on the
    # exact same frame. Lifecycle changes hidden state, not path geometry or
    # release timing.
    assert _logical_pixels(at_pre, "branch_a") == pytest.approx([(0.2, 0.0, 0.0)])
    assert _logical_pixels(at_fresh, "branch_a") == pytest.approx([(0.1, 0.0, 0.0)])
    assert len(pre_effects[1].contexts) == 2
    assert len(fresh_effects[1].contexts) == 1


class _ScriptedClock(Clock):
    def __init__(self, timestamps: tuple[float, ...]) -> None:
        self._timestamps = list(timestamps)
        self._time = self._timestamps[0]

    def now(self) -> float:
        return self._time

    def tick(self) -> float:
        previous = self._time
        if self._timestamps:
            self._time = self._timestamps.pop(0)
        return max(0.0, self._time - previous)


class _RecordingOutput(NullOutput):
    def __init__(self) -> None:
        super().__init__()
        self.frames: list[PhysicalFrame] = []

    def send_frame(self, frame: PhysicalFrame) -> None:
        self.frames.append(frame)


def _run_engine(
    show: ShowDefinition,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Engine, _RecordingOutput]:
    Config.reset()
    config = Config()
    config._data["system"]["output_fps"] = 1.0
    config._data["outputs"]["exit_safe_state"] = False
    engine = Engine(config, clock=_ScriptedClock((0.0, 1.0, 2.0)))

    effects: list[_SolidCountingEffect] = []

    def factory(_name: str) -> _SolidCountingEffect:
        effect = _SolidCountingEffect()
        effects.append(effect)
        return effect

    engine.set_show_runtime(ShowRuntime.from_layout(show, engine._layout, effect_factory=factory))
    output = _RecordingOutput()
    output.open()
    engine._outputs = {"recording": output}
    monkeypatch.setattr("light_engine.engine.time.sleep", lambda _seconds: None)

    engine.run(max_frames=3)
    return engine, output


def _physical_strip_pixels(
    engine: Engine,
    frame: PhysicalFrame,
    strip_id: str,
) -> list[tuple[float, float, float]]:
    segment = next(
        segment for segment in engine._layout.digital_segments
        if segment.strip_id == strip_id
    )
    node = next(
        node for node in frame.digital_frames
        if node.node_id == segment.node_id
    )
    return node.pixels[segment.offset : segment.offset + segment.pixel_count]


def test_hidden_pre_roll_does_not_add_transport_sends_or_consume_sequences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_targets = ("front", "wall_right")
    branched = _show(
        path_targets=parent_targets,
        branch_targets=(("wall_left",), ("rear",)),
        lifecycle="pre_roll",
    )
    baseline = _show(
        path_targets=parent_targets,
        branch_targets=(),
        lifecycle="start_on_release",
    )

    branch_engine, branch_output = _run_engine(branched, monkeypatch)
    baseline_engine, baseline_output = _run_engine(baseline, monkeypatch)

    assert [frame.sequence for frame in branch_output.frames] == [1, 2, 3]
    assert [frame.sequence for frame in branch_output.frames] == [
        frame.sequence for frame in baseline_output.frames
    ]
    assert [frame.timestamp for frame in branch_output.frames] == [0.0, 1.0, 2.0]
    assert len(branch_output.frames) == len(baseline_output.frames) == 3

    for frame in branch_output.frames[:2]:
        for strip_id in ("wall_left", "rear"):
            assert all(
                pixel == (0.0, 0.0, 0.0)
                for pixel in _physical_strip_pixels(branch_engine, frame, strip_id)
            )

    for strip_id in ("wall_left", "rear"):
        assert any(
            pixel != (0.0, 0.0, 0.0)
            for pixel in _physical_strip_pixels(branch_engine, branch_output.frames[2], strip_id)
        )

    # The branch-free engine is a true output/sequence baseline; its mapping
    # is also exercised so the comparison does not depend on a mocked send.
    assert baseline_engine.frame_count == branch_engine.frame_count == 3
