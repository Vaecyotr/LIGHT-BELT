"""Focused Phase 33 tests for ScalarSource and external-progress color wipe."""

from __future__ import annotations

import math

import pytest

from light_engine.effects import create_effect, get_effect_registration
from light_engine.effects.scalar_source import ScalarSource
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import (
    Cue,
    EffectSpec,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    TransitionSpec,
    validate_show_data,
)
from light_engine.show.compositor import CueRenderJob


def _context(
    *,
    progress: float = 0.0,
    timestamp: float = 0.0,
    delta_time: float = 0.1,
    audio: AudioFeatures | None = None,
    **parameters: object,
) -> EffectContext:
    return EffectContext(
        timestamp=timestamp,
        delta_time=delta_time,
        sequence=1,
        audio_features=audio,
        mode_parameters={
            "strip_defs": [{"id": "strip", "pixel_count": 10}],
            "zone_defs": [],
            "cue_local_time": timestamp,
            "cue_progress": progress,
            "color": [1.0, 0.0, 0.0],
            **parameters,
        },
    )


def _lit_count(ctx: EffectContext, effect=None) -> int:
    effect = effect or create_effect("color_wipe")
    frame = effect.process(ctx)
    return sum(max(pixel) > 0.0 for pixel in frame.strips[0].pixels)


def test_scalar_source_exposes_only_existing_normalized_signals() -> None:
    spectrum = tuple(index / 15.0 for index in range(16))
    audio = AudioFeatures(
        timestamp=1.0,
        loudness=0.25,
        spectrum=spectrum,
        spectral_flux=0.4,
        onset=0.6,
        peak=True,
        silence=False,
    )
    ctx = _context(progress=0.75, audio=audio)

    assert ScalarSource("cue_progress").sample(ctx) == pytest.approx(0.75)
    assert ScalarSource("audio.rms").sample(ctx) == pytest.approx(0.25)
    assert ScalarSource("audio.loudness").sample(ctx) == pytest.approx(0.25)
    assert ScalarSource("audio.bass").sample(ctx) == pytest.approx(sum(spectrum[:3]) / 3)
    assert ScalarSource("audio.mid").sample(ctx) == pytest.approx(sum(spectrum[3:10]) / 7)
    assert ScalarSource("audio.treble").sample(ctx) == pytest.approx(sum(spectrum[10:]) / 6)
    assert ScalarSource("audio.spectral_flux").sample(ctx) == pytest.approx(0.4)
    assert ScalarSource("audio.onset").sample(ctx) == pytest.approx(0.6)
    assert ScalarSource("audio.peak").sample(ctx) == 1.0
    assert ScalarSource("audio.spectrum[7]").sample(ctx) == pytest.approx(7 / 15)


@pytest.mark.parametrize(
    "name",
    [
        "audio.raw_level",
        "audio.dominant_frequency",
        "audio.spectrum[-1]",
        "audio.spectrum[16]",
        "audio.rms * 2",
        "__import__('os')",
        "wled.sampleRaw",
    ],
)
def test_scalar_source_rejects_unbounded_unknown_or_expression_sources(name: str) -> None:
    with pytest.raises(ValueError, match="scalar source|unknown|index"):
        ScalarSource(name)


def test_scalar_source_returns_zero_when_runtime_audio_is_unavailable() -> None:
    assert ScalarSource("audio.loudness").sample(_context(audio=None)) == 0.0


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -0.01, 1.01])
def test_scalar_source_rejects_non_finite_or_out_of_range_runtime_values(
    invalid: float,
) -> None:
    audio = AudioFeatures(timestamp=0.0, loudness=0.5)
    audio.loudness = invalid
    with pytest.raises(ValueError, match=r"finite and in \[0, 1\]"):
        ScalarSource("audio.loudness").sample(_context(audio=audio))


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -0.01, 1.01])
def test_scalar_source_rejects_invalid_runtime_cue_progress(invalid: float) -> None:
    with pytest.raises(ValueError, match=r"finite and in \[0, 1\]"):
        ScalarSource("cue_progress").sample(_context(progress=invalid))


def test_color_wipe_fixed_external_progress_controls_extent() -> None:
    assert _lit_count(_context(progress=0.0, progress_source="cue_progress")) == 0
    assert _lit_count(_context(progress=0.5, progress_source="cue_progress")) == 5
    assert _lit_count(_context(progress=1.0, progress_source="cue_progress")) == 10


def test_color_wipe_accepts_fixed_audio_progress() -> None:
    audio = AudioFeatures(timestamp=0.0, loudness=0.4)
    assert _lit_count(
        _context(audio=audio, progress_source="audio.loudness")
    ) == 4


