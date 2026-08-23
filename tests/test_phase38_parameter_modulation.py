"""Phase 38 safe effect-parameter modulation acceptance tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from light_engine.effects import validate_effect_params
from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame
from light_engine.show import (
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    CueBranchSpec,
    CueRenderJob,
    EffectSpec,
    ParameterModulationBindingSpec,
    ParameterModulationSpec,
    ShowValidationError,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
    validate_show_data,
)
from light_engine.show.parameter_modulation import CueParameterModulator


class _RecordingEffect(BaseEffect):
    def __init__(self, name: str):
        super().__init__(name)
        self.values: list[float] = []
        self.controls: list[tuple[float, float]] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.values.append(float(ctx.mode_parameters["contrast"]))
        self.controls.append((ctx.speed, ctx.intensity))
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=definition["id"],
                    pixel_count=definition["pixel_count"],
                    pixels=[(self.values[-1] / 4.0, 0.0, 0.0)] * definition["pixel_count"],
                )
                for definition in ctx.mode_parameters["strip_defs"]
            ],
        )


def _audio(value: float, **raw: float) -> AudioFeatures:
    spectrum = tuple(index / 15.0 for index in range(16))
    return AudioFeatures(
        timestamp=0.0,
        rms=value,
        loudness=value,
        bass=value,
        mid=value,
        treble=value,
        spectral_flux=value,
        onset=value,
        peak=value >= 0.5,
        spectrum=spectrum,
        silence=False,
        **raw,
    )


def _ctx(
    timestamp: float,
    value: float | None,
    *,
    delta: float = 0.1,
    progress: float = 0.0,
    raw: dict[str, float] | None = None,
) -> EffectContext:
    return EffectContext(
        timestamp=timestamp,
        delta_time=delta,
        sequence=round(timestamp / delta) if timestamp else 0,
        audio_features=None if value is None else _audio(value, **(raw or {})),
        mode_parameters={"cue_progress": progress},
    )


def _binding(**overrides: object) -> ParameterModulationBindingSpec:
    values: dict[str, object] = {
        "target": "contrast",
        "mode": "modulate",
        "source": "audio.bass",
        "output_min": 0.8,
        "output_max": 1.6,
    }
    values.update(overrides)
    return ParameterModulationBindingSpec(**values)  # type: ignore[arg-type]


def _modulator(binding: ParameterModulationBindingSpec) -> CueParameterModulator:
    return CueParameterModulator(
        "coherent_noise_field",
        {"contrast": 2.0},
        ParameterModulationSpec((binding,)),
    )


def test_modulate_and_drive_formulas_are_exact_and_validator_checked() -> None:
    modulated = _modulator(_binding(source="audio.rms")).apply(_ctx(0.0, 0.25), {"contrast": 2.0})
    assert modulated.values["contrast"] == pytest.approx(2.0)

    driven = _modulator(
        _binding(source="audio.rms", mode="drive", output_min=0.5, output_max=2.5, fallback=1.0)
    ).apply(_ctx(0.0, 0.25), {"contrast": 2.0})
    assert driven.values["contrast"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("audio.rms", 0.4),
        ("audio.loudness", 0.4),
        ("audio.bass", 1 / 15),
        ("audio.mid", sum(range(3, 10)) / 15 / 7),
        ("audio.treble", sum(range(10, 16)) / 15 / 6),
        ("audio.spectral_flux", 0.4),
        ("audio.onset", 0.4),
        ("audio.peak", 0.0),
        ("audio.spectrum[7]", 7 / 15),
    ],
)
def test_normalized_audio_sources(source: str, expected: float) -> None:
    result = _modulator(
        _binding(source=source, output_min=0.0, output_max=1.0)
    ).apply(_ctx(0.0, 0.4), {"contrast": 2.0})
    assert result.values["contrast"] == pytest.approx(2.0 * expected)


def test_cue_progress_is_available_without_audio() -> None:
    result = _modulator(
        _binding(source="cue_progress", mode="drive", output_min=0.5, output_max=2.5)
    ).apply(_ctx(0.0, None, progress=0.75), {"contrast": 2.0})
    assert result.values["contrast"] == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("source", "field", "raw_value", "expected"),
    [
        ("audio.raw_level", "raw_level", 15.0, 0.5),
        ("audio.dominant_frequency", "dominant_frequency", 300.0, 0.25),
        ("audio.dominant_magnitude", "dominant_magnitude", 8.0, 0.75),
    ],
)
def test_raw_sources_use_explicit_authored_normalization(
    source: str, field: str, raw_value: float, expected: float
) -> None:
    ranges = {
        "raw_level": (10.0, 20.0),
        "dominant_frequency": (200.0, 600.0),
        "dominant_magnitude": (2.0, 10.0),
    }
    minimum, maximum = ranges[field]
    result = _modulator(
        _binding(
            source=source,
            input_min=minimum,
            input_max=maximum,
            output_min=0.0,
            output_max=1.0,
        )
    ).apply(
        _ctx(0.0, 0.0, raw={field: raw_value}),
        {"contrast": 2.0},
    )
    assert result.values["contrast"] == pytest.approx(2.0 * expected)


def test_absent_audio_uses_base_for_modulate_and_explicit_drive_fallback() -> None:
    base = _modulator(_binding()).apply(_ctx(0.0, None), {"contrast": 2.0})
    assert base.values["contrast"] == 2.0
    driven = _modulator(
        _binding(mode="drive", output_min=0.5, output_max=2.5, fallback=1.25)
    ).apply(_ctx(0.0, None), {"contrast": 2.0})
    assert driven.values["contrast"] == 1.25


def test_explicit_missing_source_fallback_retains_smoothing_history() -> None:
    modulator = _modulator(
        _binding(fallback=1.6, smoothing_seconds=1.0)
    )
    first = modulator.apply(_ctx(0.0, None, delta=0.25), {"contrast": 2.0})
    second = modulator.apply(_ctx(0.25, None, delta=0.25), {"contrast": 2.0})
    assert 2.0 < first.values["contrast"] < second.values["contrast"] < 3.2


def test_exponential_smoothing_is_frame_rate_equivalent_and_reset_replays() -> None:
    binding = _binding(output_min=1.0, output_max=2.0, smoothing_seconds=0.5)

    def run(fps: int, modulator: CueParameterModulator) -> float:
        result = None
        for index in range(fps):
            result = modulator.apply(
                _ctx(index / fps, 1.0, delta=1 / fps),
                {"contrast": 2.0},
            )
        assert result is not None
        return float(result.values["contrast"])

    at_30 = run(30, _modulator(binding))
    replayable = _modulator(binding)
    at_60 = run(60, replayable)
    assert at_30 == pytest.approx(at_60, abs=1e-12)
    replayable.reset()
    assert run(60, replayable) == pytest.approx(at_60, abs=1e-12)


def _show(binding: dict[str, object], *, params: dict[str, object] | None = None):
    return {
        "schema_version": 2,
        "show": {
            "id": "parameter-modulation",
            "duration": 2.0,
            "cues": [
                {
                    "id": "cue",
                    "start": 0.0,
                    "end": 2.0,
                    "target": {"type": "digital_strip", "id": "strip"},
                    "effect": {
                        "mode": "fixed",
                        "id": "coherent_noise_field",
                        "params": params if params is not None else {"contrast": 2.0},
                    },
                    "parameter_modulation": [binding],
                }
            ],
        },
    }


def _valid_binding(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "target": "contrast",
        "mode": "modulate",
        "source": "audio.bass",
        "output_min": 0.8,
        "output_max": 1.5,
        "smoothing_seconds": 0.1,
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda binding: binding.update(target="speed"), "audio_modulation"),
        (lambda binding: binding.update(target="feature_size_px"), "modulatable"),
        (lambda binding: binding.update(target="waveform"), "unknown effect parameter"),
        (lambda binding: binding.update(source="audio.spectrum[16]"), "index"),
        (lambda binding: binding.update(source="audio.raw_level"), "input_min"),
        (lambda binding: binding.update(mode="drive"), "fallback"),
        (lambda binding: binding.update(output_min=2.0, output_max=1.0), "output_max"),
    ],
)
def test_loader_rejects_unsafe_or_incomplete_bindings(mutate, match: str) -> None:
    binding = _valid_binding()
    mutate(binding)
    with pytest.raises(ShowValidationError, match=match):
        validate_show_data(_show(binding), TargetCatalog(digital_strips={"strip"}))


def test_loader_rejects_missing_modulate_base_duplicate_and_adaptive() -> None:
    with pytest.raises(ShowValidationError, match="authored base"):
        validate_show_data(
            _show(_valid_binding(), params={}), TargetCatalog(digital_strips={"strip"})
        )
    duplicate = _show(_valid_binding())
    duplicate["show"]["cues"][0]["parameter_modulation"].append(_valid_binding())
    with pytest.raises(ShowValidationError, match="duplicate target"):
        validate_show_data(duplicate, TargetCatalog(digital_strips={"strip"}))
    adaptive = _show(_valid_binding())
    adaptive["show"]["cues"][0]["effect"] = {
        "mode": "adaptive",
        "allowed": {"silence": "calm"},
        "fallback": "calm",
    }
    with pytest.raises(ShowValidationError, match="fixed effect"):
        validate_show_data(adaptive, TargetCatalog(digital_strips={"strip"}))


def test_pre_roll_consumes_actual_historical_audio_and_reset_replays() -> None:
    resolver = TargetResolver(
        (),
        (
            ZoneDef(id="a", pixel_count=2),
            ZoneDef(id="b", pixel_count=2),
            ZoneDef(id="branch", pixel_count=2),
        ),
    )
    resolver.register_authored_paths(
        (VirtualPathSpec("path", (TargetSelector("digital_strip", id="a"), TargetSelector("digital_strip", id="b"))),)
    )
    modulation = ParameterModulationSpec(
        (_binding(source="audio.rms", output_min=1.0, output_max=2.0, smoothing_seconds=0.5),)
    )
    cue = Cue(
        id="parent",
        start=0.0,
        end=2.0,
        target=TargetSelector("virtual_path", id="path"),
        effect=EffectSpec("fixed", id="coherent_noise_field", params={"contrast": 2.0}),
        parameter_modulation=modulation,
        branches=(
            CueBranchSpec(
                path_id="path",
                after_target_id="a",
                target=TargetSelector("digital_strip", id="branch"),
                lifecycle="pre_roll",
            ),
        ),
    )
    created: list[_RecordingEffect] = []

    def factory(name: str) -> _RecordingEffect:
        effect = _RecordingEffect(name)
        created.append(effect)
        return effect

    parent = CueRenderJob(cue, 0, resolver, effect_factory=factory)
    reference = CueRenderJob(
        replace(cue, id="parent:branch:0", target=TargetSelector("digital_strip", id="branch"), branches=()),
        1,
        resolver,
        effect_factory=factory,
    )

    def play() -> tuple[float, ...]:
        values = (0.1, 0.8, 0.3)
        release = reference_output = None
        for index, audio in enumerate(values):
            ctx = _ctx(index * 0.5, audio, delta=0.5)
            parent.render(ctx)
            branches = parent.render_branches(ctx)
            reference_output = reference.render(ctx)
            if index == 2:
                release = branches[0]
            else:
                assert branches == ()
        assert release == reference_output
        return tuple(created[-2].values)

    history = play()
    assert history[0] < history[1]
    assert history[2] < history[1]
    parent.reset()
    reference.reset()
    assert play() == pytest.approx(history)


def test_legacy_audio_modulation_and_parameter_modulation_coexist() -> None:
    channel = AudioModulationChannelSpec(
        source="audio.rms",
        amount=0.5,
        min_multiplier=0.5,
        max_multiplier=1.5,
        smoothing_seconds=0.0,
    )
    cue = Cue(
        id="coexist",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(
            "fixed",
            id="coherent_noise_field",
            speed=1.2,
            intensity=0.5,
            params={"contrast": 2.0},
        ),
        audio_modulation=AudioModulationSpec(speed=channel, intensity=channel),
        parameter_modulation=ParameterModulationSpec(
            (_binding(source="audio.rms"),)
        ),
    )
    effect = _RecordingEffect("coherent_noise_field")
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip", pixel_count=2),)),
        effect=effect,
    )
    context = _ctx(0.5, 0.75)
    context.speed = 2.0
    context.intensity = 3.0
    job.render(context)

    assert effect.controls == [pytest.approx((3.0, 1.875))]
    assert effect.values == [pytest.approx(2.8)]


def test_loader_rejects_joint_relationally_invalid_output_corner() -> None:
    show = _show(_valid_binding())
    cue = show["show"]["cues"][0]
    cue["effect"] = {
        "mode": "fixed",
        "id": "flowing_bands",
        "params": {"base_gain": 0.2, "highlight_gain": 0.8},
    }
    cue["parameter_modulation"] = [
        {
            "target": "base_gain",
            "mode": "drive",
            "source": "cue_progress",
            "output_min": 0.1,
            "output_max": 0.7,
        },
        {
            "target": "highlight_gain",
            "mode": "drive",
            "source": "cue_progress",
            "output_min": 0.3,
            "output_max": 0.9,
        },
    ]
    with pytest.raises(ShowValidationError, match="output combination"):
        validate_show_data(show, TargetCatalog(digital_strips={"strip"}))


def test_loader_checks_implicit_base_fallback_against_other_live_binding() -> None:
    show = _show(_valid_binding())
    cue = show["show"]["cues"][0]
    cue["effect"] = {
        "mode": "fixed",
        "id": "flowing_bands",
        "params": {"base_gain": 0.8, "highlight_gain": 0.9},
    }
    cue["parameter_modulation"] = [
        {
            "target": "base_gain",
            "mode": "modulate",
            "source": "audio.rms",
            "output_min": 0.25,
            "output_max": 0.5,
        },
        {
            "target": "highlight_gain",
            "mode": "drive",
            "source": "cue_progress",
            "output_min": 0.5,
            "output_max": 0.9,
        },
    ]
    with pytest.raises(ShowValidationError, match="output combination"):
        validate_show_data(show, TargetCatalog(digital_strips={"strip"}))


@pytest.mark.parametrize(
    ("effect_id", "target", "params"),
    [
        ("breath", "waveform", {"waveform": "sine"}),
        ("flowing_bands", "band_width_px", {"band_width_px": 1}),
        ("onset_ripple", "wrap", {"wrap": False}),
        ("spectrum", "bass_zones", {"bass_zones": ["strip"]}),
    ],
)
def test_loader_rejects_registered_non_float_parameter_kinds(
    effect_id: str,
    target: str,
    params: dict[str, object],
) -> None:
    show = _show(_valid_binding())
    cue = show["show"]["cues"][0]
    cue["effect"] = {"mode": "fixed", "id": effect_id, "params": params}
    cue["parameter_modulation"][0]["target"] = target
    with pytest.raises(ShowValidationError, match="float runtime-mutable modulatable"):
        validate_show_data(show, TargetCatalog(digital_strips={"strip"}))


def test_runtime_rejects_programmatic_unsafe_and_duplicate_bindings() -> None:
    with pytest.raises(ValueError, match="not approved"):
        CueParameterModulator(
            "coherent_noise_field",
            {"feature_size_px": 2.0},
            ParameterModulationSpec(
                (_binding(target="feature_size_px"),)
            ),
        )
    duplicate = _binding()
    with pytest.raises(ValueError, match="duplicate"):
        CueParameterModulator(
            "coherent_noise_field",
            {"contrast": 2.0},
            ParameterModulationSpec((duplicate, duplicate)),
        )


def test_chase_zero_width_remains_valid_show_and_registry_behavior() -> None:
    assert validate_effect_params("chase", {"width": 0, "gap": 2}) == {
        "width": 0,
        "gap": 2,
    }
    show = {
        "schema_version": 2,
        "show": {
            "id": "chase-zero-width",
            "duration": 1.0,
            "cues": [
                {
                    "id": "cue",
                    "start": 0.0,
                    "end": 1.0,
                    "target": {"type": "digital_strip", "id": "strip"},
                    "effect": {
                        "mode": "fixed",
                        "id": "chase",
                        "params": {"width": 0, "gap": 2},
                    },
                }
            ],
        },
    }
    loaded = validate_show_data(show, TargetCatalog(digital_strips={"strip"}))
    assert loaded.cues[0].effect.params["width"] == 0


def test_single_dot_bounce_remains_valid_show_and_registry_behavior() -> None:
    assert validate_effect_params("single_dot", {"direction": "bounce"}) == {
        "direction": "bounce"
    }
    show = {
        "schema_version": 2,
        "show": {
            "id": "single-dot-bounce",
            "duration": 1.0,
            "cues": [
                {
                    "id": "cue",
                    "start": 0.0,
                    "end": 1.0,
                    "target": {"type": "digital_strip", "id": "strip"},
                    "effect": {
                        "mode": "fixed",
                        "id": "single_dot",
                        "params": {"direction": "bounce"},
                    },
                }
            ],
        },
    }
    loaded = validate_show_data(show, TargetCatalog(digital_strips={"strip"}))
    assert loaded.cues[0].effect.params["direction"] == "bounce"
