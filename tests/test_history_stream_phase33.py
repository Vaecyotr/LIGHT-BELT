"""Focused Phase 33 contracts for the native history_stream primitive."""

from __future__ import annotations

import math

import pytest

from light_engine.effects.history_stream import (
    HistoryStreamEffect,
    validate_history_stream_params,
)
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector
from light_engine.show.compositor import CueRenderJob


def _ctx(
    time: float,
    color: tuple[float, float, float],
    *,
    pixel_count: int = 5,
    delta_time: float = 0.1,
    speed: float = 1.0,
    direction: str = "forward",
    audio: AudioFeatures | None = None,
    **params: object,
) -> EffectContext:
    return EffectContext(
        timestamp=time,
        delta_time=delta_time,
        sequence=4,
        audio_features=audio,
        speed=speed,
        mode_parameters={
            "cue_local_time": time,
            "strip_defs": ({"id": "path", "pixel_count": pixel_count},),
            "zone_defs": (),
            "steps_per_second": 2.0,
            "direction": direction,
            "color": color,
            **params,
        },
    )


def _pixels(frame) -> tuple[tuple[float, float, float], ...]:
    return tuple(frame.strips[0].pixels)


def test_known_samples_have_fixed_spatial_order_in_both_directions() -> None:
    samples = ((0.2, 0.0, 0.0), (0.4, 0.0, 0.0), (0.6, 0.0, 0.0))
    forward = HistoryStreamEffect()
    reverse = HistoryStreamEffect()
    for time, color in zip((0.0, 0.5, 1.0), samples):
        forward_frame = forward.process(_ctx(time, color, direction="forward"))
        reverse_frame = reverse.process(_ctx(time, color, direction="reverse"))

    assert _pixels(forward_frame) == (samples[2], samples[1], samples[0], (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert _pixels(reverse_frame) == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), samples[0], samples[1], samples[2])


@pytest.mark.parametrize("pixel_count", [1, 2, 7])
def test_history_capacity_follows_every_nonempty_logical_path_length(pixel_count: int) -> None:
    effect = HistoryStreamEffect()
    frame = effect.process(_ctx(0.0, (0.5, 0.0, 0.0), pixel_count=pixel_count))
    assert len(frame.strips[0].pixels) == pixel_count
    assert frame.all_pixels_valid()


def test_partial_and_skipped_fixed_steps_have_explicit_current_sample_semantics() -> None:
    effect = HistoryStreamEffect()
    first = effect.process(_ctx(0.0, (0.2, 0.0, 0.0), steps_per_second=4.0))
    partial = effect.process(_ctx(0.24, (0.4, 0.0, 0.0), steps_per_second=4.0))
    boundary = effect.process(_ctx(0.25, (0.6, 0.0, 0.0), steps_per_second=4.0))
    skipped = effect.process(_ctx(0.75, (0.8, 0.0, 0.0), steps_per_second=4.0))

    assert _pixels(first)[:2] == ((0.2, 0.0, 0.0), (0.0, 0.0, 0.0))
    assert _pixels(partial) == _pixels(first)
    assert _pixels(boundary)[:3] == ((0.6, 0.0, 0.0), (0.2, 0.0, 0.0), (0.0, 0.0, 0.0))
    # Steps 2 and 3 became due in one render; the only observable sample is
    # the current one, so it is inserted for both due steps.
    assert _pixels(skipped)[:4] == ((0.8, 0.0, 0.0),) * 2 + ((0.6, 0.0, 0.0), (0.2, 0.0, 0.0))


def test_30_and_60_fps_arrive_at_the_same_fixed_step_history() -> None:
    def render(frame_rate: int):
        effect = HistoryStreamEffect()
        result = None
        for frame_index in range(frame_rate // 2 + 1):
            time = frame_index / frame_rate
            result = effect.process(
                _ctx(
                    time,
                    (0.3, 0.2, 0.1),
                    delta_time=1.0 / frame_rate,
                    pixel_count=8,
                    steps_per_second=8.0,
                )
            )
        assert result is not None
        return _pixels(result)

    assert render(30) == render(60)


def test_color_timeline_is_sampled_at_exact_off_frame_fixed_step_times() -> None:
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 0.5, "color": (0.0, 1.0, 0.0)},
            {"time": 1.0, "color": (0.0, 0.0, 1.0)},
        ),
    }

    def render(frame_rate: int):
        effect = HistoryStreamEffect()
        result = None
        for frame_index in range(frame_rate + 1):
            time = frame_index / frame_rate
            result = effect.process(
                _ctx(
                    time,
                    (0.0, 0.0, 0.0),
                    delta_time=1.0 / frame_rate,
                    pixel_count=9,
                    steps_per_second=7.0,
                    color_timeline=timeline,
                )
            )
        assert result is not None
        return _pixels(result)

    # 1/7-second sample times are not aligned with either render cadence.  A
    # timeline is authored deterministic data, so both cadences reconstruct
    # the same exact spatial samples rather than using their later frame color.
    assert render(30) == render(60)


def test_timeline_uses_current_gain_without_reconstructing_past_audio() -> None:
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 1.0, "color": (0.0, 1.0, 0.0)},
        ),
    }
    frame = HistoryStreamEffect().process(
        _ctx(
            1.0,
            (0.0, 0.0, 0.0),
            pixel_count=3,
            steps_per_second=2.0,
            color_timeline=timeline,
            sample_gain_source="audio.loudness",
            audio=AudioFeatures(timestamp=1.0, loudness=0.25),
        )
    )
    for actual, expected in zip(
        _pixels(frame),
        ((0.0, 0.25, 0.0), (0.125, 0.125, 0.0), (0.25, 0.0, 0.0)),
    ):
        assert actual == pytest.approx(expected)