def test_show_v2_accepts_generic_external_progress_contract() -> None:
    show = validate_show_data(
        {
            "schema_version": 2,
            "show": {
                "id": "scalar-wipe",
                "duration": 10.0,
                "cues": [
                    {
                        "id": "wipe",
                        "start": 0.0,
                        "end": 10.0,
                        "target": {"type": "digital_strip", "id": "strip"},
                        "effect": {
                            "mode": "fixed",
                            "id": "color_wipe",
                            "params": {
                                "progress_source": "audio.loudness",
                                "slew_seconds": 0.25,
                            },
                        },
                    }
                ],
            },
        },
        TargetCatalog(digital_strips={"strip"}),
    )

    assert show.cues[0].effect.params == {
        "progress_source": "audio.loudness",
        "slew_seconds": 0.25,
    }


def test_color_wipe_external_progress_slew_is_symmetric_and_resettable() -> None:
    effect = create_effect("color_wipe")
    assert _lit_count(
        _context(progress=0.0, timestamp=0.0, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    ) == 0
    assert _lit_count(
        _context(progress=1.0, timestamp=0.1, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    ) == 1
    assert _lit_count(
        _context(progress=0.0, timestamp=0.2, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    ) == 0

    effect.reset()
    assert _lit_count(
        _context(progress=1.0, timestamp=0.3, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    ) == 10


def test_color_wipe_slew_has_30_60_fps_equivalence() -> None:
    def render_at(delta_time: float, frame_count: int) -> int:
        effect = create_effect("color_wipe")
        _lit_count(
            _context(
                progress=0.0,
                timestamp=0.0,
                delta_time=delta_time,
                progress_source="cue_progress",
                slew_seconds=1.0,
            ),
            effect,
        )
        result = 0
        for frame_index in range(1, frame_count + 1):
            result = _lit_count(
                _context(
                    progress=1.0,
                    timestamp=frame_index * delta_time,
                    delta_time=delta_time,
                    progress_source="cue_progress",
                    slew_seconds=1.0,
                ),
                effect,
            )
        return result

    assert render_at(1 / 30, 15) == render_at(1 / 60, 30) == 5


def test_color_wipe_backward_seek_rebases_slew_without_future_state() -> None:
    effect = create_effect("color_wipe")
    _lit_count(
        _context(progress=0.0, timestamp=1.0, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    )
    _lit_count(
        _context(progress=1.0, timestamp=1.1, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    )

    assert _lit_count(
        _context(progress=0.6, timestamp=0.5, progress_source="cue_progress", slew_seconds=1.0),
        effect,
    ) == 6


def test_color_wipe_cue_progress_and_common_origin_advance_across_virtual_path() -> None:
    strips = (ZoneDef(id="a", pixel_count=2), ZoneDef(id="b", pixel_count=3))
    path = build_virtual_paths(
        [
            {
                "id": "joined",
                "segments": [
                    {
                        "strip_id": "a",
                        "source_start": 0,
                        "pixel_count": 2,
                        "direction": "forward",
                    },
                    {
                        "strip_id": "b",
                        "source_start": 0,
                        "pixel_count": 3,
                        "direction": "forward",
                    },
                ],
            }
        ],
        {"a": 2, "b": 3},
    )[0]
    resolver = TargetResolver((), strips, virtual_paths=(path,))
    cue = Cue(
        id="wipe",
        start=0.0,
        end=10.0,
        target=TargetSelector("virtual_path", id="joined"),
        origin="end",
        effect=EffectSpec(
            mode="fixed",
            name="color_wipe",
            parameters={"progress_source": "cue_progress", "color": [1.0, 0.0, 0.0]},
        ),
        transition=TransitionSpec(blend="replace"),
    )

    contribution = CueRenderJob(cue, 0, resolver).render(
        EffectContext(timestamp=6.0, delta_time=0.1, sequence=7)
    )

    assert [item.strip_id for item in contribution.digital] == ["a", "b"]
    assert contribution.digital[0].pixels == ((0.0, 0.0, 0.0),) * 2
    assert contribution.digital[1].pixels == ((1.0, 0.0, 0.0),) * 3


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, -0.1])
def test_color_wipe_validator_rejects_invalid_slew(invalid: float) -> None:
    validator = get_effect_registration("color_wipe").validator
    with pytest.raises(ValueError, match="slew_seconds"):
        validator({"slew_seconds": invalid})


def test_color_wipe_validator_rejects_invalid_progress_source() -> None:
    validator = get_effect_registration("color_wipe").validator
    with pytest.raises(ValueError, match="progress_source"):
        validator({"progress_source": "audio.raw_level"})
