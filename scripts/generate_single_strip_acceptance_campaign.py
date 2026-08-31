"""Generate the Phase 41V single-strip visual acceptance campaign.

The generator reads live registries and schema vocabularies.  Human visual
choices remain an explicit table because renderer identity cannot be inferred
mechanically from ParameterSpec metadata.  Generated evidence is software-only
and never records a hardware pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import wave
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import fmean, pvariance
from typing import Any, Iterable, Mapping

import yaml

from light_engine.color import evaluate_rgb_linear_timeline
from light_engine.config import Config, load_yaml
from light_engine.effects import list_effect_registrations
from light_engine.effects import scalar_source as scalar_module
from light_engine.mapping import Layout
from light_engine.models import AudioFeatures, EffectContext, MusicControlState, VideoFeatures
from light_engine.show import (
    CueRenderJob,
    ShowRuntime,
    TargetCatalog,
    TargetResolver,
    black_base_frame,
    load_show,
)
from light_engine.show.audio_modulation import SOURCE_FIELDS
from light_engine.show.loader import (
    BLEND_MODES,
    BRANCH_LIFECYCLES,
    BRIGHTNESS_INTERPOLATIONS,
    COLOR_MODES,
    COLOR_SOURCE_TYPES,
    ORIGINS,
    V2_TARGET_KINDS,
)
from light_engine.show.models import ParameterModulationBindingSpec, ParameterModulationSpec
from light_engine.show.parameter_modulation import CueParameterModulator, RAW_AUDIO_SOURCES


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "config/profiles/rk3588-host-service.yaml"
OUTPUT_DIR = ROOT / "config/acceptance/single-strip-visual-v1"
BASELINE_DIR = ROOT / "artifacts/baselines/single-strip-visual-v1"
TARGET_ID = "strip_31"
CAMPAIGN_VERSION = "single-strip-visual-v1"
ALLOWED_COVERAGE = {
    "FULL",
    "PARTIAL",
    "FALLBACK_ONLY",
    "UNOBSERVABLE_ON_10_GROUP",
    "NOT_COVERABLE_SINGLE_STRIP",
    "NOT_APPLICABLE",
}

BLUE = [0.04, 0.42, 0.90]
CYAN = [0.02, 0.65, 1.00]
AMBER = [0.90, 0.22, 0.03]
MAGENTA = [0.72, 0.04, 0.46]
RED = [0.70, 0.02, 0.01]
GREEN = [0.02, 0.65, 0.04]
BLACK = [0.0, 0.0, 0.0]


def _entry(
    campaign: str,
    duration: float,
    params: Mapping[str, Any],
    *,
    color: Mapping[str, Any] | None = None,
    warmup: float = 0.0,
    metric: str,
    expected: str,
    classification: str = "FULL",
) -> dict[str, Any]:
    return {
        "campaign": campaign,
        "duration": duration,
        "warmup_seconds": warmup,
        "observation_seconds": duration - warmup,
        "params": dict(params),
        "color": dict(color or {"mode": "solid", "color": CYAN}),
        "metric": metric,
        "expected": expected,
        "classification": classification,
    }


# Explicit renderer-aware design.  Keys must equal the live registry at runtime.
EFFECT_DESIGN: dict[str, dict[str, Any]] = {
    "static": {
        "identity": _entry("baseline", 4, {"color": BLUE}, color={"mode": "solid", "color": BLUE}, metric="steady_nonblack", expected="Uniform medium blue; no temporal motion."),
        "contrast": ("color", {"color": AMBER}, {"color": CYAN}, 4),
    },
    "breath": {
        "identity": _entry("baseline", 9, {"period": 4.0, "min_brightness": 0.08, "waveform": "sine", "color": AMBER}, color={"mode": "solid", "color": AMBER}, metric="global_brightness_range", expected="At least two smooth global extrema across two periods."),
        "contrast": ("period", {"period": 2.0, "min_brightness": 0.08, "waveform": "sine"}, {"period": 8.0, "min_brightness": 0.08, "waveform": "sine"}, 9),
        "limit": ("min_full", {"period": 3.0, "min_brightness": 1.0, "waveform": "sine"}, 4, "Oscillator collapses to constant light."),
    },
    "color_wave": {
        "identity": _entry("baseline", 8, {"speed": 0.15, "width": 1.0, "hue_cycle_rate": 0.05, "waveform": "linear", "hue_span_degrees": 240.0}, color={"mode": "effect_default"}, metric="rgb_spatial_temporal_variance", expected="A broad multihue field drifts without brightness-only false positives."),
        "contrast": ("hue_span", {"speed": 0.1, "width": 1.0, "hue_cycle_rate": 0.0, "waveform": "linear", "hue_span_degrees": 45.0}, {"speed": 0.1, "width": 1.0, "hue_cycle_rate": 0.0, "waveform": "linear", "hue_span_degrees": 300.0}, 6),
        "limit": ("span_zero", {"speed": 0.15, "width": 1.0, "hue_cycle_rate": 0.0, "waveform": "linear", "hue_span_degrees": 0.0}, 4, "Spatial hue structure disappears."),
    },
    "chase": {
        "identity": _entry("baseline", 7, {"speed": 2.0, "width": 2, "gap": 5, "direction": "forward", "trail": 0.15, "color_source": "static", "beat_boost": 0.0}, metric="mask_translation", expected="Repeating cyan blocks translate; live width may light width+1 discrete groups."),
        "contrast": ("speed", {"speed": 1.0, "width": 2, "gap": 5, "direction": "forward", "trail": 0.15, "color_source": "static", "beat_boost": 0.0}, {"speed": 5.0, "width": 2, "gap": 5, "direction": "forward", "trail": 0.15, "color_source": "static", "beat_boost": 0.0}, 6),
        "limit": ("full_width", {"speed": 2.0, "width": 10, "gap": 0, "direction": "forward", "trail": 0.0, "color_source": "static", "beat_boost": 0.0}, 4, "Width/gap collapses the short strip into full-on."),
    },
    "comet": {
        "identity": _entry("baseline", 13, {"speed": 1.5, "tail_length": 0.4, "decay": 0.75, "count": 1, "phase_spacing": 0.5, "trajectory": "bounce"}, color={"mode": "solid", "color": AMBER}, metric="head_traversal_tail_gradient", expected="One head completes a generic deterministic bounce with a fading tail."),
        "contrast": ("tail", {"speed": 1.5, "tail_length": 0.1, "decay": 0.75, "count": 1, "phase_spacing": 0.5, "trajectory": "bounce"}, {"speed": 1.5, "tail_length": 0.7, "decay": 0.75, "count": 1, "phase_spacing": 0.5, "trajectory": "bounce"}, 8),
        "limit": ("crowded", {"speed": 2.0, "tail_length": 0.8, "decay": 0.8, "count": 16, "phase_spacing": 0.0625, "trajectory": "bounce"}, 5, "Many long tails saturate ten spatial groups."),
    },
    "audio_pulse": {
        "identity": _entry("audio", 12, {"attack": 0.6, "release": 0.08, "color": AMBER}, color={"mode": "solid", "color": AMBER}, metric="audio_envelope_response", expected="Whole-strip brightness follows live RMS bursts and decays during silence.", classification="FULL"),
        "contrast": ("envelope_rate", {"attack": 0.05, "release": 0.02}, {"attack": 1.0, "release": 0.8}, 10),
    },
    "bass_pulse": {
        "identity": _entry("audio", 12, {"attack": 0.6, "release": 0.08, "color": BLUE}, color={"mode": "solid", "color": BLUE}, metric="bass_selectivity", expected="160 Hz produces a stronger pulse than equal-level 1000/4000 Hz."),
        "contrast": ("envelope_rate", {"attack": 0.05, "release": 0.02}, {"attack": 1.0, "release": 0.8}, 10),
    },
    "spectrum": {
        "identity": _entry("audio", 8, {"bass_zones": [TARGET_ID], "mid_zones": [], "treble_zones": []}, color={"mode": "effect_default"}, metric="band_routing_rgb", expected="Three serial routings make matching bass/mid/treble stimuli red/green/blue.", classification="PARTIAL"),
        "contrast": ("routing", {"bass_zones": [TARGET_ID], "mid_zones": [], "treble_zones": []}, {"bass_zones": [], "mid_zones": [], "treble_zones": [TARGET_ID]}, 8),
    },
    "video_ambient": {
        "identity": _entry("video", 12, {"smoothing": 0.15}, color={"mode": "effect_default"}, warmup=1.0, metric="video_color_tracking", expected="The strip_31 left-zone color tracks primary scenes and hard cuts.", classification="PARTIAL"),
        "contrast": ("smoothing", {"smoothing": 0.0}, {"smoothing": 0.92}, 10),
        "limit": ("smoothing_freeze", {"smoothing": 1.0}, 5, "The accepted but pathological smoother can freeze at initial black."),
    },
    "video_audio_fusion": {
        "identity": _entry("video", 15, {"video_weight": 0.55, "audio_weight": 0.45, "bass_boost": 1.2, "treble_limit": 0.0}, color={"mode": "effect_default"}, warmup=1.5, metric="source_factorial_distance", expected="Video color remains visible while bass/RMS changes brightness; deterministic evidence disables shimmer.", classification="PARTIAL"),
        "contrast": ("source_weight", {"video_weight": 1.0, "audio_weight": 0.0, "bass_boost": 0.0, "treble_limit": 0.0}, {"video_weight": 0.25, "audio_weight": 0.75, "bass_boost": 2.0, "treble_limit": 0.0}, 10),
    },
    "calm": {
        "identity": _entry("baseline", 16, {"period": 8.0, "color": BLUE}, color={"mode": "solid", "color": BLUE}, metric="slow_global_color_cycle", expected="A slow global calm pulse completes two periods."),
        "contrast": ("period", {"period": 2.0, "color": BLUE}, {"period": 16.0, "color": BLUE}, 12),
    },
    "color_wipe": {
        "identity": _entry("baseline", 6, {"speed": 2.0, "color": CYAN, "edge_softness_px": 0.0, "progress_curve": "linear"}, metric="monotonic_lit_count", expected="Fill advances through at least eight distinct group counts."),
        "contrast": ("edge", {"speed": 0.0, "progress_source": "cue_progress", "slew_seconds": 0.0, "edge_softness_px": 0.0, "progress_curve": "linear"}, {"speed": 0.0, "progress_source": "cue_progress", "slew_seconds": 0.0, "edge_softness_px": 3.0, "progress_curve": "linear"}, 6),
        "limit": ("instant", {"speed": 1000.0, "edge_softness_px": 0.0, "progress_curve": "linear"}, 3, "The entire fill occurs too quickly to observe as motion."),
    },
    "twinkle": {
        "identity": _entry("baseline", 10, {"density": 0.35, "fade_time": 1.2, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5, "color": AMBER}, color={"mode": "solid", "color": AMBER}, warmup=1.0, metric="event_birth_death", expected="Sparse deterministic events are born, widen slightly, and die."),
        "contrast": ("density", {"density": 0.08, "fade_time": 1.0, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5}, {"density": 0.8, "fade_time": 1.0, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5}, 9),
        "limit": ("saturated", {"density": 10.0, "fade_time": 5.0, "color_source": "solid", "event_width_px": 4.0, "blur_radius_px": 3.0}, 5, "High event density/width becomes a saturated field."),
    },
    "demo": {
        "identity": _entry("baseline", 12, {"cycle_interval": 2.5, "effects": ["static", "breath", "color_wave", "single_dot"]}, color={"mode": "solid", "color": CYAN}, metric="child_cycle_inventory", expected="All four deterministic child families appear without media-dependent black sections."),
        "contrast": ("interval", {"cycle_interval": 0.8, "effects": ["static", "breath", "color_wave", "single_dot"]}, {"cycle_interval": 3.0, "effects": ["static", "breath", "color_wave", "single_dot"]}, 7),
        "limit": ("rapid", {"cycle_interval": 0.1, "effects": ["static", "breath", "color_wave", "single_dot"]}, 4, "Rapid child switching becomes visually incoherent."),
    },
    "step_pulse": {
        "identity": _entry("baseline", 6, {"period": 2.0, "duty_cycle": 0.5, "low_color": [0.02, 0.02, 0.06], "high_color": AMBER}, color={"mode": "effect_default"}, metric="two_state_transitions", expected="Exactly two dominant colors alternate repeatedly."),
        "contrast": ("duty", {"period": 2.0, "duty_cycle": 0.2, "low_color": [0.02, 0.02, 0.06], "high_color": AMBER}, {"period": 2.0, "duty_cycle": 0.8, "low_color": [0.02, 0.02, 0.06], "high_color": AMBER}, 6),
        "limit": ("duty_full", {"period": 2.0, "duty_cycle": 1.0, "low_color": [0.02, 0.02, 0.06], "high_color": AMBER}, 4, "Duty cycle removes the temporal identity."),
    },
    "single_dot": {
        "identity": _entry("baseline", 10, {"speed": 2.0, "direction": "bounce", "color": CYAN}, metric="centroid_traversal", expected="One lit group traverses indices 0 through 9 and returns."),
        "contrast": ("speed", {"speed": 1.0, "direction": "forward"}, {"speed": 5.0, "direction": "forward"}, 6),
        "limit": ("aliased", {"speed": 300.0, "direction": "forward"}, 3, "Excess speed aliases at nominal frame cadence."),
    },
    "theater_phase": {
        "identity": _entry("baseline", 4, {"speed": 2.0, "color": AMBER}, color={"mode": "solid", "color": AMBER}, metric="three_mask_cycle", expected="Exactly three masks cycle; 10 groups yield an inherent 4/3/3 wobble."),
        "contrast": ("speed", {"speed": 0.75}, {"speed": 4.0}, 5),
    },
    "flowing_bands": {
        "identity": _entry("baseline", 6, {"band_width_px": 1, "gap_width_px": 1, "base_gain": 0.08, "highlight_gain": 0.8, "steps_per_second": 1.25, "direction": "forward", "color": MAGENTA}, color={"mode": "solid", "color": MAGENTA}, warmup=0.8, metric="highlight_position_coverage", expected="Alternating bands remain visible while the highlighted band visits both halves."),
        "contrast": ("width", {"band_width_px": 1, "gap_width_px": 1, "base_gain": 0.08, "highlight_gain": 0.8, "steps_per_second": 1.25, "direction": "forward"}, {"band_width_px": 2, "gap_width_px": 1, "base_gain": 0.08, "highlight_gain": 0.8, "steps_per_second": 1.25, "direction": "forward"}, 6),
        "limit": ("wide", {"band_width_px": 10, "gap_width_px": 1, "base_gain": 0.08, "highlight_gain": 0.8, "steps_per_second": 1.0, "direction": "forward"}, 4, "One wide band removes useful spatial structure."),
    },
    "onset_ripple": {
        "identity": _entry("audio", 12, {"onset_threshold": 0.25, "wave_speed_pps": 3.0, "wave_width_px": 1.3, "decay_seconds": 1.4, "floor_gain": 0.03, "event_origin": "fixed", "propagation": "one_way", "wrap": False, "color": CYAN}, warmup=0.5, metric="triggered_wave_traversal", expected="Each broadband click births a wave that travels and decays."),
        "contrast": ("wave_speed", {"onset_threshold": 0.25, "wave_speed_pps": 1.0, "wave_width_px": 1.0, "decay_seconds": 2.0, "floor_gain": 0.0, "event_origin": "fixed", "propagation": "one_way", "wrap": False}, {"onset_threshold": 0.25, "wave_speed_pps": 9.0, "wave_width_px": 1.0, "decay_seconds": 2.0, "floor_gain": 0.0, "event_origin": "fixed", "propagation": "one_way", "wrap": False}, 9),
    },
    "heat_fire": {
        "identity": _entry("baseline", 15, {"cooling_per_second": 0.5, "spark_rate": 12.0, "spark_strength": 0.9, "diffusion": 0.45, "spark_zone_px": 2, "color": AMBER}, color={"mode": "solid", "color": AMBER}, warmup=3.0, metric="warmed_spatial_temporal_variance", expected="After warm-up, sparks diffuse upward with nonzero spatial and temporal structure."),
        "contrast": ("diffusion", {"cooling_per_second": 0.5, "spark_rate": 12.0, "spark_strength": 0.9, "diffusion": 0.1, "spark_zone_px": 2}, {"cooling_per_second": 0.5, "spark_rate": 12.0, "spark_strength": 0.9, "diffusion": 0.75, "spark_zone_px": 2}, 10),
    },
    "history_stream": {
        "identity": _entry("baseline", 8, {"steps_per_second": 2.0, "direction": "forward", "color_timeline": {"interpolation": "rgb_linear", "keyframes": [{"time": 0, "color": RED}, {"time": 2, "color": GREEN}, {"time": 4, "color": BLUE}, {"time": 7, "color": RED}]}}, color={"mode": "effect_default"}, warmup=5.0, metric="spatial_history_order", expected="After 5 s, at least three chronological colors occupy the strip."),
        "contrast": ("direction", {"steps_per_second": 2.0, "direction": "forward", "color_timeline": {"interpolation": "rgb_linear", "keyframes": [{"time": 0, "color": RED}, {"time": 2, "color": GREEN}, {"time": 4, "color": BLUE}]}}, {"steps_per_second": 2.0, "direction": "reverse", "color_timeline": {"interpolation": "rgb_linear", "keyframes": [{"time": 0, "color": RED}, {"time": 2, "color": GREEN}, {"time": 4, "color": BLUE}]}}, 8),
        "limit": ("uniform_history", {"steps_per_second": 10.0, "direction": "forward", "color": [1.0, 1.0, 1.0]}, 4, "Constant white fills ten history cells and becomes uniform."),
    },
    "coherent_noise_field": {
        "identity": _entry("baseline", 12, {"feature_size_px": 2.5, "drift_rate": 0.35, "contrast": 1.8, "floor_gain": 0.08, "ceiling_gain": 0.75, "color": CYAN}, color={"mode": "solid", "color": CYAN}, metric="joint_spatial_temporal_variance", expected="A coherent brightness field has spatial structure and slow temporal evolution."),
        "contrast": ("contrast", {"feature_size_px": 2.5, "drift_rate": 0.35, "contrast": 0.3, "floor_gain": 0.08, "ceiling_gain": 0.75}, {"feature_size_px": 2.5, "drift_rate": 0.35, "contrast": 3.0, "floor_gain": 0.08, "ceiling_gain": 0.75}, 8),
        "limit": ("contrast_zero", {"feature_size_px": 2.5, "drift_rate": 0.35, "contrast": 0.0, "floor_gain": 0.08, "ceiling_gain": 0.75}, 5, "Zero contrast makes drift invisible."),
    },
}


class ShowBuilder:
    def __init__(self, part: str) -> None:
        self.part = part
        self.time = 0.0
        self.cues: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.brightness_tracks: list[dict[str, Any]] = []

    def add(
        self,
        cue_id: str,
        duration: float,
        effect_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        color: Mapping[str, Any] | None = None,
        role: str,
        warmup: float = 0.0,
        metric: str,
        expected: str,
        classification: str = "FULL",
        origin: str = "start",
        priority: int = 10,
        transition: Mapping[str, Any] | None = None,
        extra: Mapping[str, Any] | None = None,
        pair_id: str | None = None,
        allow_black: bool = False,
        allow_full: bool = False,
        gap: float = 0.4,
        start_at: float | None = None,
        advance_time: bool = True,
        common_speed: float = 1.0,
        common_intensity: float = 1.0,
    ) -> str:
        if classification not in ALLOWED_COVERAGE:
            raise ValueError(classification)
        start = round(self.time if start_at is None else start_at, 3)
        end = round(start + duration, 3)
        effect = {
            "mode": "fixed",
            "id": effect_id,
            "speed": common_speed,
            "intensity": common_intensity,
        }
        if params:
            effect["params"] = dict(params)
        cue: dict[str, Any] = {
            "id": cue_id,
            "start": start,
            "end": end,
            "priority": priority,
            "target": {"type": "digital_strip", "id": TARGET_ID},
            "origin": origin,
            "effect": effect,
            "color": dict(color or {"mode": "solid", "color": CYAN}),
            "transition": dict(transition or {"fade_in": 0.25, "fade_out": 0.25, "blend": "replace"}),
        }
        if extra:
            cue.update(dict(extra))
        self.cues.append(cue)
        self.rows.append({
            "cue_id": cue_id,
            "campaign_part": self.part,
            "effect": effect_id,
            "role": role,
            "start": start,
            "end": end,
            "duration_seconds": duration,
            "warmup_seconds": warmup,
            "observation_seconds": duration - warmup,
            "authored_params": dict(params or {}),
            "common_speed": effect.get("speed", 1.0),
            "common_intensity": effect.get("intensity", 1.0),
            "color": dict(color or {"mode": "solid", "color": CYAN}),
            "origin": origin,
            "expected_observation": expected,
            "observability_metric": metric,
            "software_coverage": "FULL",
            "single_strip_hardware_coverage": classification,
            "pair_id": pair_id,
            "allow_black": allow_black,
            "allow_full": allow_full,
            "priority": priority,
            "blend": cue["transition"]["blend"],
        })
        if advance_time:
            self.time = end + gap
        return cue_id

    def add_identity(self, effect_id: str, design: Mapping[str, Any]) -> None:
        self.add(
            f"FX_{effect_id}_IDENTITY",
            float(design["duration"]),
            effect_id,
            params=design["params"],
            color=design["color"],
            role="IDENTITY",
            warmup=float(design["warmup_seconds"]),
            metric=str(design["metric"]),
            expected=str(design["expected"]),
            classification=str(design["classification"]),
        )

    def finish(self) -> dict[str, Any]:
        duration = round(self.time + 0.1, 3)
        return {
            "schema_version": 2,
            "show": {
                "id": f"{CAMPAIGN_VERSION}-{self.part}",
                "duration": duration,
                "defaults": {"fade_in": 0.0, "fade_out": 0.0, "blend": "replace", "min_effect_hold": 0.0, "switch_cooldown": 0.0},
                **({"brightness_tracks": self.brightness_tracks} if self.brightness_tracks else {}),
                "cues": self.cues,
            },
        }


def _add_calibration(builder: ShowBuilder) -> None:
    for cue_id, color in (("CAL_black", BLACK), ("CAL_red", [0.25, 0, 0]), ("CAL_green", [0, 0.25, 0]), ("CAL_blue", [0, 0, 0.25]), ("CAL_medium_white", [0.45, 0.45, 0.45])):
        builder.add(cue_id, 3, "static", params={"color": color}, color={"mode": "solid", "color": color}, role="CALIBRATION", metric="steady_color", expected=f"All ten logical groups show {cue_id.removeprefix('CAL_')} at a conservative level.", allow_black=cue_id == "CAL_black")
    for cue_id, origin in (("CAL_first_group", "start"), ("CAL_last_group", "end")):
        builder.add(cue_id, 3, "single_dot", params={"speed": 0.0, "direction": "forward", "color": CYAN}, role="CALIBRATION", origin=origin, metric="single_group_location", expected="Exactly one endpoint group is lit.")
    builder.add("CAL_forward_traversal", 6, "single_dot", params={"speed": 2.0, "direction": "forward", "color": CYAN}, role="CALIBRATION", metric="centroid_direction", expected="The dot travels from logical first to last.")
    builder.add("CAL_reverse_traversal", 6, "single_dot", params={"speed": 2.0, "direction": "reverse", "color": AMBER}, role="CALIBRATION", metric="centroid_direction", expected="The dot travels from logical last to first.")


def _add_contrasts_and_limits(builder: ShowBuilder, effect_ids: Iterable[str]) -> None:
    for effect_id in effect_ids:
        design = EFFECT_DESIGN[effect_id]
        axis, low, high, duration = design["contrast"]
        pair = f"{effect_id}:{axis}"
        base_color = design["identity"]["color"]
        for suffix, params in (("low", low), ("high", high)):
            authored_params = params
            authored_color = base_color
            if effect_id == "static" and "color" in params:
                authored_params = {}
                authored_color = {"mode": "solid", "color": params["color"]}
            builder.add(f"FX_{effect_id}_CONTRAST_{axis}_{suffix}", duration, effect_id, params=authored_params, color=authored_color, role="CONTRAST", metric=f"ab_{axis}", expected=f"The {axis} {suffix} state must be measurably distinct from its paired scene.", classification=design["identity"]["classification"], pair_id=pair)
        if "limit" in design:
            label, params, limit_duration, expected = design["limit"]
            builder.add(f"FX_{effect_id}_LIMIT_{label}", limit_duration, effect_id, params=params, color=base_color, role="LIMIT", metric="intentional_pathology", expected=expected, classification="UNOBSERVABLE_ON_10_GROUP" if effect_id in {"color_wave", "coherent_noise_field"} else design["identity"]["classification"], allow_black="black" in expected.lower() or "invisible" in expected.lower(), allow_full=True)


def _add_origin_color_control(builder: ShowBuilder) -> None:
    for origin in sorted(ORIGINS):
        builder.add(f"ORIGIN_wipe_{origin}", 5, "color_wipe", params={"speed": 0.0, "progress_source": "cue_progress", "slew_seconds": 0.0, "edge_softness_px": 0.0, "progress_curve": "linear"}, origin=origin, role="SHOW_FEATURE", metric="origin_mask_geometry", expected=f"A partial wipe makes the {origin} coordinate transform directly visible.")
    builder.add("COLOR_effect_default", 4, "static", params={}, color={"mode": "effect_default"}, role="SHOW_FEATURE", metric="steady_color", expected="Renderer default color remains intact.")
    builder.add("COLOR_solid", 4, "static", params={}, color={"mode": "solid", "color": AMBER}, role="SHOW_FEATURE", metric="steady_color", expected="Solid ColorSpec produces authored amber.")
    builder.add("COLOR_palette", 6, "static", params={}, color={"mode": "palette", "colors": [RED, GREEN, BLUE]}, role="SHOW_FEATURE", metric="palette_step_colors", expected="Compatibility palette steps through three distinct global colors.")
    builder.add("COLOR_SOURCE_timeline_GLOBAL", 8, "static", params={}, color={"mode": "effect_default"}, role="SHOW_FEATURE", metric="timeline_rgb_distance", expected="Cue-local color moves red to green to blue.", extra={"color_source": {"type": "timeline", "interpolation": "rgb_linear", "keyframes": [{"time": 0, "color": RED}, {"time": 4, "color": GREEN}, {"time": 8, "color": BLUE}]}})
    builder.add("COLOR_SOURCE_spatial_POSITIONAL", 6, "color_wipe", params={"speed": 1000.0, "edge_softness_px": 0.0, "progress_curve": "linear"}, color={"mode": "effect_default"}, role="SHOW_FEATURE", metric="endpoint_color_separation", expected="All ten groups span a red-green-blue spatial palette.", extra={"color_source": {"type": "spatial_palette", "palette": [RED, GREEN, BLUE]}})
    builder.add("COLOR_SOURCE_timeline_EVENT", 10, "twinkle", params={"density": 0.6, "fade_time": 2.0, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5}, color={"mode": "effect_default"}, warmup=1.0, role="SHOW_FEATURE", metric="event_birth_color_retention", expected="Events retain their birth color while the timeline changes.", extra={"color_source": {"type": "timeline", "interpolation": "rgb_linear", "keyframes": [{"time": 0, "color": RED}, {"time": 5, "color": BLUE}, {"time": 10, "color": GREEN}]}})

    # Cue-progress parameter modulation covers all non-media modulatable targets.
    modulation_cues = [
        ("MOD_breath_min_brightness", "breath", {"period": 3.0, "min_brightness": 0.1}, [{"target": "min_brightness", "mode": "drive", "source": "cue_progress", "output_min": 0.05, "output_max": 0.7}]),
        ("MOD_color_wave_hue_span", "color_wave", {"speed": 0.0, "width": 1.0, "hue_cycle_rate": 0.0, "waveform": "linear", "hue_span_degrees": 180.0}, [{"target": "hue_span_degrees", "mode": "drive", "source": "cue_progress", "output_min": 30.0, "output_max": 300.0}]),
        ("MOD_color_wipe_edge", "color_wipe", {"speed": 0.0, "progress_source": "cue_progress", "edge_softness_px": 1.0}, [{"target": "edge_softness_px", "mode": "drive", "source": "cue_progress", "output_min": 0.0, "output_max": 3.0}]),
        ("MOD_flowing_gains", "flowing_bands", {"band_width_px": 1, "gap_width_px": 1, "base_gain": 0.1, "highlight_gain": 0.6, "steps_per_second": 1.0, "direction": "forward"}, [{"target": "base_gain", "mode": "drive", "source": "cue_progress", "output_min": 0.05, "output_max": 0.3}, {"target": "highlight_gain", "mode": "drive", "source": "cue_progress", "output_min": 0.4, "output_max": 0.9}]),
        ("MOD_noise_contrast", "coherent_noise_field", {"feature_size_px": 2.5, "drift_rate": 0.0, "contrast": 1.0, "floor_gain": 0.08, "ceiling_gain": 0.75}, [{"target": "contrast", "mode": "drive", "source": "cue_progress", "output_min": 0.2, "output_max": 3.0}]),
    ]
    for cue_id, effect_id, params, bindings in modulation_cues:
        builder.add(cue_id, 8, effect_id, params=params, role="SHOW_FEATURE", metric="parameter_progress_response", expected="The approved effect-local parameter changes continuously with cue progress.", extra={"parameter_modulation": bindings})
    builder.add("SCALAR_wipe_cue_progress", 7, "color_wipe", params={"speed": 0.0, "progress_source": "cue_progress", "slew_seconds": 0.0, "edge_softness_px": 0.0}, role="SHOW_FEATURE", metric="monotonic_lit_count", expected="The native ScalarSource consumer fills from cue progress.")
    builder.add("SCALAR_twinkle_gate_gain", 9, "twinkle", params={"density": 0.7, "fade_time": 1.2, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5, "event_gate_source": "cue_progress", "birth_gain_source": "cue_progress"}, role="SHOW_FEATURE", metric="progressive_birth_rate_gain", expected="Birth count and newborn gain rise with cue progress.")
    builder.add("SCALAR_history_gain", 10, "history_stream", params={"steps_per_second": 2.0, "direction": "forward", "sample_gain_source": "cue_progress", "color": CYAN}, warmup=5.0, role="SHOW_FEATURE", metric="history_gain_gradient", expected="The stored spatial history records increasing cue-progress gain.")

    # Show controls: brightness tracks, fades, overlapping composition, common controls.
    track_start = builder.time
    builder.add("CONTROL_brightness_linear", 8, "static", params={"color": [0.45, 0.12, 0.03]}, color={"mode": "solid", "color": [0.45, 0.12, 0.03]}, role="SHOW_FEATURE", metric="global_brightness_track", expected="Linear track ramps dim to bright to dim.")
    builder.brightness_tracks.append({"id": "CONTROL_linear_track", "target": {"type": "digital_strip", "id": TARGET_ID}, "start": track_start, "end": track_start + 8, "interpolation": "linear", "keyframes": [{"time": track_start, "value": 0.15}, {"time": track_start + 4, "value": 0.8}, {"time": track_start + 8, "value": 0.15}]})
    track_start = builder.time
    builder.add("CONTROL_brightness_step", 8, "static", params={"color": BLUE}, color={"mode": "solid", "color": BLUE}, role="SHOW_FEATURE", metric="step_brightness_levels", expected="Step track holds two visibly distinct levels.")
    builder.brightness_tracks.append({"id": "CONTROL_step_track", "target": {"type": "digital_strip", "id": TARGET_ID}, "start": track_start, "end": track_start + 8, "interpolation": "step", "keyframes": [{"time": track_start, "value": 0.2}, {"time": track_start + 4, "value": 0.75}, {"time": track_start + 7.9, "value": 0.2}]})
    builder.add("CONTROL_fade", 7, "color_wipe", params={"speed": 2.0, "edge_softness_px": 0.0}, role="SHOW_FEATURE", metric="transition_weight", expected="A partial fill visibly fades in and out.", transition={"fade_in": 2.0, "fade_out": 2.0, "blend": "replace"})
    for label, overlay_blend in (("replace", "replace"), ("add", "add")):
        start = builder.time
        builder.add(
            f"CONTROL_blend_{label}_base",
            5,
            "static",
            params={"color": [0.18, 0.0, 0.0]},
            color={"mode": "solid", "color": [0.18, 0.0, 0.0]},
            role="SHOW_FEATURE",
            metric="overlap_blend_rgb",
            expected="A dim red replace contribution establishes the nonblack composition base.",
            priority=10,
            transition={"fade_in": 0.0, "fade_out": 0.0, "blend": "replace"},
            start_at=start,
            advance_time=False,
        )
        builder.add(
            f"CONTROL_blend_{label}_overlay",
            5,
            "static",
            params={"color": [0.0, 0.0, 0.18]},
            color={"mode": "solid", "color": [0.0, 0.0, 0.18]},
            role="SHOW_FEATURE",
            metric="overlap_blend_rgb",
            expected="Blue replaces red, while blue add over red yields unclipped magenta.",
            priority=20,
            transition={"fade_in": 0.0, "fade_out": 0.0, "blend": overlay_blend},
            start_at=start,
            advance_time=False,
        )
        builder.time = round(start + 5.4, 3)

    for label, red_priority, blue_priority in (("blue_wins", 10, 20), ("red_wins", 20, 10)):
        start = builder.time
        for color_name, color, priority in (("red", [0.18, 0.0, 0.0], red_priority), ("blue", [0.0, 0.0, 0.18], blue_priority)):
            builder.add(
                f"CONTROL_priority_{label}_{color_name}",
                5,
                "static",
                params={"color": color},
                color={"mode": "solid", "color": color},
                role="SHOW_FEATURE",
                metric="overlap_priority_rgb",
                expected=f"The higher-priority contribution wins the replace conflict ({label}).",
                priority=priority,
                transition={"fade_in": 0.0, "fade_out": 0.0, "blend": "replace"},
                start_at=start,
                advance_time=False,
            )
        builder.time = round(start + 5.4, 3)

    for label, multiplier in (("low", 0.5), ("high", 2.0)):
        builder.add(
            f"CONTROL_common_speed_{label}",
            6,
            "single_dot",
            params={"speed": 2.0, "direction": "forward"},
            role="CONTRAST",
            metric="common_speed_centroid_rate",
            expected=f"Show common effect.speed={multiplier} changes traversal rate while effect-local speed stays fixed.",
            common_speed=multiplier,
            pair_id="control:common_speed",
        )
    for label, multiplier in (("low", 0.25), ("high", 1.0)):
        builder.add(
            f"CONTROL_common_intensity_{label}",
            4,
            "static",
            params={"color": CYAN},
            color={"mode": "solid", "color": CYAN},
            role="CONTRAST",
            metric="common_intensity_luminance",
            expected=f"Show common effect.intensity={multiplier} changes renderer luminance without changing color.",
            common_intensity=multiplier,
            pair_id="control:common_intensity",
        )


def _add_stress_and_safe_end(builder: ShowBuilder) -> None:
    prefix = builder.part.upper()
    for index, (effect_id, params) in enumerate((
        ("static", {"color": RED}), ("static", {"color": GREEN}), ("static", {"color": BLUE}),
        ("single_dot", {"speed": 14.0, "direction": "forward"}),
        ("comet", {"speed": 12.0, "tail_length": 0.7, "decay": 0.8, "count": 8, "phase_spacing": 0.125, "trajectory": "bounce"}),
        ("demo", {"cycle_interval": 0.3, "effects": ["static", "breath", "color_wave", "single_dot"]}),
    )):
        builder.add(f"{prefix}_STRESS_rapid_{index:02d}_{effect_id}", 0.4, effect_id, params=params, role="STRESS", metric="finite_fast_switch", expected="Legal rapid switching remains finite and exception-free.", allow_full=True, gap=0.0, transition={"fade_in": 0.0, "fade_out": 0.0, "blend": "replace"})
    builder.add(f"{prefix}_STRESS_stateful_long", 24, "heat_fire", params={"cooling_per_second": 0.5, "spark_rate": 12.0, "spark_strength": 0.9, "diffusion": 0.45, "spark_zone_px": 2}, warmup=3.0, role="STRESS", metric="long_run_finite_evolution", expected="Long stateful operation shows no frozen frame, NaN, or state leakage.")
    builder.add(f"{prefix}_SAFE_fade_to_black", 3, "static", params={"color": [0.08, 0.18, 0.24]}, color={"mode": "solid", "color": [0.08, 0.18, 0.24]}, role="SAFE_END", metric="fade_to_black", expected="A conservative blue guard visibly fades to zero across the complete cue.", transition={"fade_in": 0.0, "fade_out": 3.0, "blend": "replace"}, gap=0.0)
    builder.add(f"{prefix}_SAFE_black_hold", 3, "static", params={"color": BLACK}, color={"mode": "solid", "color": BLACK}, role="SAFE_END", metric="black_output", expected="All ten logical groups remain black.", allow_black=True, transition={"fade_in": 0.0, "fade_out": 0.0, "blend": "replace"}, gap=0.0)


def _build_baseline() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    builder = ShowBuilder("baseline")
    _add_calibration(builder)
    deterministic = [effect_id for effect_id, design in EFFECT_DESIGN.items() if design["identity"]["campaign"] == "baseline"]
    for effect_id in deterministic:
        builder.add_identity(effect_id, EFFECT_DESIGN[effect_id]["identity"])
    _add_contrasts_and_limits(builder, deterministic)
    _add_origin_color_control(builder)
    _add_stress_and_safe_end(builder)
    return builder.finish(), builder.rows


def _audio_extra_cues(builder: ShowBuilder) -> None:
    for band, params in (("bass", {"bass_zones": [TARGET_ID], "mid_zones": [], "treble_zones": []}), ("mid", {"bass_zones": [], "mid_zones": [TARGET_ID], "treble_zones": []}), ("treble", {"bass_zones": [], "mid_zones": [], "treble_zones": [TARGET_ID]})):
        builder.add(f"AUD_spectrum_{band}", 8, "spectrum", params=params, color={"mode": "effect_default"}, role="MEDIA", metric="band_routing_rgb", expected=f"Matching {band} stimulus dominates the intended spectrum color.", classification="PARTIAL")
    builder.add("AUD_chase_beat_boost", 10, "chase", params={"speed": 2.0, "width": 2, "gap": 5, "direction": "forward", "trail": 0.1, "color_source": "static", "beat_boost": 3.0}, role="MEDIA", metric="beat_motion_acceleration", expected="120 BPM peaks visibly accelerate the chase.")
    builder.add("AUD_adaptive_audio_control", 24, "calm", params={"period": 6.0}, role="MEDIA", metric="adaptive_selection_state", expected="Music state, hold, cooldown, and tempo sync select visibly distinct renderers.", classification="PARTIAL", extra={"effect": {"mode": "adaptive", "allowed": {"silence": "calm", "calm": "calm", "flowing": "breath", "ambient": "breath", "rhythmic": "chase", "energetic": "comet", "impact": "comet", "transition": "color_wave"}, "fallback": "calm"}, "audio_control": {"tempo_sync": "auto", "tempo_confidence_min": 0.65, "beat_regularity_min": 0.6, "beats_per_cycle": 4.0, "beat_subdivision": 1.0, "speed_smoothing_seconds": 0.5, "state_confirmation_seconds": 0.5, "min_effect_hold": 2.0, "switch_cooldown": 1.0}})
    builder.add("AUD_common_modulation", 12, "breath", params={"period": 3.0, "min_brightness": 0.1}, role="MEDIA", metric="three_common_modulation_channels", expected="Energy, beat strength, and bass independently affect brightness/speed/intensity.", extra={"audio_modulation": {"brightness": {"source": "music.energy", "amount": 0.7, "min_multiplier": 0.3, "max_multiplier": 1.7, "smoothing_seconds": 0.1}, "speed": {"source": "music.beat_strength", "amount": 0.7, "min_multiplier": 0.4, "max_multiplier": 1.8, "smoothing_seconds": 0.1}, "intensity": {"source": "music.bass_pulse", "amount": 0.7, "min_multiplier": 0.3, "max_multiplier": 1.7, "smoothing_seconds": 0.1}}})
    builder.add("AUD_parameter_modulation", 12, "flowing_bands", params={"band_width_px": 1, "gap_width_px": 1, "base_gain": 0.08, "highlight_gain": 0.6, "steps_per_second": 1.0, "direction": "forward"}, role="MEDIA", metric="audio_parameter_response", expected="Live RMS drives highlight gain; missing/stale/zero states remain distinct.", extra={"parameter_modulation": [{"target": "highlight_gain", "mode": "drive", "source": "audio.rms", "output_min": 0.35, "output_max": 0.95, "fallback": 0.5, "smoothing_seconds": 0.1}]})
    builder.add("AUD_onset_floor_modulation", 12, "onset_ripple", params={"onset_threshold": 0.25, "wave_speed_pps": 3.0, "wave_width_px": 1.3, "decay_seconds": 1.4, "floor_gain": 0.03, "event_origin": "fixed", "propagation": "one_way", "wrap": False}, role="MEDIA", metric="audio_parameter_response", expected="Live bass drives the approved ripple floor without hiding waves.", extra={"parameter_modulation": [{"target": "floor_gain", "mode": "drive", "source": "audio.bass", "output_min": 0.0, "output_max": 0.25, "fallback": 0.03}]})
    builder.add("AUD_SCALAR_wipe_loudness", 10, "color_wipe", params={"speed": 0.0, "progress_source": "audio.loudness", "slew_seconds": 0.1, "edge_softness_px": 0.0}, role="MEDIA", metric="audio_lit_count", expected="Live loudness controls wipe fill length.")
    builder.add("AUD_SCALAR_twinkle_peak_gate", 10, "twinkle", params={"density": 1.2, "fade_time": 1.0, "color_source": "solid", "event_width_px": 1.0, "blur_radius_px": 0.5, "event_gate_source": "audio.peak", "birth_gain_source": "audio.loudness"}, role="MEDIA", metric="audio_event_birth_gain", expected="Peaks gate event births and loudness scales newborn brightness.")
    builder.add("AUD_SCALAR_history_rms", 12, "history_stream", params={"steps_per_second": 2.0, "direction": "forward", "sample_gain_source": "audio.rms", "color": CYAN}, warmup=5.0, role="MEDIA", metric="audio_spatial_history", expected="RMS history becomes a spatial trace after warm-up.")
    builder.add("AUD_COLOR_dominant_frequency_GLOBAL", 12, "static", params={}, color={"mode": "effect_default"}, role="MEDIA", metric="frequency_color_separation", expected="160/1000/4000 Hz map to distinct authored palette regions.", extra={"color_source": {"type": "dominant_frequency_palette", "frequency_min_hz": 100.0, "frequency_max_hz": 5000.0, "palette": [RED, GREEN, BLUE], "fallback": MAGENTA}})
    builder.add("AUD_COLOR_spectrum_POSITIONAL", 12, "color_wipe", params={"speed": 1000.0}, color={"mode": "effect_default"}, role="MEDIA", metric="positional_spectrum_color", expected="Ten positions sample the 16-band spectrum; this cannot prove all bins independently.", classification="PARTIAL", extra={"color_source": {"type": "audio_spectrum_palette", "palette": [BLUE, GREEN, AMBER], "fallback": MAGENTA}})
    builder.add("AUD_COLOR_fallback", 5, "static", params={"color": [1.0, 1.0, 1.0]}, color={"mode": "effect_default"}, role="MEDIA", metric="conspicuous_fallback", expected="Missing audio produces exact authored magenta over a unit renderer envelope and is never counted as live evidence.", classification="FALLBACK_ONLY", extra={"color_source": {"type": "dominant_frequency_palette", "frequency_min_hz": 100.0, "frequency_max_hz": 5000.0, "palette": [RED, BLUE], "fallback": MAGENTA}})


def _build_audio() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    builder = ShowBuilder("audio")
    for effect_id in ("audio_pulse", "bass_pulse", "spectrum", "onset_ripple"):
        builder.add_identity(effect_id, EFFECT_DESIGN[effect_id]["identity"])
    _add_contrasts_and_limits(builder, ("audio_pulse", "bass_pulse", "spectrum", "onset_ripple"))
    _audio_extra_cues(builder)
    _add_stress_and_safe_end(builder)
    return builder.finish(), builder.rows


def _build_video() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    builder = ShowBuilder("video")
    for effect_id in ("video_ambient", "video_audio_fusion"):
        builder.add_identity(effect_id, EFFECT_DESIGN[effect_id]["identity"])
    _add_contrasts_and_limits(builder, ("video_ambient", "video_audio_fusion"))
    video_color_pair = "video_color:average_vs_dominant"
    builder.add("VID_COLOR_average_GLOBAL", 12, "static", params={}, color={"mode": "effect_default"}, role="MEDIA", metric="video_average_tracking", expected="Global color follows VideoFeatures.average_rgb and hard cuts.", classification="PARTIAL", pair_id=video_color_pair, extra={"color_source": {"type": "video_average", "fallback": MAGENTA}})
    builder.add("VID_COLOR_dominant_GLOBAL", 12, "static", params={}, color={"mode": "effect_default"}, role="MEDIA", metric="video_dominant_tracking", expected="Global color follows VideoFeatures.dominant_rgb and differs from average on the identical mixed-scene input.", classification="PARTIAL", pair_id=video_color_pair, extra={"color_source": {"type": "video_dominant", "fallback": MAGENTA}})
    builder.add("VID_chase_internal_video", 12, "chase", params={"speed": 2.0, "width": 2, "gap": 5, "direction": "forward", "trail": 0.15, "color_source": "video", "beat_boost": 0.0}, role="MEDIA", metric="legacy_video_color_envelope", expected="Legacy chase video color uses average RGB while retaining its mask.", classification="PARTIAL")
    fusion_ranges = {
        "video_weight": (0.2, 0.8),
        "audio_weight": (0.2, 0.8),
        "bass_boost": (0.0, 2.5),
        "treble_limit": (0.0, 0.1),
    }
    for target, (output_min, output_max) in fusion_ranges.items():
        builder.add(
            f"VID_fusion_MOD_{target}",
            8,
            "video_audio_fusion",
            params={"video_weight": 0.55, "audio_weight": 0.45, "bass_boost": 1.0, "treble_limit": 0.0},
            color={"mode": "effect_default"},
            warmup=1.5,
            role="MEDIA",
            metric="single_parameter_progress_response",
            expected=f"Only approved target {target} is driven by cue progress; independent machine evidence inspects its resolved value.",
            classification="PARTIAL",
            extra={"parameter_modulation": [{"target": target, "mode": "drive", "source": "cue_progress", "output_min": output_min, "output_max": output_max}]},
        )
    builder.add("VID_fusion_treble_live_A", 8, "video_audio_fusion", params={"video_weight": 0.5, "audio_weight": 0.5, "bass_boost": 1.0, "treble_limit": 0.0}, color={"mode": "effect_default"}, role="CONTRAST", metric="live_shimmer_variance", expected="Live treble shimmer disabled.", classification="PARTIAL", pair_id="live_only:video_audio_fusion:treble_limit")
    builder.add("VID_fusion_treble_live_B", 8, "video_audio_fusion", params={"video_weight": 0.5, "audio_weight": 0.5, "bass_boost": 1.0, "treble_limit": 0.1}, color={"mode": "effect_default"}, role="CONTRAST", metric="live_shimmer_variance", expected="Live treble shimmer enabled below the 0.15 functional ceiling; deterministic digest is not claimed.", classification="PARTIAL", pair_id="live_only:video_audio_fusion:treble_limit")
    builder.add("VID_COLOR_fallback", 5, "static", params={"color": [1.0, 1.0, 1.0]}, color={"mode": "effect_default"}, role="MEDIA", metric="conspicuous_fallback", expected="Missing video produces exact authored magenta over a unit renderer envelope and is not live evidence.", classification="FALLBACK_ONLY", extra={"color_source": {"type": "video_average", "fallback": MAGENTA}})
    _add_stress_and_safe_end(builder)
    return builder.finish(), builder.rows


def _git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _target_facts() -> dict[str, Any]:
    profile = load_yaml(PROFILE_PATH)
    strip = next((item for item in profile["layout"]["strips"] if item["id"] == TARGET_ID), None)
    if strip is None or strip.get("type") != "digital" or strip.get("pixel_count") != 10:
        raise RuntimeError(f"live target gate failed for {TARGET_ID}: {strip!r}")
    return {"id": TARGET_ID, "type": strip["type"], "logical_group_count": strip["pixel_count"], "physical_description": "10 logical pixels / 10 WS2811 controllable groups / approximately 50 cm", "hardware_verified": False}


def scalar_sources() -> list[str]:
    audio = AudioFeatures(timestamp=0.0)
    return ["cue_progress", *sorted(scalar_module._AUDIO_FIELDS), *(f"audio.spectrum[{index}]" for index in range(len(audio.spectrum or ())))]


def _scalar_source_machine_evidence() -> list[dict[str, Any]]:
    """Execute every live normalized source, including unavailable-input behavior."""

    base_audio = AudioFeatures(
        timestamp=0.0,
        rms=0.21,
        bass=0.31,
        mid=0.41,
        treble=0.51,
        spectral_flux=0.61,
        onset=0.71,
        peak=True,
        silence=False,
    )
    spectrum_values = tuple((index + 1) / 20.0 for index in range(16))
    spectrum_audio = AudioFeatures(
        timestamp=0.0,
        rms=0.21,
        spectral_flux=0.61,
        onset=0.71,
        peak=True,
        silence=False,
        spectrum=spectrum_values,
    )
    evidence: list[dict[str, Any]] = []
    for source_name in scalar_sources():
        source = scalar_module.ScalarSource(source_name)
        if source_name == "cue_progress":
            injected = 0.625
            available_ctx = EffectContext(timestamp=0.0, delta_time=0.1, sequence=1, mode_parameters={"cue_progress": injected})
            missing_ctx = EffectContext(timestamp=0.0, delta_time=0.1, sequence=2)
            missing_optional = source.sample_optional(missing_ctx)
            missing_sample = source.sample(missing_ctx)
        else:
            audio = spectrum_audio if source_name.startswith("audio.spectrum[") else base_audio
            available_ctx = EffectContext(timestamp=0.0, delta_time=0.1, sequence=1, audio_features=audio)
            injected = source.sample_optional(available_ctx)
            missing_ctx = EffectContext(timestamp=0.0, delta_time=0.1, sequence=2, audio_features=None)
            missing_optional = source.sample_optional(missing_ctx)
            missing_sample = source.sample(missing_ctx)
        observed = source.sample_optional(available_ctx)
        if observed != injected:
            raise AssertionError((source_name, injected, observed))
        evidence.append({
            "id": f"scalar:{source_name}",
            "source": source_name,
            "consumer": "ScalarSource.sample_optional/sample machine probe",
            "injected_value": injected,
            "observed_value": observed,
            "missing_optional": missing_optional,
            "missing_sample": missing_sample,
            "result": "PASS",
        })
    return evidence


def _parameter_modulation_machine_evidence() -> list[dict[str, Any]]:
    """Inspect each approved target independently after runtime modulation."""

    ranges = {
        "breath.min_brightness": (0.05, 0.70),
        "color_wave.hue_span_degrees": (30.0, 300.0),
        "video_audio_fusion.video_weight": (0.20, 0.80),
        "video_audio_fusion.audio_weight": (0.20, 0.80),
        "video_audio_fusion.bass_boost": (0.0, 2.50),
        "video_audio_fusion.treble_limit": (0.0, 0.10),
        "color_wipe.edge_softness_px": (0.0, 3.0),
        "flowing_bands.base_gain": (0.05, 0.30),
        "flowing_bands.highlight_gain": (0.40, 0.90),
        "onset_ripple.floor_gain": (0.0, 0.25),
        "coherent_noise_field.contrast": (0.20, 3.0),
    }
    ctx = EffectContext(timestamp=0.0, delta_time=0.1, sequence=1, mode_parameters={"cue_progress": 0.25})
    evidence: list[dict[str, Any]] = []
    for full_target, (output_min, output_max) in ranges.items():
        effect_id, target = full_target.split(".", 1)
        authored = dict(EFFECT_DESIGN[effect_id]["identity"]["params"])
        binding = ParameterModulationBindingSpec(
            target=target,
            mode="drive",
            source="cue_progress",
            output_min=output_min,
            output_max=output_max,
        )
        result = CueParameterModulator(effect_id, authored, ParameterModulationSpec((binding,))).apply(ctx, authored)
        expected = output_min + (output_max - output_min) * 0.25
        observed = float(result.values[target])
        if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12):
            raise AssertionError((full_target, expected, observed))
        evidence.append({
            "id": f"parameter_modulation:{full_target}:drive",
            "target": full_target,
            "mode": "drive",
            "source": "cue_progress",
            "source_value": 0.25,
            "authored_base": authored[target],
            "expected_value": expected,
            "observed_value": observed,
            "result": "PASS",
        })

    authored = dict(EFFECT_DESIGN["breath"]["identity"]["params"])
    authored["min_brightness"] = 0.4
    modulate = ParameterModulationBindingSpec(
        target="min_brightness",
        mode="modulate",
        source="cue_progress",
        output_min=0.5,
        output_max=1.5,
    )
    result = CueParameterModulator("breath", authored, ParameterModulationSpec((modulate,))).apply(ctx, authored)
    expected = 0.4 * 0.75
    observed = float(result.values["min_brightness"])
    if not math.isclose(observed, expected, rel_tol=0.0, abs_tol=1e-12):
        raise AssertionError((expected, observed))
    evidence.append({
        "id": "parameter_modulation:breath.min_brightness:modulate",
        "target": "breath.min_brightness",
        "mode": "modulate",
        "source": "cue_progress",
        "source_value": 0.25,
        "authored_base": 0.4,
        "expected_value": expected,
        "observed_value": observed,
        "result": "PASS",
    })
    return evidence


def _show_control_machine_evidence(show_path: Path) -> list[dict[str, Any]]:
    """Render actual overlapping Show cues and inspect resolved common controls."""

    Config.reset()
    config = Config.get_instance(PROFILE_PATH)
    layout = Layout.from_config(config)
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    cue_map = {cue.id: cue for cue in show.cues}

    def pixel_at(cue_id: str) -> tuple[float, float, float]:
        cue = cue_map[cue_id]
        timestamp = cue.start + 2.0
        runtime = ShowRuntime.from_layout(show, layout, seed=41)
        base = black_base_frame(timestamp=timestamp, sequence=1, analog_zones=layout.zones, digital_strips=layout.strips)
        frame = runtime.render(EffectContext(timestamp=timestamp, delta_time=0.1, sequence=1), base)
        strip = next(item for item in frame.strips if item.strip_id == TARGET_ID)
        return tuple(float(channel) for channel in strip.pixels[0])

    replace_rgb = pixel_at("CONTROL_blend_replace_overlay")
    add_rgb = pixel_at("CONTROL_blend_add_overlay")
    blue_wins = pixel_at("CONTROL_priority_blue_wins_blue")
    red_wins = pixel_at("CONTROL_priority_red_wins_red")
    expected = {
        "replace": (0.0, 0.0, 0.18),
        "add": (0.18, 0.0, 0.18),
        "blue_wins": (0.0, 0.0, 0.18),
        "red_wins": (0.18, 0.0, 0.0),
    }
    observed = {"replace": replace_rgb, "add": add_rgb, "blue_wins": blue_wins, "red_wins": red_wins}
    if any(any(not math.isclose(a, b, rel_tol=0.0, abs_tol=1e-12) for a, b in zip(observed[key], value)) for key, value in expected.items()):
        raise AssertionError((expected, observed))
    speed_low = cue_map["CONTROL_common_speed_low"].effect.speed
    speed_high = cue_map["CONTROL_common_speed_high"].effect.speed
    intensity_low = cue_map["CONTROL_common_intensity_low"].effect.intensity
    intensity_high = cue_map["CONTROL_common_intensity_high"].effect.intensity
    return [
        {"id": "show_control:blend", "expected": {key: list(expected[key]) for key in ("replace", "add")}, "observed": {key: list(observed[key]) for key in ("replace", "add")}, "result": "PASS"},
        {"id": "show_control:priority", "expected": {key: list(expected[key]) for key in ("blue_wins", "red_wins")}, "observed": {key: list(observed[key]) for key in ("blue_wins", "red_wins")}, "result": "PASS"},
        {"id": "show_control:common_speed", "authored_low": speed_low, "authored_high": speed_high, "effect_local_speed": 2.0, "result": "PASS" if speed_low == 0.5 and speed_high == 2.0 else "FAIL"},
        {"id": "show_control:common_intensity", "authored_low": intensity_low, "authored_high": intensity_high, "result": "PASS" if intensity_low == 0.25 and intensity_high == 1.0 else "FAIL"},
    ]


def _valid_value(spec: Any, design_params: Mapping[str, Any]) -> Any:
    if spec.name in design_params:
        return design_params[spec.name]
    if spec.kind == "float":
        return spec.minimum if spec.minimum is not None and spec.minimum > 0 else 1.0
    if spec.kind == "integer":
        return int(spec.minimum if spec.minimum is not None else 1)
    if spec.kind == "boolean":
        return False
    if spec.kind == "enum":
        return spec.choices[0]
    if spec.kind == "rgb":
        return [0.2, 0.4, 0.6]
    if spec.kind == "scalar_source":
        return "cue_progress"
    if spec.kind == "color_timeline":
        return {"interpolation": "linear", "keyframes": [{"time": 0, "color": RED}, {"time": 1, "color": BLUE}]}
    if spec.kind == "id_list":
        return [TARGET_ID]
    if spec.kind == "object":
        return {}
    raise AssertionError(spec.kind)


def _relation_safe(effect_id: str, name: str, value: Any) -> dict[str, Any]:
    values = {name: value}
    if effect_id == "flowing_bands" and name == "base_gain":
        values["highlight_gain"] = 1.0
    if effect_id == "flowing_bands" and name == "highlight_gain":
        values["base_gain"] = 0.0
    if effect_id == "coherent_noise_field" and name == "floor_gain":
        values["ceiling_gain"] = 1.0
    if effect_id == "coherent_noise_field" and name == "ceiling_gain":
        values["floor_gain"] = 0.0
    return values


def _probe_parameters() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for registration in list_effect_registrations():
        design_params = EFFECT_DESIGN[registration.id]["identity"]["params"]
        registration.validator({})
        for spec in registration.parameter_specs:
            cases: list[dict[str, Any]] = [{"id": "omitted_default", "expected": "valid", "observed": "valid"}]
            valid_values: list[tuple[str, Any]] = [("representative", _valid_value(spec, design_params))]
            if spec.minimum is not None:
                valid_values.append(("minimum", int(spec.minimum) if spec.kind == "integer" else spec.minimum))
            if spec.maximum is not None:
                valid_values.append(("maximum", int(spec.maximum) if spec.kind == "integer" else spec.maximum))
            if spec.kind == "enum":
                valid_values.extend((f"choice:{choice}", choice) for choice in spec.choices)
            if spec.kind == "boolean":
                valid_values.extend((("false", False), ("true", True)))
            seen: set[str] = set()
            for case_id, value in valid_values:
                if case_id in seen:
                    continue
                seen.add(case_id)
                registration.validator(_relation_safe(registration.id, spec.name, value))
                cases.append({"id": case_id, "expected": "valid", "observed": "valid", "value": value})
            invalid_values: list[tuple[str, Any]] = [("invalid_type", object())]
            if spec.kind in {"float", "integer"}:
                invalid_values.extend((("nan", float("nan")), ("positive_inf", float("inf")), ("negative_inf", float("-inf"))))
            if spec.minimum is not None:
                invalid_values.append(("below_minimum", int(spec.minimum - 1) if spec.kind == "integer" else spec.minimum - max(1.0, abs(spec.minimum) * 0.1 + 0.01)))
            if spec.maximum is not None:
                invalid_values.append(("above_maximum", int(spec.maximum + 1) if spec.kind == "integer" else spec.maximum + max(1.0, abs(spec.maximum) * 0.1 + 0.01)))
            if spec.kind == "enum":
                invalid_values.append(("unknown_choice", "__invalid__"))
            for case_id, value in invalid_values:
                try:
                    registration.validator({spec.name: value})
                except (TypeError, ValueError):
                    observed = "rejected"
                else:
                    raise AssertionError(f"{registration.id}.{spec.name} accepted {case_id}")
                json_value = value
                if isinstance(value, float) and not math.isfinite(value):
                    json_value = repr(value)
                elif not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                    json_value = f"<{type(value).__name__}>"
                cases.append({"id": case_id, "expected": "rejected", "observed": observed, "value": json_value})
            result.append({"id": f"{registration.id}.{spec.name}", "effect": registration.id, "name": spec.name, "kind": spec.kind, "minimum": spec.minimum, "maximum": spec.maximum, "choices": list(spec.choices), "unit": spec.unit, "runtime_mutable": spec.runtime_mutable, "modulatable": spec.modulatable, "description": spec.description, "machine_cases": cases, "machine_coverage": "FULL"})
    return result


def _show_feature_inventory() -> list[dict[str, Any]]:
    return [
        {"id": "targets", "valid_values": sorted(V2_TARGET_KINDS), "consumer": "loader._target -> TargetResolver", "single_strip_hardware_coverage": "PARTIAL"},
        {"id": "origin", "valid_values": sorted(ORIGINS), "consumer": "CueRenderJob -> compositor._apply_origin", "single_strip_hardware_coverage": "FULL"},
        {"id": "color", "valid_values": sorted(COLOR_MODES), "consumer": "CueRenderJob scoped color", "single_strip_hardware_coverage": "FULL"},
        {"id": "color_source", "valid_values": sorted(COLOR_SOURCE_TYPES), "consumer": "ColorSampler", "single_strip_hardware_coverage": "PARTIAL"},
        {"id": "blend", "valid_values": sorted(BLEND_MODES), "consumer": "compose_frame", "single_strip_hardware_coverage": "FULL"},
        {"id": "brightness_tracks", "valid_values": sorted(BRIGHTNESS_INTERPOLATIONS), "consumer": "apply_brightness_tracks", "single_strip_hardware_coverage": "FULL"},
        {"id": "branch_lifecycle", "valid_values": sorted(BRANCH_LIFECYCLES), "consumer": "CueRenderJob branch jobs", "single_strip_hardware_coverage": "NOT_COVERABLE_SINGLE_STRIP"},
        {"id": "audio_modulation", "valid_values": sorted(SOURCE_FIELDS), "consumer": "CueAudioModulator", "single_strip_hardware_coverage": "PARTIAL"},
        {"id": "parameter_modulation", "valid_values": ["modulate", "drive"], "consumer": "CueParameterModulator", "single_strip_hardware_coverage": "PARTIAL"},
        {"id": "scalar_source", "valid_values": scalar_sources(), "consumer": "four native fields plus CueParameterModulator", "single_strip_hardware_coverage": "PARTIAL"},
    ]


def _capability(cap_id: str, category: str, part: str, cue_ids: list[str], software: str, hardware: str, expected: str, metric: str, limitations: list[str] | None = None) -> dict[str, Any]:
    if software not in ALLOWED_COVERAGE or hardware not in ALLOWED_COVERAGE:
        raise ValueError((software, hardware))
    return {"id": cap_id, "category": category, "campaign_part": part, "cue_ids": cue_ids, "human_cue_ids": cue_ids, "machine_evidence_ids": [], "software_coverage": software, "single_strip_hardware_coverage": hardware, "expected_observation": expected, "observability_metric": metric, "limitations": limitations or []}


def _coverage_plan(
    rows: list[dict[str, Any]],
    parameter_inventory: list[dict[str, Any]],
    scalar_evidence: list[dict[str, Any]],
    modulation_evidence: list[dict[str, Any]],
    show_control_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    registrations = list_effect_registrations()
    cue_by_effect: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cue_by_effect.setdefault(row["effect"], []).append(row)
    capabilities = [
        _capability(f"cue:{row['cue_id']}", "human_cue", row["campaign_part"], [row["cue_id"]], row["software_coverage"], row["single_strip_hardware_coverage"], row["expected_observation"], row["observability_metric"])
        for row in rows
    ]
    for registration in registrations:
        effect_rows = cue_by_effect[registration.id]
        identities = [row["cue_id"] for row in effect_rows if row["role"] == "IDENTITY"]
        contrasts = [row["cue_id"] for row in effect_rows if row["role"] == "CONTRAST"]
        classification = EFFECT_DESIGN[registration.id]["identity"]["classification"]
        capabilities.append(_capability(f"effect:{registration.id}", "effect_capability", EFFECT_DESIGN[registration.id]["identity"]["campaign"], identities + contrasts, "FULL", classification, EFFECT_DESIGN[registration.id]["identity"]["expected"], EFFECT_DESIGN[registration.id]["identity"]["metric"]))
    feature_map = {
        "origin": [row["cue_id"] for row in rows if row["cue_id"].startswith("ORIGIN_")],
        "color_spec": [row["cue_id"] for row in rows if row["cue_id"].startswith("COLOR_") and not row["cue_id"].startswith("COLOR_SOURCE")],
        "color_source": [row["cue_id"] for row in rows if "COLOR_SOURCE" in row["cue_id"] or "_COLOR_" in row["cue_id"]],
        "brightness_tracks": [row["cue_id"] for row in rows if row["cue_id"].startswith("CONTROL_brightness")],
        "transition": [row["cue_id"] for row in rows if row["cue_id"] == "CONTROL_fade"],
        "blend": [row["cue_id"] for row in rows if row["cue_id"].startswith("CONTROL_blend_")],
        "priority": [row["cue_id"] for row in rows if row["cue_id"].startswith("CONTROL_priority_")],
        "common_speed": [row["cue_id"] for row in rows if row["cue_id"].startswith("CONTROL_common_speed_")],
        "common_intensity": [row["cue_id"] for row in rows if row["cue_id"].startswith("CONTROL_common_intensity_")],
        "parameter_modulation": [row["cue_id"] for row in rows if row["cue_id"].startswith("MOD_") or "parameter_modulation" in row["cue_id"].lower()],
        "scalar_source_consumers": [row["cue_id"] for row in rows if "SCALAR_" in row["cue_id"]],
        "safe_end": [row["cue_id"] for row in rows if "_SAFE_" in row["cue_id"]],
    }
    for feature, cue_ids in feature_map.items():
        capability = _capability(f"show:{feature}", "show_feature", "shared", cue_ids, "FULL", "PARTIAL" if feature in {"color_source", "parameter_modulation", "scalar_source_consumers"} else "FULL", f"Independent Show-language evidence for {feature}.", "feature_specific")
        control_evidence_id = f"show_control:{feature}"
        if any(item["id"] == control_evidence_id for item in show_control_evidence):
            capability["machine_evidence_ids"] = [control_evidence_id]
        capabilities.append(capability)
    for cap_id, limitation in (
        ("limit:virtual_path_seam", "One physical strip has no member seam."),
        ("limit:branch_member_handoff", "A branch release requires another member/target set."),
        ("limit:cross_strip_continuity", "No second strip is observed."),
        ("limit:multi_node_sync", "One strip cannot reveal node-to-node latch skew."),
        ("limit:multi_region_video", "strip_31 observes only its left video zone."),
        ("limit:simultaneous_spectrum_zones", "Three serial routes do not prove simultaneous multi-zone mapping."),
        ("limit:multi_strip_color_continuity", "No physical boundary exists on one strip."),
    ):
        capabilities.append(_capability(cap_id, "single_strip_limit", "none", [], "PARTIAL", "NOT_COVERABLE_SINGLE_STRIP", limitation, "not_observable", [limitation]))
    color_inventory = []
    color_cues = {
        "timeline": ["COLOR_SOURCE_timeline_GLOBAL", "COLOR_SOURCE_timeline_EVENT"],
        "spatial_palette": ["COLOR_SOURCE_spatial_POSITIONAL"],
        "video_average": ["VID_COLOR_average_GLOBAL", "VID_COLOR_fallback"],
        "video_dominant": ["VID_COLOR_dominant_GLOBAL"],
        "audio_spectrum_palette": ["AUD_COLOR_spectrum_POSITIONAL"],
        "dominant_frequency_palette": ["AUD_COLOR_dominant_frequency_GLOBAL", "AUD_COLOR_fallback"],
    }
    for source_type in sorted(COLOR_SOURCE_TYPES):
        color_inventory.append({"type": source_type, "cue_ids": color_cues[source_type], "consumer_families": ["GLOBAL", "POSITIONAL", "EVENT"] if source_type == "timeline" else (["GLOBAL", "POSITIONAL"] if source_type in {"spatial_palette", "audio_spectrum_palette"} else ["GLOBAL"]), "fallback_required": source_type in {"video_average", "video_dominant", "audio_spectrum_palette", "dominant_frequency_palette"}, "software_coverage": "FULL", "single_strip_hardware_coverage": "PARTIAL" if source_type.startswith(("video", "audio", "dominant")) else "FULL"})
    scalar_evidence_by_source = {item["source"]: item for item in scalar_evidence}
    actual_scalar_consumers = {
        "cue_progress": ["color_wipe.progress_source", "twinkle.event_gate_source", "twinkle.birth_gain_source", "history_stream.sample_gain_source", "parameter_modulation"],
        "audio.loudness": ["color_wipe.progress_source", "twinkle.birth_gain_source"],
        "audio.peak": ["twinkle.event_gate_source"],
        "audio.rms": ["history_stream.sample_gain_source", "parameter_modulation"],
        "audio.bass": ["parameter_modulation"],
    }
    scalar_inventory = []
    for source in scalar_sources():
        part = "baseline" if source == "cue_progress" else "audio"
        cue_ids = {
            "cue_progress": ["SCALAR_wipe_cue_progress", "SCALAR_twinkle_gate_gain", "SCALAR_history_gain"],
            "audio.loudness": ["AUD_SCALAR_wipe_loudness", "AUD_SCALAR_twinkle_peak_gate"],
            "audio.peak": ["AUD_SCALAR_twinkle_peak_gate"],
            "audio.rms": ["AUD_SCALAR_history_rms", "AUD_parameter_modulation"],
            "audio.bass": ["AUD_onset_floor_modulation"],
        }.get(source, [])
        scalar_inventory.append({
            "source": source,
            "consumer_fields": actual_scalar_consumers.get(source, []),
            "machine_consumer": scalar_evidence_by_source[source]["consumer"],
            "machine_evidence_id": scalar_evidence_by_source[source]["id"],
            "campaign_part": part,
            "cue_ids": cue_ids,
            "software_coverage": "FULL",
            "single_strip_hardware_coverage": "PARTIAL" if source != "cue_progress" else "FULL",
        })
    modulatable_inventory = []
    target_cues = {
        "breath.min_brightness": ["MOD_breath_min_brightness"], "color_wave.hue_span_degrees": ["MOD_color_wave_hue_span"],
        "video_audio_fusion.video_weight": ["VID_fusion_MOD_video_weight"], "video_audio_fusion.audio_weight": ["VID_fusion_MOD_audio_weight"],
        "video_audio_fusion.bass_boost": ["VID_fusion_MOD_bass_boost"], "video_audio_fusion.treble_limit": ["VID_fusion_MOD_treble_limit", "VID_fusion_treble_live_A", "VID_fusion_treble_live_B"],
        "color_wipe.edge_softness_px": ["MOD_color_wipe_edge"], "flowing_bands.base_gain": ["MOD_flowing_gains"], "flowing_bands.highlight_gain": ["MOD_flowing_gains", "AUD_parameter_modulation"],
        "onset_ripple.floor_gain": ["AUD_onset_floor_modulation"], "coherent_noise_field.contrast": ["MOD_noise_contrast"],
    }
    for item in parameter_inventory:
        if item["modulatable"]:
            target_machine = [evidence for evidence in modulation_evidence if evidence["target"] == item["id"]]
            modulatable_inventory.append({"id": item["id"], "cue_ids": target_cues[item["id"]], "machine_evidence_ids": [evidence["id"] for evidence in target_machine], "modes": sorted({evidence["mode"] for evidence in target_machine}), "software_coverage": "FULL", "single_strip_hardware_coverage": "PARTIAL" if item["effect"] in {"video_audio_fusion", "onset_ripple"} else "FULL"})
    classifications = Counter(cap["single_strip_hardware_coverage"] for cap in capabilities)
    return {
        "campaign_version": CAMPAIGN_VERSION,
        "generated_from_head": _git_head(),
        "hardware_verified": False,
        "target": _target_facts(),
        "logical_group_count": 10,
        "effect_inventory": [{"id": reg.id, "parameter_count": len(reg.parameter_specs), "color_source_support": reg.color_source_support, "identity_cue_ids": [row["cue_id"] for row in cue_by_effect[reg.id] if row["role"] == "IDENTITY"]} for reg in registrations],
        "parameter_inventory": parameter_inventory,
        "show_feature_inventory": _show_feature_inventory(),
        "color_spec_inventory": sorted(COLOR_MODES),
        "color_source_inventory": color_inventory,
        "scalar_source_inventory": scalar_inventory,
        "scalar_source_machine_evidence": scalar_evidence,
        "audio_modulation_source_inventory": sorted(SOURCE_FIELDS),
        "parameter_modulation_source_inventory": sorted(set(scalar_sources()) | set(RAW_AUDIO_SOURCES)),
        "modulatable_inventory": modulatable_inventory,
        "parameter_modulation_machine_evidence": modulation_evidence,
        "show_control_machine_evidence": show_control_evidence,
        "human_cues": rows,
        "capabilities": capabilities,
        "coverage_counts": dict(sorted(classifications.items())),
        "stimulus_plans": {
            "audio": {"format": "44.1 kHz mono PCM WAV", "safe_tones_hz": [160, 1000, 4000], "timeline": ["2s silence", "3s 160Hz + 1s silence", "3s 1000Hz + 1s silence", "3s 4000Hz + 1s silence", "6s logarithmic 160-5000Hz sweep", "isolated 25ms Hann click", "8s regular 120BPM clicks", "8s irregular transients", "5s mixed continuous energy", "operator-selected 10-15s music excerpt"]},
            "video": {"format": "local deterministic 320x180 MJPG AVI", "timeline": ["black", "white", "red", "green", "blue", "brightness ramp", "dominant-color scene", "mixed-color scene", "hard cuts", "smooth RGB transition"]},
        },
        "runtime_findings": [
            "Spectrum defaults use obsolete non-strip target IDs and render black on current topology unless strip_31 routing is explicit.",
            "Chase uses dist <= width, so integer phase may light width+1 groups; documentation prose differs.",
            "Audio pulse attack/release metadata says seconds while runtime applies rate * delta_time * 60.",
            "color_wave.width is implemented as strip-relative scale despite pixel-unit metadata.",
            "video_ambient.smoothing lacks live bounds and accepted value 1 can freeze initial black.",
            "VideoAnalyzer average and dominant colors share one smoother; the two estimates contaminate each other.",
            "video_audio_fusion shimmer consumes module-global RNG; deterministic evidence disables shimmer.",
            "video_audio_fusion treble_limit values >= 0.15 are functionally duplicate for bounded treble.",
            "WLED live stale input is zero-valued AudioFeatures, not None, so authored missing-input fallbacks do not activate.",
            "WLED Audio Sync receiver has no sender filter; hardware acceptance requires exactly one stable sender.",
            "Video availability has no freshness signal; local file playback and hard-cut response must be independently observed.",
        ],
    }


def _audio_features(local_time: float) -> AudioFeatures:
    phase = int(local_time // 2) % 4
    spectrum = [0.05] * 16
    if phase == 0:
        for index in range(3): spectrum[index] = 0.9
        dominant = 160.0
    elif phase == 1:
        for index in range(3, 10): spectrum[index] = 0.8
        dominant = 1000.0
    elif phase == 2:
        for index in range(10, 16): spectrum[index] = 0.75
        dominant = 4000.0
    else:
        dominant = 600.0
    peak = abs(local_time - round(local_time)) < 0.06
    return AudioFeatures(timestamp=local_time, rms=0.65 if phase != 3 else 0.15, spectral_flux=1.0 if peak else 0.05, onset=1.0 if peak else 0.05, silence=False, raw_level=1200.0, loudness=0.65 if phase != 3 else 0.15, spectrum=tuple(spectrum), peak=peak, dominant_frequency=dominant, dominant_magnitude=1500.0)


def _video_features(local_time: float) -> VideoFeatures:
    colors = [tuple(RED), tuple(GREEN), tuple(BLUE), (0.55, 0.25, 0.10)]
    average = colors[int(local_time // 2) % len(colors)]
    dominant = colors[(int(local_time // 2) + 1) % len(colors)]
    return VideoFeatures(timestamp=local_time, average_rgb=average, dominant_rgb=dominant, zone_colors={"left": average, "right": dominant, "top": tuple(BLUE), "bottom": tuple(AMBER), "center": (0.3, 0.3, 0.3)}, brightness=max(average), saturation=0.8, scene_change=1.0 if abs(local_time % 2) < 0.11 else 0.0)


def _music_state(local_time: float) -> MusicControlState:
    strength = 0.9 if abs(local_time * 2 - round(local_time * 2)) < 0.08 else 0.2
    return MusicControlState(timestamp=local_time, tempo_bpm=120.0, tempo_confidence=0.9, beat_phase=(local_time * 2) % 1.0, beat_strength=strength, beat_regularity=0.9, energy=0.65, energy_trend=0.2, transient=strength, bass_ambient=0.45, bass_pulse=strength, spectral_motion=0.6)


def _fusion_factorial_probe(cue: Any, declaration_index: int, resolver: TargetResolver) -> dict[str, float]:
    """Hold one fusion input fixed while varying the other, then swap axes."""

    def video(color: tuple[float, float, float]) -> VideoFeatures:
        return VideoFeatures(
            timestamp=0.0,
            average_rgb=color,
            dominant_rgb=color,
            zone_colors={zone: color for zone in ("left", "right", "top", "bottom", "center")},
            brightness=max(color),
            saturation=0.8,
            scene_change=0.0,
        )

    def audio(level: float) -> AudioFeatures:
        return AudioFeatures(timestamp=0.0, rms=level, loudness=level, bass=level, mid=0.2, treble=0.0, peak=False, silence=False)

    def settled(audio_features: AudioFeatures, video_features: VideoFeatures, seed: int) -> list[list[float]]:
        job = CueRenderJob(cue, declaration_index, resolver, cue_seed=seed)
        pixels: list[list[float]] = []
        for sample in range(21):
            local_time = sample / 10.0
            contribution = job.render(EffectContext(
                timestamp=cue.start + local_time,
                delta_time=0.1,
                sequence=sample,
                audio_features=audio_features,
                video_features=video_features,
                music_control_state=_music_state(local_time),
            ))
            strip = next(item for item in contribution.digital if item.strip_id == TARGET_ID)
            pixels = [[float(channel) for channel in pixel] for pixel in strip.pixels]
        return pixels

    def distance(first: list[list[float]], second: list[list[float]]) -> float:
        return fmean(abs(a - b) for pa, pb in zip(first, second) for a, b in zip(pa, pb))

    fixed_video = video((0.2, 0.4, 0.7))
    fixed_audio = audio(0.45)
    audio_axis = distance(settled(audio(0.1), fixed_video, 51001), settled(audio(0.8), fixed_video, 51001))
    video_axis = distance(settled(fixed_audio, video((0.7, 0.05, 0.05)), 51002), settled(fixed_audio, video((0.05, 0.05, 0.7)), 51002))
    return {"fusion_audio_axis_distance": audio_axis, "fusion_video_axis_distance": video_axis}


def _metrics_for_rows(show_path: Path, rows: list[dict[str, Any]], *, fps: int = 10) -> tuple[dict[str, Any], dict[str, float]]:
    Config.reset()
    config = Config.get_instance(PROFILE_PATH)
    layout = Layout.from_config(config)
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    resolver = TargetResolver.from_layout(layout)
    cue_map = {cue.id: cue for cue in show.cues}
    metrics: dict[str, Any] = {}
    sequences: dict[str, list[list[list[float]]]] = {}
    for index, row in enumerate(rows):
        cue = cue_map[row["cue_id"]]
        job = CueRenderJob(cue, index, resolver, cue_seed=41000 + index)
        frames: list[list[list[float]]] = []
        observed_times: list[float] = []
        digest = hashlib.sha256()
        sample_count = max(2, int(math.ceil(row["duration_seconds"] * fps)))
        for sample in range(sample_count):
            local_time = min(row["duration_seconds"] - 1e-6, sample / fps)
            timestamp = cue.start + local_time
            audio_features = None if row["cue_id"] == "AUD_COLOR_fallback" else _audio_features(local_time)
            if row["effect"] == "onset_ripple":
                trigger = abs(local_time - 1.0) < 0.06
                audio_features = AudioFeatures(
                    timestamp=local_time,
                    rms=0.2,
                    loudness=0.2,
                    spectral_flux=1.0 if trigger else 0.0,
                    onset=1.0 if trigger else 0.0,
                    peak=trigger,
                    silence=False,
                    spectrum=tuple([0.4, 0.3, 0.2] + [0.0] * 13),
                )
            if row["effect"] == "video_audio_fusion":
                # Deterministic evidence deliberately disables the renderer's
                # module-global treble shimmer.  The live-only 0 vs 0.10 cue
                # pair remains in the human Show and is not assigned a digest
                # A/B acceptance threshold.
                level = 0.2 + 0.6 * ((math.sin(local_time) + 1.0) / 2.0)
                audio_features = AudioFeatures(
                    timestamp=local_time,
                    rms=level,
                    loudness=level,
                    spectrum=tuple([level, level, level] + [0.0] * 13),
                    peak=False,
                    silence=False,
                    dominant_frequency=160.0,
                    dominant_magnitude=1000.0,
                )
            video_features = None if row["cue_id"] == "VID_COLOR_fallback" else _video_features(local_time)
            ctx = EffectContext(timestamp=timestamp, delta_time=1.0 / fps, sequence=sample, audio_features=audio_features, video_features=video_features, music_control_state=_music_state(local_time))
            contribution = job.render(ctx)
            strip = next(item for item in contribution.digital if item.strip_id == TARGET_ID)
            pixels = [[float(channel) for channel in pixel] for pixel in strip.pixels]
            if not all(math.isfinite(channel) for pixel in pixels for channel in pixel):
                raise AssertionError(f"non-finite output in {row['cue_id']}")
            if local_time + 1e-9 >= row["warmup_seconds"]:
                frames.append(pixels)
                observed_times.append(local_time)
                digest.update(json.dumps(pixels, separators=(",", ":")).encode())
        sequences[row["cue_id"]] = frames
        luminance = [[0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in frame] for frame in frames]
        quantized = {tuple(round(channel * 255) for pixel in frame for channel in pixel) for frame in frames}
        lit_counts = [sum(max(pixel) > 0.02 for pixel in frame) for frame in frames]
        spatial = [pvariance(values) if len(values) > 1 else 0.0 for values in luminance]
        rgb_spatial = [fmean(pvariance([pixel[channel] for pixel in frame]) for channel in range(3)) for frame in frames]
        temporal = [fmean(abs(a - b) for pa, pb in zip(frames[i - 1], frames[i]) for a, b in zip(pa, pb)) for i in range(1, len(frames))]
        mean_brightness = [fmean(values) for values in luminance]
        unique_pixel_colors = [len({tuple(round(channel * 255) for channel in pixel) for pixel in frame}) for frame in frames]
        births = sum(current > previous for previous, current in zip(lit_counts, lit_counts[1:]))
        deaths = sum(current < previous for previous, current in zip(lit_counts, lit_counts[1:]))
        centroids = []
        brightest_indices = []
        for values in luminance:
            total = sum(values)
            centroids.append(sum(i * value for i, value in enumerate(values)) / total if total > 1e-9 else 0.0)
            brightest_indices.append(max(range(len(values)), key=values.__getitem__))
        all_black_fraction = sum(max(channel for pixel in frame for channel in pixel) <= 0.02 for frame in frames) / len(frames)
        all_white_fraction = sum(all(min(pixel) >= 0.98 for pixel in frame) for frame in frames) / len(frames)
        phase_mean_brightness = {}
        phase_mean_rgb = {}
        for phase in range(4):
            indices = [position for position, local_time in enumerate(observed_times) if int(local_time // 2) % 4 == phase]
            if indices:
                phase_mean_brightness[str(phase)] = fmean(mean_brightness[position] for position in indices)
                phase_mean_rgb[str(phase)] = [fmean(frames[position][pixel][channel] for position in indices for pixel in range(len(frames[position]))) for channel in range(3)]
        row_metrics = {
            "finite": True,
            "frame_count": len(frames),
            "digest_sha256": digest.hexdigest(),
            "unique_frame_count": len(quantized),
            "lit_group_count_min": min(lit_counts),
            "lit_group_count_max": max(lit_counts),
            "brightness_min": min(min(values) for values in luminance),
            "brightness_max": max(max(values) for values in luminance),
            "spatial_variance_mean": fmean(spatial),
            "spatial_variance_max": max(spatial),
            "rgb_spatial_variance_mean": fmean(rgb_spatial),
            "rgb_spatial_variance_max": max(rgb_spatial),
            "temporal_distance_mean": fmean(temporal) if temporal else 0.0,
            "temporal_distance_max": max(temporal) if temporal else 0.0,
            "mean_brightness_min": min(mean_brightness),
            "mean_brightness_max": max(mean_brightness),
            "unique_pixel_colors_max": max(unique_pixel_colors),
            "lit_count_birth_steps": births,
            "lit_count_death_steps": deaths,
            "centroid_min": min(centroids),
            "centroid_max": max(centroids),
            "brightest_index_min": min(brightest_indices),
            "brightest_index_max": max(brightest_indices),
            "first_pixel_rgb": frames[0][0],
            "phase_mean_brightness": phase_mean_brightness,
            "phase_mean_rgb": phase_mean_rgb,
            "all_black_fraction": all_black_fraction,
            "all_white_fraction": all_white_fraction,
            "warmup_seconds_excluded": row["warmup_seconds"],
        }
        if row["cue_id"] == "FX_video_audio_fusion_IDENTITY":
            row_metrics.update(_fusion_factorial_probe(cue, index, resolver))
        if row["cue_id"] == "FX_history_stream_IDENTITY":
            timeline = row["authored_params"]["color_timeline"]
            steps_per_second = float(row["authored_params"]["steps_per_second"])
            current_step = math.floor(observed_times[-1] * steps_per_second + 1e-12)
            first_step = max(0, current_step - len(frames[-1]) + 1)
            chronological = [evaluate_rgb_linear_timeline(timeline, step / steps_per_second) for step in range(first_step, current_step + 1)]
            expected_order = list(reversed(chronological))
            actual_order = frames[-1]
            row_metrics["history_expected_order_distance"] = fmean(abs(a - b) for actual, expected in zip(actual_order, expected_order) for a, b in zip(actual, expected))
            row_metrics["history_expected_order_rgb"] = [list(color) for color in expected_order]
            row_metrics["history_actual_order_rgb"] = actual_order
        metrics[row["cue_id"]] = row_metrics
    pair_members: dict[str, list[str]] = {}
    for row in rows:
        if row["pair_id"]:
            pair_members.setdefault(row["pair_id"], []).append(row["cue_id"])
    distances: dict[str, float] = {}
    for pair_id, members in pair_members.items():
        if len(members) != 2:
            raise AssertionError(f"contrast pair {pair_id} has {members}")
        if pair_id.startswith("live_only:"):
            continue
        first, second = sequences[members[0]], sequences[members[1]]
        count = min(len(first), len(second))
        frame_distances = [
            fmean(abs(a - b) for pa, pb in zip(first[index], second[index]) for a, b in zip(pa, pb))
            for index in range(count)
        ]
        # Ripple evidence is an isolated transient; averaging its event window
        # into several seconds of identical black would hide the intended A/B.
        distance = max(frame_distances) if pair_id == "onset_ripple:wave_speed" else fmean(frame_distances)
        distances[pair_id] = distance
    return metrics, distances


def _identity_static(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "one_frame_family": m["unique_frame_count"] == 1, "stationary": m["temporal_distance_max"] == 0.0}


def _identity_global_cycle(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "global_uniform": m["spatial_variance_max"] < 1e-12, "brightness_range": m["mean_brightness_max"] - m["mean_brightness_min"] >= 0.04, "temporal_evolution": m["unique_frame_count"] >= 10}


def _identity_spatial_temporal(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "spatial_rgb": m["rgb_spatial_variance_max"] > 1e-5, "temporal": m["temporal_distance_max"] > 1e-4}


def _identity_mask_translation(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "mask_families": m["unique_frame_count"] >= 6, "spatial_mask": m["spatial_variance_max"] > 1e-5}


def _identity_comet(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"head_traversal": m["centroid_max"] - m["centroid_min"] >= 7.0, "tail_gradient": m["unique_pixel_colors_max"] >= 3, "temporal": m["unique_frame_count"] >= 10}


def _identity_audio_global(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "global_uniform": m["spatial_variance_max"] < 1e-12, "input_response": m["mean_brightness_max"] - m["mean_brightness_min"] >= 0.08}


def _identity_bass_selectivity(m: Mapping[str, Any]) -> dict[str, bool]:
    phases = m["phase_mean_brightness"]
    bass = phases["0"]
    nonbass = max(phases["1"], phases["2"])
    return {"equal_rms_bass_dominates": bass >= nonbass * 1.5, "bass_nonblack": bass > 0.05, "global_uniform": m["spatial_variance_max"] < 1e-12}


def _identity_spectrum(m: Mapping[str, Any]) -> dict[str, bool]:
    phases = m["phase_mean_brightness"]
    bass_rgb = m["phase_mean_rgb"]["0"]
    return {"bass_route_red_dominant": bass_rgb[0] >= max(bass_rgb[1], bass_rgb[2]) * 3.0, "matching_route_nonblack": phases["0"] > 0.05, "nonmatching_route_dim": max(phases["1"], phases["2"]) <= phases["0"] * 0.35}


def _identity_video(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"nonblack": m["brightness_max"] > 0.02, "scene_tracking": m["unique_frame_count"] >= 4, "hard_cut_response": m["temporal_distance_max"] >= 0.05}


def _identity_fusion(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"audio_axis_response": m["fusion_audio_axis_distance"] >= 0.02, "video_axis_response": m["fusion_video_axis_distance"] >= 0.05, "deterministic_no_shimmer": m["temporal_distance_max"] > 0.0}


def _identity_wipe(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"lit_count_span": m["lit_group_count_max"] - m["lit_group_count_min"] >= 8, "many_fill_states": m["unique_frame_count"] >= 8}


def _identity_twinkle(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"births": m["lit_count_birth_steps"] > 0, "deaths": m["lit_count_death_steps"] > 0, "not_saturated": m["lit_group_count_min"] < 10, "temporal": m["unique_frame_count"] >= 10}


def _identity_demo(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"multiple_child_families": m["unique_frame_count"] >= 8, "spatial_and_global_frames": m["rgb_spatial_variance_max"] > 1e-5, "nonblack": m["all_black_fraction"] < 0.2}


def _identity_step(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"two_or_more_states": m["unique_frame_count"] >= 2, "brightness_separation": m["mean_brightness_max"] - m["mean_brightness_min"] >= 0.05}


def _identity_dot(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"one_group": m["lit_group_count_min"] == 1 and m["lit_group_count_max"] == 1, "full_traversal": m["centroid_max"] - m["centroid_min"] >= 8.0}


def _identity_theater(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"three_masks": m["unique_frame_count"] == 3, "ten_group_wobble": m["lit_group_count_min"] == 3 and m["lit_group_count_max"] == 4}


def _identity_flowing(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"spatial_bands": m["spatial_variance_max"] > 1e-5, "highlight_positions": m["unique_frame_count"] >= 5, "both_halves": m["centroid_max"] - m["centroid_min"] >= 4.0}


def _identity_ripple(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"triggered_temporal_response": m["temporal_distance_max"] > 0.005, "spatial_wave": m["spatial_variance_max"] > 1e-4, "brightest_group_traversal": m["brightest_index_max"] - m["brightest_index_min"] >= 7}


def _identity_fire(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"post_warmup_spatial": m["spatial_variance_max"] > 1e-5, "post_warmup_temporal": m["temporal_distance_max"] > 1e-4, "upper_activity": m["centroid_max"] >= 3.0}


def _identity_history(m: Mapping[str, Any]) -> dict[str, bool]:
    return {"spatial_history": m["rgb_spatial_variance_max"] > 1e-5, "chronological_spatial_order": m["history_expected_order_distance"] <= 1e-12, "chronological_colors": m["unique_pixel_colors_max"] >= 3, "post_warmup_frames": m["frame_count"] >= 20}


IDENTITY_METRIC_EVALUATORS = {
    "steady_nonblack": _identity_static,
    "global_brightness_range": _identity_global_cycle,
    "rgb_spatial_temporal_variance": _identity_spatial_temporal,
    "mask_translation": _identity_mask_translation,
    "head_traversal_tail_gradient": _identity_comet,
    "audio_envelope_response": _identity_audio_global,
    "bass_selectivity": _identity_bass_selectivity,
    "band_routing_rgb": _identity_spectrum,
    "video_color_tracking": _identity_video,
    "source_factorial_distance": _identity_fusion,
    "slow_global_color_cycle": _identity_global_cycle,
    "monotonic_lit_count": _identity_wipe,
    "event_birth_death": _identity_twinkle,
    "child_cycle_inventory": _identity_demo,
    "two_state_transitions": _identity_step,
    "centroid_traversal": _identity_dot,
    "three_mask_cycle": _identity_theater,
    "highlight_position_coverage": _identity_flowing,
    "triggered_wave_traversal": _identity_ripple,
    "warmed_spatial_temporal_variance": _identity_fire,
    "spatial_history_order": _identity_history,
    "joint_spatial_temporal_variance": _identity_spatial_temporal,
}


def _evaluate_identity_observability(rows: list[dict[str, Any]], metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for row in rows:
        if row["role"] != "IDENTITY":
            continue
        metric_name = row["observability_metric"]
        evaluator = IDENTITY_METRIC_EVALUATORS.get(metric_name)
        if evaluator is None:
            raise AssertionError(f"no executable identity evaluator for {metric_name}")
        checks = evaluator(metrics[row["cue_id"]])
        result = "PASS" if checks and all(checks.values()) else "FAIL"
        evidence[row["cue_id"]] = {"metric": metric_name, "checks": checks, "result": result}
    failures = {cue_id: item for cue_id, item in evidence.items() if item["result"] != "PASS"}
    if failures:
        raise AssertionError(f"identity observability failures: {failures}")
    return evidence


def _evaluate_spectrum_band_routing(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    routes = {
        "bass": ("FX_spectrum_IDENTITY", "0", 0),
        "mid": ("AUD_spectrum_mid", "1", 1),
        "treble": ("AUD_spectrum_treble", "2", 2),
    }
    evidence: dict[str, Any] = {}
    for band, (cue_id, matching_phase, expected_channel) in routes.items():
        cue_metrics = metrics[cue_id]
        rgb = cue_metrics["phase_mean_rgb"][matching_phase]
        brightness = cue_metrics["phase_mean_brightness"]
        nonmatching = [value for phase, value in brightness.items() if phase in {"0", "1", "2"} and phase != matching_phase]
        checks = {
            "expected_channel_dominant": rgb[expected_channel] >= max(rgb[channel] for channel in range(3) if channel != expected_channel) * 3.0,
            "matching_nonblack": brightness[matching_phase] > 0.05,
            "nonmatching_dim": max(nonmatching) <= brightness[matching_phase] * 0.35,
        }
        evidence[band] = {"cue_id": cue_id, "matching_phase": matching_phase, "matching_rgb": rgb, "checks": checks, "result": "PASS" if all(checks.values()) else "FAIL"}
    failures = {band: item for band, item in evidence.items() if item["result"] != "PASS"}
    if failures:
        raise AssertionError(f"spectrum band routing failures: {failures}")
    return evidence


def _write_yaml(path: Path, data: Mapping[str, Any], purpose: str) -> None:
    header = f"# created_at: 2026-08-30\n# purpose: {purpose}\n# status: approved acceptance fixture\n# source: independent live-registry generator\n# hardware_verified: false\n"
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _readme(plan: Mapping[str, Any], shows: Mapping[str, Mapping[str, Any]]) -> str:
    counts = plan["coverage_counts"]
    return f"""# Single-Strip Visual Acceptance v1

