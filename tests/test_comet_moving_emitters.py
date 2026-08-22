"""Focused contracts for composable comet moving emitters."""

from __future__ import annotations

import math

import pytest

from light_engine.effects.comet import CometEffect, validate_comet_params
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import EffectContext
from light_engine.show import Cue, CueRenderJob, EffectSpec, TargetResolver, TargetSelector, TransitionSpec


def _frame(
    params: dict,
    *,
    cue_time: float,
    pixel_count: int = 12,
    effect: CometEffect | None = None,
    delta_time: float = 1 / 60,
):
    effect = effect or CometEffect()
    frame = effect.process(
        EffectContext(
            timestamp=cue_time,
            delta_time=delta_time,
            sequence=11,
            mode_parameters={
                "strip_defs": [{"id": "path", "pixel_count": pixel_count}],
                "zone_defs": [],
                "cue_local_time": cue_time,
                **params,
            },
        )
    )
    return effect, frame


def _lit_indices(frame) -> list[int]:
    return [
        index
        for index, pixel in enumerate(frame.strips[0].pixels)
        if max(pixel) > 0.0
    ]


def test_count_one_wrap_is_exactly_the_legacy_render_path() -> None:
    """Explicit generic controls must not perturb the count-one comet contract."""

    legacy = CometEffect()
    explicit = CometEffect()
    common = {"speed": 2.75, "tail_length": 0.4, "decay": 0.83, "color": [1.0, 0.2, 0.1]}
    for cue_time in (0.0, 0.1, 0.8, 2.1, 5.2):
        _, legacy_frame = _frame(common, cue_time=cue_time, effect=legacy, delta_time=0.1)
        _, explicit_frame = _frame(
            {**common, "count": 1, "phase_spacing": 0.73, "trajectory": "wrap"},
            cue_time=cue_time,
            effect=explicit,
            delta_time=0.1,
        )
        assert explicit_frame == legacy_frame
    assert explicit._positions == legacy._positions
    assert explicit._tails == legacy._tails


def test_multiple_emitters_and_phase_spacing_are_path_length_independent() -> None:
    base = {"speed": 2.0, "tail_length": 0.0, "decay": 0.0, "count": 2, "color": [1.0, 0.0, 0.0]}
    _, evenly_spaced = _frame(base, cue_time=1.0)
    _, custom_spacing = _frame({**base, "phase_spacing": 0.25}, cue_time=1.0)

    assert _lit_indices(evenly_spaced) == [2, 8]
    assert _lit_indices(custom_spacing) == [2, 5]


@pytest.mark.parametrize(
    ("trajectory", "cue_time", "expected"),
    [
        ("wrap", 3.0, 1),
        ("bounce", 3.0, 2),
        ("sine", 0.5, 0),
    ],
)
def test_trajectories_follow_distinct_bounded_logical_paths(
    trajectory: str,
    cue_time: float,
    expected: int,
) -> None:
    _, frame = _frame(
        {
            "speed": 2.0,
            "tail_length": 0.0,
            "decay": 0.0,
            "count": 2,
            "phase_spacing": 0.0,
            "trajectory": trajectory,
            "color": [1.0, 0.0, 0.0],
        },
        cue_time=cue_time,
        pixel_count=5,
    )
    assert _lit_indices(frame) == [expected]


def test_zero_tail_keeps_only_the_moving_heads() -> None:
    _, frame = _frame(
        {
            "speed": 1.0,
            "tail_length": 0.0,
            "decay": 0.0,
            "count": 3,
            "phase_spacing": 1 / 3,
            "color": [0.4, 0.2, 0.1],
        },
        cue_time=1.0,
        pixel_count=12,
    )
    assert _lit_indices(frame) == [1, 5, 9]
    assert {pixel for pixel in frame.strips[0].pixels if max(pixel) > 0.0} == {
        (0.4, 0.2, 0.1)
    }


def test_count_one_zero_tail_has_a_visible_head_without_a_trail() -> None:
    _, frame = _frame(
        {
            "speed": 2.0,
            "tail_length": 0.0,
            "decay": 0.0,
            "count": 1,
            "trajectory": "wrap",
            "color": [1.0, 0.0, 0.0],
        },
        cue_time=1.0,
    )
    assert _lit_indices(frame) == [2]
    assert frame.strips[0].pixels[2] == (1.0, 0.0, 0.0)


def test_uncolored_generic_emitters_are_independent_of_global_rng(monkeypatch) -> None:
    monkeypatch.setattr(
        "light_engine.effects.comet.random.uniform",
        lambda _a, _b: pytest.fail("generic emitters must not use process-global RNG"),
    )
    params = {
        "speed": 4.0,
        "tail_length": 0.3,
        "decay": 0.8,
        "count": 3,
        "phase_spacing": 0.2,
        "trajectory": "bounce",
        "cue_id": "same-cue",
    }
    left = CometEffect(seed=20260822)
    right = CometEffect(seed=20260822)

    _, left_frame = _frame(params, cue_time=1.25, effect=left)
    _, right_frame = _frame(params, cue_time=1.25, effect=right)

    assert left_frame == right_frame


def test_uncolored_generic_emitters_replay_after_seek_and_reset() -> None:
    params = {
        "speed": 7.0,
        "tail_length": 0.35,
        "decay": 0.72,
        "count": 3,
        "phase_spacing": 0.23,
        "trajectory": "sine",
        "cue_id": "replay-cue",
    }
    effect = CometEffect(seed=19)
    _, at_two_seconds = _frame(params, cue_time=2.0, effect=effect)
    _, after_seek = _frame(params, cue_time=0.25, effect=effect)
    _, fresh_at_seek = _frame(params, cue_time=0.25, effect=CometEffect(seed=19))
    assert after_seek == fresh_at_seek

    effect.reset()
    _, after_reset = _frame(params, cue_time=2.0, effect=effect)
    assert after_reset == at_two_seconds


