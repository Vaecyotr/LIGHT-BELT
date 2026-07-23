from copy import deepcopy

import pytest

from light_engine.show import (
    AudioModulationChannelSpec,
    ShowValidationError,
    TargetCatalog,
    validate_show_data,
)


def _channel(source: str = "music.energy") -> dict[str, float | str]:
    return {
        "source": source,
        "amount": 0.30,
        "min_multiplier": 0.75,
        "max_multiplier": 1.30,
        "smoothing_seconds": 0.25,
    }


def _show() -> dict:
    return {
        "schema_version": 1,
        "show": {
            "id": "audio-modulation",
            "duration": 10.0,
            "cues": [
                {
                    "id": "fixed",
                    "start": 0.0,
                    "end": 10.0,
                    "target": {"type": "digital_strip", "id": "strip"},
                    "effect": {"mode": "fixed", "name": "comet"},
                    "audio_modulation": {
                        "enabled": True,
                        "brightness": _channel("music.energy"),
                        "speed": _channel("music.beat_strength"),
                        "intensity": _channel("audio.bass"),
                    },
                }
            ],
        },
    }


def _catalog() -> TargetCatalog:
    return TargetCatalog(digital_strips=("strip",))


def test_audio_modulation_loads_into_typed_cue_models() -> None:
    show = validate_show_data(_show(), _catalog())

    modulation = show.cues[0].audio_modulation
    assert modulation is not None
    assert modulation.enabled is True
    assert isinstance(modulation.brightness, AudioModulationChannelSpec)
    assert modulation.brightness.source == "music.energy"
    assert modulation.speed is not None
    assert modulation.speed.source == "music.beat_strength"
    assert modulation.intensity is not None
    assert modulation.intensity.source == "audio.bass"


@pytest.mark.parametrize(
    ("mutate", "path", "reason"),
    [
        (
            lambda data: data["show"]["cues"][0]["audio_modulation"].update({"hue": _channel()}),
            "show.cues[0].audio_modulation.hue",
            "unknown field",
        ),
        (
            lambda data: data["show"]["cues"][0]["audio_modulation"]["brightness"].update({"source": "music.energy_level"}),
            "show.cues[0].audio_modulation.brightness.source",
            "must be one of",
        ),
        (
            lambda data: data["show"]["cues"][0]["audio_modulation"]["speed"].pop("amount"),
            "show.cues[0].audio_modulation.speed.amount",
            "is required",
        ),
        (
            lambda data: data["show"]["cues"][0]["audio_modulation"]["intensity"].update({"min_multiplier": 1.5, "max_multiplier": 1.0}),
            "show.cues[0].audio_modulation.intensity.max_multiplier",
            "must be >= min_multiplier",
        ),
    ],
)
def test_audio_modulation_validation_reports_exact_yaml_paths(mutate, path: str, reason: str) -> None:
    data = deepcopy(_show())
    mutate(data)

    with pytest.raises(ShowValidationError) as exc_info:
        validate_show_data(data, _catalog())

    assert exc_info.value.path == path
    assert reason in exc_info.value.reason
