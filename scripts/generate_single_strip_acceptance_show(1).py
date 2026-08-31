"""Generate the single-strip (strip_31) RK3568 hardware acceptance campaign.

Coverage scope is enumerated from the live ``light_engine.effects`` registry
(``list_effect_registrations``).  No effect list is hand-written here: a
registered effect without a scenario entry, a scenario referencing an unknown
or renamed parameter, an out-of-range value, or an uncovered enum choice or
declared boundary is a hard generation error.  Human input is limited to the
10px visual scenario shaping (IDENTITY / CONTRAST / LIMIT), which renderer
identity cannot be inferred mechanically from ParameterSpec metadata.

Outputs (deterministic, idempotent; the "(1)" suffix marks this newer
generation alongside the earlier single-strip-visual-v1 draft):
  config/acceptance/single-strip-acceptance-v1/show(1).yaml            Part 1+2
  config/acceptance/single-strip-acceptance-v1/show-video(1).yaml      Part 3
  config/acceptance/single-strip-acceptance-v1/coverage-manifest(1).json
  config/acceptance/single-strip-acceptance-v1/README(1).md

Run with ``--check`` to verify the committed files still match the live
registry byte-for-byte (used by the sync test).

The generated evidence is software-only and never records a hardware pass.
LIMIT cues are intentional pathologies; their degradation on real hardware is
an acceptance finding, not a failure to engineer away.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from light_engine.effects import (  # noqa: E402
    get_effect_parameter_specs,
    get_effect_registration,
    list_effects,
    validate_effect_params,
)
from light_engine.show.loader import (  # noqa: E402
    BLEND_MODES,
    COLOR_MODES,
    COLOR_SOURCE_TYPES,
    ORIGINS,
)

TARGET_ID = "strip_31"
PROFILE_PATH = Path("config/profiles/rk3588-host-service.yaml")
OUT_DIR = Path("config/acceptance/single-strip-acceptance-v1")
CREATED_AT = "2026-08-30"
SHOW_ID_MAIN = "single-strip-acceptance-v1"
SHOW_ID_VIDEO = "single-strip-acceptance-video-v1"
PRIORITY_BASE = 10
PRIORITY_OVERLAY = 20

# Metric classes consumed by tests/test_single_strip_acceptance_observability.py
CLASS_UNIFORM_STATIC = "UNIFORM_STATIC"
CLASS_UNIFORM_BLACK = "UNIFORM_BLACK"
CLASS_UNIFORM_TEMPORAL = "UNIFORM_TEMPORAL"
CLASS_SPATIAL = "SPATIAL"
CLASS_EVENT = "EVENT"
CLASS_BLACK_UNTIL_MEDIA = "BLACK_UNTIL_MEDIA"
CLASS_RAPID_SWITCH = "RAPID_SWITCH"
CLASS_EXPECTED_DEGRADED = "EXPECTED_DEGRADED"
CLASS_VIDEO_INPUT = "VIDEO_INPUT"


class GenerationError(RuntimeError):
    """Raised when scenario data disagrees with the live registry."""


@dataclass
class CueSpec:
    """One authored acceptance cue before timeline placement."""

    id: str
    duration: float
    effect_id: str
    params: dict[str, Any] = field(default_factory=dict)
    speed: float | None = None
    intensity: float | None = None
    color: list[float] | None = None
    palette: list[list[float]] | None = None
    color_source: dict[str, Any] | None = None
    color_timeline: list[dict[str, Any]] | None = None
    origin: str | None = None
    priority: int = PRIORITY_BASE
    fade_in: float = 0.0
    fade_out: float = 0.0
    blend: str | None = None
    audio_modulation: dict[str, Any] | None = None
    parameter_modulation: list[dict[str, Any]] | None = None
    audio_control: dict[str, Any] | None = None
    adaptive: dict[str, str] | None = None
    fallback: str | None = None
    role: str = "identity"
    pair: str | None = None
    metric_class: str = CLASS_SPATIAL
    expected: str = ""
    warmup: float = 0.0
    start: float = 0.0
    part: str = "main"


def _validate_cue(spec: CueSpec) -> None:
    """Validate one cue against the live registry and loader vocabularies."""
    if spec.effect_id not in list_effects():
        raise GenerationError(f"{spec.id}: unknown effect {spec.effect_id!r}")
    registration = get_effect_registration(spec.effect_id)
    try:
        validate_effect_params(spec.effect_id, spec.params)
    except ValueError as exc:
        raise GenerationError(f"{spec.id}: {exc}") from exc
    unknown = set(spec.params) - set(registration.parameter_keys)
    if unknown:
        raise GenerationError(f"{spec.id}: unknown params {sorted(unknown)}")
    if spec.speed is not None and (not isinstance(spec.speed, (int, float)) or spec.speed < 0):
        raise GenerationError(f"{spec.id}: effect.speed must be >= 0")
    if spec.intensity is not None and (
        not isinstance(spec.intensity, (int, float)) or spec.intensity < 0
    ):
        raise GenerationError(f"{spec.id}: effect.intensity must be >= 0")
    if spec.color is not None:
        if spec.palette is not None:
            raise GenerationError(f"{spec.id}: color and palette are mutually exclusive")
        _validate_rgb(spec.color, f"{spec.id}.color")
    if spec.palette is not None:
        if not spec.palette:
            raise GenerationError(f"{spec.id}: palette must be non-empty")
        for entry in spec.palette:
            _validate_rgb(entry, f"{spec.id}.palette")
    if spec.origin is not None and spec.origin not in ORIGINS:
        raise GenerationError(f"{spec.id}: origin {spec.origin!r} not in {ORIGINS}")
    if spec.blend is not None and spec.blend not in BLEND_MODES:
        raise GenerationError(f"{spec.id}: blend {spec.blend!r} not in {BLEND_MODES}")
    if spec.color_source is not None:
        source_type = spec.color_source.get("type")
        if source_type not in COLOR_SOURCE_TYPES:
            raise GenerationError(f"{spec.id}: color_source type {source_type!r} invalid")
        if registration.color_source_support == "NOT_APPLICABLE":
            raise GenerationError(
                f"{spec.id}: effect {spec.effect_id!r} rejects a color_source block"
            )
        for key in ("palette",):
            if key in spec.color_source:
                for entry in spec.color_source[key]:
                    _validate_rgb(entry, f"{spec.id}.color_source.{key}")
        if "fallback" in spec.color_source:
            _validate_rgb(spec.color_source["fallback"], f"{spec.id}.color_source.fallback")
    if spec.adaptive is not None:
        if not spec.fallback:
            raise GenerationError(f"{spec.id}: adaptive cue requires fallback")
        if spec.params or spec.color_source is not None:
            raise GenerationError(f"{spec.id}: adaptive cue cannot author params/color_source")
        for state, effect_id in spec.adaptive.items():
            if effect_id not in list_effects():
                raise GenerationError(f"{spec.id}: adaptive state {state} -> unknown effect")
    if spec.parameter_modulation:
        specs = {item.name: item for item in get_effect_parameter_specs(spec.effect_id)}
        for binding in spec.parameter_modulation:
            target = binding.get("target")
            if target not in specs:
                raise GenerationError(f"{spec.id}: modulation target {target!r} not registered")
            item = specs[target]
            if not (item.kind == "float" and item.runtime_mutable and item.modulatable):
                raise GenerationError(
                    f"{spec.id}: modulation target {target!r} is not a modulatable float"
                )
            mode = binding.get("mode", "modulate")
            if mode not in {"modulate", "drive"}:
                raise GenerationError(f"{spec.id}: modulation mode {mode!r} invalid")
            if mode == "modulate" and target not in spec.params:
                raise GenerationError(
                    f"{spec.id}: modulate requires authored base param {target!r}"
                )
    if spec.duration <= 0:
        raise GenerationError(f"{spec.id}: duration must be > 0")
    for value in (spec.warmup,):
        if value < 0 or value >= spec.duration:
            raise GenerationError(f"{spec.id}: warmup must be in [0, duration)")


def _validate_rgb(value: Any, label: str) -> None:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(
            not isinstance(channel, (int, float))
            or not math.isfinite(float(channel))
            or not 0.0 <= float(channel) <= 1.0
            for channel in value
        )
    ):
        raise GenerationError(f"{label} must be 3 channels in [0, 1]")


def cue(cid: str, duration: float, effect_id: str, **kwargs: Any) -> CueSpec:
    """Build and validate one cue spec."""
    spec = CueSpec(id=cid, duration=duration, effect_id=effect_id, **kwargs)
    _validate_cue(spec)
    return spec


def _timeline(cues: list[CueSpec], start: float) -> float:
    """Place cues sequentially and return the resulting cursor."""
    cursor = start
    for spec in cues:
        spec.start = cursor
        cursor += spec.duration
    return cursor


def _overlay(base_id: str, specs: list[CueSpec]) -> None:
    """Set overlay cues to start inside their base cue window."""
    by_id = {spec.id: spec for spec in specs}
    base = by_id[base_id]
    for spec in specs:
        if spec.id == base_id:
            continue
        spec.start = base.start + (base.duration - spec.duration) / 2.0


# ---------------------------------------------------------------------------
# Scenario table.  Every registered effect MUST have an entry; every enum
# choice and every declared min/max boundary must be exercised by at least one
# cue.  Values follow the 10px visual study: authored visible levels >= 0.2
# under the rk3588 profile (gamma 1.3, max_brightness 0.65), contrast pairs
# >= 0.25 apart, cue durations derived from renderer cycle/traversal math.
# ---------------------------------------------------------------------------


def _s0_safety(pixel_count: int) -> list[CueSpec]:
    full = [1.0, 1.0, 1.0]
    cues = [
        cue("cal_black_hold", 2.0, "static", params={"color": [0.0, 0.0, 0.0]},
            metric_class=CLASS_UNIFORM_BLACK, role="identity",
            expected="all-black safe state"),
        cue("cal_red_solid", 2.0, "static", params={"color": [1.0, 0.0, 0.0]},
            metric_class=CLASS_UNIFORM_STATIC, role="identity",
            expected="10 uniform red groups (wiring/order check)"),
        cue("cal_green_solid", 2.0, "static", params={"color": [0.0, 1.0, 0.0]},
            metric_class=CLASS_UNIFORM_STATIC, role="identity",
            expected="10 uniform green groups"),
        cue("cal_blue_solid", 2.0, "static", params={"color": [0.0, 0.0, 1.0]},
            metric_class=CLASS_UNIFORM_STATIC, role="identity",
            expected="10 uniform blue groups"),
        cue("cal_white_solid", 2.0, "static", params={"color": full},
            metric_class=CLASS_UNIFORM_STATIC, role="identity",
            expected="10 uniform white groups"),
    ]
    # Fixed order (ORIGINS is a set; iteration order must not leak into output)
    for origin in ("start", "end", "center", "edges"):
        note = {
            "start": "dot runs 0->9",
            "end": "dot runs 9->0 (mirrored)",
            "center": "content folds outward from middle",
            "edges": "two dots glide from both ends inward",
        }[origin]
        cues.append(
            cue(f"cal_origin_{origin}", 4.0, "single_dot",
                params={"speed": 3.0, "direction": "forward", "color": [0.1, 1.0, 0.1]},
                origin=origin, metric_class=CLASS_SPATIAL, role="identity",
                expected=f"origin={origin}: {note}"),
        )
    return cues


def _s1_effects(pixel_count: int) -> list[CueSpec]:
    n = pixel_count
    cues: list[CueSpec] = []

    # static -----------------------------------------------------------------
    cues += [
        cue("fx_static_identity", 2.0, "static", params={"color": [1.0, 0.0, 0.0]},
            metric_class=CLASS_UNIFORM_STATIC, expected="uniform saturated red"),
        cue("fx_static_con_a", 2.0, "static", params={"color": [1.0, 0.0, 0.0]},
            intensity=1.0, role="contrast_a", pair="fx_static_con",
            metric_class=CLASS_UNIFORM_STATIC, expected="full red"),
        cue("fx_static_con_b", 2.0, "static", params={"color": [1.0, 0.0, 0.0]},
            intensity=0.3, role="contrast_b", pair="fx_static_con",
            metric_class=CLASS_UNIFORM_STATIC, expected="dim red (common intensity)"),
        cue("fx_static_lim_black", 1.5, "static", params={"color": [0.0, 0.0, 0.0]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="all black (off-path)"),
        cue("fx_static_lim_intensity10", 1.5, "static", params={"color": [1.0, 0.0, 0.0]},
            intensity=10.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="clamped to full, no overdrive"),
    ]

    # breath -----------------------------------------------------------------
    cues += [
        cue("fx_breath_identity", 7.0, "breath",
            params={"period": 3.0, "min_brightness": 0.05, "waveform": "sine",
                    "color": [0.55, 0.2, 1.0]},
            warmup=0.2, metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="whole strip swells dim->bright->dim, 2+ cycles"),
        cue("fx_breath_con_a", 7.0, "breath",
            params={"period": 3.0, "min_brightness": 0.05, "waveform": "sine",
                    "color": [0.55, 0.2, 1.0]},
            role="contrast_a", pair="fx_breath_wave",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="sine: lingers at extremes"),
        cue("fx_breath_con_b", 7.0, "breath",
            params={"period": 3.0, "min_brightness": 0.05, "waveform": "triangle",
                    "color": [0.55, 0.2, 1.0]},
            role="contrast_b", pair="fx_breath_wave",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="triangle: linear ramp"),
        cue("fx_breath_wave_smoothstep", 5.0, "breath",
            params={"period": 3.0, "min_brightness": 0.1, "waveform": "smoothstep",
                    "color": [0.55, 0.2, 1.0]},
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="smoothstep branch"),
        cue("fx_breath_lim_period_micro", 2.0, "breath",
            params={"period": 0.001, "min_brightness": 0.3, "color": [0.55, 0.2, 1.0]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="1kHz flicker integrates to dim blur"),
        cue("fx_breath_lim_min0", 4.0, "breath",
            params={"period": 2.0, "min_brightness": 0.0, "color": [0.55, 0.2, 1.0]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="strip goes fully dark each cycle (min boundary)"),
        cue("fx_breath_lim_min1", 4.0, "breath",
            params={"period": 2.0, "min_brightness": 1.0, "color": [0.55, 0.2, 1.0]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="flat full brightness, mechanism invisible (max boundary)"),
        cue("fx_breath_lim_period_max", 2.0, "breath",
            params={"period": 600.0, "min_brightness": 0.1, "color": [0.55, 0.2, 1.0]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="single half-cycle for the whole cue: near-static (unbounded stress)"),
    ]

    # color_wave -------------------------------------------------------------
    cw = {"speed": 0.5, "width": 1.0, "waveform": "sine", "hue_span_degrees": 360.0,
          "hue_cycle_rate": 0.0}
    cues += [
        cue("fx_colorwave_identity", 5.0, "color_wave", params=dict(cw),
            warmup=0.2, metric_class=CLASS_SPATIAL,
            expected="one full rainbow band gliding 0->9 every 2s"),
        cue("fx_colorwave_con_a", 5.0, "color_wave", params=dict(cw, width=1.0),
            role="contrast_a", pair="fx_colorwave_width",
            metric_class=CLASS_SPATIAL, expected="one rainbow across 10px"),
        cue("fx_colorwave_con_b", 5.0, "color_wave", params=dict(cw, width=0.2),
            role="contrast_b", pair="fx_colorwave_width",
            metric_class=CLASS_SPATIAL, expected="five compressed rainbows"),
        cue("fx_colorwave_wave_linear", 4.0, "color_wave",
            params=dict(cw, waveform="linear", hue_cycle_rate=0.3),
            metric_class=CLASS_SPATIAL, expected="linear hue ramp branch"),
        cue("fx_colorwave_wave_triangle", 4.0, "color_wave",
            params=dict(cw, waveform="triangle", hue_cycle_rate=0.3),
            metric_class=CLASS_SPATIAL, expected="triangle branch"),
        cue("fx_colorwave_wave_saw", 4.0, "color_wave",
            params=dict(cw, waveform="saw", hue_cycle_rate=0.3),
            metric_class=CLASS_SPATIAL, expected="saw branch"),
        cue("fx_colorwave_lim_span0", 2.0, "color_wave",
            params=dict(cw, hue_span_degrees=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="uniform color, no wave (min boundary)"),
        cue("fx_colorwave_lim_speed0", 2.0, "color_wave", params=dict(cw, speed=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="static gradient"),
        cue("fx_colorwave_lim_speed50", 1.5, "color_wave", params=dict(cw, speed=50.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="hue strobe mush"),
        cue("fx_colorwave_lim_width100", 2.0, "color_wave", params=dict(cw, width=100.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="wavelength 1000px: near-uniform tint drift"),
        cue("fx_colorwave_lim_rate5", 2.0, "color_wave",
            params=dict(cw, hue_cycle_rate=5.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="base hue rotates faster than perceivable"),
    ]

    # chase ------------------------------------------------------------------
    ch = {"speed": 5.0, "width": 1, "gap": 4, "direction": "forward", "trail": 0.4,
          "color_source": "static", "beat_boost": 0.0}
    cues += [
        cue("fx_chase_identity", 3.5, "chase", params=dict(ch),
            color=[1.0, 0.55, 0.15], metric_class=CLASS_SPATIAL,
            expected="two 1px dots marching 0->9, 1s pattern period"),
        cue("fx_chase_con_a", 3.0, "chase", params=dict(ch, gap=4),
            color=[1.0, 0.55, 0.15], role="contrast_a", pair="fx_chase_gap",
            metric_class=CLASS_SPATIAL, expected="two dots (period 5px)"),
        cue("fx_chase_con_b", 3.0, "chase", params=dict(ch, gap=14),
            color=[1.0, 0.55, 0.15], role="contrast_b", pair="fx_chase_gap",
            metric_class=CLASS_SPATIAL, expected="one lone dot (period 15px > strip)"),
        cue("fx_chase_con_dir_a", 4.0, "chase", params=dict(ch),
            color=[1.0, 0.55, 0.15], role="contrast_a", pair="fx_chase_dir",
            metric_class=CLASS_SPATIAL, expected="forward march"),
        cue("fx_chase_con_dir_b", 4.0, "chase", params=dict(ch, direction="bounce"),
            color=[1.0, 0.55, 0.15], role="contrast_b", pair="fx_chase_dir",
            metric_class=CLASS_SPATIAL, expected="bounce reverses at px9"),
        cue("fx_chase_dir_reverse", 3.0, "chase", params=dict(ch, direction="reverse"),
            color=[1.0, 0.55, 0.15], metric_class=CLASS_SPATIAL,
            expected="reverse march branch"),
        cue("fx_chase_src_rainbow", 3.0, "chase", params=dict(ch, color_source="rainbow"),
            metric_class=CLASS_SPATIAL,
            expected="rainbow: per-index hue gradient, window moves (hue does NOT travel)"),
        cue("fx_chase_lim_width_full", 2.0, "chase", params=dict(ch, width=10, gap=0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="all pixels lit, motion invisible"),
        cue("fx_chase_lim_width0", 1.5, "chase", params=dict(ch, width=0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="all black"),
        cue("fx_chase_lim_speed0", 1.5, "chase", params=dict(ch, speed=0.0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="frozen pattern"),
        cue("fx_chase_lim_speed100", 1.5, "chase", params=dict(ch, speed=100.0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="shimmer aliasing"),
        cue("fx_chase_lim_trail_flat", 2.0, "chase", params=dict(ch, trail=1000.0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="trail saturates: full window, no decay"),
        cue("fx_chase_lim_beatboost", 2.5, "chase", params=dict(ch, beat_boost=4.0),
            color=[1.0, 0.55, 0.15], role="limit", metric_class=CLASS_SPATIAL,
            expected="P1: normal speed (no beat input); P2: march accelerates on beats"),
    ]

    # comet ------------------------------------------------------------------
    cm = {"speed": 6.0, "tail_length": 0.4, "decay": 0.85, "count": 2,
          "phase_spacing": 0.5, "trajectory": "wrap"}
    cues += [
        cue("fx_comet_identity", 5.0, "comet", params=dict(cm),
            color=[1.0, 1.0, 0.85], warmup=0.3, metric_class=CLASS_SPATIAL,
            expected="two white heads with ~4px tails wrap the strip (2.5 cycles)"),
        cue("fx_comet_con_a", 5.0, "comet", params=dict(cm),
            color=[1.0, 1.0, 0.85], role="contrast_a", pair="fx_comet_traj",
            metric_class=CLASS_SPATIAL, expected="wrap: exits one end, re-enters other"),
        cue("fx_comet_con_b", 5.0, "comet", params=dict(cm, trajectory="bounce"),
            color=[1.0, 1.0, 0.85], role="contrast_b", pair="fx_comet_traj",
            metric_class=CLASS_SPATIAL, expected="bounce: decelerates and returns"),
        cue("fx_comet_traj_sine", 4.0, "comet", params=dict(cm, trajectory="sine"),
            color=[1.0, 1.0, 0.85], metric_class=CLASS_SPATIAL,
            expected="sine trajectory branch"),
        cue("fx_comet_lim_count1", 4.0, "comet",
            params={"speed": 6.0, "tail_length": 0.4, "decay": 0.85, "count": 1,
                    "trajectory": "wrap"},
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_SPATIAL,
            expected="count=1 legacy wrap branch (authored color keeps it deterministic)"),
        cue("fx_comet_lim_tail0", 2.0, "comet", params=dict(cm, tail_length=0.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="no tail: bare heads only (min boundary)"),
        cue("fx_comet_lim_decay0", 2.0, "comet", params=dict(cm, decay=0.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="tail vanishes instantly behind the head (min boundary)"),
        cue("fx_comet_lim_phase0", 2.0, "comet", params=dict(cm, phase_spacing=0.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="emitters fully overlapped into one (min boundary)"),
        cue("fx_comet_lim_phase1", 2.0, "comet", params=dict(cm, phase_spacing=1.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="emitters coincide at the same phase (max boundary)"),
        cue("fx_comet_lim_count64", 2.0, "comet", params=dict(cm, count=64),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="64 emitters saturate all 10px (max boundary)"),
        cue("fx_comet_lim_tail_full", 2.5, "comet", params=dict(cm, tail_length=5.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="50px tail covers whole strip"),
        cue("fx_comet_lim_decay1", 2.5, "comet", params=dict(cm, decay=1.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="tail never fades, strip fills (max boundary)"),
        cue("fx_comet_lim_speed0", 1.5, "comet", params=dict(cm, speed=0.0),
            color=[1.0, 1.0, 0.85], role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="frozen head"),
    ]

    # calm -------------------------------------------------------------------
    ca = {"period": 5.0, "color": [0.15, 0.35, 1.0]}
    cues += [
        cue("fx_calm_identity", 10.0, "calm", params=dict(ca),
            warmup=1.0, metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="faint desaturated blue, slow hue drift; amplitude via brightness track"),
        cue("fx_calm_con_a", 8.0, "calm", params=dict(ca, period=3.0),
            role="contrast_a", pair="fx_calm_period",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="visible hue sway"),
        cue("fx_calm_con_b", 8.0, "calm", params=dict(ca, period=15.0),
            role="contrast_b", pair="fx_calm_period",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="nearly static tint"),
        cue("fx_calm_lim_period_micro", 2.0, "calm", params=dict(ca, period=0.001),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="fast wobble flattened by the 0.35 value cap"),
        cue("fx_calm_lim_period_max", 2.0, "calm", params=dict(ca, period=600.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="near-static faint tint (unbounded stress)"),
    ]

    # color_wipe -------------------------------------------------------------
    wi = {"speed": 5.0, "color": [0.1, 0.7, 1.0], "edge_softness_px": 0.0,
          "progress_curve": "linear", "slew_seconds": 0.0}
    cues += [
        cue("fx_colorwipe_identity", 2.2, "color_wipe", params=dict(wi),
            metric_class=CLASS_SPATIAL,
            expected="cyan fills pixel-by-pixel 0->9 in 1.8s"),
        cue("fx_colorwipe_con_a", 2.2, "color_wipe", params=dict(wi, edge_softness_px=0.0),
            role="contrast_a", pair="fx_colorwipe_edge",
            metric_class=CLASS_SPATIAL, expected="crisp front"),
        cue("fx_colorwipe_con_b", 2.2, "color_wipe", params=dict(wi, edge_softness_px=3.0),
            role="contrast_b", pair="fx_colorwipe_edge",
            metric_class=CLASS_SPATIAL, expected="3px gradient front"),
        cue("fx_colorwipe_con_curve_a", 2.5, "color_wipe",
            params=dict(wi, speed=4.0, progress_curve="linear"),
            role="contrast_a", pair="fx_colorwipe_curve",
            metric_class=CLASS_SPATIAL, expected="linear progress"),
        cue("fx_colorwipe_con_curve_b", 2.5, "color_wipe",
            params=dict(wi, speed=4.0, progress_curve="smoothstep"),
            role="contrast_b", pair="fx_colorwipe_curve",
            metric_class=CLASS_SPATIAL, expected="ease-in/out progress"),
        cue("fx_colorwipe_lim_speed0", 1.5, "color_wipe", params=dict(wi, speed=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="1px lit, frozen (min boundary)"),
        cue("fx_colorwipe_lim_speed1000", 1.5, "color_wipe", params=dict(wi, speed=1000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="instantly full (max boundary)"),
        cue("fx_colorwipe_lim_soft_max", 2.5, "color_wipe",
            params=dict(wi, edge_softness_px=10000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="whole strip dimly lit from frame one (max boundary)"),
        cue("fx_colorwipe_lim_slew_high", 3.0, "color_wipe",
            params=dict(wi, speed=0.0, progress_source="cue_progress", slew_seconds=3.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="external progress drives the fill; authored speed is inert in "
                     "this mode and the 3s slew lags cue progress (unbounded stress)"),
    ]

    # twinkle ----------------------------------------------------------------
    tw = {"density": 0.4, "fade_time": 0.35, "color_source": "random",
          "event_width_px": 1.0, "blur_radius_px": 1.0, "color": [1.0, 0.9, 0.5]}
    cues += [
        cue("fx_twinkle_identity", 5.0, "twinkle", params=dict(tw),
            warmup=0.2, metric_class=CLASS_EVENT,
            expected="~4 sparks/s popping at random pixels, each fading ~1.5s"),
        cue("fx_twinkle_con_a", 6.0, "twinkle", params=dict(tw, density=0.05),
            role="contrast_a", pair="fx_twinkle_density",
            metric_class=CLASS_EVENT, expected="~2 lonely twinkles"),
        cue("fx_twinkle_con_b", 6.0, "twinkle", params=dict(tw, density=0.6),
            role="contrast_b", pair="fx_twinkle_density",
            metric_class=CLASS_EVENT, expected="~36 sparks, near-continuous sparkle"),
        cue("fx_twinkle_src_solid", 3.0, "twinkle",
            params=dict(tw, color_source="solid", color=[1.0, 0.2, 0.2]),
            metric_class=CLASS_EVENT, expected="solid-color sparks branch"),
        cue("fx_twinkle_src_palette", 3.0, "twinkle",
            params=dict(tw, color_source="palette"),
            color=None,
            palette=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.2, 1.0]],
            metric_class=CLASS_EVENT, expected="palette-color sparks branch"),
        cue("fx_twinkle_lim_density0", 2.0, "twinkle", params=dict(tw, density=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="no events, black (min boundary)"),
        cue("fx_twinkle_lim_density100", 2.0, "twinkle", params=dict(tw, density=100.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="1000 spawns/s, strip pinned bright (max boundary)"),
        cue("fx_twinkle_lim_fade_min", 2.0, "twinkle", params=dict(tw, fade_time=0.01),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="strobe sparks (min boundary)"),
        cue("fx_twinkle_lim_fade_max", 3.0, "twinkle", params=dict(tw, fade_time=60.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="sparks never clear, saturates (max boundary)"),
        cue("fx_twinkle_lim_width_min", 2.0, "twinkle", params=dict(tw, event_width_px=0.01),
            role="limit", metric_class=CLASS_EVENT,
            expected="single-pixel hard events (min boundary)"),
        cue("fx_twinkle_lim_blur0", 2.0, "twinkle",
            params=dict(tw, blur_radius_px=0.0, event_width_px=2.0),
            role="limit", metric_class=CLASS_EVENT,
            expected="hard unblurred 2px events (min boundary; width != 1 keeps the "
                     "seeded event path)"),
        cue("fx_twinkle_lim_width_max", 2.5, "twinkle", params=dict(tw, event_width_px=10000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="full-strip flash per event (max boundary)"),
        cue("fx_twinkle_lim_blur_max", 2.5, "twinkle", params=dict(tw, blur_radius_px=10000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="each birth softly lights the entire strip (max boundary)"),
        cue("fx_twinkle_gate_progress", 5.0, "twinkle",
            params=dict(tw, density=1.5, event_gate_source="cue_progress"),
            metric_class=CLASS_EVENT,
            expected="births gated by cue progress: sparse -> dense ramp"),
        cue("fx_twinkle_birth_progress", 5.0, "twinkle",
            params=dict(tw, density=1.0, birth_gain_source="cue_progress"),
            metric_class=CLASS_EVENT,
            expected="birth gain follows cue progress: dim -> bright events"),
    ]

    # demo -------------------------------------------------------------------
    dm = {"cycle_interval": 3.0, "effects": ["static", "breath", "color_wave", "chase"]}
    cues += [
        cue("fx_demo_identity", 12.5, "demo", params=dict(dm),
            metric_class=CLASS_SPATIAL,
            expected="3s tour: static/breath/color_wave/chase, each freshly reset"),
        cue("fx_demo_con_a", 6.5, "demo",
            params=dict(dm, effects=["static", "breath"]),
            role="contrast_a", pair="fx_demo_children",
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="two-child tour (spatially uniform children)"),
        cue("fx_demo_con_b", 12.5, "demo", params=dict(dm),
            role="contrast_b", pair="fx_demo_children",
            metric_class=CLASS_SPATIAL, expected="four-child tour"),
        cue("fx_demo_lim_interval_micro", 2.5, "demo",
            params=dict(dm, cycle_interval=0.05),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="children reset before rendering: strobing first-frames"),
        cue("fx_demo_lim_unknown_child", 2.5, "demo",
            params=dict(dm, effects=["not_a_registered_effect"]),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="unknown ids skipped -> static fallback"),
        cue("fx_demo_lim_interval_max", 2.5, "demo",
            params=dict(dm, cycle_interval=600.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="single child for the whole cue (unbounded stress)"),
    ]

    # step_pulse -------------------------------------------------------------
    sp = {"period": 1.0, "duty_cycle": 0.25, "low_color": [0.15, 0.15, 0.15],
          "high_color": [1.0, 0.2, 0.2]}
    cues += [
        cue("fx_steppulse_identity", 3.0, "step_pulse", params=dict(sp),
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="crisp 0.25s bright / 0.75s dim steps, never intermediate"),
        cue("fx_steppulse_con_a", 3.0, "step_pulse", params=dict(sp, duty_cycle=0.25),
            role="contrast_a", pair="fx_steppulse_duty",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="short flash / long dim"),
        cue("fx_steppulse_con_b", 3.0, "step_pulse", params=dict(sp, duty_cycle=0.75),
            role="contrast_b", pair="fx_steppulse_duty",
            metric_class=CLASS_UNIFORM_TEMPORAL, expected="long bright / short dim"),
        cue("fx_steppulse_lim_duty0", 1.5, "step_pulse", params=dict(sp, duty_cycle=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="permanently low (min boundary)"),
        cue("fx_steppulse_lim_duty1", 1.5, "step_pulse", params=dict(sp, duty_cycle=1.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="permanently high (max boundary)"),
        cue("fx_steppulse_lim_strobe", 2.0, "step_pulse", params=dict(sp, period=0.05),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="20Hz strobe"),
        cue("fx_steppulse_lim_period_max", 2.0, "step_pulse", params=dict(sp, period=600.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="single state for the whole cue (unbounded stress)"),
    ]

    # single_dot -------------------------------------------------------------
    sd = {"speed": 3.0, "direction": "forward", "color": [0.1, 1.0, 0.1]}
    cues += [
        cue("fx_single_dot_identity", 4.0, "single_dot", params=dict(sd),
            metric_class=CLASS_SPATIAL,
            expected="single green pixel stepping 0->9, 3.33s per revolution"),
        cue("fx_single_dot_con_a", 4.0, "single_dot", params=dict(sd),
            role="contrast_a", pair="fx_single_dot_dir",
            metric_class=CLASS_SPATIAL, expected="forward wrap 9->0"),
        cue("fx_single_dot_con_b", 7.0, "single_dot", params=dict(sd, direction="bounce"),
            role="contrast_b", pair="fx_single_dot_dir",
            metric_class=CLASS_SPATIAL, expected="bounce walks back from px9"),
        cue("fx_single_dot_dir_reverse", 3.0, "single_dot", params=dict(sd, direction="reverse"),
            metric_class=CLASS_SPATIAL, expected="reverse march branch"),
        cue("fx_single_dot_speed_a", 4.0, "single_dot", params=dict(sd),
            speed=0.5, role="contrast_a", pair="fx_single_dot_speed",
            metric_class=CLASS_SPATIAL,
            expected="common effect.speed 0.5: half march rate (6.7s/rev)"),
        cue("fx_single_dot_speed_b", 3.0, "single_dot", params=dict(sd),
            speed=2.0, role="contrast_b", pair="fx_single_dot_speed",
            metric_class=CLASS_SPATIAL,
            expected="common effect.speed 2.0: double march rate (1.67s/rev)"),
        cue("fx_single_dot_lim_speed0", 1.5, "single_dot", params=dict(sd, speed=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="frozen dot at px0"),
        cue("fx_single_dot_lim_speed50", 2.0, "single_dot", params=dict(sd, speed=50.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="500px/s exceeds frame rate: dot teleports"),
        cue("fx_single_dot_lim_speedslow", 2.5, "single_dot", params=dict(sd, speed=0.1),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="10s per single step: near-static"),
    ]

    # theater_phase ----------------------------------------------------------
    tp = {"speed": 3.0, "color": [1.0, 1.0, 1.0]}
    cues += [
        cue("fx_theater_phase_identity", 3.0, "theater_phase", params=dict(tp),
            metric_class=CLASS_SPATIAL,
            expected="three evenly spaced dots marching, 3-phase cycle each second"),
        cue("fx_theater_phase_con_a", 3.0, "theater_phase", params=dict(tp, speed=2.0),
            role="contrast_a", pair="fx_theater_phase_speed",
            metric_class=CLASS_SPATIAL, expected="legible 3-dot march"),
        cue("fx_theater_phase_con_b", 3.0, "theater_phase", params=dict(tp, speed=8.0),
            role="contrast_b", pair="fx_theater_phase_speed",
            metric_class=CLASS_SPATIAL, expected="masks interleave into flicker"),
        cue("fx_theater_phase_lim_speed0", 2.0, "theater_phase", params=dict(tp, speed=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="frozen 4/3/3 lit split (short-strip finding)"),
        cue("fx_theater_phase_lim_speed60", 1.5, "theater_phase", params=dict(tp, speed=60.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="strobe mush"),
    ]

    # flowing_bands ----------------------------------------------------------
    fb = {"band_width_px": 2, "gap_width_px": 2, "base_gain": 0.15,
          "highlight_gain": 1.0, "steps_per_second": 3.0, "direction": "forward",
          "phase_offset_steps": 0, "color": [1.0, 1.0, 1.0]}
    cues += [
        cue("fx_flow_bands_identity", 4.0, "flowing_bands", params=dict(fb),
            metric_class=CLASS_SPATIAL,
            expected="3 dim bands, one bright band hopping forward every 0.33s"),
        cue("fx_flow_bands_con_a", 4.0, "flowing_bands", params=dict(fb),
            role="contrast_a", pair="fx_flow_bands_dir",
            metric_class=CLASS_SPATIAL, expected="highlight hops left->right"),
        cue("fx_flow_bands_con_b", 4.0, "flowing_bands", params=dict(fb, direction="reverse"),
            role="contrast_b", pair="fx_flow_bands_dir",
            metric_class=CLASS_SPATIAL, expected="highlight hops right->left"),
        cue("fx_flow_bands_lim_band_max", 2.5, "flowing_bands",
            params=dict(fb, band_width_px=8, gap_width_px=8),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="band+gap >= 10: single band, no motion (short-strip finding)"),
        cue("fx_flow_bands_lim_band10000", 2.0, "flowing_bands",
            params=dict(fb, band_width_px=10000, gap_width_px=10000),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="all lit always (max boundaries)"),
        cue("fx_flow_bands_lim_base_eq_highlight", 2.0, "flowing_bands",
            params=dict(fb, base_gain=1.0, highlight_gain=1.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="uniform, highlight invisible (relational boundary)"),
        cue("fx_flow_bands_lim_base0", 2.5, "flowing_bands",
            params=dict(fb, band_width_px=1, gap_width_px=1, base_gain=0.0,
                        highlight_gain=1.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="background invisible: only the highlight band shows (min boundary)"),
        cue("fx_flow_bands_lim_steps_max", 1.5, "flowing_bands",
            params=dict(fb, steps_per_second=1000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="highlight aliasing/strobe (max boundary)"),
        cue("fx_flow_bands_lim_steps0", 2.0, "flowing_bands",
            params=dict(fb, steps_per_second=0.0, base_gain=0.0, highlight_gain=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="uniform dark bands: no highlight, no background (min boundaries)"),
        cue("fx_flow_bands_phase_offset", 2.5, "flowing_bands",
            params=dict(fb, phase_offset_steps=10000),
            metric_class=CLASS_SPATIAL,
            expected="phase offset 10000 mod band_count: shifted start (max boundary)"),
    ]

    # heat_fire --------------------------------------------------------------
    hf = {"cooling_per_second": 0.8, "spark_rate": 10.0, "spark_strength": 0.9,
          "diffusion": 0.5, "spark_zone_px": 10, "color": [1.0, 0.32, 0.04]}
    cues += [
        cue("fx_heat_fire_identity", 5.0, "heat_fire", params=dict(hf),
            warmup=1.0, metric_class=CLASS_SPATIAL,
            expected="flickering base with flame tips reaching px9 (~1s warm-up)"),
        cue("fx_heat_fire_con_a", 5.0, "heat_fire", params=dict(hf, diffusion=0.5),
            warmup=1.0, role="contrast_a", pair="fx_heat_fire_diffusion",
            metric_class=CLASS_SPATIAL, expected="flames climb the strip"),
        cue("fx_heat_fire_con_b", 5.0, "heat_fire", params=dict(hf, diffusion=0.0),
            warmup=1.0, role="contrast_b", pair="fx_heat_fire_diffusion",
            metric_class=CLASS_SPATIAL, expected="heat cannot propagate: base only"),
        cue("fx_heat_fire_lim_zone1", 3.0, "heat_fire", params=dict(hf, spark_zone_px=1),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="sparks at px0 only, 90% of strip never burns (min boundary)"),
        cue("fx_heat_fire_lim_rate0", 2.5, "heat_fire",
            params=dict(hf, spark_rate=0.0, cooling_per_second=0.0, spark_strength=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="black: no sparks/cooling/strength (min boundaries)"),
        cue("fx_heat_fire_lim_rate_max", 2.5, "heat_fire", params=dict(hf, spark_rate=60.0),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="uniform inferno (max boundary)"),
        cue("fx_heat_fire_lim_zone_max", 2.0, "heat_fire",
            params=dict(hf, spark_zone_px=10000),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="sparks anywhere: uniform flicker, no gradient (max boundary, "
                     "clamped to strip)"),
        cue("fx_heat_fire_lim_cooling_max", 2.5, "heat_fire",
            params=dict(hf, cooling_per_second=60.0),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="near-black with rare flashes (max boundary)"),
        cue("fx_heat_fire_lim_strength_max", 2.0, "heat_fire",
            params=dict(hf, spark_strength=1.0),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="clipped white-hot base (max boundary)"),
        cue("fx_heat_fire_lim_diffusion_max", 2.0, "heat_fire", params=dict(hf, diffusion=1.0),
            warmup=1.0, role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="heat smears instantly, whole strip flickers (max boundary)"),
    ]

    # history_stream ---------------------------------------------------------
    hs = {"steps_per_second": 2.0, "direction": "forward"}
    hs_timeline = {
        "interpolation": "rgb_linear",
        "keyframes": [
            {"time": 0.0, "color": [1.0, 0.1, 0.1]},
            {"time": 5.0, "color": [0.1, 0.2, 1.0]},
        ],
    }
    cues += [
        cue("fx_history_identity", 7.0, "history_stream", params=dict(hs),
            color_timeline=hs_timeline, warmup=5.2, metric_class=CLASS_SPATIAL,
            expected="color snake fills 0->9 in 5s, then scrolls red->blue history"),
        cue("fx_history_con_a", 8.0, "history_stream",
            params=dict(hs, steps_per_second=1.0), color_timeline=hs_timeline,
            role="contrast_a", pair="fx_history_sps", warmup=5.2,
            metric_class=CLASS_SPATIAL, expected="legible cell-by-cell shift"),
        cue("fx_history_con_b", 4.0, "history_stream",
            params=dict(hs, steps_per_second=5.0), color_timeline=hs_timeline,
            role="contrast_b", pair="fx_history_sps", warmup=2.2,
            metric_class=CLASS_SPATIAL, expected="fluid 2s fill"),
        cue("fx_history_dir_reverse", 8.0, "history_stream",
            params=dict(hs, steps_per_second=2.0, direction="reverse"),
            color_timeline=hs_timeline, warmup=5.2,
            metric_class=CLASS_SPATIAL, expected="history flows toward px0 branch"),
        cue("fx_history_lim_sps_min", 2.5, "history_stream",
            params=dict(hs, steps_per_second=0.001), color_timeline=hs_timeline,
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="one sample per 1000s: 1px lit (min boundary)"),
        cue("fx_history_lim_sps_max", 2.0, "history_stream",
            params=dict(hs, steps_per_second=1000.0), color_timeline=hs_timeline,
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="buffer overwritten within one frame: flat single color (max boundary)"),
    ]

    # coherent_noise_field ---------------------------------------------------
    cn = {"feature_size_px": 4.0, "drift_rate": 0.5, "contrast": 2.0,
          "floor_gain": 0.1, "ceiling_gain": 0.9, "color": [0.2, 0.8, 1.0]}
    cues += [
        cue("fx_noise_identity", 6.0, "coherent_noise_field", params=dict(cn),
            metric_class=CLASS_SPATIAL,
            expected="~2.5 soft blobs breathing and sliding, never fully dark"),
        cue("fx_noise_con_a", 5.0, "coherent_noise_field", params=dict(cn, drift_rate=0.0),
            role="contrast_a", pair="fx_noise_drift",
            metric_class=CLASS_SPATIAL, expected="frozen spatial pattern"),
        cue("fx_noise_con_b", 5.0, "coherent_noise_field", params=dict(cn, drift_rate=3.0),
            role="contrast_b", pair="fx_noise_drift",
            metric_class=CLASS_SPATIAL, expected="fast boiling shimmer"),
        cue("fx_noise_lim_feature_max", 2.5, "coherent_noise_field",
            params=dict(cn, feature_size_px=10000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="one gradient spans the strip: uniform slow glow (max boundary)"),
        cue("fx_noise_lim_feature_min", 2.0, "coherent_noise_field",
            params=dict(cn, feature_size_px=0.01),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="per-pixel static chaos (min boundary)"),
        cue("fx_noise_lim_contrast_max", 2.5, "coherent_noise_field",
            params=dict(cn, contrast=4.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="harsh black/white banding (max boundary)"),
        cue("fx_noise_lim_contrast0", 2.0, "coherent_noise_field",
            params=dict(cn, contrast=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="flat mid gain (min boundary)"),
        cue("fx_noise_lim_flat", 2.0, "coherent_noise_field",
            params=dict(cn, floor_gain=0.5, ceiling_gain=0.5),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="ceiling == floor: completely flat (relational boundary)"),
        cue("fx_noise_lim_drift_max", 2.0, "coherent_noise_field",
            params=dict(cn, drift_rate=1000.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="temporal aliasing: per-frame random field (max boundary)"),
        cue("fx_noise_lim_flat_white", 1.5, "coherent_noise_field",
            params=dict(cn, floor_gain=1.0, ceiling_gain=1.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="flat full-brightness field (max boundaries)"),
        cue("fx_noise_lim_ceiling0", 1.5, "coherent_noise_field",
            params=dict(cn, floor_gain=0.0, ceiling_gain=0.0),
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="flat black field (min boundaries)"),
    ]
    return cues


def _s2_color() -> list[CueSpec]:
    return [
        cue("col_timeline_sweep", 14.0, "static",
            color_timeline={
                "interpolation": "rgb_linear",
                "keyframes": [
                    {"time": 0.0, "color": [1.0, 0.0, 0.0]},
                    {"time": 2.0, "color": [1.0, 1.0, 0.0]},
                    {"time": 4.0, "color": [0.0, 1.0, 0.0]},
                    {"time": 6.0, "color": [0.0, 1.0, 1.0]},
                    {"time": 8.0, "color": [0.0, 0.0, 1.0]},
                    {"time": 10.0, "color": [1.0, 0.0, 1.0]},
                    {"time": 12.0, "color": [1.0, 1.0, 1.0]},
                    {"time": 14.0, "color": [0.2, 0.2, 0.2]},
                ],
            },
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="R->Y->G->C->B->M->W->dim: primaries, secondaries, white"),
        cue("col_palette_cycle", 9.5, "breath",
            params={"period": 4.0, "min_brightness": 0.1, "waveform": "sine"},
            palette=[
                [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 1.0],
                [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.15, 0.15, 0.15],
            ],
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="8-color 1Hz hard-stepped palette over a breathing envelope"),
        cue("col_spatial_gradient", 5.5, "color_wipe",
            params={"speed": 2.0, "color": [1.0, 1.0, 1.0], "edge_softness_px": 0.0},
            color_source={"type": "spatial_palette",
                          "palette": [[1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 0.0, 1.0]]},
            metric_class=CLASS_SPATIAL,
            expected="10px R->Y->B gradient revealed by the wipe front"),
        cue("col_event_spatial", 5.0, "twinkle",
            params={"density": 0.8, "fade_time": 0.3, "event_width_px": 1.0,
                    "blur_radius_px": 1.0, "color": [1.0, 1.0, 1.0]},
            color_source={"type": "spatial_palette",
                          "palette": [[1.0, 0.1, 0.1], [0.1, 1.0, 0.1], [0.2, 0.3, 1.0],
                                      [1.0, 1.0, 0.1], [1.0, 0.2, 1.0], [0.1, 1.0, 1.0]]},
            metric_class=CLASS_EVENT,
            expected="multi-colored twinkles: per-event palette sampling"),
        cue("col_event_timeline", 8.0, "onset_ripple",
            params={"onset_threshold": 0.35, "wave_speed_pps": 18.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.5, "floor_gain": 0.3, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True},
            color_source={"type": "timeline",
                          "interpolation": "rgb_linear",
                          "keyframes": [
                              {"time": 0.0, "color": [1.0, 0.4, 0.1]},
                              {"time": 4.0, "color": [0.2, 0.9, 0.3]},
                              {"time": 8.0, "color": [0.3, 0.4, 1.0]},
                          ]},
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="amber->green->blue floor; P2 adds ripples in the live color"),
        cue("col_dominant_freq_fallback", 4.0, "static",
            color_source={"type": "dominant_frequency_palette",
                          "frequency_min_hz": 100.0, "frequency_max_hz": 4000.0,
                          "palette": [[1.0, 0.1, 0.1], [1.0, 1.0, 0.1],
                                      [0.2, 1.0, 0.3], [0.3, 0.4, 1.0]],
                          "fallback": [0.3, 0.3, 0.3]},
            metric_class=CLASS_UNIFORM_STATIC,
            expected="P1: steady fallback gray; P2: hue follows tone pitch"),
        cue("col_audio_spectrum_fallback", 4.0, "chase",
            params={"speed": 3.0, "width": 1, "gap": 4, "direction": "forward",
                    "trail": 0.4, "color_source": "static", "beat_boost": 0.0},
            color=[0.6, 0.6, 0.6],
            color_source={"type": "audio_spectrum_palette",
                          "palette": [[0.1, 0.1, 0.4], [0.1, 0.6, 0.8],
                                      [1.0, 0.9, 0.2], [1.0, 0.2, 0.1]],
                          "fallback": [0.2, 0.2, 0.25]},
            metric_class=CLASS_SPATIAL,
            expected="P1: moving window in fallback color; P2: spectrum-shaped gradient"),
        cue("col_video_fallback", 3.0, "static",
            color_source={"type": "video_average", "fallback": [0.25, 0.25, 0.3]},
            metric_class=CLASS_UNIFORM_STATIC,
            expected="P1: steady fallback; Part 3 drives the live color"),
    ]


def _s3_modulation() -> list[CueSpec]:
    cues = [
        cue("mod_track_linear", 8.0, "breath",
            params={"period": 3.0, "min_brightness": 0.05, "waveform": "sine",
                    "color": [0.9, 0.5, 0.1]},
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="brightness track 1.0->0.25->1.0 linear over the breath"),
        cue("mod_track_step", 6.0, "static", params={"color": [1.0, 0.6, 0.1]},
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="stepped brightness 1.0/0.3/0.7/1.0"),
        cue("mod_param_breath_min_drive", 8.0, "breath",
            params={"period": 2.0, "min_brightness": 0.05, "color": [0.55, 0.2, 1.0]},
            parameter_modulation=[{
                "target": "min_brightness", "mode": "drive", "source": "cue_progress",
                "output_min": 0.0, "output_max": 0.8, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="dim floor rises from black to 0.8 as the cue progresses"),
        cue("mod_param_colorwave_span_mod", 8.0, "color_wave",
            params={"speed": 0.5, "width": 1.0, "waveform": "sine",
                    "hue_span_degrees": 360.0, "hue_cycle_rate": 0.0},
            parameter_modulation=[{
                "target": "hue_span_degrees", "mode": "modulate", "source": "cue_progress",
                "output_min": 0.1, "output_max": 1.0, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_SPATIAL,
            expected="rainbow collapses toward uniform color and re-opens"),
        cue("mod_param_wipe_softness_drive", 5.0, "color_wipe",
            params={"speed": 4.0, "color": [0.1, 0.7, 1.0], "edge_softness_px": 0.0},
            parameter_modulation=[{
                "target": "edge_softness_px", "mode": "drive", "source": "cue_progress",
                "output_min": 0.0, "output_max": 6.0, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_SPATIAL,
            expected="wipe front sharpens into a 6px soft gradient"),
        cue("mod_param_bands_base_mod", 6.0, "flowing_bands",
            params={"band_width_px": 2, "gap_width_px": 2, "base_gain": 0.15,
                    "highlight_gain": 1.0, "steps_per_second": 3.0,
                    "direction": "forward", "phase_offset_steps": 0,
                    "color": [1.0, 1.0, 1.0]},
            parameter_modulation=[{
                "target": "base_gain", "mode": "modulate", "source": "cue_progress",
                "output_min": 0.2, "output_max": 3.0, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_SPATIAL,
            expected="background bands swell from 0.03 to clipped 0.45"),
        cue("mod_param_bands_highlight_mod", 6.0, "flowing_bands",
            params={"band_width_px": 2, "gap_width_px": 2, "base_gain": 0.15,
                    "highlight_gain": 1.0, "steps_per_second": 3.0,
                    "direction": "forward", "phase_offset_steps": 0,
                    "color": [1.0, 1.0, 1.0]},
            parameter_modulation=[{
                "target": "highlight_gain", "mode": "modulate", "source": "cue_progress",
                "output_min": 0.5, "output_max": 1.0, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_SPATIAL,
            expected="highlight dimmer than background at first, overtakes it"),
        cue("mod_param_noise_contrast_drive", 8.0, "coherent_noise_field",
            params={"feature_size_px": 4.0, "drift_rate": 0.5, "contrast": 2.0,
                    "floor_gain": 0.1, "ceiling_gain": 0.9, "color": [0.2, 0.8, 1.0]},
            parameter_modulation=[{
                "target": "contrast", "mode": "drive", "source": "cue_progress",
                "output_min": 0.2, "output_max": 3.5, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_SPATIAL,
            expected="soft blobs harden into harsh bands"),
        cue("mod_param_onset_floor_drive", 8.0, "onset_ripple",
            params={"onset_threshold": 0.35, "wave_speed_pps": 18.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.5, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [0.4, 0.9, 0.4]},
            parameter_modulation=[{
                "target": "floor_gain", "mode": "drive", "source": "cue_progress",
                "output_min": 0.0, "output_max": 0.5, "smoothing_seconds": 0.05,
            }],
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="ripple floor rises from black to visible green without media"),
        cue("mod_param_audio_rms", 6.0, "flowing_bands",
            params={"band_width_px": 2, "gap_width_px": 2, "base_gain": 0.15,
                    "highlight_gain": 1.0, "steps_per_second": 3.0,
                    "direction": "forward", "phase_offset_steps": 0,
                    "color": [1.0, 1.0, 1.0]},
            parameter_modulation=[{
                "target": "base_gain", "mode": "modulate", "source": "audio.rms",
                "output_min": 1.0, "output_max": 3.0, "smoothing_seconds": 0.1,
            }],
            metric_class=CLASS_SPATIAL,
            expected="P1: authored base (zero signal maps to x1.0); "
                     "P2: background swells up to x3 with loudness"),
        cue("mod_adaptive_states", 32.0, "static",
            adaptive={
                "silence": "static", "calm": "breath", "flowing": "chase",
                "energetic": "color_wave",
            },
            fallback="static",
            audio_control={
                "tempo_sync": "auto", "tempo_confidence_min": 0.3,
                "beat_regularity_min": 0.3, "state_confirmation_seconds": 1.0,
                "min_effect_hold": 2.0, "switch_cooldown": 1.0,
            },
            metric_class=CLASS_UNIFORM_STATIC,
            expected="P1: silence->static (fallback path); P2: states switch with music"),
        cue("mod_audio_brightness", 8.0, "breath",
            params={"period": 2.0, "min_brightness": 0.1, "color": [0.9, 0.5, 0.1]},
            audio_modulation={
                "enabled": True,
                "brightness": {"source": "music.energy", "amount": 0.8,
                               "min_multiplier": 1.0, "max_multiplier": 1.8,
                               "smoothing_seconds": 0.2},
            },
            metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="P1: neutral (multiplier floor 1.0 at zero signal); "
                     "P2: breath brightens with music energy"),
        cue("mod_audio_speed", 8.0, "chase",
            params={"speed": 5.0, "width": 1, "gap": 4, "direction": "forward",
                    "trail": 0.4, "color_source": "static", "beat_boost": 0.0},
            color=[1.0, 0.55, 0.15],
            audio_modulation={
                "enabled": True,
                "speed": {"source": "music.beat_strength", "amount": 0.9,
                          "min_multiplier": 1.0, "max_multiplier": 3.0,
                          "smoothing_seconds": 0.15},
            },
            metric_class=CLASS_SPATIAL,
            expected="P1: normal march (floor 1.0); P2: march accelerates on beats"),
        cue("mod_audio_intensity", 6.0, "twinkle",
            params={"density": 0.5, "fade_time": 0.3, "event_width_px": 1.0,
                    "blur_radius_px": 1.0, "color": [1.0, 0.9, 0.5]},
            audio_modulation={
                "enabled": True,
                "intensity": {"source": "audio.rms", "amount": 0.9,
                              "min_multiplier": 1.0, "max_multiplier": 2.5,
                              "smoothing_seconds": 0.15},
            },
            metric_class=CLASS_EVENT,
            expected="P1: normal sparks (floor 1.0); P2: spark brightness follows loudness"),
    ]
    return cues


def _s_audio() -> list[CueSpec]:
    return [
        cue("aud_audiopulse_identity", 10.0, "audio_pulse",
            params={"attack": 0.05, "release": 0.5, "color": [1.0, 0.5, 0.1]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: punchy swells following RMS"),
        cue("aud_audiopulse_con_a", 8.0, "audio_pulse",
            params={"attack": 0.05, "release": 0.5, "color": [1.0, 0.5, 0.1]},
            role="contrast_a", pair="aud_audiopulse_attack",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="tight kicks"),
        cue("aud_audiopulse_con_b", 8.0, "audio_pulse",
            params={"attack": 2.0, "release": 0.5, "color": [1.0, 0.5, 0.1]},
            role="contrast_b", pair="aud_audiopulse_attack",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="sluggish glow"),
        cue("aud_audiopulse_lim_release60", 4.0, "audio_pulse",
            params={"attack": 0.05, "release": 60.0, "color": [1.0, 0.5, 0.1]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="brightness freezes after the first hit (unbounded stress)"),
        cue("aud_basspulse_identity", 10.0, "bass_pulse",
            params={"attack": 0.08, "release": 0.4, "color": [0.2, 0.6, 1.0]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: cyan thumps locked to low-frequency energy"),
        cue("aud_basspulse_con_a", 8.0, "bass_pulse",
            params={"attack": 0.08, "release": 0.4, "color": [0.2, 0.6, 1.0]},
            role="contrast_a", pair="aud_basspulse_attack",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="per-kick thump"),
        cue("aud_basspulse_con_b", 8.0, "bass_pulse",
            params={"attack": 1.5, "release": 0.4, "color": [0.2, 0.6, 1.0]},
            role="contrast_b", pair="aud_basspulse_attack",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="smeared constant glow"),
        cue("aud_basspulse_lim_attack60", 3.0, "bass_pulse",
            params={"attack": 60.0, "release": 0.4, "color": [0.2, 0.6, 1.0]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="barely reaches visible brightness (unbounded stress)"),
        cue("aud_spectrum_bass", 10.0, "spectrum",
            params={"bass_zones": [TARGET_ID], "mid_zones": [], "treble_zones": []},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: whole strip red, pulsing with bass only"),
        cue("aud_spectrum_mid", 10.0, "spectrum",
            params={"bass_zones": [], "mid_zones": [TARGET_ID], "treble_zones": []},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: whole strip green with mid energy"),
        cue("aud_spectrum_treble", 10.0, "spectrum",
            params={"bass_zones": [], "mid_zones": [], "treble_zones": [TARGET_ID]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: whole strip blue with treble energy"),
        cue("aud_onset_ripple_identity", 12.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: black; P2: amber wave from px0 on each beat, 1s crossing"),
        cue("aud_onset_ripple_con_a", 8.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="contrast_a", pair="aud_onset_prop",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="single front leaves px0"),
        cue("aud_onset_ripple_con_b", 8.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "bidirectional", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="contrast_b", pair="aud_onset_prop",
            metric_class=CLASS_BLACK_UNTIL_MEDIA, expected="two mirrored fronts"),
        cue("aud_onset_ripple_origin_random", 6.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "random",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="random-origin branch: waves born at hashed pixels"),
        cue("aud_onset_ripple_nowrap", 6.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": False, "color": [1.0, 0.6, 0.15]},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="wrap=false branch: fronts die at strip ends"),
        cue("aud_onset_ripple_lim_threshold1", 4.0, "onset_ripple",
            params={"onset_threshold": 1.0, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="almost no triggers (max boundary)"),
        cue("aud_onset_ripple_lim_threshold0", 3.0, "onset_ripple",
            params={"onset_threshold": 0.0, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="every onset triggers: continuous wave spam (min boundary)"),
        cue("aud_onset_ripple_lim_speed0", 3.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 0.0, "wave_width_px": 0.1,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="frozen hairline front at the origin (min boundaries)"),
        cue("aud_onset_ripple_lim_speed1000", 2.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 1000.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="front crosses faster than a frame: whole-strip flash (max boundary)"),
        cue("aud_onset_ripple_lim_width1000", 2.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 1000.0,
                    "decay_seconds": 1.2, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="every onset lights the entire strip (max boundary)"),
        cue("aud_onset_ripple_lim_decay_min", 3.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 0.01, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="waves vanish almost instantly (min boundary)"),
        cue("aud_onset_ripple_lim_decay_max", 3.0, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 60.0, "floor_gain": 0.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="waves linger far beyond the cue (max boundary)"),
        cue("aud_onset_ripple_lim_floor1", 2.5, "onset_ripple",
            params={"onset_threshold": 0.1, "wave_speed_pps": 10.0, "wave_width_px": 2.0,
                    "decay_seconds": 1.2, "floor_gain": 1.0, "event_origin": "fixed",
                    "propagation": "one_way", "wrap": True, "color": [1.0, 0.6, 0.15]},
            role="limit", metric_class=CLASS_EXPECTED_DEGRADED,
            expected="constant full-brightness floor, waves invisible (max boundary)"),
        cue("aud_historystream_rms", 6.0, "history_stream",
            params={"steps_per_second": 2.0, "direction": "forward",
                    "sample_gain_source": "audio.rms"},
            color_timeline={
                "interpolation": "rgb_linear",
                "keyframes": [
                    {"time": 0.0, "color": [1.0, 0.1, 0.1]},
                    {"time": 6.0, "color": [0.1, 0.2, 1.0]},
                ],
            },
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: gain 0 -> black samples; P2: history brightens with loudness"),
        cue("aud_twinkle_gate_bass", 6.0, "twinkle",
            params={"density": 1.0, "fade_time": 0.3, "event_width_px": 1.0,
                    "blur_radius_px": 1.0, "color": [1.0, 0.9, 0.5],
                    "event_gate_source": "audio.bass"},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: gated to black; P2: sparks only on bass content"),
        cue("aud_twinkle_birth_treble", 6.0, "twinkle",
            params={"density": 1.0, "fade_time": 0.3, "event_width_px": 1.0,
                    "blur_radius_px": 1.0, "color": [1.0, 0.9, 0.5],
                    "birth_gain_source": "audio.treble"},
            metric_class=CLASS_BLACK_UNTIL_MEDIA,
            expected="P1: zero birth gain -> black; P2: treble lights the sparks"),
    ]


def _s4_stress() -> list[CueSpec]:
    rapid_effects = [
        ("single_dot", {"speed": 30.0, "direction": "forward", "color": [0.1, 1.0, 0.1]},
         None, None, CLASS_SPATIAL),
        ("theater_phase", {"speed": 10.0, "color": [1.0, 1.0, 1.0]}, None, None, CLASS_SPATIAL),
        ("chase", {"speed": 20.0, "width": 1, "gap": 4, "direction": "forward",
                   "trail": 0.4, "color_source": "static", "beat_boost": 0.0},
         [1.0, 0.55, 0.15], None, CLASS_SPATIAL),
        ("step_pulse", {"period": 0.2, "duty_cycle": 0.5,
                        "low_color": [0.15, 0.15, 0.15], "high_color": [1.0, 0.2, 0.2]},
         None, None, CLASS_RAPID_SWITCH),
        ("color_wipe", {"speed": 30.0, "color": [0.1, 0.7, 1.0], "edge_softness_px": 0.0},
         None, None, CLASS_RAPID_SWITCH),
        ("comet", {"speed": 20.0, "tail_length": 0.4, "decay": 0.85, "count": 2,
                   "phase_spacing": 0.5, "trajectory": "wrap"},
         [1.0, 1.0, 0.85], None, CLASS_RAPID_SWITCH),
        ("twinkle", {"density": 2.0, "fade_time": 0.1, "event_width_px": 1.0,
                     "blur_radius_px": 1.0, "color": [1.0, 0.9, 0.5]},
         None, None, CLASS_EVENT),
        ("static", {"color": [1.0, 0.3, 0.3]}, None, None, CLASS_RAPID_SWITCH),
    ]
    cues = [
        cue(f"str_rapid_{index:02d}", 0.4, effect_id, params=params, color=color,
            palette=palette, metric_class=metric_class, role="stress",
            expected=f"rapid switch #{index}: fresh effect instance each 0.4s")
        for index, (effect_id, params, color, palette, metric_class) in enumerate(rapid_effects)
    ]
    cues += [
        cue("str_priority_base", 4.0, "static", params={"color": [0.1, 0.1, 0.35]},
            priority=PRIORITY_BASE, role="stress", metric_class=CLASS_UNIFORM_STATIC,
            expected="dim blue base"),
        cue("str_priority_flash", 2.0, "single_dot",
            params={"speed": 2.0, "direction": "forward", "color": [1.0, 0.9, 0.2]},
            priority=PRIORITY_OVERLAY, role="stress", metric_class=CLASS_SPATIAL,
            expected="priority-20 overlay replaces the base strip contribution: "
                     "dot on black, base hidden"),
        cue("str_blend_base", 4.0, "static", params={"color": [0.3, 0.1, 0.1]},
            blend="add", priority=PRIORITY_BASE, role="stress",
            metric_class=CLASS_UNIFORM_STATIC, expected="red base (add)"),
        cue("str_blend_overlay", 2.0, "static", params={"color": [0.2, 0.3, 0.2]},
            blend="add", priority=PRIORITY_OVERLAY, role="stress",
            metric_class=CLASS_UNIFORM_STATIC,
            expected="overlap sums toward white clipping, hue partially destroyed"),
        cue("str_fade_envelope", 5.0, "breath",
            params={"period": 2.0, "min_brightness": 0.1, "color": [0.55, 0.2, 1.0]},
            fade_in=1.5, fade_out=1.5, role="stress", metric_class=CLASS_UNIFORM_TEMPORAL,
            expected="breath rises/falls inside 1.5s fades"),
        cue("str_min_cue", 0.2, "static", params={"color": [0.5, 0.5, 0.5]},
            role="stress", metric_class=CLASS_UNIFORM_STATIC,
            expected="minimum practical cue length"),
    ]
    return cues


def _s5_safe() -> list[CueSpec]:
    return [
        cue("safe_fade_to_black", 5.0, "static", params={"color": [0.35, 0.35, 0.35]},
            fade_out=3.0, metric_class=CLASS_UNIFORM_TEMPORAL, role="safe",
            expected="fades to black over the last 3s"),
        cue("safe_black_hold", 4.0, "static", params={"color": [0.0, 0.0, 0.0]},
            metric_class=CLASS_UNIFORM_BLACK, role="safe",
            expected="final all-black safe state hold"),
    ]


def _video_cues() -> list[CueSpec]:
    return [
        cue("vid_average_steps", 24.0, "static",
            color_source={"type": "video_average", "fallback": [0.2, 0.2, 0.25]},
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="strip follows clip R(0-8)->G(8-16)->B(16-24) with ~1s lag"),
        cue("vid_dominant_bar", 6.0, "static",
            color_source={"type": "video_dominant", "fallback": [0.2, 0.2, 0.2]},
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="dominant stays red while a white bar sweeps (vs average)"),
        cue("vid_chase_video", 8.0, "chase",
            params={"speed": 5.0, "width": 1, "gap": 4, "direction": "forward",
                    "trail": 0.4, "color_source": "video", "beat_boost": 0.0},
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="dim video-tinted chase window over the near-black scene"),
        cue("vid_ambient_smoothfast", 6.0, "video_ambient",
            params={"smoothing": 0.9}, part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="fast cuts land almost immediately"),
        cue("vid_ambient_smoothslow", 6.0, "video_ambient",
            params={"smoothing": 0.02}, part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="same cuts glide in over ~2s (A/B lag contrast)"),
        cue("vid_fusion_videoonly", 3.0, "video_audio_fusion",
            params={"video_weight": 0.65, "audio_weight": 0.0, "bass_boost": 0.0,
                    "treble_limit": 0.0},
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="video-only leg over the white segment: bright steady strip"),
        cue("vid_fusion_audioheavy", 3.0, "video_audio_fusion",
            params={"video_weight": 0.65, "audio_weight": 0.35, "bass_boost": 10.0,
                    "treble_limit": 1.0},
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="same white video + wav beats: brightness pumps (A/B audio_weight); "
                     "treble_limit 1.0 (max boundary) enables shimmer whose per-pixel "
                     "jitter is expected to vary run-to-run"),
        cue("vid_fusion_weights_mod", 4.0, "video_audio_fusion",
            params={"video_weight": 1.0, "audio_weight": 1.0, "bass_boost": 1.5,
                    "treble_limit": 0.5},
            parameter_modulation=[
                {"target": "video_weight", "mode": "modulate", "source": "cue_progress",
                 "output_min": 0.1, "output_max": 1.0, "smoothing_seconds": 0.05},
                {"target": "treble_limit", "mode": "modulate", "source": "cue_progress",
                 "output_min": 0.2, "output_max": 1.0, "smoothing_seconds": 0.05},
            ],
            part="video", metric_class=CLASS_VIDEO_INPUT,
            expected="video weight ramps 1.0 -> 0.1 over the white segment (modulate)"),
    ]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _cue_to_yaml(spec: CueSpec, pixel_count: int) -> dict[str, Any]:
    del pixel_count  # targeting never embeds physical sizes; kept for symmetry
    item: dict[str, Any] = {
        "id": spec.id,
        "start": round(spec.start, 3),
        "end": round(spec.start + spec.duration, 3),
        "priority": spec.priority,
        "target": {"type": "digital_strip", "id": TARGET_ID},
    }
    if spec.origin is not None:
        item["origin"] = spec.origin
    effect: dict[str, Any] = {"mode": "fixed" if spec.adaptive is None else "adaptive"}
    if spec.adaptive is not None:
        effect["allowed"] = dict(spec.adaptive)
        effect["fallback"] = spec.fallback
    else:
        effect["id"] = spec.effect_id
        if spec.speed is not None:
            effect["speed"] = spec.speed
        if spec.intensity is not None:
            effect["intensity"] = spec.intensity
        params = dict(spec.params)
        if spec.color_timeline is not None:
            params["color_timeline"] = spec.color_timeline
        if params:
            effect["params"] = params
    item["effect"] = effect
    if spec.color is not None:
        item["color"] = {"mode": "solid", "color": list(spec.color)}
    elif spec.palette is not None:
        item["color"] = {"mode": "palette", "colors": [list(c) for c in spec.palette]}
    if spec.color_source is not None:
        item["color_source"] = spec.color_source
    if spec.audio_modulation is not None:
        item["audio_modulation"] = spec.audio_modulation
    if spec.parameter_modulation is not None:
        item["parameter_modulation"] = spec.parameter_modulation
    if spec.audio_control is not None:
        item["audio_control"] = spec.audio_control
    transition: dict[str, Any] = {}
    if spec.fade_in:
        transition["fade_in"] = spec.fade_in
    if spec.fade_out:
        transition["fade_out"] = spec.fade_out
    if spec.blend:
        transition["blend"] = spec.blend
    if transition:
        item["transition"] = transition
    return item


def _brightness_tracks(placed: list[CueSpec]) -> list[dict[str, Any]]:
    by_id = {spec.id: spec for spec in placed}

    def window(cue_id: str) -> tuple[float, float]:
        spec = by_id[cue_id]
        return spec.start, spec.start + spec.duration

    tracks = []
    for track_id, cue_id, values, interpolation in (
        ("bt_calm_amplitude", "fx_calm_identity", (1.0, 0.25, 1.0), "linear"),
        ("bt_calm_amplitude_a", "fx_calm_con_a", (1.0, 0.3, 1.0), "linear"),
        ("bt_calm_amplitude_b", "fx_calm_con_b", (1.0, 0.3, 1.0), "linear"),
        ("bt_mod_linear", "mod_track_linear", (1.0, 0.25, 1.0), "linear"),
        ("bt_mod_step", "mod_track_step", (1.0, 0.3, 0.7, 1.0), "step"),
    ):
        start, end = window(cue_id)
        span = end - start
        count = len(values)
        keyframes = [
            {"time": round(start + index * span / (count - 1), 3), "value": value}
            for index, value in enumerate(values)
        ]
        tracks.append({
            "id": track_id,
            "target": {"type": "digital_strip", "id": TARGET_ID},
            "start": round(start, 3),
            "end": round(end, 3),
            "interpolation": interpolation,
            "keyframes": keyframes,
        })
    return tracks


def build_main_show(pixel_count: int) -> tuple[dict[str, Any], list[CueSpec]]:
    segments: list[CueSpec] = []
    segments += _s0_safety(pixel_count)
    segments += _s1_effects(pixel_count)
    segments += _s2_color()
    segments += _s3_modulation()
    segments += _s_audio()
    segments += _s4_stress()
    segments += _s5_safe()

    _timeline(segments, 0.0)
    _overlay("str_priority_base", [s for s in segments if s.id.startswith("str_priority")])
    _overlay("str_blend_base", [s for s in segments if s.id.startswith("str_blend")])
    cursor = max(spec.start + spec.duration for spec in segments)
    sequential = segments
    ids = [spec.id for spec in sequential]
    if len(ids) != len(set(ids)):
        raise GenerationError("duplicate cue ids")

    show = {
        "schema_version": 2,
        "show": {
            "id": SHOW_ID_MAIN,
            "duration": round(cursor, 3),
            "defaults": {
                "fade_in": 0.0, "fade_out": 0.0, "blend": "replace",
                "min_effect_hold": 0.0, "switch_cooldown": 0.0,
            },
            "brightness_tracks": _brightness_tracks(sequential),
            "cues": [_cue_to_yaml(spec, pixel_count) for spec in sequential],
        },
    }
    return show, sequential


def build_video_show(pixel_count: int) -> tuple[dict[str, Any], list[CueSpec]]:
    specs = _video_cues()
    cursor = _timeline(specs, 0.0)
    show = {
        "schema_version": 2,
        "show": {
            "id": SHOW_ID_VIDEO,
            "duration": round(cursor, 3),
            "defaults": {
                "fade_in": 0.0, "fade_out": 0.0, "blend": "replace",
                "min_effect_hold": 0.0, "switch_cooldown": 0.0,
            },
            "cues": [_cue_to_yaml(spec, pixel_count) for spec in specs],
        },
    }
    return show, specs


# ---------------------------------------------------------------------------
# Coverage manifest
# ---------------------------------------------------------------------------


def _uint8_table() -> dict[str, Any]:
    smoothing = _profile_smoothing()
    gamma = float(smoothing["gamma"])
    max_brightness = float(smoothing["max_brightness"])

    def to_uint8(level: float) -> int:
        return round((level * max_brightness) ** gamma * 255)

    levels = [0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.5, 0.75, 1.0]
    return {
        "profile": str(PROFILE_PATH),
        "gamma": gamma,
        "max_brightness": max_brightness,
        "note": "authored visible levels must map to >= ~10/255; levels below 0.15 "
                "collapse toward black under this transform",
        "table": {f"{level:.2f}": to_uint8(level) for level in levels},
    }


_PROFILE_SMOOTHING: dict[str, Any] | None = None


def _profile_smoothing() -> dict[str, Any]:
    global _PROFILE_SMOOTHING
    if _PROFILE_SMOOTHING is None:
        from light_engine.config import Config

        Config.reset()
        config = Config.get_instance(_ROOT / PROFILE_PATH)
        _PROFILE_SMOOTHING = {
            "gamma": config.get("system.smoothing.gamma", 2.2),
            "max_brightness": config.get("system.smoothing.max_brightness", 0.85),
        }
    return _PROFILE_SMOOTHING


def _coverage_manifest(
    main_specs: list[CueSpec],
    video_specs: list[CueSpec],
    pixel_count: int,
) -> dict[str, Any]:
    by_id = {spec.id: spec for spec in main_specs + video_specs}
    metrics = {
        spec.id: {
            "role": spec.role,
            "pair": spec.pair,
            "metric_class": spec.metric_class,
            "expected": spec.expected,
            "duration_seconds": spec.duration,
            "start": round(spec.start, 3),
            "warmup_seconds": spec.warmup,
            "part": spec.part,
        }
        for spec in main_specs + video_specs
    }

    def cues(prefix: str) -> list[str]:
        return sorted(spec.id for spec in main_specs + video_specs
                      if spec.id.startswith(prefix))

    effect_cues: dict[str, list[str]] = {}
    for spec in main_specs + video_specs:
        effect_id = spec.effect_id
        if spec.adaptive is not None:
            for mapped in spec.adaptive.values():
                effect_cues.setdefault(mapped, []).append(spec.id)
            effect_cues.setdefault(spec.fallback or "", []).append(spec.id)
        else:
            effect_cues.setdefault(effect_id, []).append(spec.id)
    effect_cues = {k: sorted(set(v)) for k, v in effect_cues.items() if k}

    audio_dependent = {"audio_pulse", "bass_pulse", "spectrum", "onset_ripple"}
    video_dependent = {"video_ambient"}
    capabilities: list[dict[str, Any]] = []
    for effect_id in list_effects():
        if effect_id in video_dependent:
            status = "FULL"
            notes = "evidence requires Part 3 local video"
        elif effect_id == "spectrum":
            status = "PARTIAL"
            notes = ("three independent single-band cues (bass/mid/treble); simultaneous "
                     "multi-zone banding is NOT_COVERABLE_SINGLE_STRIP")
        elif effect_id == "video_audio_fusion":
            status = "FULL"
            notes = ("evidence requires Part 3 local video; treble shimmer (treble_limit > 0) "
                     "consumes global RNG at render time, so Part 3 frames are excluded "
                     "from digest pinning and shimmer amplitude is expected to vary run-to-run")
        elif effect_id in audio_dependent:
            status = "FULL"
            notes = "fallback/silence stability in Part 1; dynamic evidence in Part 2"
        else:
            status = "FULL"
            notes = ""
        capabilities.append({
            "id": f"effect.{effect_id}",
            "kind": "effect",
            "status": status,
            "cue_ids": effect_cues.get(effect_id, []),
            "color_source_support": get_effect_registration(effect_id).color_source_support,
            "notes": notes,
        })
    capabilities += [
        {"id": "show.effect.speed_intensity", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("fx_static_con") + cues("fx_single_dot_speed")))},
        {"id": "show.origin", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("cal_origin_")},
        {"id": "show.color_spec_solid", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("cal_") + cues("fx_chase_identity")))},
        {"id": "show.color_spec_palette", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("col_palette") + cues("fx_twinkle_src")},
        {"id": "show.transition_fades", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("str_fade") + cues("safe_")},
        {"id": "show.blend_add", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("str_blend")},
        {"id": "show.priority", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("str_priority")},
        {"id": "show.brightness_tracks", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("mod_track")},
        {"id": "show.adaptive_mode", "kind": "show_language", "status": "PARTIAL",
         "cue_ids": cues("mod_adaptive"),
         "notes": "Part 1 exercises only the silence/fallback path; state switching needs Part 2"},
        {"id": "show.audio_control", "kind": "show_language", "status": "PARTIAL",
         "cue_ids": cues("mod_adaptive"),
         "notes": "gates only the adaptive selector; inert on fixed cues; the "
                  "beat-locked fields (beats_per_cycle, beat_subdivision, "
                  "speed_smoothing_seconds) are declared but need live tempo evidence "
                  "in Part 2"},
        {"id": "show.min_effect_hold_switch_cooldown", "kind": "show_language",
         "status": "PARTIAL", "cue_ids": cues("mod_adaptive"),
         "notes": "adaptive-only gates; fixed-cue rows would be a false pass"},
        {"id": "show.audio_modulation", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("mod_audio"),
         "notes": "channels neutral (1.0) without audio; dynamic evidence in Part 2"},
        {"id": "show.parameter_modulation_modulate", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("mod_param_colorwave") + cues("mod_param_bands")
                               + cues("mod_param_audio") + ["vid_fusion_weights_mod"]))},
        {"id": "show.parameter_modulation_drive", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("mod_param_breath") + cues("mod_param_wipe")
                               + cues("mod_param_noise") + cues("mod_param_onset")))},
        {"id": "show.modulatable_params", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("mod_param") + ["vid_fusion_weights_mod",
                                                    "vid_fusion_videoonly",
                                                    "vid_fusion_audioheavy"])),
         "notes": "all 11 registry-modulatable float params exercised; "
                  "video_audio_fusion members in Part 3"},
        {"id": "show.scalar_source_cue_progress", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("mod_param") + cues("fx_twinkle_gate")
                               + cues("fx_twinkle_birth") + cues("fx_colorwipe_progress")))},
        {"id": "show.scalar_source_audio", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("aud_historystream") + cues("aud_twinkle")
                               + cues("mod_param_audio"))),
         "notes": "fallback behavior in Part 1; live values in Part 2"},
        {"id": "show.colorsource_timeline", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("col_timeline") + cues("col_event_timeline")
                               + cues("fx_history_identity")))},
        {"id": "show.colorsource_spatial_palette", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("col_spatial") + cues("col_event_spatial")))},
        {"id": "show.colorsource_audio_spectrum_palette", "kind": "show_language",
         "status": "FULL", "cue_ids": cues("col_audio_spectrum"),
         "notes": "fallback in Part 1; live spectrum in Part 2"},
        {"id": "show.colorsource_dominant_frequency_palette", "kind": "show_language",
         "status": "FULL", "cue_ids": cues("col_dominant_freq"),
         "notes": "fallback in Part 1; pitch tracking in Part 2"},
        {"id": "show.colorsource_video_average", "kind": "show_language", "status": "FULL",
         "cue_ids": sorted(set(cues("vid_average") + cues("col_video_fallback"))),
         "notes": "fallback in Part 1; live evidence in Part 3"},
        {"id": "show.colorsource_video_dominant", "kind": "show_language", "status": "FULL",
         "cue_ids": cues("vid_dominant"), "notes": "live evidence in Part 3"},
        {"id": "show.virtual_paths_multi_member", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "members require >=2 distinct strips; a 1-member path degenerates"},
        {"id": "show.branches_start_on_release", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "branches need a multi-member virtual path and a digital_set target"},
        {"id": "show.branches_pre_roll", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "same structural dependency as start_on_release"},
        {"id": "show.digital_group", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "no group registry in a single-strip catalog"},
        {"id": "show.all_digital", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "v1-only grammar; on one strip it degenerates to strip_31"},
        {"id": "show.analog_zones_rgbcct", "kind": "show_language",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "WS2811 carries RGB only; warm/cool white channels are analog-only"},
        {"id": "color.cross_strip_seam", "kind": "visual",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "requires >=2 physical strips"},
        {"id": "color.spectrum_simultaneous_zones", "kind": "visual",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "one strip carries exactly one band color (bass precedence)"},
        {"id": "color.video_multi_zone_mapping", "kind": "visual",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "video_ambient paints all 10px one video_zone color"},
        {"id": "audio.beat_sync_fixed_cues", "kind": "visual",
         "status": "NOT_COVERABLE_SINGLE_STRIP", "cue_ids": [],
         "notes": "tempo only reaches motion through the adaptive selector"},
        {"id": "audio.onset_vs_spectral_flux_distinction", "kind": "visual",
         "status": "PARTIAL", "cue_ids": cues("aud_onset_ripple"),
         "notes": "WLED sync derives onset == spectral_flux; the two mechanisms "
                  "cannot be distinguished through this chain"},
        {"id": "audio.silence_state", "kind": "visual", "status": "PARTIAL",
         "cue_ids": cues("mod_adaptive"),
         "notes": "environment-dependent (mic gain, room tone, WLED AGC)"},
        {"id": "stress.rapid_cue_switching", "kind": "stress", "status": "FULL",
         "cue_ids": cues("str_rapid")},
        {"id": "stress.demo_registry_cycling", "kind": "stress", "status": "PARTIAL",
         "cue_ids": cues("fx_demo"),
         "notes": "children run on renderer defaults; self-sufficient subset only"},
    ]

    enum_coverage: dict[str, list[str]] = {}
    authored: dict[str, set[float]] = {}
    for spec in main_specs + video_specs:
        registration = get_effect_registration(spec.effect_id)
        for item in registration.parameter_specs:
            key = f"{spec.effect_id}.{item.name}"
            if item.kind == "enum":
                covered = enum_coverage.setdefault(key, [])
                if spec.params.get(item.name) is not None:
                    if spec.params[item.name] not in covered:
                        covered.append(spec.params[item.name])
            elif item.kind in {"float", "integer"}:
                if item.name in spec.params and isinstance(
                    spec.params[item.name], (int, float)
                ):
                    authored.setdefault(key, set()).add(float(spec.params[item.name]))

    missing_enums: dict[str, list[str]] = {}
    for registration_obj in (get_effect_registration(name) for name in list_effects()):
        for item in registration_obj.parameter_specs:
            if item.kind != "enum":
                continue
            key = f"{registration_obj.id}.{item.name}"
            covered = set(enum_coverage.get(key, ()))
            absent = [choice for choice in item.choices if choice not in covered]
            if absent:
                missing_enums[key] = absent

    boundary_notes: dict[str, str] = {}
    boundary_exemptions = {
        "video_audio_fusion.video_weight.min":
            "mechanism identical to audio_weight=0 (authored 0.0 in vid_fusion_videoonly)",
    }
    for registration_obj in (get_effect_registration(name) for name in list_effects()):
        for item in registration_obj.parameter_specs:
            if item.kind not in {"float", "integer"}:
                continue
            key = f"{registration_obj.id}.{item.name}"
            values = authored.get(key, set())
            for label, bound in (("min", item.minimum), ("max", item.maximum)):
                if bound is None:
                    continue
                if any(value == float(bound) for value in values):
                    continue
                exemption_key = f"{key}.{label}"
                if exemption_key in boundary_exemptions:
                    boundary_notes[exemption_key] = boundary_exemptions[exemption_key]
                else:
                    raise GenerationError(
                        f"declared {label} {bound} of {key} is not exercised by any cue"
                    )

    adaptive_effects = {"static", "breath", "chase", "color_wave"}
    demo_children = ["static", "breath", "color_wave", "chase"]
    return {
        "schema_version": 1,
        "generated_at": CREATED_AT,
        "target": {
            "strip_id": TARGET_ID,
            "pixel_count": pixel_count,
            "physical": "50cm WS2811, 10 controllable groups (pixel_count counts IC groups)",
            "source_profile": str(PROFILE_PATH),
        },
        "effect_registry_source": "light_engine.effects.list_effect_registrations()",
        "effect_count": len(list_effects()),
        "show_parts": {
            "part1_part2": {
                "file": "show(1).yaml",
                "show_id": SHOW_ID_MAIN,
                "cues": len(main_specs),
                "duration_seconds": round(max(s.start + s.duration for s in main_specs), 3),
            },
            "part3_video": {
                "file": "show-video(1).yaml",
                "show_id": SHOW_ID_VIDEO,
                "cues": len(video_specs),
                "duration_seconds": round(max(s.start + s.duration for s in video_specs), 3),
            },
        },
        "uint8_levels": _uint8_table(),
        "adaptive_mapped_effects": sorted(adaptive_effects),
        "demo_children": demo_children,
        "enum_choice_coverage": dict(sorted(enum_coverage.items())),
        "missing_enum_choices": missing_enums,
        "boundary_coverage_notes": dict(sorted(boundary_notes.items())),
        "capabilities": capabilities,
        "cue_metrics": metrics,
        "hardware_claim": "SOFTWARE EVIDENCE ONLY - no hardware pass is recorded here; "
                          "hardware gates are documented in README.md",
    }


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


def _readme(main_specs: list[CueSpec], video_specs: list[CueSpec]) -> str:
    main_duration = max(s.start + s.duration for s in main_specs)
    video_duration = max(s.start + s.duration for s in video_specs)
    counts: dict[str, int] = {}
    for spec in main_specs + video_specs:
        counts[spec.metric_class] = counts.get(spec.metric_class, 0) + 1
    class_rows = "\n".join(
        f"| {name} | {count} |" for name, count in sorted(counts.items())
    )
    return f"""# Single-Strip Acceptance v1 (strip_31)

