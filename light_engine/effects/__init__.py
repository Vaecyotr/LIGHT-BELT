"""Lighting effects - each effect produces a PixelFrame from an EffectContext.

All effects implement the BaseEffect interface.
P0 minimum: STATIC, VIDEO_AMBIENT, AUDIO_PULSE, COLOR_WAVE, CHASE, BREATH,
            VIDEO_AUDIO_FUSION, DEMO (8 effects).
"""

from light_engine.effects.base import (
    BaseEffect,
    EffectCapability,
    EffectRegistration,
    ParameterSpec,
    _EFFECT_REGISTRY,
    create_effect,
    get_effect_registration,
    list_effect_registrations,
    list_effects,
    get_effect_parameter_keys,
    get_effect_parameter_specs,
    register_effect,
    validate_effect_params,
)


_PARAMETER_DESCRIPTIONS = {
    "attack": "Envelope attack time.",
    "audio_weight": "Weight of audio features in the fused output.",
    "band_width_px": "Width of each repeating base band in pixels.",
    "base_gain": "Brightness gain of the non-highlighted bands.",
    "bass_boost": "Additional bass contribution in the fused output.",
    "bass_zones": "Logical zones assigned to bass response.",
    "beat_boost": "Speed multiplier applied when a beat is present.",
    "birth_gain_source": "Normalized scalar source for new twinkle brightness.",
    "blur_radius_px": "Soft-edge radius around each twinkle event in pixels.",
    "ceiling_gain": "Maximum brightness gain of the noise field.",
    "color": "Effect-local RGB base color.",
    "color_source": "Renderer-specific color selection mode.",
    "color_timeline": "Compositor-sampled wall-clock RGB timeline.",
    "contrast": "Contrast shaping strength for the coherent noise field.",
    "cooling_per_second": "Heat removed per second by the fire simulation.",
    "count": "Number of concurrently emitted comets.",
    "cycle_interval": "Duration before the demo renderer selects its next effect.",
    "decay": "Per-frame comet tail decay factor.",
    "decay_seconds": "Time for an onset ripple to decay.",
    "density": "Twinkle event density per pixel per second.",
    "diffusion": "Neighbor diffusion amount in the fire simulation.",
    "direction": "Direction used by the effect's spatial motion.",
    "drift_rate": "Temporal rate at which the coherent field drifts.",
    "duty_cycle": "Fraction of each step-pulse period spent in the high color.",
    "edge_softness_px": "Width of the softened color-wipe front in pixels.",
    "effects": "Registered effect IDs cycled by the demo renderer.",
    "event_gate_source": "Normalized scalar source that gates twinkle births.",
    "event_origin": "Origin policy for each onset-ripple event.",
    "event_width_px": "Solid width of each twinkle event in pixels.",
    "fade_time": "Time for a twinkle event to fade out.",
    "feature_size_px": "Characteristic spatial size of coherent noise features.",
    "floor_gain": "Minimum background brightness gain.",
    "gap": "Unlit pixel gap between chase segments.",
    "gap_width_px": "Width of each repeating unlit band in pixels.",
    "high_color": "RGB color emitted during the high step-pulse state.",
    "highlight_gain": "Brightness gain of the moving highlighted band.",
    "hue_cycle_rate": "Rate of color-wave hue progression.",
    "hue_span_degrees": "Hue span covered by one color-wave waveform.",
    "low_color": "RGB color emitted during the low step-pulse state.",
    "mid_zones": "Logical zones assigned to midrange response.",
    "min_brightness": "Lowest brightness reached by the breath envelope.",
    "onset_threshold": "Audio onset level required to create a ripple.",
    "period": "Duration of one complete effect cycle.",
    "phase_offset_steps": "Discrete band-step offset applied before rendering.",
    "phase_spacing": "Cycle fraction separating multiple comet emitters.",
    "progress_curve": "Curve applied to color-wipe progress.",
    "progress_source": "Optional normalized scalar source for wipe progress.",
    "propagation": "One-way or bidirectional ripple propagation.",
    "release": "Envelope release time.",
    "sample_gain_source": "Normalized scalar source for history-stream sample gain.",
    "smoothing": "Temporal smoothing amount for video ambient output.",
    "spark_rate": "Rate of new heat sparks per second.",
    "spark_strength": "Heat added by each fire spark.",
    "spark_zone_px": "Pixel extent near the source where sparks may start.",
    "speed": "Effect-local animation speed.",
    "slew_seconds": "Time used to slew externally sampled wipe progress.",
    "steps_per_second": "Fixed simulation or band-advance step rate.",
    "tail_length": "Length of the comet tail relative to the path.",
    "trail": "Brightness decay trail following each chase segment.",
    "trajectory": "Path trajectory followed by comet emitters.",
    "treble_limit": "Maximum treble contribution in the fused output.",
    "treble_zones": "Logical zones assigned to treble response.",
    "video_weight": "Weight of video features in the fused output.",
    "wave_speed_pps": "Ripple wavefront speed in pixels per second.",
    "wave_width_px": "Ripple wavefront width in pixels.",
    "waveform": "Shape used to calculate the effect waveform.",
    "width": "Width of a generated spatial feature in pixels.",
    "wrap": "Whether the ripple wavefront wraps across path ends.",
}


