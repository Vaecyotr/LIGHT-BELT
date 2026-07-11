"""Tests for effect registry show-schema metadata."""

import pytest

from light_engine.effects import get_effect_registration, list_effects
from light_engine.effects.base import get_effect_parameter_keys


def test_registered_effects_have_v1_parameter_metadata() -> None:
    effects = set(list_effects())

    assert "chase" in effects
    assert "breath" in effects
    assert get_effect_parameter_keys("chase") >= {
        "speed",
        "width",
        "gap",
        "color_source",
    }
    assert "period" in get_effect_parameter_keys("breath")


def test_effect_registration_binds_id_validator_and_renderer_without_targets() -> None:
    contract = get_effect_registration("chase")

    assert contract.id == "chase"
    assert contract.renderer.__name__ == "ChaseEffect"
    assert contract.validator({"speed": 2.0}) == {"speed": 2.0}
    with pytest.raises(ValueError, match="unknown effect parameters"):
        contract.validator({"target_dispatch": "strip_41"})