**NOT HARDWARE VERIFIED.** Acceptance fixture for the RK3568 hardware run
(RK3568 is the backup/degraded host; the runbook and profile are identical to
the RK3588 production procedure). Targets only `{TARGET_ID}`: {10} logical
pixels / 10 WS2811 controllable groups / ~50 cm (pixel_count counts WS2811 IC
groups, not LED dies). The Show references the logical strip id only;
node/IP/GPIO resolution stays in the profile.

Generated by `scripts/generate_single_strip_acceptance_show.py` from the live
`light_engine.effects` registry — do not hand-edit the YAML; re-generate instead.

## Campaign parts

| Part | File | Run mode | Cues | Duration |
| --- | --- | --- | ---: | ---: |
| Part 1 — deterministic no-media baseline | `show(1).yaml` | `--clock internal` | {len(main_specs)} | {main_duration:.0f}s |
| Part 2 — formal live audio chain | `show(1).yaml` (same file) | same, with WLED Audio Sync V2 live | {len(main_specs)} | {main_duration:.0f}s |
| Part 3 — local video / fusion | `show-video(1).yaml` | `--clock mpv --video clip --audio wav` | {len(video_specs)} | {video_duration:.0f}s |

Machine coverage: `coverage-manifest(1).json` (FULL / PARTIAL /
NOT_COVERABLE_SINGLE_STRIP per capability, plus per-cue metric class and the
post-transform uint8 level table). No `FULL` record means hardware PASS.

