"""Focused closeout contracts for Phase 32 native effects."""

from __future__ import annotations

from light_engine.effects import create_effect
from light_engine.models import AudioFeatures, EffectContext


def _ripple_context(*, time: float, audio: AudioFeatures) -> EffectContext:
    return EffectContext(
        timestamp=time,
        sequence=1,
        delta_time=0.25,
        audio_features=audio,
        mode_parameters={
            "cue_local_time": time,
            "strip_defs": ({"id": "strip", "pixel_count": 8},),
            "wave_speed_pps": 1.0,
            "wave_width_px": 4.0,
            "decay_seconds": 2.0,
            "color": [1.0, 1.0, 1.0],
        },
    )


def test_silence_blocks_new_ripple_births_but_existing_wave_keeps_decaying() -> None:
    effect = create_effect("onset_ripple")
    born = effect.process(
        _ripple_context(
            time=0.0,
            audio=AudioFeatures(
                timestamp=0.0, onset=1.0, peak=True, loudness=1.0, silence=False
            ),
        )
    )
    wave_count = len(effect._waves)

    silent = effect.process(
        _ripple_context(
            time=0.25,
            audio=AudioFeatures(
                timestamp=0.25, onset=1.0, peak=True, loudness=1.0, silence=True
            ),
        )
    )

    assert wave_count == len(effect._waves) == 1
    assert any(pixel != (0.0, 0.0, 0.0) for pixel in silent.strips[0].pixels)
    assert silent.strips[0].pixels != born.strips[0].pixels
