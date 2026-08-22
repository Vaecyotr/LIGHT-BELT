"""Tests for effect registry show-schema metadata."""

import random

import pytest

from light_engine.effects import (
    create_effect,
    get_effect_registration,
    list_effect_registrations,
    list_effects,
    register_effect,
)
from light_engine.effects.base import get_effect_parameter_keys
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures


def _visible_context(*, speed: float, intensity: float) -> EffectContext:
    return EffectContext(
        timestamp=1.0,
        delta_time=0.25,
        sequence=1,
        speed=speed,
        intensity=intensity,
        audio_features=AudioFeatures(
            timestamp=1.0,
            loudness=0.8,
            spectrum=(0.8,) * 16,
            peak=True,
        ),
        video_features=VideoFeatures(
            timestamp=1.0,
            average_rgb=(0.8, 0.4, 0.2),
            dominant_rgb=(0.8, 0.4, 0.2),
            zone_colors={"center": (0.8, 0.4, 0.2)},
        ),
        mode_parameters={
            "cue_local_time": 1.0,
            "strip_defs": [
                {
                    "id": "strip",
                    "pixel_count": 8,
                    "video_zone": "center",
                    "direction": "forward",
                }
            ],
            "zone_defs": [{"id": "zone", "video_zone": "center"}],
        },
    )


def test_registered_effects_have_v1_parameter_metadata() -> None:
    effects = set(list_effects())

    assert "chase" in effects
    assert "breath" in effects
    assert "color_wipe" in effects
    assert "twinkle" in effects
    assert get_effect_parameter_keys("chase") >= {
        "speed",
        "width",
        "gap",
        "color_source",
    }
    assert "period" in get_effect_parameter_keys("breath")
    assert get_effect_parameter_keys("color_wipe") >= {"speed", "color"}
    assert get_effect_parameter_keys("twinkle") >= {
        "density",
        "fade_time",
        "color_source",
        "color",
    }


def test_effect_registration_binds_id_validator_and_renderer_without_targets() -> None:
    contract = get_effect_registration("chase")

    assert contract.id == "chase"
    assert contract.renderer.__name__ == "ChaseEffect"
    assert contract.factory("chase").name == "chase"
    assert contract.parameter_keys >= {"speed", "width", "gap", "color_source"}
    assert contract.capability.display_name == "Chase"
    assert contract.capability.common_controls == frozenset({"speed", "intensity"})
    assert contract.validator({"speed": 2.0}) == {"speed": 2.0}
    with pytest.raises(ValueError, match="unknown effect parameters"):
        contract.validator({"target_dispatch": "strip_41"})


def test_duplicate_effect_registration_is_rejected_without_replacing_contract() -> None:
    original = get_effect_registration("static")

    with pytest.raises(ValueError, match="already registered"):
        register_effect(
            "static",
            original.renderer,
            parameter_keys=original.parameter_keys,
        )

    assert get_effect_registration("static") is original


@pytest.mark.parametrize(
    "effect_id",
    [
        registration.id
        for registration in list_effect_registrations()
        if "intensity" in registration.capability.common_controls
    ],
)
def test_every_declared_common_intensity_can_black_the_visible_frame(effect_id) -> None:
    random.seed(32)
    frame = create_effect(effect_id).process(
        _visible_context(speed=1.0, intensity=0.0)
    )

    assert all(pixel == (0.0, 0.0, 0.0) for strip in frame.strips for pixel in strip.pixels)
    assert all(
        (zone.color.r, zone.color.g, zone.color.b, zone.color.warm_white, zone.color.cool_white)
        == (0.0, 0.0, 0.0, 0.0, 0.0)
        for zone in frame.zones
    )


@pytest.mark.parametrize(
    ("effect_id", "params"),
    [
        ("color_wipe", {"speed": 5.0}),
        ("single_dot", {"speed": 2.0}),
        ("theater_phase", {"speed": 2.0}),
    ],
)
def test_discrete_legacy_effects_multiply_params_speed_by_common_speed(
    effect_id, params
) -> None:
    stopped = _visible_context(speed=0.0, intensity=1.0)
    stopped.mode_parameters.update(params)
    moving = _visible_context(speed=1.0, intensity=1.0)
    moving.mode_parameters.update(params)

    stopped_frame = create_effect(effect_id).process(stopped)
    moving_frame = create_effect(effect_id).process(moving)

    assert stopped_frame.strips[0].pixels != moving_frame.strips[0].pixels


def test_new_effect_parameter_contracts_enforce_authored_ranges() -> None:
    wipe = get_effect_registration("color_wipe")
    twinkle = get_effect_registration("twinkle")

    assert wipe.validator({"speed": 25.0, "color": [1.0, 0.5, 0.0]}) == {
        "speed": 25.0,
        "color": [1.0, 0.5, 0.0],
    }
    assert twinkle.validator(
        {"density": 0.12, "fade_time": 0.7, "color_source": "solid"}
    ) == {"density": 0.12, "fade_time": 0.7, "color_source": "solid"}
    with pytest.raises(ValueError, match="speed must be in"):
        wipe.validator({"speed": 1001.0})
    with pytest.raises(ValueError, match="density must be in"):
        twinkle.validator({"density": -0.1})
    with pytest.raises(ValueError, match="color_source must be one of"):
        twinkle.validator({"color_source": "video"})
