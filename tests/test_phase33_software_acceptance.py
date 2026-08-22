"""Phase 33 catalog, non-goal, and immutable-asset acceptance gates."""

from __future__ import annotations

import hashlib
from pathlib import Path

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
_ENERGY_WAKEUP_SHA256 = (
    "627d23a4c73e66f1913c7b5cbb15cf1b16926e6772289237165535a2278c142d"
)


def test_history_stream_is_the_only_phase33_effect_id() -> None:
    current = set(list_effects())
    assert current - _PHASE32_EFFECTS == {"history_stream"}
    assert _PHASE32_EFFECTS <= current


def test_phase33_does_not_register_forbidden_frameworks_or_wled_aliases() -> None:
    forbidden = {
        "coherent_noise_field",
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


def test_immutable_energy_wakeup_asset_is_byte_identical() -> None:
    payload = Path("assets/energy-wakeup/energy-wakeup.yaml").read_bytes()
    assert hashlib.sha256(payload).hexdigest() == _ENERGY_WAKEUP_SHA256
