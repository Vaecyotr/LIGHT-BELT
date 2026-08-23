"""Phase 37 internal typed authoring-contract regression tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
import subprocess
import sys

import pytest

from light_engine.effects import list_effect_registrations
from light_engine.effects.base import ParameterSpec
from light_engine.show import TargetCatalog, validate_show_data


def test_parameter_keys_are_derived_from_immutable_specs() -> None:
    assert "parameter_keys" not in {field.name for field in fields(type(list_effect_registrations()[0]))}
    for registration in list_effect_registrations():
        names = tuple(spec.name for spec in registration.parameter_specs)
        assert names
        assert len(names) == len(set(names))
        assert registration.parameter_keys == frozenset(names)
        assert all(spec.description for spec in registration.parameter_specs)
        assert all(
            not spec.description.startswith("Effect-specific ")
            for spec in registration.parameter_specs
        )
        for spec in registration.parameter_specs:
            if spec.kind == "color_timeline":
                assert spec.runtime_mutable


def test_metadata_prevents_unsafe_generic_modulation_at_construction() -> None:
    with pytest.raises(ValueError, match="common modulation"):
        ParameterSpec(
            name="speed",
            kind="float",
            runtime_mutable=True,
            modulatable=True,
        )
    with pytest.raises(ValueError, match="only float"):
        ParameterSpec(
            name="enabled",
            kind="boolean",
            runtime_mutable=True,
            modulatable=True,
        )


def test_parameter_specs_are_frozen() -> None:
    spec = list_effect_registrations()[0].parameter_specs[0]
    with pytest.raises(FrozenInstanceError):
        spec.name = "mutated"  # type: ignore[misc]


def test_live_validator_boundary_cannot_drift_beyond_specs() -> None:
    """Every exported scalar/type boundary is enforced by the live wrapper."""

    for registration in list_effect_registrations():
        assert dict(registration.validator({})) == {}
        with pytest.raises(ValueError, match="unknown effect parameters"):
            registration.validator({"__metadata_drift_probe__": 1})
        for spec in registration.parameter_specs:
            with pytest.raises(ValueError, match=spec.name):
                registration.validator({spec.name: _wrong_kind_value(spec)})
            if spec.minimum is not None:
                with pytest.raises(ValueError, match=spec.name):
                    registration.validator({spec.name: spec.minimum - 1})
            if spec.maximum is not None:
                with pytest.raises(ValueError, match=spec.name):
                    registration.validator({spec.name: spec.maximum + 1})
            if spec.kind == "enum":
                with pytest.raises(ValueError, match=spec.name):
                    registration.validator({spec.name: "__invalid_enum_choice__"})


def _wrong_kind_value(spec: ParameterSpec) -> object:
    values: dict[str, object] = {
        "float": "not-a-number",
        "integer": 0.5,
        "boolean": 1,
        "enum": 1,
        "rgb": [0.0, 0.0],
        "scalar_source": 1,
        "color_timeline": [],
        "id_list": ["valid-id", 1],
        "object": [],
    }
    return values[spec.kind]


def test_exporter_is_live_registry_json() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "export_authoring_contract.py")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    exported = json.loads(result.stdout)
    expected = list_effect_registrations()
    assert exported["schema_version"] == 1
    assert [effect["id"] for effect in exported["effects"]] == [
        registration.id for registration in expected
    ]
    for item, registration in zip(exported["effects"], expected):
        assert item["common_params"] == list(registration.capability.common_params)
        assert item["common_controls"] == sorted(registration.capability.common_controls)
        assert [spec["name"] for spec in item["parameters"]] == [
            spec.name for spec in registration.parameter_specs
        ]


@pytest.mark.parametrize(
    ("effect_id", "parameter"),
    [
        ("color_wipe", "progress_source"),
        ("twinkle", "event_gate_source"),
        ("twinkle", "birth_gain_source"),
        ("history_stream", "sample_gain_source"),
    ],
)
def test_explicit_null_optional_scalar_sources_remain_show_compatible(
    effect_id: str,
    parameter: str,
) -> None:
    show = validate_show_data(
        {
            "schema_version": 2,
            "show": {
                "id": "null-scalar-source",
                "duration": 1.0,
                "cues": [
                    {
                        "id": "cue",
                        "start": 0.0,
                        "end": 1.0,
                        "target": {"type": "digital_strip", "id": "strip_11"},
                        "effect": {"mode": "fixed", "id": effect_id, "params": {parameter: None}},
                    }
                ],
            },
        },
        TargetCatalog(digital_strips={"strip_11"}),
    )

    assert show.cues[0].effect.params[parameter] is None
