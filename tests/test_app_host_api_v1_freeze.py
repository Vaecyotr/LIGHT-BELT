"""Gate 0 regression guards for the released APP-facing Host API V1 surface."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from host_services import engine_adapter
from host_services.app_v1 import (
    APP_V1_EFFECTS,
    APP_V1_EFFECT_TYPES,
    APP_V1_SUPPORTS,
    APP_V1_WS_MESSAGE_TYPES,
    capabilities,
)
from host_services.main import app


_ROOT = Path(__file__).resolve().parents[1]
_MARKDOWN = _ROOT / "docs" / "reference" / "host-api-v1.md"
_OPENAPI = _ROOT / "docs" / "reference" / "host-api-v1.openapi.yaml"
_HISTORICAL_BASELINE_FIXTURE = _ROOT / "tests" / "fixtures" / "app_v1" / "pre_phase32_0380e4e.json"

_REST_PATHS = {
    "/api/v1/status",
    "/api/v1/auth/pair",
    "/api/v1/auth/refresh",
    "/api/v1/session/ws-ticket",
    "/api/v1/state",
    "/api/v1/shows",
    "/api/v1/capabilities",
    "/api/v1/playback/play",
    "/api/v1/playback/pause",
    "/api/v1/playback/resume",
    "/api/v1/playback/stop",
    "/api/v1/playback/seek",
    "/api/v1/playback/state",
    "/api/v1/playback/reset",
    "/api/v1/lights/set",
    "/api/v1/effects/set",
    "/api/v1/audio",
    "/api/v1/audio/set",
    "/api/v1/scenes",
    "/api/v1/scenes/save",
    "/api/v1/scenes/apply",
    "/api/v1/scenes/delete",
    "/api/v1/brightness",
    "/api/v1/brightness/set",
}

_FORBIDDEN_INTERNAL_TERMS = (
    "coherent_noise_field",
    "parameter_modulation",
    "parameterspec",
    "modulatable",
    "colorsource",
    "spatial_palette",
    "video_average",
    "video_dominant",
    "audio_spectrum_palette",
    "dominant_frequency_palette",
    "branch lifecycle",
    "start_on_release",
    "pre_roll",
)


def _documented_operations() -> dict[str, set[str]]:
    return {
        path: {method.lower()}
        for method, path in re.findall(
            r"^### (GET|POST) (/api/v1/[^\s]+)",
            _MARKDOWN.read_text(encoding="utf-8"),
            re.M,
        )
    }


def _openapi_refs(value):
    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        for child in value.values():
            yield from _openapi_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from _openapi_refs(child)


def _resolve_openapi_ref(document: dict, ref: str):
    assert ref.startswith("#/")
    value: object = document
    for part in ref[2:].split("/"):
        assert isinstance(value, dict)
        value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


def test_documented_rest_paths_match_openapi_and_runtime_routes() -> None:
    document = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    markdown_operations = _documented_operations()
    openapi_operations = {
        f"/api/v1{path}": set(operations)
        for path, operations in document["paths"].items()
    }
    runtime_operations = {
        endpoint.path: {method.lower() for method in endpoint.methods if method != "HEAD"}
        for route in app.routes
        for endpoint in getattr(getattr(route, "original_router", None), "routes", ())
        if endpoint.path.startswith("/api/v1/")
    }

    assert set(markdown_operations) == _REST_PATHS
    assert set(openapi_operations) == _REST_PATHS
    assert set(runtime_operations) == _REST_PATHS
    assert markdown_operations == openapi_operations == runtime_operations


def test_capabilities_freeze_effects_and_events_but_preserve_target_discovery() -> None:
    data = engine_adapter.get_capabilities()

    assert data["targets"] == engine_adapter._capability_targets
    assert data["effects"] == list(APP_V1_EFFECTS)
    assert data["websocket"]["message_types"] == list(APP_V1_WS_MESSAGE_TYPES)
    assert data["supports"] == APP_V1_SUPPORTS
    assert set(APP_V1_EFFECT_TYPES) == {
        "static", "breath", "chase", "color_wave", "comet", "audio_pulse",
        "bass_pulse", "spectrum", "video_ambient", "video_audio_fusion", "calm",
        "demo", "twinkle",
    }
    assert all(set(effect) == {"effect_type", "name", "params", "effect_params"} for effect in data["effects"])
    assert all(set(target) <= {"target_id", "name", "supported_effects"} for target in data["targets"])
    assert "coherent_noise_field" not in {effect["effect_type"] for effect in data["effects"]}


def test_layout_target_discovery_cannot_leak_physical_metadata() -> None:
    projected = capabilities([
        {
            "target_id": "strip_11",
            "name": "屏幕上方",
            "supported_effects": ["static"],
            "host": "192.168.31.201",
            "node_id": 1,
            "transport": "udp_v3",
        }
    ])

    assert projected["targets"] == [{
        "target_id": "strip_11",
        "name": "屏幕上方",
        "supported_effects": ["static"],
    }]


def test_openapi_captures_released_v12_paths_and_public_capability_shape() -> None:
    document = yaml.safe_load(_OPENAPI.read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]

    for path in ("/playback/state", "/playback/reset", "/brightness", "/brightness/set"):
        assert path in document["paths"]
    assert "effect_params" in schemas["CapabilityEffect"]["properties"]
    assert "x-effect-registry" not in schemas["EffectType"]
    assert schemas["EffectType"]["enum"] == list(APP_V1_EFFECT_TYPES)
    assert schemas["WsMessageType"]["enum"] == list(APP_V1_WS_MESSAGE_TYPES)
    assert set(schemas["CapabilitySupports"]["required"]) == set(APP_V1_SUPPORTS)
    assert set(schemas["CapabilitySupports"]["properties"]) == set(APP_V1_SUPPORTS)
    assert schemas["PlaybackStateData"]["required"] == [
        "playback_state", "show", "position_ms", "duration_ms", "brightness_scale", "audio"
    ]
    assert schemas["BrightnessSetRequest"]["required"] == ["brightness_scale"]
    assert schemas["WsEnvelope"]["required"] == ["type", "timestamp", "sequence", "data"]
    for ref in _openapi_refs(document):
        _resolve_openapi_ref(document, ref)


def test_host_contract_artifacts_exclude_phase35_to_39_authoring_internals() -> None:
    contract_text = _MARKDOWN.read_text(encoding="utf-8") + _OPENAPI.read_text(encoding="utf-8")
    generated_openapi = json.dumps(app.openapi(), sort_keys=True)

    for term in _FORBIDDEN_INTERNAL_TERMS:
        assert term not in contract_text.lower()
        assert term not in generated_openapi.lower()


def test_app_v1_facade_matches_pre_phase32_historical_baseline() -> None:
    baseline = json.loads(_HISTORICAL_BASELINE_FIXTURE.read_text(encoding="utf-8"))
    provenance = baseline["provenance"]
    assert provenance["source_repository"] == "https://github.com/zxlzzz/LIGHT-BELT"
    assert provenance["source_commit"] == "0380e4e1ecb926148d9afc07b7f95f6ad0aa4c6b"
    assert provenance["source_short_commit"] == "0380e4e"
    assert provenance["source_date"] == "2026-08-19"
    assert "pre-Phase32" in provenance["reason"]

    assert list(APP_V1_EFFECTS) == baseline["app_visible_effects"]
    assert list(APP_V1_WS_MESSAGE_TYPES) == baseline["websocket_message_types"]
    assert APP_V1_SUPPORTS == baseline["supports"]
    assert _REST_PATHS == set(baseline["rest_paths"])
    assert list(APP_V1_EFFECT_TYPES) == [
        e["effect_type"] for e in baseline["app_visible_effects"]
    ] + baseline["special_effect_types"]

