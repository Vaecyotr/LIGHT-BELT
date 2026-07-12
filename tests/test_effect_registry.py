"""Tests for effect registry show-schema metadata."""

import pytest

from light_engine.effects import get_effect_registration, list_effects
from light_engine.effects.base import get_effect_parameter_keys


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
    assert contract.validator({"speed": 2.0}) == {"speed": 2.0}
    with pytest.raises(ValueError, match="unknown effect parameters"):
        contract.validator({"target_dispatch": "strip_41"})


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