## Run (bundled interpreter only)

```powershell
# regenerate + verify (byte-identical proof the coverage still matches the registry)
.\\.python\\Scripts\\python.exe "scripts\\generate_single_strip_acceptance_show(1).py" --check

# preflight (no sockets)
.\\.python\\Scripts\\python.exe -m light_engine --config {PROFILE_PATH.as_posix()} validate-show --show "{OUT_DIR.as_posix()}/show(1).yaml"
.\\.python\\Scripts\\python.exe -m light_engine --config {PROFILE_PATH.as_posix()} inspect-topology --show "{OUT_DIR.as_posix()}/show(1).yaml"

# Part 1: deterministic no-media baseline. The silence wav prevents the CLI's
# synthetic fallback (run --show without --video/--audio would feed the engine's
# synthetic scene generator to video-dependent cues); file silence also pins
# the audio path to defined silence. Expect: audio-dependent cues render
# defined black, video_average shows the authored steady fallback.
.\\.python\\Scripts\\python.exe -m light_engine --config {PROFILE_PATH.as_posix()} run --show "{OUT_DIR.as_posix()}/show(1).yaml" --clock internal --audio acceptance-silence.wav

# Part 2: SAME COMMAND WITHOUT --audio while the formal chain is live:
.\\.python\\Scripts\\python.exe -m light_engine --config {PROFILE_PATH.as_posix()} run --show "{OUT_DIR.as_posix()}/show(1).yaml" --clock internal
#   loudspeaker -> ESP32 mic -> WLED Audio Reactive -> WLED Audio Sync V2
#   (multicast 239.0.0.1:11988) -> RK3568 -> strip_31
# Why --audio MUST be dropped: the file audio reader takes absolute priority
# over the live WLED source (engine/__init__.py _get_audio_features), so the
# silence wav would mute Part 2. Without media flags the CLI engages its
# synthetic data source, but the live WLED source shadows synthetic AUDIO and
# only the single video_average cue (col_video_fallback) sees synthetic scene
# colors instead of its fallback in Part 2 - an accepted, documented artifact.
# Never attach music as --audio/media_path: file audio bypasses the live input.

# Part 3: local video on the Linux host (no hotspot, no bluetooth). mpv IPC is
# an AF_UNIX filesystem socket: pass the SAME path to mpv and --mpv-socket.
# (The mpv IPC clock does not work on Windows CPython; run Part 3 on the host.)
mpv --input-ipc-server=/tmp/light-belt-mpv-ipc --idle=yes acceptance-clip.mp4
.\\.python\\Scripts\\python.exe -m light_engine --config {PROFILE_PATH.as_posix()} run --show "{OUT_DIR.as_posix()}/show-video(1).yaml" --clock mpv --mpv-socket /tmp/light-belt-mpv-ipc --video acceptance-clip.mp4 --audio acceptance-beats.wav
```

