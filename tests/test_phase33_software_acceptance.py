"""Current catalog and bounded-authoring contracts introduced in Phase 33."""

from __future__ import annotations

import pytest

from light_engine.effects import list_effects
from light_engine.effects.scalar_source import ScalarSource


_PHASE32_EFFECTS = {
    "static",
    "breath",
    "color_wave",
    "chase",
    "comet",
    "audio_pulse",
    "bass_pulse",
    "spectrum",
    "video_ambient",
    "video_audio_fusion",
    "calm",
    "color_wipe",
    "twinkle",
    "demo",
    "step_pulse",
    "single_dot",
    "theater_phase",
    "flowing_bands",
    "onset_ripple",
    "heat_fire",
}


def test_phase35_adds_only_coherent_noise_field_after_phase33() -> None:
    current = set(list_effects())
    assert current - _PHASE32_EFFECTS == {"history_stream", "coherent_noise_field"}
    assert _PHASE32_EFFECTS <= current


def test_phase33_does_not_register_forbidden_frameworks_or_wled_aliases() -> None:
    forbidden = {
        "audio_reactive_palette",
        "multi_comet",
        "juggle",
        "sinelon",
        "ripple_peak",
        "percent",
        "puddles",
        "freqwave",
        "dj_light",
    }
    assert forbidden.isdisjoint(list_effects())


@pytest.mark.parametrize(
    "source",
    (
        "audio.raw_level",
        "audio.dominant_frequency",
        "audio.dominant_magnitude",
        "audio.rms * 2",
        "wled.sampleRaw",
    ),
)
def test_scalar_source_has_no_unbounded_expression_or_wled_semantics(source: str) -> None:
    with pytest.raises(ValueError):
        ScalarSource(source)
