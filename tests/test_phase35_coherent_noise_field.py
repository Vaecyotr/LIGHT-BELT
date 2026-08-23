"""Phase 35 contracts for the native coherent-noise field."""

from __future__ import annotations

import math

import pytest

from light_engine.effects import create_effect, get_effect_registration, list_effects, validate_effect_params
from light_engine.effects.coherent_noise import coherent_noise_2d, derive_coherent_seed
from light_engine.effects.coherent_noise_field import CoherentNoiseFieldEffect
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import EffectContext
from light_engine.motion import MotionInterval
from light_engine.show import Cue, CueRenderJob, EffectSpec, TargetResolver, TargetSelector


def _params(**overrides):
    values = {
        "feature_size_px": 2.0,
        "drift_rate": 1.0,
        "contrast": 1.0,
        "floor_gain": 0.1,
        "ceiling_gain": 0.9,
        "color": (1.0, 0.0, 0.0),
    }
    values.update(overrides)
    return values


def _context(*, cue_time=0.0, motion_time=None, previous_motion_time=0.0, speed=1.0,
             params=None, length=6, zones=(), cue_id="noise"):
    motion = None
    if motion_time is not None:
        motion = MotionInterval(previous_motion_time, motion_time, 0.0, cue_time)
    return EffectContext(
        timestamp=cue_time,
        delta_time=1 / 60,
        sequence=7,
        speed=speed,
        motion=motion,
        mode_parameters={
            "cue_local_time": cue_time,
            "cue_id": cue_id,
            "strip_defs": ({"id": "path", "pixel_count": length},),
            "zone_defs": tuple({"id": zone} for zone in zones),
            **(params or _params()),
        },
    )


def _levels(frame):
    return [pixel[0] for pixel in frame.strips[0].pixels]


def test_clean_room_primitive_is_bounded_seeded_and_coherent() -> None:
    values = [coherent_noise_2d(index / 8.0, index / 13.0, seed=73) for index in range(-16, 17)]
    assert all(0.0 <= value <= 1.0 and math.isfinite(value) for value in values)
    assert values == [coherent_noise_2d(index / 8.0, index / 13.0, seed=73) for index in range(-16, 17)]
    assert values != [coherent_noise_2d(index / 8.0, index / 13.0, seed=74) for index in range(-16, 17)]
    assert abs(coherent_noise_2d(1.0 - 1e-5, .25, seed=73) - coherent_noise_2d(1.0 + 1e-5, .25, seed=73)) < 1e-6
    assert abs(coherent_noise_2d(.25, 1.0 - 1e-5, seed=73) - coherent_noise_2d(.25, 1.0 + 1e-5, seed=73)) < 1e-6
    local_change = abs(coherent_noise_2d(.25, .25, seed=73) - coherent_noise_2d(.25, .251, seed=73))
    distant_change = abs(coherent_noise_2d(.25, .25, seed=73) - coherent_noise_2d(.25, 8.25, seed=73))
    assert local_change < 0.01
    assert distant_change > local_change
    with pytest.raises(ValueError):
        coherent_noise_2d(float("nan"), 0.0)


def test_seed_derivation_is_deterministic_and_decorrelates_cues() -> None:
    assert derive_coherent_seed(3, "cue-a") == derive_coherent_seed(3, "cue-a")
    assert derive_coherent_seed(3, "cue-a") != derive_coherent_seed(3, "cue-b")
    left = CoherentNoiseFieldEffect(seed=3).process(_context(cue_id="cue-a"))
    right = CoherentNoiseFieldEffect(seed=3).process(_context(cue_id="cue-b"))
    assert left.strips[0].pixels != right.strips[0].pixels


def test_feature_size_and_gain_contract_shape_the_field() -> None:
    effect = CoherentNoiseFieldEffect(seed=11)
    fine = effect.process(_context(params=_params(feature_size_px=1.0), cue_id="s"))
    coarse = effect.process(_context(params=_params(feature_size_px=10.0), cue_id="s"))
    bounded = effect.process(_context(params=_params(floor_gain=.3, ceiling_gain=.6), cue_id="s"))
    flat = effect.process(_context(params=_params(contrast=0.0), cue_id="s"))
    assert fine.strips[0].pixels != coarse.strips[0].pixels
    assert all(.3 <= level <= .6 for level in _levels(bounded))
    assert _levels(flat) == pytest.approx([.5] * 6)