Build the deterministic clip + wav with
`"scripts/make_acceptance_video_clip(1).py" --out-dir <dir>` (64s: R/G/B 8s each,
red field + white sweeping bar 6s, near-black 8s, 4x3s bright hard cuts,
white 10s, black 4s).

## Part 2 acoustic stimulus sequence (loudspeaker -> mic; phone + small speaker)

Play into the air near the ESP32 mic. Verify WLED AGC/gain first; keep volume
fixed. Do not judge ripple counts (onset == spectral_flux in this chain; peaks
can double-trigger).

| # | Duration | Stimulus | Observe on strip_31 |
| --- | --- | --- | --- |
| 0 | 10s | Silence (room baseline; verify stale=false, packets_valid increasing) | floor/black, no ripples |
| 1 | 10s | 150-200 Hz thumps, loud (phone speakers cannot do 40 Hz) | `aud_basspulse_*`, `aud_spectrum_bass` swell red/cyan |
| 2 | 8s | 500 Hz mid tone | `aud_spectrum_mid` green |
| 3 | 8s | 3-6 kHz bursts, loud | `aud_spectrum_treble` blue (accept small movement) |
| 4 | 12s | Log sweep 100 Hz -> 8 kHz | `col_dominant_freq` hue walks; spectrum gradient slides |
| 5 | 16s | Isolated handclaps ~2s apart | `aud_onset_ripple_*` waves; judge presence/origin, not count |
| 6 | >=30s | 120 BPM metronome | `mod_adaptive_states` locks rhythmic; tempo needs >=5 beats |
| 7 | 15s | Irregular knocks | ripples without tempo lock |
| 8 | 45s | Continuous bass-rich music | energetic/impact states, modulation ceilings |
| 9 | 15s | Quiet speech | calm/flowing states, low-gain end |
| 10 | 10s | Silence | envelopes release to baseline |