**NOT HARDWARE VERIFIED.** This directory is an acceptance fixture, not an active production Show library. It targets only `strip_31`: 10 logical pixels / 10 WS2811 controllable groups / approximately 50 cm.

## Campaign parts

| Part | Purpose | Cues | Duration |
| --- | --- | ---: | ---: |
| `baseline-show.yaml` | deterministic calibration, effects, color, Show controls, cue-progress modulation, stress | {len(shows['baseline']['show']['cues'])} | {shows['baseline']['show']['duration'] / 60:.1f} min |
| `live-audio-show.yaml` | speaker → air → one ESP32 mic → WLED Audio Sync V2 → RK3568 → strip_31 | {len(shows['audio']['show']['cues'])} | {shows['audio']['show']['duration'] / 60:.1f} min |
| `video-fusion-show.yaml` | deterministic local video plus optional live WLED audio | {len(shows['video']['show']['cues'])} | {shows['video']['show']['duration'] / 60:.1f} min |

Machine coverage is in `coverage-plan.json`; deterministic render evidence is in `../../../artifacts/baselines/single-strip-visual-v1/software-baseline.json`. Hardware coverage counts are {json.dumps(counts, sort_keys=True)}. A software `FULL` record never means hardware PASS.

## Generate and validate

```powershell
.\\.python\\Scripts\\python.exe scripts\\generate_single_strip_acceptance_campaign.py
.\\.python\\Scripts\\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/baseline-show.yaml
.\\.python\\Scripts\\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/live-audio-show.yaml
.\\.python\\Scripts\\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/video-fusion-show.yaml
```