def test_generic_emitters_are_30_60_fps_equivalent_and_seek_reset_safe() -> None:
    params = {
        "speed": 7.0,
        "tail_length": 0.35,
        "decay": 0.72,
        "count": 3,
        "phase_spacing": 0.23,
        "trajectory": "sine",
        "color": [0.7, 0.2, 0.1],
    }
    at_30 = CometEffect()
    at_60 = CometEffect()
    for index in range(31):
        _frame(params, cue_time=index / 30, effect=at_30, delta_time=1 / 30)
    for index in range(61):
        _frame(params, cue_time=index / 60, effect=at_60, delta_time=1 / 60)
    _, frame_30 = _frame(params, cue_time=1.0, effect=at_30, delta_time=1 / 30)
    _, frame_60 = _frame(params, cue_time=1.0, effect=at_60, delta_time=1 / 60)
    assert frame_30 == frame_60

    effect = CometEffect()
    _, at_two_seconds = _frame(params, cue_time=2.0, effect=effect)
    _, after_seek = _frame(params, cue_time=0.25, effect=effect)
    _, fresh_at_seek = _frame(params, cue_time=0.25)
    assert after_seek == fresh_at_seek
    effect.reset()
    _, after_reset = _frame(params, cue_time=2.0, effect=effect)
    assert after_reset == at_two_seconds


@pytest.mark.parametrize("pixel_count", [1, 2, 7])
def test_generic_emitters_support_every_nonempty_logical_path_length(pixel_count: int) -> None:
    _, frame = _frame(
        {
            "speed": 3.0,
            "tail_length": 0.2,
            "decay": 0.8,
            "count": 4,
            "phase_spacing": 0.2,
            "trajectory": "bounce",
            "color": [1.0, 0.0, 0.0],
        },
        cue_time=0.7,
        pixel_count=pixel_count,
    )
    assert len(frame.strips[0].pixels) == pixel_count
    assert frame.all_pixels_valid()


def test_virtual_path_crosses_the_seam_as_one_continuous_logical_path() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "seam",
                "segments": [
                    {"strip_id": "left", "pixel_count": 3, "direction": "forward"},
                    {"strip_id": "right", "pixel_count": 4, "direction": "forward"},
                ],
            }
        ],
        {"left": 3, "right": 4},
    )[0]
    resolver = TargetResolver(
        (),
        (ZoneDef(id="left", pixel_count=3), ZoneDef(id="right", pixel_count=4)),
        virtual_paths=(path,),
    )
    cue = Cue(
        id="moving-seam",
        start=0.0,
        end=10.0,
        target=TargetSelector("virtual_path", id="seam"),
        effect=EffectSpec(
            mode="fixed",
            name="comet",
            parameters={
                "speed": 1.0,
                "tail_length": 0.0,
                "decay": 0.0,
                "count": 2,
                "phase_spacing": 0.5,
                "trajectory": "wrap",
            },
        ),
        transition=TransitionSpec(blend="replace"),
    )
    job = CueRenderJob(cue, 0, resolver)

    before = job.render(EffectContext(timestamp=2.9, delta_time=0.1, sequence=1))
    after = job.render(EffectContext(timestamp=3.1, delta_time=0.1, sequence=2))

    def positions(contribution) -> list[int]:
        pixels = tuple(contribution.digital[0].pixels) + tuple(contribution.digital[1].pixels)
        return [index for index, pixel in enumerate(pixels) if max(pixel) > 0.0]

    assert positions(before) == [2, 6]
    assert positions(after) == [3, 6]


def test_common_origin_still_remaps_the_generic_logical_path() -> None:
    resolver = TargetResolver((), (ZoneDef(id="strip", pixel_count=8),))
    cue = Cue(
        id="reverse-origin",
        start=0.0,
        end=10.0,
        target=TargetSelector("digital_strip", id="strip"),
        origin="end",
        effect=EffectSpec(
            mode="fixed",
            name="comet",
            parameters={
                "speed": 2.0,
                "tail_length": 0.0,
                "decay": 0.0,
                "count": 2,
                "phase_spacing": 0.0,
            },
        ),
        transition=TransitionSpec(blend="replace"),
    )
    frame = CueRenderJob(cue, 0, resolver).render(
        EffectContext(timestamp=1.0, delta_time=0.1, sequence=1)
    )
    assert [index for index, pixel in enumerate(frame.digital[0].pixels) if max(pixel) > 0.0] == [5]


@pytest.mark.parametrize(
    "values",
    [
        {"count": True},
        {"count": 0},
        {"count": 65},
        {"count": 1.0},
        {"phase_spacing": -0.01},
        {"phase_spacing": 1.01},
        {"phase_spacing": math.nan},
        {"phase_spacing": math.inf},
        {"trajectory": "zigzag"},
        {"tail_length": -0.01},
        {"tail_length": math.nan},
        {"tail_length": math.inf},
    ],
)
def test_comet_validator_rejects_invalid_moving_emitter_parameters(values: dict) -> None:
    with pytest.raises(ValueError):
        validate_comet_params(values)


def test_comet_validator_accepts_a_zero_tail() -> None:
    assert validate_comet_params(
        {"count": 2, "phase_spacing": 0.5, "trajectory": "sine", "tail_length": 0.0}
    )["tail_length"] == 0.0
