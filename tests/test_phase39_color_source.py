"""Phase 39 internal/YAML ColorSource acceptance coverage."""

from __future__ import annotations

import random

import pytest

from light_engine.effects import list_effect_registrations
from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame, VideoFeatures
from light_engine.show import (
    ColorSourceKeyframe,
    ColorSourceSpec,
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    CueBranchSpec,
    CueRenderJob,
    EffectSpec,
    ParameterModulationBindingSpec,
    ParameterModulationSpec,
    ShowDefinition,
    ShowRuntime,
    ShowValidationError,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
    black_base_frame,
    validate_show_data,
)
from light_engine.show.color_source import (
    ColorSampler,
    interpolate_palette,
    normalized_pixel_position,
)


_PALETTE = ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))


class _RecordingWhiteEffect(BaseEffect):
    def __init__(self, name: str):
        super().__init__(name)
        self.contrasts: list[float] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contrasts.append(float(ctx.mode_parameters["contrast"]))
        return PixelFrame(
            ctx.timestamp,
            ctx.sequence,
            [
                DigitalStrip(
                    definition["id"],
                    definition["pixel_count"],
                    [(1.0, 1.0, 1.0)] * definition["pixel_count"],
                )
                for definition in ctx.mode_parameters["strip_defs"]
            ],
        )


class _ColorHistoryEffect(BaseEffect):
    def __init__(self, name: str):
        super().__init__(name)
        self.history: list[tuple[float, float, float]] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        color = ctx.mode_parameters["color_sampler"].sample_current(ctx)
        self.history.append(color)
        return PixelFrame(
            ctx.timestamp,
            ctx.sequence,
            [
                DigitalStrip(
                    definition["id"],
                    definition["pixel_count"],
                    [color] * definition["pixel_count"],
                )
                for definition in ctx.mode_parameters["strip_defs"]
            ],
        )


def _catalog() -> TargetCatalog:
    return TargetCatalog(digital_strips=("strip_a", "strip_b"))


def _show_data(effect_id: str = "static") -> dict:
    return {
        "schema_version": 2,
        "show": {
            "id": "color-source",
            "duration": 2.0,
            "cues": [
                {
                    "id": "cue",
                    "start": 0.0,
                    "end": 2.0,
                    "target": {"type": "digital_strip", "id": "strip_a"},
                    "effect": {"mode": "fixed", "id": effect_id, "params": {}},
                }
            ],
        },
    }


def _ctx(
    timestamp: float = 0.0,
    *,
    audio: AudioFeatures | None = None,
    video: VideoFeatures | None = None,
) -> EffectContext:
    return EffectContext(
        timestamp=timestamp,
        delta_time=1.0,
        sequence=int(timestamp * 10),
        audio_features=audio,
        video_features=video,
        mode_parameters={"cue_local_time": timestamp},
    )


def test_palette_interpolation_and_one_pixel_coordinate_are_exact() -> None:
    assert interpolate_palette(_PALETTE, 0.0) == _PALETTE[0]
    assert interpolate_palette(_PALETTE, 1.0) == _PALETTE[-1]
    assert interpolate_palette(_PALETTE, 0.5) == pytest.approx((0.5, 0.0, 0.5))
    assert normalized_pixel_position(0, 1) == 0.5
    assert [normalized_pixel_position(i, 4) for i in range(4)] == pytest.approx(
        [0.0, 1 / 3, 2 / 3, 1.0]
    )


def test_timeline_is_a_separate_cue_local_source() -> None:
    sampler = ColorSampler(
        ColorSourceSpec(
            type="timeline",
            keyframes=(
                ColorSourceKeyframe(0.0, (1.0, 0.0, 0.0)),
                ColorSourceKeyframe(2.0, (0.0, 0.0, 1.0)),
            ),
        )
    )
    assert sampler.sample_current(_ctx(1.0)) == pytest.approx((0.5, 0.0, 0.5))