def test_drift_uses_integrated_motion_and_freezes_at_zero_speed() -> None:
    effect = CoherentNoiseFieldEffect(seed=19)
    first = effect.process(_context(cue_time=1.0, motion_time=1.0, params=_params()))
    paused = effect.process(_context(cue_time=2.0, motion_time=1.0, previous_motion_time=1.0, params=_params()))
    resumed = effect.process(_context(cue_time=3.0, motion_time=2.0, previous_motion_time=1.0, params=_params()))
    dynamic = effect.process(_context(cue_time=4.0, motion_time=3.25, previous_motion_time=2.0, params=_params()))
    assert paused.strips == first.strips
    assert resumed.strips != paused.strips
    assert dynamic.strips != resumed.strips


def test_reset_replay_one_pixel_and_non_black_analog_fallback() -> None:
    effect = CoherentNoiseFieldEffect(seed=29)
    before = effect.process(_context(cue_time=2.0, motion_time=2.0, length=1, zones=("zone",)))
    effect.reset()
    replay = effect.process(_context(cue_time=2.0, motion_time=2.0, length=1, zones=("zone",)))
    assert before == replay
    assert len(before.strips[0].pixels) == 1
    assert max(before.zones[0].color.r, before.zones[0].color.g, before.zones[0].color.b,
               before.zones[0].color.warm_white, before.zones[0].color.cool_white) > 0.0


@pytest.mark.parametrize(
    "params",
    [
        {"feature_size_px": 0.0}, {"drift_rate": float("inf")},
        {"contrast": -0.1}, {"floor_gain": 0.8, "ceiling_gain": 0.7},
        {"color": [1.0, 0.0]}, {"unknown": 1},
    ],
)
def test_invalid_authored_parameters_fail_explicitly(params) -> None:
    with pytest.raises(ValueError):
        validate_effect_params("coherent_noise_field", params)


def test_registry_is_internal_only_and_exposes_exact_authored_keys() -> None:
    registration = get_effect_registration("coherent_noise_field")
    assert len(list_effects()) == 22
    assert registration.capability.common_params == ("color", "speed", "intensity")
    assert registration.parameter_keys == frozenset({
        "feature_size_px", "drift_rate", "contrast", "floor_gain", "ceiling_gain", "color", "color_timeline",
    })
    assert isinstance(create_effect("coherent_noise_field"), CoherentNoiseFieldEffect)


def test_virtual_path_is_continuous_and_origin_stays_compositor_owned() -> None:
    path = build_virtual_paths(
        [{"id": "joined", "segments": [
            {"strip_id": "left", "pixel_count": 3, "direction": "forward"},
            {"strip_id": "right", "pixel_count": 3, "direction": "forward"},
        ]}], {"left": 3, "right": 3},
    )[0]
    resolver = TargetResolver((), (ZoneDef("left", pixel_count=3), ZoneDef("right", pixel_count=3)), virtual_paths=(path,))
    base = dict(id="noise", start=0.0, end=10.0, target=TargetSelector("virtual_path", id="joined"), effect=EffectSpec(mode="fixed", id="coherent_noise_field", params=_params(drift_rate=0.0)))
    start = CueRenderJob(Cue(**base, origin="start"), 0, resolver).render(EffectContext(timestamp=0.0, delta_time=1/60, sequence=1))
    end = CueRenderJob(Cue(**base, origin="end"), 0, resolver).render(EffectContext(timestamp=0.0, delta_time=1/60, sequence=1))
    start_pixels = tuple(pixel for item in start.digital for pixel in item.pixels)
    end_pixels = tuple(pixel for item in end.digital for pixel in item.pixels)
    assert end_pixels == tuple(reversed(start_pixels))
    direct = CoherentNoiseFieldEffect().process(_context(params=_params(drift_rate=0.0), length=6, cue_id="noise"))
    assert start_pixels == tuple(direct.strips[0].pixels)


def test_color_timeline_is_resolved_on_cue_wall_time_not_motion_time() -> None:
    timeline = {"interpolation": "rgb_linear", "keyframes": (
        {"time": 0.0, "color": (1.0, 0.0, 0.0)}, {"time": 2.0, "color": (0.0, 0.0, 1.0)},
    )}
    cue = Cue(id="timeline", start=0.0, end=3.0, target=TargetSelector("digital_strip", id="strip"), effect=EffectSpec(mode="fixed", id="coherent_noise_field", params=_params(contrast=0.0, floor_gain=1.0, ceiling_gain=1.0, color_timeline=timeline)))
    contribution = CueRenderJob(cue, 0, TargetResolver((), (ZoneDef("strip", pixel_count=1),))).render(EffectContext(timestamp=1.0, delta_time=1/60, sequence=1, speed=0.0))
    assert contribution.digital[0].pixels[0] == pytest.approx((.5, 0.0, .5))