Optional stimuli go under `artifacts/runs`, never this fixture directory:

```powershell
.\\.python\\Scripts\\python.exe scripts\\generate_single_strip_acceptance_campaign.py --stimulus-dir artifacts/runs/single-strip-visual-v1/stimuli
```

## H0–H7 RK3568 physical runbook

### H0 — Electrical and safe start

Operator confirms ESP32, WS2811 power/ground/data, actual ten controllable groups, conservative brightness, and a reachable safe-black command. Do not begin with full-white/high-brightness stress.

### H1 — Target identity

Confirm the Host resolves the expected node for `strip_31`; other nodes may be offline. Do not edit topology. Record resolved host and node 6 mapping.

### H2 — Calibration

Run the `CAL_*` section. Record RGB order, actual group count, first/last logical group, physical forward/reverse direction, DDP update, and blackout.

### H3 — Baseline Show

Run `baseline-show.yaml`. For every human cue record `PASS`, `PARTIAL`, `FAIL`, `UNOBSERVABLE_ON_10_GROUP`, or `NOT_APPLICABLE`, plus actual/expected/difference/reason, photo/video reference, and notes. LIMIT scenes are intentional pathologies and never substitute for IDENTITY.

### H4 — Live audio

Use exactly one WLED Audio Sync sender/microphone. Record its expected IP and WLED `useBandPassFilter`, AGC/gain, and FFT scaling. During the run verify diagnostics show `stale=false`, increasing `packets_valid`, and stable `last_sender`. `audio_available=true` alone is insufficient.