def test_video_sources_use_only_global_average_or_dominant_and_fixed_fallback() -> None:
    features = VideoFeatures(
        timestamp=0.0,
        average_rgb=(0.1, 0.2, 0.3),
        dominant_rgb=(0.7, 0.6, 0.5),
        zone_colors={"strip_a": (1.0, 0.0, 0.0), "strip_b": (0.0, 1.0, 0.0)},
    )
    average = ColorSampler(ColorSourceSpec(type="video_average", fallback=(0.9, 0.8, 0.7)))
    dominant = ColorSampler(ColorSourceSpec(type="video_dominant", fallback=(0.9, 0.8, 0.7)))
    assert average.sample_current(_ctx(video=features)) == pytest.approx((0.1, 0.2, 0.3))
    assert dominant.sample_current(_ctx(video=features)) == pytest.approx((0.7, 0.6, 0.5))
    assert average.sample_position(_ctx(), 0.0) == pytest.approx((0.9, 0.8, 0.7))


def test_audio_spectrum_maps_position_to_band_then_energy_to_authored_palette() -> None:
    spectrum = tuple(index / 15.0 for index in range(16))
    audio = AudioFeatures(timestamp=0.0, spectrum=spectrum, silence=False)
    sampler = ColorSampler(
        ColorSourceSpec(
            type="audio_spectrum_palette",
            palette=((0.0, 1.0, 0.0), (1.0, 0.0, 1.0)),
            fallback=(0.2, 0.2, 0.2),
        )
    )
    assert sampler.sample_position(_ctx(audio=audio), 0.0) == pytest.approx((0.0, 1.0, 0.0))
    assert sampler.sample_position(_ctx(audio=audio), 1.0) == pytest.approx((1.0, 0.0, 1.0))
    assert sampler.sample_position(_ctx(), 0.75) == pytest.approx((0.2, 0.2, 0.2))
    zero_spectrum_audio = AudioFeatures(timestamp=0.0, silence=False)
    assert sampler.sample_position(_ctx(audio=zero_spectrum_audio), 0.75) == pytest.approx(
        (0.0, 1.0, 0.0)
    )


def test_dominant_frequency_uses_only_authored_bounds_and_palette_direction() -> None:
    audio = AudioFeatures(timestamp=0.0, dominant_frequency=300.0, silence=False)
    forward = ColorSampler(
        ColorSourceSpec(
            type="dominant_frequency_palette",
            frequency_min_hz=100.0,
            frequency_max_hz=500.0,
            palette=_PALETTE,
            fallback=(0.0, 1.0, 0.0),
        )
    )
    reverse = ColorSampler(
        ColorSourceSpec(
            type="dominant_frequency_palette",
            frequency_min_hz=100.0,
            frequency_max_hz=500.0,
            palette=tuple(reversed(_PALETTE)),
            fallback=(0.0, 1.0, 0.0),
        )
    )
    assert forward.sample_current(_ctx(audio=audio)) == pytest.approx((0.5, 0.0, 0.5))
    low = AudioFeatures(timestamp=0.0, dominant_frequency=100.0, silence=False)
    assert forward.sample_current(_ctx(audio=low)) == _PALETTE[0]
    assert reverse.sample_current(_ctx(audio=low)) == _PALETTE[-1]
    assert forward.sample_current(_ctx()) == (0.0, 1.0, 0.0)


def test_event_sampling_is_seeded_by_logical_identity_not_global_rng_or_call_order() -> None:
    sampler = ColorSampler(ColorSourceSpec(type="spatial_palette", palette=_PALETTE), cue_seed=42)
    expected = sampler.sample_event(_ctx(), ("logical-path", 7))
    random.seed(999)
    random.random()
    sampler.sample_event(_ctx(), ("unrelated", 1000))
    assert sampler.sample_event(_ctx(), ("logical-path", 7)) == expected
    assert ColorSampler(
        ColorSourceSpec(type="spatial_palette", palette=_PALETTE), cue_seed=42
    ).sample_event(_ctx(), ("logical-path", 7)) == expected


def test_loader_keeps_legacy_color_and_effect_color_source_independent() -> None:
    data = _show_data("twinkle")
    cue = data["show"]["cues"][0]
    cue["color"] = {"mode": "palette", "colors": [[1, 0, 0], [0, 1, 0]]}
    cue["effect"]["params"] = {"color_source": "random"}
    cue["color_source"] = {
        "type": "video_average",
        "fallback": [0.0, 0.0, 1.0],
    }
    show = validate_show_data(data, _catalog())
    loaded = show.cues[0]
    assert loaded.color.mode == "palette"
    assert loaded.color.palette == ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    assert loaded.effect.params["color_source"] == "random"
    assert loaded.color_source == ColorSourceSpec(
        type="video_average", fallback=(0.0, 0.0, 1.0)
    )