## Metric classes (offline observability audit)

| Class | Count |
| --- | ---: |
{class_rows}

`BLACK_UNTIL_MEDIA` cues must render defined black in Part 1 and are the Part 2
observation targets. `EXPECTED_DEGRADED` (LIMIT) cues are intentional
pathologies — record their actual degradation as an acceptance finding. The
audit uses conservative thresholds only to catch "valid but visually inert"
scenes; it is not an aesthetic rule and never changes renderer behavior.

## NOT_COVERABLE_SINGLE_STRIP (zero cues spent)

Multi-member virtual paths, branches (start_on_release / pre_roll), digital
groups, all_digital, cross-strip seams/continuity, simultaneous multi-zone
spectrum, multi-zone video mapping, warm/cool white (CCT), beat sync on fixed
cues. See `coverage-manifest.json` for the full list with reasons.

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

Safe end: let `safe_fade_to_black` + `safe_black_hold` finish, stop playback,
confirm strip_31 is black.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_all(pixel_count: int) -> dict[str, str]:
    main_show, main_specs = build_main_show(pixel_count)
    video_show, video_specs = build_video_show(pixel_count)
    manifest = _coverage_manifest(main_specs, video_specs, pixel_count)
    missing_enums = manifest["missing_enum_choices"]
    if missing_enums:
        raise GenerationError(f"enum choices not covered by any cue: {missing_enums}")
    readme = _readme(main_specs, video_specs)
    return {
        str(OUT_DIR / "show(1).yaml"): _yaml_text(main_show),
        str(OUT_DIR / "show-video(1).yaml"): _yaml_text(video_show),
        str(OUT_DIR / "coverage-manifest(1).json"): json.dumps(
            manifest, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False,
        ) + "\n",
        str(OUT_DIR / "README(1).md"): readme,
    }