def test_paused_speed_preserves_current_sample_semantics_and_reverse_edge() -> None:
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 1.0, "color": (0.0, 1.0, 0.0)},
        ),
    }
    effect = HistoryStreamEffect()
    first = effect.process(
        _ctx(
            0.5,
            (0.2, 0.3, 0.4),
            direction="reverse",
            speed=0.0,
            steps_per_second=7.0,
            color_timeline=timeline,
        )
    )
    later = effect.process(
        _ctx(
            1.0,
            (0.9, 0.8, 0.7),
            direction="reverse",
            speed=0.0,
            steps_per_second=7.0,
            color_timeline=timeline,
        )
    )
    assert _pixels(first) == ((0.0, 0.0, 0.0),) * 4 + ((0.2, 0.3, 0.4),)
    assert _pixels(later) == _pixels(first)


def test_reset_backward_seek_and_fresh_replay_are_deterministic() -> None:
    params = {"steps_per_second": 2.0, "direction": "forward"}
    effect = HistoryStreamEffect()
    first = effect.process(_ctx(0.0, (0.1, 0.0, 0.0), **params))
    effect.process(_ctx(1.0, (0.9, 0.0, 0.0), **params))
    sought = effect.process(_ctx(0.0, (0.1, 0.0, 0.0), **params))
    assert _pixels(sought) == _pixels(first)

    effect.reset()
    reset = effect.process(_ctx(0.0, (0.1, 0.0, 0.0), **params))
    fresh = HistoryStreamEffect().process(_ctx(0.0, (0.1, 0.0, 0.0), **params))
    assert _pixels(reset) == _pixels(fresh) == _pixels(first)


def test_virtual_path_advances_once_before_member_split() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "joined",
                "segments": [
                    {"strip_id": "left", "pixel_count": 2, "direction": "forward"},
                    {"strip_id": "right", "pixel_count": 3, "direction": "forward"},
                ],
            }
        ],
        {"left": 2, "right": 3},
    )[0]
    resolver = TargetResolver(
        (),
        (ZoneDef(id="left", pixel_count=2), ZoneDef(id="right", pixel_count=3)),
        virtual_paths=(path,),
    )
    cue = Cue(
        id="history-seam",
        start=0.0,
        end=2.0,
        target=TargetSelector("virtual_path", id="joined"),
        effect=EffectSpec(
            mode="fixed",
            id="history_stream",
            params={"steps_per_second": 2.0, "color": (1.0, 0.0, 0.0)},
        ),
    )
    job = CueRenderJob(cue, 0, resolver, effect=HistoryStreamEffect())
    job.render(EffectContext(timestamp=0.0, delta_time=0.1, sequence=1))
    job.render(EffectContext(timestamp=0.5, delta_time=0.1, sequence=2))
    contribution = job.render(EffectContext(timestamp=1.0, delta_time=0.1, sequence=3))

    assert [item.strip_id for item in contribution.digital] == ["left", "right"]
    joined = tuple(contribution.digital[0].pixels + contribution.digital[1].pixels)
    assert [index for index, pixel in enumerate(joined) if max(pixel) > 0.0] == [0, 1, 2]
    assert max(contribution.digital[0].pixels[-1]) > 0.0
    assert max(contribution.digital[1].pixels[0]) > 0.0


def test_scalar_gain_uses_the_shared_scalar_source_contract() -> None:
    frame = HistoryStreamEffect().process(
        _ctx(
            0.0,
            (1.0, 0.4, 0.2),
            sample_gain_source="audio.loudness",
            audio=AudioFeatures(timestamp=0.0, loudness=0.25),
        )
    )
    assert _pixels(frame)[0] == pytest.approx((0.25, 0.1, 0.05))


def test_compositor_color_timeline_samples_become_spatial_history() -> None:
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 1.0, "color": (0.0, 1.0, 0.0)},
        ),
    }
    cue = Cue(
        id="history-color",
        start=10.0,
        end=12.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(
            mode="fixed",
            id="history_stream",
            params={"steps_per_second": 2.0, "color_timeline": timeline},
        ),
    )
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip", pixel_count=4),)),
        effect=HistoryStreamEffect(),
    )
    job.render(EffectContext(timestamp=10.0, delta_time=0.1, sequence=1))
    job.render(EffectContext(timestamp=10.5, delta_time=0.1, sequence=2))
    contribution = job.render(EffectContext(timestamp=11.0, delta_time=0.1, sequence=3))

    for actual, expected in zip(
        contribution.digital[0].pixels[:3],
        ((0.0, 1.0, 0.0), (0.5, 0.5, 0.0), (1.0, 0.0, 0.0)),
    ):
        assert actual == pytest.approx(expected)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 0.0])
def test_validator_rejects_invalid_step_rates(value: float) -> None:
    with pytest.raises(ValueError, match="steps_per_second"):
        validate_history_stream_params({"steps_per_second": value})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("direction", "sideways"),
        ("sample_gain_source", "audio.raw_level"),
        ("sample_gain_source", "audio.dominant_frequency"),
        ("color", (math.nan, 0.0, 0.0)),
        ("color", (math.inf, 0.0, 0.0)),
    ],
)
def test_validator_rejects_invalid_parameters(key: str, value: object) -> None:
    with pytest.raises(ValueError):
        validate_history_stream_params({key: value})