@pytest.mark.parametrize(
    "source",
    [
        {
            "type": "timeline",
            "interpolation": "rgb_linear",
            "keyframes": [
                {"time": 0, "color": [1, 0, 0]},
                {"time": 1, "color": [0, 0, 1]},
            ],
        },
        {"type": "spatial_palette", "palette": [[1, 0, 0], [0, 0, 1]]},
        {"type": "video_average", "fallback": [0, 0, 0]},
        {"type": "video_dominant", "fallback": [0, 0, 0]},
        {
            "type": "audio_spectrum_palette",
            "palette": [[1, 0, 0], [0, 0, 1]],
            "fallback": [0, 0, 0],
        },
        {
            "type": "dominant_frequency_palette",
            "frequency_min_hz": 80,
            "frequency_max_hz": 8000,
            "palette": [[1, 0, 0], [0, 0, 1]],
            "fallback": [0, 0, 0],
        },
    ],
)
def test_all_six_explicit_yaml_source_types_load(source: dict) -> None:
    data = _show_data()
    data["show"]["cues"][0]["color_source"] = source
    assert validate_show_data(data, _catalog()).cues[0].color_source is not None


def test_omitted_color_source_preserves_old_palette_per_second_behavior() -> None:
    data = _show_data("static")
    data["show"]["cues"][0]["color"] = {
        "mode": "palette",
        "colors": [[1, 0, 0], [0, 1, 0]],
    }
    cue = validate_show_data(data, _catalog()).cues[0]
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip_a", pixel_count=1),)),
    )
    first = job.render(_ctx(0.25)).digital[0].pixels[0]
    second = job.render(_ctx(1.25)).digital[0].pixels[0]
    assert first == (1.0, 0.0, 0.0)
    assert second == (0.0, 1.0, 0.0)


def test_virtual_path_spatial_palette_samples_once_before_member_split() -> None:
    path = VirtualPathSpec(
        id="logical",
        targets=(
            TargetSelector("digital_strip", id="strip_a"),
            TargetSelector("digital_strip", id="strip_b"),
        ),
    )
    cue = Cue(
        id="gradient",
        start=0.0,
        end=1.0,
        target=TargetSelector("virtual_path", id="logical"),
        effect=EffectSpec(
            mode="fixed",
            id="coherent_noise_field",
            params={"contrast": 0.0, "floor_gain": 1.0, "ceiling_gain": 1.0},
        ),
        color_source=ColorSourceSpec(type="spatial_palette", palette=_PALETTE),
    )
    show = ShowDefinition(2, "virtual", 1.0, (cue,), virtual_paths=(path,))
    resolver = TargetResolver(
        (),
        (
            ZoneDef(id="strip_a", pixel_count=2),
            ZoneDef(id="strip_b", pixel_count=2),
        ),
    )
    runtime = ShowRuntime(show, resolver, seed=8)
    base = black_base_frame(
        timestamp=0.0,
        sequence=0,
        analog_zones=(),
        digital_strips=(
            ZoneDef(id="strip_a", pixel_count=2),
            ZoneDef(id="strip_b", pixel_count=2),
        ),
    )
    frame = runtime.render(_ctx(), base)
    pixels = [pixel for strip in frame.strips for pixel in strip.pixels]
    expected = [
        (1.0, 0.0, 0.0),
        (2 / 3, 0.0, 1 / 3),
        (1 / 3, 0.0, 2 / 3),
        (0.0, 0.0, 1.0),
    ]
    assert all(actual == pytest.approx(wanted) for actual, wanted in zip(pixels, expected))


def test_twinkle_event_color_reset_replay_is_exact_and_ignores_global_rng() -> None:
    cue = Cue(
        id="events",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip_a"),
        effect=EffectSpec(
            mode="fixed",
            id="twinkle",
            params={"density": 1.0, "fade_time": 10.0, "color_source": "random"},
        ),
        color_source=ColorSourceSpec(type="spatial_palette", palette=_PALETTE),
    )
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip_a", pixel_count=4),)),
        cue_seed=123,
    )
    expected = job.render(_ctx()).digital[0].pixels
    random.seed(777)
    random.random()
    job.reset()
    assert job.render(_ctx()).digital[0].pixels == expected