def _yaml_text(data: dict[str, Any]) -> str:
    header = (
        f"# created_at: {CREATED_AT}\n"
        f"# purpose: single-strip ({TARGET_ID}) hardware acceptance campaign — "
        "systematic 1D lighting-language coverage; degradation on a short strip is an "
        "acceptance finding, not a renderer bug\n"
        "# status: draft\n"
        "# source: independent live-registry generator "
        "(scripts/generate_single_strip_acceptance_show.py)\n"
        "# hardware_verified: false\n"
    )
    return header + yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True, width=100,
    )


def resolve_pixel_count() -> int:
    from light_engine.config import Config
    from light_engine.mapping import Layout

    Config.reset()
    config = Config.get_instance(_ROOT / PROFILE_PATH)
    layout = Layout.from_config(config)
    for strip in layout.strips:
        if strip.id == TARGET_ID:
            return int(strip.pixel_count)
    raise GenerationError(f"{TARGET_ID} not present in {PROFILE_PATH}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify on-disk outputs match a fresh generation")
    args = parser.parse_args(argv)

    pixel_count = resolve_pixel_count()
    outputs = build_all(pixel_count)

    if args.check:
        mismatches = []
        for relative, text in outputs.items():
            path = _ROOT / relative
            if not path.exists():
                mismatches.append(f"{relative}: missing")
            elif path.read_text(encoding="utf-8") != text:
                mismatches.append(f"{relative}: content drift")
        if mismatches:
            print("GENERATION DRIFT DETECTED — re-run without --check:")
            for line in mismatches:
                print(f"  {line}")
            return 1
        print("GENERATION OK — outputs match the live registry")
        return 0

    for relative, text in outputs.items():
        path = _ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {relative} ({len(text.splitlines())} lines)")
    print(
        f"effects covered: {len(list_effects())}; "
        f"pixel_count({TARGET_ID})={pixel_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
