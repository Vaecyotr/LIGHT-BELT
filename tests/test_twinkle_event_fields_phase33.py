"""Focused Phase 33 contracts for generalized twinkle event fields."""

from __future__ import annotations

import math
import random
from hashlib import sha256

import pytest

from light_engine.effects.twinkle import TwinkleEffect, validate_twinkle_params
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import EffectContext
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector
from light_engine.show.compositor import CueRenderJob


def _ctx(
    time: float = 0.0,
    *,
    delta_time: float = 0.1,
    progress: float = 1.0,
    **params: object,
) -> EffectContext:
    return EffectContext(
        timestamp=time,
        delta_time=delta_time,
        sequence=7,
        mode_parameters={
            "cue_local_time": time,
            "cue_progress": progress,
            "strip_defs": ({"id": "path", "pixel_count": 5},),
            "zone_defs": (),
            "density": 2.0,
            "fade_time": 1.0,
            "color_source": "solid",
            "color": (1.0, 0.5, 0.25),
            **params,
        },
    )


def _active(frame) -> list[int]:
    return [
        index
        for index, pixel in enumerate(frame.strips[0].pixels)
        if max(pixel) > 0.0
    ]


def _event_position(seed: int, *, cue_id: str = "<direct>", length: int = 5) -> int:
    digest = sha256(f"twinkle-event-v1:{seed}:{cue_id}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big")).randrange(length)


def test_legacy_default_and_explicit_default_event_controls_are_exact(monkeypatch) -> None:
    monkeypatch.setattr("light_engine.effects.twinkle.random.randrange", lambda _n: 2)
    implicit = TwinkleEffect()
    explicit = TwinkleEffect()

    implicit_frame = implicit.process(_ctx())
    explicit_frame = explicit.process(_ctx(event_width_px=1.0, blur_radius_px=0.0))

    assert implicit_frame.strips[0].pixels == explicit_frame.strips[0].pixels
    assert _active(implicit_frame) == [2]


def test_width_and_blur_create_one_clipped_logical_event_field() -> None:
    seed = 19
    position = _event_position(seed)
    wide = TwinkleEffect(seed=seed).process(_ctx(event_width_px=3.0))
    assert _active(wide) == [
        index for index in range(5) if abs(index - position) < 1.5
    ]

    blurred = TwinkleEffect(seed=seed).process(
        _ctx(event_width_px=1.0, blur_radius_px=2.0)
    )
    pixels = blurred.strips[0].pixels
    assert pixels[position] == pytest.approx((1.0, 0.5, 0.25))
    if position > 0:
        assert pixels[position - 1] == pytest.approx((0.75, 0.375, 0.1875))
    if position < 4:
        assert pixels[position + 1] == pytest.approx((0.75, 0.375, 0.1875))


def test_gate_source_scales_birth_budget_and_birth_gain_scales_event_color() -> None:
    blocked = TwinkleEffect(seed=4).process(
        _ctx(event_gate_source="cue_progress", progress=0.0)
    )
    assert _active(blocked) == []

    gated = TwinkleEffect(seed=4).process(
        _ctx(event_gate_source="cue_progress", progress=1.0)
    )
    assert len(_active(gated)) == 1

    gained = TwinkleEffect(seed=4).process(
        _ctx(birth_gain_source="cue_progress", progress=0.25)
    )
    position = _active(gained)[0]
    assert gained.strips[0].pixels[position] == pytest.approx((0.25, 0.125, 0.0625))


def test_event_field_replays_after_reset_and_backward_seek() -> None:
    params = {"event_width_px": 3.0, "blur_radius_px": 1.0}
    first = TwinkleEffect(seed=123)
    replay = TwinkleEffect(seed=123)
    initial = first.process(_ctx(0.0, **params))
    assert initial.strips[0].pixels == replay.process(_ctx(0.0, **params)).strips[0].pixels

    first.process(_ctx(1.0, **params))
    sought = first.process(_ctx(0.0, **params))
    assert sought.strips[0].pixels == initial.strips[0].pixels

    first.reset()
    reset = first.process(_ctx(0.0, **params))
    assert reset.strips[0].pixels == initial.strips[0].pixels


def test_event_field_rng_is_cue_scoped_and_never_reads_module_rng(monkeypatch) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("event-field renderer must not read module RNG")

    monkeypatch.setattr("light_engine.effects.twinkle.random.getrandbits", forbidden)
    monkeypatch.setattr("light_engine.effects.twinkle.random.random", forbidden)
    params = dict(_ctx(event_width_px=2.0, color_source="random").mode_parameters)
    params.pop("color")  # The random event color is not author-supplied.
    params["cue_id"] = "shared-cue"
    context = EffectContext(timestamp=0.0, delta_time=0.1, sequence=7, mode_parameters=params)

    first = TwinkleEffect(seed=77).process(context)
    second = TwinkleEffect(seed=77).process(context)
    assert first.strips[0].pixels == second.strips[0].pixels


def test_virtual_path_field_crosses_member_seam_before_compositor_split() -> None:
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
    # The seeded event is born at global index 2, so a three-pixel field must
    # occupy indices 1, 2, 3 across the physical-member boundary.
    seed = next(seed for seed in range(100) if _event_position(seed, cue_id="twinkle-seam") == 2)
    cue = Cue(
        id="twinkle-seam",
        start=0.0,
        end=2.0,
        target=TargetSelector("virtual_path", id="joined"),
        effect=EffectSpec(
            mode="fixed",
            id="twinkle",
            params={
                "density": 2.0,
                "fade_time": 1.0,
                "color_source": "solid",
                "color": (1.0, 0.0, 0.0),
                "event_width_px": 3.0,
            },
        ),
    )
    contribution = CueRenderJob(
        cue,
        0,
        resolver,
        effect=TwinkleEffect(seed=seed),
    ).render(EffectContext(timestamp=0.0, delta_time=0.1, sequence=1))

    assert [item.strip_id for item in contribution.digital] == ["left", "right"]
    joined = tuple(contribution.digital[0].pixels + contribution.digital[1].pixels)
    assert [index for index, pixel in enumerate(joined) if max(pixel) > 0.0] == [1, 2, 3]
    assert contribution.digital[0].pixels[-1] == contribution.digital[1].pixels[0]


@pytest.mark.parametrize("key", ["event_width_px", "blur_radius_px"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_event_field_validator_rejects_non_finite_values(key: str, value: float) -> None:
    with pytest.raises(ValueError, match=key):
        validate_twinkle_params({key: value})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("event_width_px", 0.0),
        ("blur_radius_px", -0.1),
        ("event_gate_source", "audio.raw_level"),
        ("birth_gain_source", "audio.dominant_frequency"),
    ],
)
def test_event_field_validator_rejects_invalid_ranges_and_sources(
    key: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match=key):
        validate_twinkle_params({key: value})