def test_onset_event_color_reset_replay_is_exact() -> None:
    cue = Cue(
        id="onset-events",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip_a"),
        effect=EffectSpec(
            mode="fixed",
            id="onset_ripple",
            params={"onset_threshold": 0.5, "wave_width_px": 2.0},
        ),
        color_source=ColorSourceSpec(type="spatial_palette", palette=_PALETTE),
    )
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip_a", pixel_count=4),)),
        cue_seed=987,
    )
    audio = AudioFeatures(
        timestamp=0.0,
        onset=1.0,
        loudness=1.0,
        peak=True,
        silence=False,
    )
    expected = job.render(_ctx(audio=audio)).digital[0].pixels
    job.reset()
    assert job.render(_ctx(audio=audio)).digital[0].pixels == expected


def test_color_source_audio_and_parameter_modulation_keep_separate_ownership() -> None:
    effect = _RecordingWhiteEffect("coherent_noise_field")
    cue = Cue(
        id="coexist",
        start=0.0,
        end=1.0,
        target=TargetSelector("digital_strip", id="strip_a"),
        effect=EffectSpec(
            mode="fixed",
            id="coherent_noise_field",
            params={"contrast": 1.0},
        ),
        audio_modulation=AudioModulationSpec(
            brightness=AudioModulationChannelSpec(
                source="audio.rms",
                amount=0.5,
                min_multiplier=0.5,
                max_multiplier=1.5,
                smoothing_seconds=0.0,
            )
        ),
        parameter_modulation=ParameterModulationSpec(
            (
                ParameterModulationBindingSpec(
                    target="contrast",
                    mode="drive",
                    source="cue_progress",
                    output_min=0.0,
                    output_max=4.0,
                ),
            )
        ),
        color_source=ColorSourceSpec(type="video_average", fallback=(0.0, 0.0, 0.0)),
    )
    job = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip_a", pixel_count=1),)),
        effect=effect,
    )
    audio = AudioFeatures(timestamp=0.5, loudness=1.0, silence=False)
    video = VideoFeatures(0.5, (0.2, 0.4, 0.6), (1.0, 0.0, 0.0))
    output = job.render(_ctx(0.5, audio=audio, video=video)).digital[0].pixels[0]
    assert effect.contrasts == [2.0]
    assert output == pytest.approx((0.3, 0.6, 0.9))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            ColorSourceSpec(
                type="timeline",
                keyframes=(
                    ColorSourceKeyframe(0.0, (1.0, 0.0, 0.0)),
                    ColorSourceKeyframe(1.0, (0.0, 0.0, 1.0)),
                ),
            ),
            [(1.0, 0.0, 0.0), (0.5, 0.0, 0.5), (0.0, 0.0, 1.0)],
        ),
        (
            ColorSourceSpec(type="video_average", fallback=(0.0, 1.0, 0.0)),
            [(0.0, 1.0, 0.0)] * 3,
        ),
    ],
)
def test_pre_roll_consumes_actual_color_history_and_reset_replays(
    source: ColorSourceSpec, expected: list[tuple[float, float, float]]
) -> None:
    resolver = TargetResolver(
        (),
        (
            ZoneDef(id="path_a", pixel_count=2),
            ZoneDef(id="path_b", pixel_count=2),
            ZoneDef(id="branch", pixel_count=2),
        ),
    )
    resolver.register_authored_paths(
        (
            VirtualPathSpec(
                id="release",
                targets=(
                    TargetSelector("digital_strip", id="path_a"),
                    TargetSelector("digital_strip", id="path_b"),
                ),
            ),
        )
    )
    cue = Cue(
        id="pre-roll-colors",
        start=0.0,
        end=2.0,
        target=TargetSelector("virtual_path", id="release"),
        effect=EffectSpec(mode="fixed", id="static"),
        color_source=source,
        branches=(
            CueBranchSpec(
                path_id="release",
                after_target_id="path_a",
                target=TargetSelector("digital_strip", id="branch"),
                lifecycle="pre_roll",
            ),
        ),
    )
    created: list[_ColorHistoryEffect] = []

    def factory(name: str) -> _ColorHistoryEffect:
        effect = _ColorHistoryEffect(name)
        created.append(effect)
        return effect

    job = CueRenderJob(cue, 0, resolver, effect_factory=factory, cue_seed=55)
    contexts = [_ctx(timestamp) for timestamp in (0.0, 0.5, 1.0)]
    for context in contexts:
        job.render(context)
        job.render_branches(context)
    assert created[1].history == pytest.approx(expected)

    job.reset()
    for context in contexts:
        job.render(context)
        job.render_branches(context)
    assert created[-1].history == pytest.approx(expected)