Play the generated WAV through a speaker into air and the ESP32 microphone. **Do not attach it as Engine `--audio`, Host `audio_path`, or audio-only `media_path`: file audio has priority and would silently bypass WLED live input.** Use an external speaker player or `run-mpv --media <stimulus.wav> --show ...`, confirming this path does not call `Engine.load_audio`.

The diagnostic tones are 160/1000/4000 Hz because they avoid default WLED bin boundaries, but the hardware preflight must first record that each tone actually dominates the intended aggregate bin group. Continue with sweep, isolated broadband click, regular and irregular beats, continuous energy, then a short real-music excerpt. Fresh silence, fresh gap, stale zero-valued features, and missing input are different states; authored fallback is not evidence of a live source.

### H5 — Local video

Play the deterministic local AVI with `video-fusion-show.yaml`. Independently confirm file open, clock/timeline movement, and response to known hard cuts. `video_available=true`, black/zero features, or a fallback color alone does not prove live video. Compare average versus dominant only on the prescribed mixed scenes and retain the known shared-smoother limitation.

### H6 — Fusion

Run local video plus speaker audio captured by the same single WLED mic. Compare video-only versus audio-heavy scenes. `treble_limit=0` is the deterministic no-shimmer baseline; live `0` versus `0.10` is the only shimmer contrast. One strip is PARTIAL for multi-region fusion.

