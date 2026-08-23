"""Focused Host/API contract tests for the runtime effect Registry."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
import yaml

from host_services import engine_adapter
from host_services.app_v1 import APP_V1_EFFECTS, APP_V1_EFFECT_TYPES
from host_services.schemas import EffectCommonParams
from light_engine.effects import list_effects


_OPENAPI_PATH = Path("docs/reference/host-api-v1.openapi.yaml")


class _CommonParams:
    def __init__(self, *, color=None, speed=None, intensity=None):
        self.color = color
        self.speed = speed
        self.intensity = intensity

    def model_dump(self, *, exclude_none: bool = False) -> dict:
        values = {
            "color": (
                {"r": self.color.r, "g": self.color.g, "b": self.color.b}
                if self.color is not None
                else None
            ),
            "speed": self.speed,
            "intensity": self.intensity,
        }
        if exclude_none:
            return {key: value for key, value in values.items() if value is not None}
        return values


class _RecordingAdapter:
    def __init__(self):
        self.commands: list[list[dict]] = []

    def on_manual_command(self, states: list[dict]) -> None:
        self.commands.append(states)


def test_host_capabilities_use_the_frozen_app_projection() -> None:
    effects = engine_adapter.get_capabilities()["effects"]

    assert effects == list(APP_V1_EFFECTS)
    assert set(list_effects()) > {effect["effect_type"] for effect in effects}


def test_static_openapi_effect_contract_uses_the_frozen_app_v1_list() -> None:
    document = yaml.safe_load(_OPENAPI_PATH.read_text(encoding="utf-8"))
    schema = document["components"]["schemas"]["EffectType"]

    assert schema["enum"] == list(APP_V1_EFFECT_TYPES)
    assert "x-effect-registry" not in schema


def test_pydantic_request_schema_does_not_publish_the_internal_registry() -> None:
    pytest.importorskip("pydantic")
    from host_services.schemas import EffectsSetRequest, SceneEntry

    effects_schema = EffectsSetRequest.model_json_schema()
    scene_schema = SceneEntry.model_json_schema()

    assert "enum" not in effects_schema["properties"]["effect_type"]
    assert "enum" not in scene_schema["properties"]["effect_type"]


def test_host_schema_source_has_no_effect_id_list_or_registry_schema_export() -> None:
    source = Path("host_services/schemas.py").read_text(encoding="utf-8")
    assert "VALID_EFFECT_TYPES" not in source
    assert "list_effects" not in source


def test_host_accepts_every_registered_effect_and_rejects_unknown_ids(
    monkeypatch,
) -> None:
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    monkeypatch.setattr(
        engine_adapter,
        "_valid_target_ids",
        frozenset({"all", "strip_11", "starry_sky"}),
    )

    for effect_type in list_effects():
        data, error = engine_adapter.effects_set("strip_11", effect_type, 0)
        assert error is None
        assert data["effect_type"] == effect_type

    data, error = engine_adapter.effects_set("strip_11", "not_registered", 0)
    assert error == "INVALID_ARGUMENT"
    assert data["error_detail"]["field"] == "effect_type"


def test_host_uses_registry_validator_for_manual_and_scene_requests(
    monkeypatch,
) -> None:
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    monkeypatch.setattr(
        engine_adapter,
        "_valid_target_ids",
        frozenset({"all", "strip_11", "starry_sky"}),
    )
    monkeypatch.setattr(engine_adapter, "_save_scenes", lambda: None)
    monkeypatch.setattr(engine_adapter, "_scenes", {})

    data, error = engine_adapter.effects_set(
        "strip_11", "color_wipe", 0, effect_params={"speed": 1001.0}
    )
    assert error == "INVALID_ARGUMENT"
    assert data["error_detail"]["field"] == "effect_params"
    assert "speed must be in" in data["error_detail"]["reason"]

    data, error = engine_adapter.scene_save(
        "registry-scene",
        "Registry scene",
        None,
        [
            {
                "target_id": "strip_11",
                "effect_type": "color_wipe",
                "effect_params": {"unknown": 1},
            }
        ],
    )
    assert error == "INVALID_ARGUMENT"
    assert data["error_detail"]["entry_index"] == 0
    assert data["error_detail"]["field"] == "effect_params"

    monkeypatch.setattr(
        engine_adapter,
        "_scenes",
        {
            "persisted-invalid": {
                "name": "Persisted invalid",
                "entries": [
                    {
                        "target_id": "strip_11",
                        "effect_type": "color_wipe",
                        "effect_params": {"speed": 1001.0},
                    }
                ],
            }
        },
    )
    data, error = engine_adapter.scene_apply("persisted-invalid", None)
    assert error == "INVALID_ARGUMENT"
    assert data["error_detail"]["field"] == "effect_params"


def test_manual_command_preserves_common_controls_and_effect_params(
    monkeypatch,
) -> None:
    recorder = _RecordingAdapter()
    monkeypatch.setattr(engine_adapter, "_real_adapter", recorder)
    monkeypatch.setattr(engine_adapter, "_manual_targets", {})
    monkeypatch.setattr(engine_adapter, "_push_brightness_scale", lambda: None)
    monkeypatch.setattr(engine_adapter, "_mark_devices_output", lambda: None)
    monkeypatch.setattr(
        engine_adapter,
        "_valid_target_ids",
        frozenset({"all", "strip_11", "starry_sky"}),
    )
    params = _CommonParams(
        color=SimpleNamespace(r=255, g=128, b=0),
        speed=1.2,
        intensity=2.5,
    )

    data, error = engine_adapter.effects_set(
        "strip_11",
        "color_wipe",
        0,
        params=params,
        effect_params={"speed": 25.0},
    )

    assert error is None
    assert data["params"]["speed"] == pytest.approx(1.2)
    assert data["params"]["intensity"] == pytest.approx(2.5)
    assert data["effect_params"] == {"speed": 25.0}
    assert recorder.commands == [
        [
            {
                "target_id": "strip_11",
                "effect_type": "color_wipe",
                "color": [1.0, 128 / 255, 0.0],
                "speed": 1.2,
                "intensity": 2.5,
                "effect_params": {"speed": 25.0},
            }
        ]
    ]


def test_host_common_multipliers_match_show_nonnegative_finite_contract() -> None:
    params = EffectCommonParams(speed=1.2, intensity=2.5)
    assert params.speed == pytest.approx(1.2)
    assert params.intensity == pytest.approx(2.5)

    for field, value in (("speed", -0.1), ("intensity", float("nan"))):
        with pytest.raises(ValidationError):
            EffectCommonParams(**{field: value})