@pytest.mark.parametrize(
    "constructor",
    [
        lambda: ColorSourceKeyframe(float("nan"), (1.0, 0.0, 0.0)),
        lambda: ColorSourceKeyframe(0.0, (2.0, 0.0, 0.0)),
        lambda: ColorSourceSpec(type="spatial_palette", palette=((float("inf"), 0.0, 0.0),)),
        lambda: ColorSourceSpec(type="video_average", fallback=(-1.0, 0.0, 0.0)),
    ],
)
def test_programmatic_color_source_rejects_nonfinite_and_out_of_range_rgb(
    constructor: object,
) -> None:
    with pytest.raises(ValueError):
        constructor()  # type: ignore[operator]


@pytest.mark.parametrize(
    "effect_id",
    ["color_wave", "spectrum", "video_ambient", "video_audio_fusion", "demo", "step_pulse"],
)
def test_not_applicable_effects_reject_color_source(effect_id: str) -> None:
    data = _show_data(effect_id)
    data["show"]["cues"][0]["color_source"] = {
        "type": "spatial_palette",
        "palette": [[1, 0, 0], [0, 0, 1]],
    }
    with pytest.raises(ShowValidationError, match="does not have meaningful"):
        validate_show_data(data, _catalog())


def test_live_registry_color_source_audit_covers_all_22_effects_exactly() -> None:
    registrations = list_effect_registrations()
    assert len(registrations) == 22
    by_support: dict[str, set[str]] = {}
    for registration in registrations:
        by_support.setdefault(registration.color_source_support, set()).add(registration.id)
    assert by_support == {
        "GLOBAL": {"static", "breath", "audio_pulse", "bass_pulse", "calm"},
        "POSITIONAL": {
            "chase", "comet", "color_wipe", "single_dot", "theater_phase",
            "flowing_bands", "heat_fire", "history_stream", "coherent_noise_field",
        },
        "EVENT": {"twinkle", "onset_ripple"},
        "NOT_APPLICABLE": {
            "color_wave", "spectrum", "video_ambient", "video_audio_fusion", "demo", "step_pulse",
        },
    }


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ({"type": "video_average"}, "must be a list"),
        ({"type": "spatial_palette", "palette": []}, "non-empty"),
        (
            {
                "type": "dominant_frequency_palette",
                "frequency_min_hz": 500,
                "frequency_max_hz": 100,
                "palette": [[1, 0, 0]],
                "fallback": [0, 0, 0],
            },
            "must be >",
        ),
    ],
)
def test_loader_rejects_missing_fallback_palette_and_invalid_frequency_bounds(
    source: dict, reason: str
) -> None:
    data = _show_data()
    data["show"]["cues"][0]["color_source"] = source
    with pytest.raises(ShowValidationError, match=reason):
        validate_show_data(data, _catalog())


def test_color_source_is_v2_only_and_adaptive_is_rejected() -> None:
    v1 = _show_data()
    v1["schema_version"] = 1
    v1["show"]["cues"][0]["color_source"] = {
        "type": "video_average",
        "fallback": [0, 0, 0],
    }
    with pytest.raises(ShowValidationError, match="unknown field"):
        validate_show_data(v1, _catalog())

    adaptive = _show_data()
    adaptive["show"]["cues"][0]["effect"] = {
        "mode": "adaptive",
        "allowed": {"calm": "static"},
        "fallback": "static",
    }
    adaptive["show"]["cues"][0]["color_source"] = {
        "type": "video_average",
        "fallback": [0, 0, 0],
    }
    with pytest.raises(ShowValidationError, match="requires a fixed effect"):
        validate_show_data(adaptive, _catalog())