### H7 — Safe end and recovery

Allow `SAFE_fade_to_black` and `SAFE_black_hold` to complete, stop playback, confirm `strip_31` is black, restart ESP32/RK3568 only if required, and rerun calibration without topology edits.

## Hardware observation record

```text
cue_id:
result: PASS | PARTIAL | FAIL | UNOBSERVABLE_ON_10_GROUP | NOT_APPLICABLE
expected_observation:
actual_observation:
difference:
possible_reason:
photo_or_video_reference:
operator_notes:
```

Multi-strip seams/branches, cross-strip continuity, simultaneous spectrum zones, multi-region video, multi-node synchronization, packet latch skew, and multi-strip ColorSource continuity are `NOT_COVERABLE_SINGLE_STRIP`. Hardware gates H0–H7 remain `NOT RUN` until physically executed.
"""


def write_stimuli(directory: Path) -> None:
    """Write bounded diagnostic media outside tracked baseline directories."""
    import numpy as np
    import cv2

    directory.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100
    audio: list[float] = []

    def silence(seconds: float) -> None:
        audio.extend([0.0] * int(seconds * sample_rate))

    def tone(freq: float, seconds: float, amplitude: float = 0.18) -> None:
        count = int(seconds * sample_rate)
        ramp = min(int(0.02 * sample_rate), count // 2)
        for index in range(count):
            gain = min(1.0, index / max(1, ramp), (count - 1 - index) / max(1, ramp))
            audio.append(amplitude * gain * math.sin(2 * math.pi * freq * index / sample_rate))

    silence(2); tone(160, 3); silence(1); tone(1000, 3); silence(1); tone(4000, 3); silence(1)
    count = 6 * sample_rate
    for index in range(count):
        t = index / sample_rate
        freq = 160 * (5000 / 160) ** (t / 6)
        audio.append(0.14 * math.sin(2 * math.pi * freq * t))
    silence(2)
    click = np.hanning(int(0.025 * sample_rate)) * 0.3
    audio.extend(click.tolist()); silence(2)
    for _ in range(16):
        audio.extend((np.hanning(int(0.04 * sample_rate)) * 0.25).tolist()); silence(0.46)
    for interval in (0.38, 0.83, 0.47, 0.94, 0.56, 0.72, 0.41, 0.88):
        audio.extend((np.hanning(int(0.035 * sample_rate)) * 0.25).tolist()); silence(interval)
    for index in range(5 * sample_rate):
        t = index / sample_rate
        audio.append(0.07 * (math.sin(2 * math.pi * 160 * t) + math.sin(2 * math.pi * 1000 * t) + math.sin(2 * math.pi * 4000 * t)))
    samples = np.clip(np.asarray(audio) * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(directory / "wled-live-audio-stimulus.wav"), "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(sample_rate); output.writeframes(samples.tobytes())

    width, height, fps = 320, 180, 10
    writer = cv2.VideoWriter(str(directory / "local-video-stimulus.avi"), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("MJPG VideoWriter is unavailable")
    scenes = [(0, 0, 0), (255, 255, 255), (0, 0, 255), (0, 255, 0), (255, 0, 0)]
    for color in scenes:
        frame = np.full((height, width, 3), color, dtype=np.uint8)
        for _ in range(2 * fps): writer.write(frame)
    for level in range(0, 256, 5): writer.write(np.full((height, width, 3), level, dtype=np.uint8))
    mixed = np.zeros((height, width, 3), dtype=np.uint8); mixed[:, : width // 2] = (0, 0, 255); mixed[:, width // 2 :] = (255, 0, 0)
    for _ in range(3 * fps): writer.write(mixed)
    for step in range(4 * fps):
        ratio = step / (4 * fps - 1); writer.write(np.full((height, width, 3), (int(255 * ratio), int(255 * (1 - ratio)), 0), dtype=np.uint8))
    writer.release()
    _write_json(directory / "stimulus-manifest.json", {"hardware_verified": False, "audio": "wled-live-audio-stimulus.wav", "video": "local-video-stimulus.avi", "sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir() if path.is_file() and path.name != "stimulus-manifest.json"}})


def generate(output_dir: Path = OUTPUT_DIR, baseline_dir: Path = BASELINE_DIR) -> dict[str, Any]:
    _target_facts()
    live_ids = [registration.id for registration in list_effect_registrations()]
    if set(EFFECT_DESIGN) != set(live_ids):
        raise RuntimeError(f"visual design table drift: live={live_ids}, designed={sorted(EFFECT_DESIGN)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline, baseline_rows = _build_baseline()
    audio, audio_rows = _build_audio()
    video, video_rows = _build_video()
    shows = {"baseline": baseline, "audio": audio, "video": video}
    paths = {"baseline": output_dir / "baseline-show.yaml", "audio": output_dir / "live-audio-show.yaml", "video": output_dir / "video-fusion-show.yaml"}
    _write_yaml(paths["baseline"], baseline, "Deterministic single-strip visual identity, contrast, limits, Show controls, stress, and safe end")
    _write_yaml(paths["audio"], audio, "Live WLED Audio Sync single-strip effects, consumers, modulation, color, and safe end")
    _write_yaml(paths["video"], video, "Local deterministic video and optional live-audio fusion on one strip")
    rows = baseline_rows + audio_rows + video_rows
    parameter_inventory = _probe_parameters()
    scalar_evidence = _scalar_source_machine_evidence()
    modulation_evidence = _parameter_modulation_machine_evidence()
    show_control_evidence = _show_control_machine_evidence(paths["baseline"])
    plan = _coverage_plan(rows, parameter_inventory, scalar_evidence, modulation_evidence, show_control_evidence)
    _write_json(output_dir / "coverage-plan.json", plan)
    metrics: dict[str, Any] = {}
    distances: dict[str, float] = {}
    for part, part_rows in (("baseline", baseline_rows), ("audio", audio_rows), ("video", video_rows)):
        part_metrics, part_distances = _metrics_for_rows(paths[part], part_rows)
        metrics.update(part_metrics); distances.update(part_distances)
    identity_observability = _evaluate_identity_observability(rows, metrics)
    spectrum_band_routing = _evaluate_spectrum_band_routing(metrics)
    baseline_data = {
        "campaign_version": CAMPAIGN_VERSION,
        "generated_from_head": plan["generated_from_head"],
        "hardware_verified": False,
        "evidence_kind": "deterministic software observability only",
        "effect_count": len(live_ids),
        "parameter_count": len(parameter_inventory),
        "modulatable_count": len(plan["modulatable_inventory"]),
        "cue_counts": {part: len(show["show"]["cues"]) for part, show in shows.items()},
        "show_sha256": {part: hashlib.sha256(path.read_bytes()).hexdigest() for part, path in paths.items()},
        "cue_metrics": metrics,
        "identity_observability": identity_observability,
        "spectrum_band_routing": spectrum_band_routing,
        "ab_sequence_distances": distances,
        "ab_metric_reducers": {pair_id: ("max_event_frame_rgb_distance" if pair_id == "onset_ripple:wave_speed" else "mean_sequence_rgb_distance") for pair_id in distances},
        "coverage_counts": plan["coverage_counts"],
        "limitations": [cap["id"] for cap in plan["capabilities"] if cap["single_strip_hardware_coverage"] == "NOT_COVERABLE_SINGLE_STRIP"],
    }
    _write_json(baseline_dir / "software-baseline.json", baseline_data)
    (output_dir / "README.md").write_text(_readme(plan, shows), encoding="utf-8")
    return {"shows": paths, "coverage_plan": output_dir / "coverage-plan.json", "software_baseline": baseline_dir / "software-baseline.json", "readme": output_dir / "README.md"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--baseline-dir", type=Path, default=BASELINE_DIR)
    parser.add_argument("--stimulus-dir", type=Path)
    args = parser.parse_args()
    result = generate(args.output_dir, args.baseline_dir)
    if args.stimulus_dir is not None:
        write_stimuli(args.stimulus_dir)
    print(json.dumps({key: str(value) for key, value in result.items()}, indent=2))


if __name__ == "__main__":
    main()
