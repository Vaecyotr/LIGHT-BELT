"""Lighting effects - each effect produces a PixelFrame from an EffectContext.

All effects implement the BaseEffect interface.
P0 minimum: STATIC, VIDEO_AMBIENT, AUDIO_PULSE, COLOR_WAVE, CHASE, BREATH,
            VIDEO_AUDIO_FUSION, DEMO (8 effects).
"""

from light_engine.effects.base import (
    BaseEffect,
    EffectCapability,
    EffectRegistration,
    _EFFECT_REGISTRY,
    create_effect,
    get_effect_registration,
    list_effect_registrations,
    list_effects,
    register_effect,
    validate_effect_params,
)


def _register_all() -> None:
    """Register all built-in effects."""
    from light_engine.effects.static import StaticEffect
    from light_engine.effects.breath import BreathEffect
    from light_engine.effects.color_wave import ColorWaveEffect
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
    from light_engine.effects.step_pulse import StepPulseEffect
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

    register_effect(
        "static", StaticEffect,
        parameter_keys=frozenset({"color", "color_timeline"}),
        display_name="Static",
        common_params=("color", "intensity"),
    )
    register_effect(
        "breath", BreathEffect,
        parameter_keys=frozenset({"period", "min_brightness", "color", "color_timeline"}),
        display_name="Breath",
        common_params=("color", "intensity"),
    )
    register_effect(
        "color_wave", ColorWaveEffect,
        parameter_keys=frozenset({"speed", "width", "hue_cycle_rate"}),
        display_name="Color Wave",
        common_params=("speed", "intensity"),
    )
    register_effect(
        "chase", ChaseEffect,
        parameter_keys=frozenset(
            {"speed", "width", "gap", "direction", "trail", "color_source", "beat_boost"}
        ),
        display_name="Chase",
        common_params=("speed", "intensity"),
    )
    register_effect(
        "comet", CometEffect, validate_comet_params,
        parameter_keys=frozenset({
            "speed", "tail_length", "decay", "count", "phase_spacing", "trajectory",
        }),
        display_name="Comet",
        common_params=("speed", "intensity"),
    )
    register_effect(
        "audio_pulse", AudioPulseEffect,
        parameter_keys=frozenset({"attack", "release", "color", "color_timeline"}),
        display_name="Audio Pulse",
        common_params=("color", "intensity"),
    )
    register_effect(
        "bass_pulse", BassPulseEffect,
        parameter_keys=frozenset({"attack", "release", "color", "color_timeline"}),
        display_name="Bass Pulse",
        common_params=("color", "intensity"),
    )
    register_effect(
        "spectrum", SpectrumEffect,
        parameter_keys=frozenset({"bass_zones", "mid_zones", "treble_zones"}),
        display_name="Spectrum",
        common_params=("intensity",),
    )
    register_effect(
        "video_ambient", VideoAmbientEffect,
        parameter_keys=frozenset({"smoothing"}),
        display_name="Video Ambient",
        common_params=("intensity",),
    )
    register_effect(
        "video_audio_fusion", VideoAudioFusionEffect,
        parameter_keys=frozenset(
            {"video_weight", "audio_weight", "bass_boost", "treble_limit"}
        ),
        display_name="Video Audio Fusion",
        common_params=("intensity",),
    )
    register_effect(
        "calm", CalmEffect,
        parameter_keys=frozenset({"period", "color", "color_timeline"}),
        display_name="Calm",
        common_params=("color", "intensity"),
    )
    register_effect(
        "color_wipe", ColorWipeEffect, validate_color_wipe_params,
        parameter_keys=frozenset(
            {"speed", "color", "color_timeline", "progress_source", "slew_seconds"}
        ),
        display_name="Color Wipe",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "twinkle", TwinkleEffect, validate_twinkle_params,
        parameter_keys=frozenset(
            {
                "density", "fade_time", "color_source", "event_width_px",
                "blur_radius_px", "event_gate_source", "birth_gain_source",
                "color", "color_timeline",
            }
        ),
        display_name="Twinkle",
        common_params=("color", "intensity"),
    )
    register_effect(
        "demo", DemoEffect,
        parameter_keys=frozenset({"cycle_interval", "effects"}),
        display_name="Demo",
    )
    register_effect(
        "step_pulse", StepPulseEffect,
        parameter_keys=frozenset({"period", "low_color", "high_color"}),
        display_name="Step Pulse",
        common_params=("intensity",),
    )
    register_effect(
        "single_dot", SingleDotEffect,
        parameter_keys=frozenset({"speed", "direction", "color", "color_timeline"}),
        display_name="Single Dot",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "theater_phase", TheaterPhaseEffect,
        parameter_keys=frozenset({"speed", "color", "color_timeline"}),
        display_name="Theater Phase",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "flowing_bands", FlowingBandsEffect, validate_flowing_bands_params,
        parameter_keys=frozenset({
            "band_width_px", "gap_width_px", "base_gain", "highlight_gain",
            "steps_per_second", "direction", "phase_offset_steps",
            "color", "color_timeline",
        }),
        display_name="Flowing Bands",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "onset_ripple", OnsetRippleEffect, validate_onset_ripple_params,
        parameter_keys=frozenset({
            "onset_threshold", "wave_speed_pps", "wave_width_px",
            "decay_seconds", "floor_gain", "event_origin", "propagation", "wrap",
            "color", "color_timeline",
        }),
        display_name="Onset Ripple",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "heat_fire", HeatFireEffect, validate_heat_fire_params,
        parameter_keys=frozenset({
            "cooling_per_second", "spark_rate", "spark_strength", "diffusion",
            "spark_zone_px", "color", "color_timeline",
        }),
        display_name="Heat Fire",
        common_params=("color", "speed", "intensity"),
    )
    register_effect(
        "history_stream", HistoryStreamEffect, validate_history_stream_params,
        parameter_keys=frozenset({
            "steps_per_second", "direction", "sample_gain_source",
            "color", "color_timeline",
        }),
        display_name="History Stream",
        common_params=("color", "speed", "intensity"),
    )


# Auto-register on first import
_register_all()