def _spec(
    name: str,
    kind: str,
    *,
    description: str | None = None,
    **kwargs: object,
) -> ParameterSpec:
    """Create one built-in spec with mandatory author-facing semantics."""

    semantic_description = description or _PARAMETER_DESCRIPTIONS.get(name)
    if semantic_description is None:
        raise ValueError(f"missing semantic ParameterSpec description for {name!r}")
    if name == "color_timeline":
        # The compositor samples timelines at cue wall time for every frame.
        kwargs["runtime_mutable"] = True

    return ParameterSpec(
        name=name,
        kind=kind,  # type: ignore[arg-type]
        description=semantic_description,
        **kwargs,
    )


def _register_all() -> None:
    """Register all built-in effects."""
    from light_engine.effects.static import StaticEffect
    from light_engine.effects.breath import BreathEffect, validate_breath_params
    from light_engine.effects.color_wave import ColorWaveEffect, validate_color_wave_params
    from light_engine.effects.chase import ChaseEffect
    from light_engine.effects.comet import CometEffect, validate_comet_params
    from light_engine.effects.audio_pulse import AudioPulseEffect
    from light_engine.effects.bass_pulse import BassPulseEffect
    from light_engine.effects.spectrum import SpectrumEffect
    from light_engine.effects.video_ambient import VideoAmbientEffect
    from light_engine.effects.video_audio_fusion import VideoAudioFusionEffect
    from light_engine.effects.calm import CalmEffect
    from light_engine.effects.color_wipe import (
        ColorWipeEffect,
        validate_color_wipe_params,
    )
    from light_engine.effects.twinkle import TwinkleEffect, validate_twinkle_params
    from light_engine.effects.demo import DemoEffect
    from light_engine.effects.single_dot import SingleDotEffect
    from light_engine.effects.step_pulse import StepPulseEffect, validate_step_pulse_params
    from light_engine.effects.theater_phase import TheaterPhaseEffect
    from light_engine.effects.flowing_bands import (
        FlowingBandsEffect,
        validate_flowing_bands_params,
    )
    from light_engine.effects.onset_ripple import (
        OnsetRippleEffect,
        validate_onset_ripple_params,
    )
    from light_engine.effects.heat_fire import HeatFireEffect, validate_heat_fire_params
    from light_engine.effects.history_stream import (
        HistoryStreamEffect,
        validate_history_stream_params,
    )
    from light_engine.effects.coherent_noise_field import (
        CoherentNoiseFieldEffect,
        validate_coherent_noise_field_params,
    )

    register_effect(
        "static", StaticEffect,
        parameter_specs=(
            _spec("color", "rgb", runtime_mutable=True, description="Solid RGB output color."),
            _spec("color_timeline", "color_timeline", runtime_mutable=True, description="Wall-clock RGB timeline."),
        ),
        display_name="Static",
        common_params=("color", "intensity"),
        color_source_support="GLOBAL",
    )
    register_effect(
        "breath", BreathEffect, validate_breath_params,
        parameter_specs=(
            _spec("period", "float", unit="seconds", runtime_mutable=True),
            _spec("min_brightness", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("waveform", "enum", choices=("sine", "triangle", "smoothstep"), runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
        ),
        display_name="Breath",
        common_params=("color", "intensity"),
        color_source_support="GLOBAL",
    )
    register_effect(
        "color_wave", ColorWaveEffect, validate_color_wave_params,
        parameter_specs=(
            _spec("speed", "float", runtime_mutable=True, unit="cycles_per_second"),
            _spec("width", "float", runtime_mutable=True),
            _spec("hue_cycle_rate", "float", runtime_mutable=True, unit="cycles_per_second"),
            _spec("waveform", "enum", choices=("linear", "sine", "triangle", "saw"), runtime_mutable=True),
            _spec("hue_span_degrees", "float", minimum=0.0, maximum=360.0, unit="degrees", runtime_mutable=True, modulatable=True),
        ),
        display_name="Color Wave",
        common_params=("speed", "intensity"),
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "chase", ChaseEffect,
        parameter_specs=(
            _spec("speed", "float", runtime_mutable=True, unit="pixels_per_second"),
            _spec("width", "integer", minimum=0, runtime_mutable=True, unit="pixels"),
            _spec("gap", "integer", minimum=0, runtime_mutable=True, unit="pixels"),
            _spec("direction", "enum", choices=("forward", "reverse", "bounce"), runtime_mutable=True),
            _spec("trail", "float", runtime_mutable=True),
            _spec("color_source", "enum", choices=("rainbow", "video", "static"), runtime_mutable=True),
            _spec("beat_boost", "float", runtime_mutable=True),
        ),
        display_name="Chase",
        common_params=("speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "comet", CometEffect, validate_comet_params,
        parameter_specs=(
            _spec("speed", "float", minimum=0.0, runtime_mutable=True, unit="pixels_per_second"),
            _spec("tail_length", "float", minimum=0.0, runtime_mutable=True, unit="path_fraction"),
            _spec("decay", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("count", "integer", minimum=1, maximum=64, runtime_mutable=True),
            _spec("phase_spacing", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, unit="cycle_fraction"),
            _spec("trajectory", "enum", choices=("wrap", "bounce", "sine"), runtime_mutable=True),
        ),
        display_name="Comet",
        common_params=("speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "audio_pulse", AudioPulseEffect,
        parameter_specs=(
            _spec("attack", "float", unit="seconds", runtime_mutable=True),
            _spec("release", "float", unit="seconds", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
        ),
        display_name="Audio Pulse",
        common_params=("color", "intensity"),
        color_source_support="GLOBAL",
    )
    register_effect(
        "bass_pulse", BassPulseEffect,
        parameter_specs=(
            _spec("attack", "float", unit="seconds", runtime_mutable=True),
            _spec("release", "float", unit="seconds", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
        ),
        display_name="Bass Pulse",
        common_params=("color", "intensity"),
        color_source_support="GLOBAL",
    )
    register_effect(
        "spectrum", SpectrumEffect,
        parameter_specs=(
            _spec("bass_zones", "id_list", runtime_mutable=True, description="Logical zones assigned to bass response."),
            _spec("mid_zones", "id_list", runtime_mutable=True, description="Logical zones assigned to mid response."),
            _spec("treble_zones", "id_list", runtime_mutable=True, description="Logical zones assigned to treble response."),
        ),
        display_name="Spectrum",
        common_params=("intensity",),
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "video_ambient", VideoAmbientEffect,
        parameter_specs=(
            _spec("smoothing", "float", runtime_mutable=True),
        ),
        display_name="Video Ambient",
        common_params=("intensity",),
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "video_audio_fusion", VideoAudioFusionEffect,
        parameter_specs=(
            _spec("video_weight", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("audio_weight", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("bass_boost", "float", minimum=0.0, maximum=10.0, runtime_mutable=True, modulatable=True),
            _spec("treble_limit", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
        ),
        display_name="Video Audio Fusion",
        common_params=("intensity",),
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "calm", CalmEffect,
        parameter_specs=(
            _spec("period", "float", unit="seconds", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
        ),
        display_name="Calm",
        common_params=("color", "intensity"),
        color_source_support="GLOBAL",
    )
    register_effect(
        "color_wipe", ColorWipeEffect, validate_color_wipe_params,
        parameter_specs=(
            _spec("speed", "float", minimum=0.0, maximum=1000.0, runtime_mutable=True, unit="pixels_per_second"),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
            _spec("progress_source", "scalar_source", runtime_mutable=True),
            _spec("slew_seconds", "float", minimum=0.0, runtime_mutable=True, unit="seconds"),
            _spec("edge_softness_px", "float", minimum=0.0, maximum=10000.0, runtime_mutable=True, modulatable=True, unit="pixels"),
            _spec("progress_curve", "enum", choices=("linear", "smoothstep"), runtime_mutable=True),
        ),
        display_name="Color Wipe",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "twinkle", TwinkleEffect, validate_twinkle_params,
        parameter_specs=(
            _spec("density", "float", minimum=0.0, maximum=100.0, runtime_mutable=True, unit="events_per_pixel_second"),
            _spec("fade_time", "float", minimum=0.01, maximum=60.0, runtime_mutable=True, unit="seconds"),
            _spec("color_source", "enum", choices=("solid", "palette", "random"), runtime_mutable=True),
            _spec("event_width_px", "float", minimum=0.01, maximum=10000.0, runtime_mutable=True, unit="pixels"),
            _spec("blur_radius_px", "float", minimum=0.0, maximum=10000.0, runtime_mutable=True, unit="pixels"),
            _spec("event_gate_source", "scalar_source", runtime_mutable=True),
            _spec("birth_gain_source", "scalar_source", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline", runtime_mutable=True),
        ),
        display_name="Twinkle",
        common_params=("color", "intensity"),
        color_source_support="EVENT",
    )
    register_effect(
        "demo", DemoEffect,
        parameter_specs=(
            _spec("cycle_interval", "float", unit="seconds", runtime_mutable=True),
            _spec("effects", "id_list", runtime_mutable=True, description="Registered effect IDs cycled by the demo renderer."),
        ),
        display_name="Demo",
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "step_pulse", StepPulseEffect, validate_step_pulse_params,
        parameter_specs=(
            _spec("period", "float", runtime_mutable=True, unit="seconds"),
            _spec("duty_cycle", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, unit="fraction"),
            _spec("low_color", "rgb", runtime_mutable=True),
            _spec("high_color", "rgb", runtime_mutable=True),
        ),
        display_name="Step Pulse",
        common_params=("intensity",),
        color_source_support="NOT_APPLICABLE",
    )
    register_effect(
        "single_dot", SingleDotEffect,
        parameter_specs=(
            _spec("speed", "float", runtime_mutable=True, unit="pixels_per_second"),
            _spec("direction", "enum", choices=("forward", "reverse", "bounce"), runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Single Dot",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "theater_phase", TheaterPhaseEffect,
        parameter_specs=(
            _spec("speed", "float", runtime_mutable=True, unit="pixels_per_second"),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Theater Phase",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "flowing_bands", FlowingBandsEffect, validate_flowing_bands_params,
        parameter_specs=(
            _spec("band_width_px", "integer", minimum=1, maximum=10000, runtime_mutable=True, unit="pixels"),
            _spec("gap_width_px", "integer", minimum=1, maximum=10000, runtime_mutable=True, unit="pixels"),
            _spec("base_gain", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("highlight_gain", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("steps_per_second", "float", minimum=0.0, maximum=1000.0, runtime_mutable=True, unit="steps_per_second"),
            _spec("direction", "enum", choices=("forward", "reverse"), runtime_mutable=True),
            _spec("phase_offset_steps", "integer", minimum=0, maximum=10000, runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Flowing Bands",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "onset_ripple", OnsetRippleEffect, validate_onset_ripple_params,
        parameter_specs=(
            _spec("onset_threshold", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("wave_speed_pps", "float", minimum=0.0, maximum=1000.0, runtime_mutable=True, unit="pixels_per_second"),
            _spec("wave_width_px", "float", minimum=0.1, maximum=1000.0, runtime_mutable=True, unit="pixels"),
            _spec("decay_seconds", "float", minimum=0.01, maximum=60.0, runtime_mutable=True, unit="seconds"),
            _spec("floor_gain", "float", minimum=0.0, maximum=1.0, runtime_mutable=True, modulatable=True),
            _spec("event_origin", "enum", choices=("fixed", "random"), runtime_mutable=True),
            _spec("propagation", "enum", choices=("one_way", "bidirectional"), runtime_mutable=True),
            _spec("wrap", "boolean", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Onset Ripple",
        common_params=("color", "speed", "intensity"),
        color_source_support="EVENT",
    )
    register_effect(
        "heat_fire", HeatFireEffect, validate_heat_fire_params,
        parameter_specs=(
            _spec("cooling_per_second", "float", minimum=0.0, maximum=60.0, runtime_mutable=True, unit="per_second"),
            _spec("spark_rate", "float", minimum=0.0, maximum=60.0, runtime_mutable=True, unit="per_second"),
            _spec("spark_strength", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("diffusion", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("spark_zone_px", "integer", minimum=1, maximum=10000, runtime_mutable=True, unit="pixels"),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Heat Fire",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "history_stream", HistoryStreamEffect, validate_history_stream_params,
        parameter_specs=(
            _spec("steps_per_second", "float", minimum=0.001, maximum=1000.0, runtime_mutable=True, unit="steps_per_second"),
            _spec("direction", "enum", choices=("forward", "reverse"), runtime_mutable=True),
            _spec("sample_gain_source", "scalar_source", runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="History Stream",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )
    register_effect(
        "coherent_noise_field",
        CoherentNoiseFieldEffect,
        validate_coherent_noise_field_params,
        parameter_specs=(
            _spec("feature_size_px", "float", minimum=0.01, maximum=10000.0, runtime_mutable=True, unit="pixels"),
            _spec("drift_rate", "float", minimum=0.0, maximum=1000.0, runtime_mutable=True, unit="noise_time_per_second"),
            _spec("contrast", "float", minimum=0.0, maximum=4.0, runtime_mutable=True, modulatable=True),
            _spec("floor_gain", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("ceiling_gain", "float", minimum=0.0, maximum=1.0, runtime_mutable=True),
            _spec("color", "rgb", runtime_mutable=True),
            _spec("color_timeline", "color_timeline"),
        ),
        display_name="Coherent Noise Field",
        common_params=("color", "speed", "intensity"),
        color_source_support="POSITIONAL",
    )


# Auto-register on first import
_register_all()
