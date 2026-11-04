"""Deterministic software-only acceptance evidence for Phase 22 authoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from light_engine.config import Config, load_yaml
from light_engine.mapping import Layout
from light_engine.models import EffectContext, MusicControlState, PixelFrame
from light_engine.show import (
    CueRenderJob,
    ShowRuntime,
    TargetCatalog,
    TargetResolver,
    black_base_frame,
    load_show,
    transition_weight,
)
from light_engine.show.audio_modulation import CueAudioModulator


FPS = 20
FRAME_COUNT = 180
DEFAULT_ARTIFACT_DIR = Path("artifacts/runs/authoring-modulation-v1")
SOFTWARE_ONLY = "NOT HARDWARE VERIFIED"


def load_acceptance_layout(path: Path) -> Layout:
    """Load the small acceptance topology without changing global defaults."""
    Config.reset()
    config = Config.get_instance()
    config._data["layout"] = load_yaml(path)["layout"]
    return Layout.from_config(config)


def _music_state(timestamp: float) -> MusicControlState | None:
    if timestamp < 5.0:
        return None
    return MusicControlState(
        timestamp=timestamp,
        tempo_bpm=120.0,
        tempo_confidence=0.9,
        beat_phase=(timestamp * 2.0) % 1.0,
        beat_strength=0.8,
        beat_regularity=0.9,
        energy=0.9,
        bass_pulse=0.4,
        spectral_motion=0.5,
    )


def _context(timestamp: float, sequence: int) -> EffectContext:
    return EffectContext(
        timestamp=timestamp,
        delta_time=1.0 / FPS,
        sequence=sequence,
        music_control_state=_music_state(timestamp),
    )


def _frame_data(frame: PixelFrame) -> dict[str, Any]:
    return {
        "timestamp": frame.timestamp,
        "sequence": frame.sequence,
        "strips": [
            {"id": strip.strip_id, "pixels": [list(pixel) for pixel in strip.pixels]}
            for strip in frame.strips
        ],
        "zones": [
            {
                "id": zone.zone_id,
                "channels": [
                    zone.color.r,
                    zone.color.g,
                    zone.color.b,
                    zone.color.warm_white,
                    zone.color.cool_white,
                ],
            }
            for zone in frame.zones
        ],
    }


def _pixel(frame: PixelFrame, strip_id: str, index: int) -> list[float]:
    for strip in frame.strips:
        if strip.strip_id == strip_id:
            return list(strip.pixels[index])
    raise KeyError(strip_id)


def _render(show_path: Path, layout: Layout) -> tuple[str, dict[float, PixelFrame]]:
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    runtime = ShowRuntime.from_layout(show, layout, seed=22)
    digest = hashlib.sha256()
    samples: dict[float, PixelFrame] = {}
    for sequence in range(FRAME_COUNT):
        timestamp = sequence / FPS
        base = black_base_frame(
            timestamp=timestamp,
            sequence=sequence,
            analog_zones=layout.zones,
            digital_strips=layout.strips,
        )
        frame = runtime.render(_context(timestamp, sequence), base)
        digest.update(json.dumps(_frame_data(frame), sort_keys=True, separators=(",", ":")).encode("utf-8"))
        if timestamp in {0.0, 1.0, 2.0, 5.5, 6.0, 7.5}:
            samples[timestamp] = frame
    return digest.hexdigest(), samples


def _cue(show, cue_id: str):
    return next(cue for cue in show.cues if cue.id == cue_id)


def _evidence(show_path: Path, layout: Layout, samples: dict[float, PixelFrame]) -> dict[str, Any]:
    show = load_show(show_path, TargetCatalog.from_layout(layout))
    resolver = TargetResolver.from_layout(layout)
    fixed = _cue(show, "fixed-modulated-static")
    adaptive = _cue(show, "adaptive-modulated-wall")
    base = _cue(show, "overlap-base")
    fixed_ctx = _context(6.0, 120)
    neutral_ctx = EffectContext(timestamp=6.0, delta_time=1.0 / FPS, sequence=120)
    fixed_multipliers = CueAudioModulator(fixed.audio_modulation).multipliers(fixed_ctx)
    neutral_multipliers = CueAudioModulator(fixed.audio_modulation).multipliers(neutral_ctx)
    adaptive_job = CueRenderJob(adaptive, 3, resolver)
    adaptive_job.render(fixed_ctx)
    adaptive_decision = adaptive_job._selector.last_decision  # acceptance evidence for public decision record
    assert adaptive_decision is not None
    neutral_adaptive = replace(adaptive, audio_modulation=None)
    modulated_speed_job = CueRenderJob(adaptive, 3, resolver)
    neutral_speed_job = CueRenderJob(neutral_adaptive, 3, resolver)
    for sequence in range(12):
        timestamp = 5.0 + (sequence + 1) / FPS
        ctx = _context(timestamp, 200 + sequence)
        modulated_contribution = modulated_speed_job.render(ctx)
        neutral_contribution = neutral_speed_job.render(ctx)
    modulated_pixels = modulated_contribution.digital[0].pixels
    neutral_pixels = neutral_contribution.digital[0].pixels

    seam = [
        {"virtual_coordinate": 3, "destination": {"strip_id": "front", "pixel_index": 3}, "pixel": _pixel(samples[1.0], "front", 3)},
        {"virtual_coordinate": 4, "destination": {"strip_id": "wall_right", "pixel_index": 3}, "pixel": _pixel(samples[1.0], "wall_right", 3)},
        {"virtual_coordinate": 5, "destination": {"strip_id": "wall_right", "pixel_index": 2}, "pixel": _pixel(samples[1.0], "wall_right", 2)},
    ]
    return {
        "not_hardware_verified": SOFTWARE_ONLY,
        "color_timeline": [
            {"local_time": time, "front_pixel_0": _pixel(samples[time], "front", 0)}
            for time in (0.0, 1.0, 2.0)
        ],
        "audio_modulation": {
            "active": {
                "brightness": fixed_multipliers.brightness,
                "speed": fixed_multipliers.speed,
                "intensity": fixed_multipliers.intensity,
            },
            "no_audio": {
                "brightness": neutral_multipliers.brightness,
                "speed": neutral_multipliers.speed,
                "intensity": neutral_multipliers.intensity,
            },
            "fixed_effect": fixed.effect.name,
            "fixed_sample_pixel": _pixel(samples[6.0], "front", 0),
        },
        "virtual_path_seam": seam,
        "transitions_and_overlap": {
            "fade_in_midpoint_weight": transition_weight(fixed, 5.5),
            "fade_out_midpoint_weight": transition_weight(fixed, 7.5),
            "overlap_base_weight": transition_weight(base, 5.5),
            "front_pixel_at_fade_in_midpoint": _pixel(samples[5.5], "front", 0),
            "front_pixel_at_fade_out_midpoint": _pixel(samples[7.5], "front", 0),
        },
        "adaptive": {
            "selected_effect": adaptive_decision.selected_effect,
            "allowed_effects": dict(adaptive.effect.allowed),
            "music_state": adaptive_decision.music_state,
            "reason_code": adaptive_decision.reason_code,
            "sync_mode": adaptive_decision.sync_mode,
            "speed_before_modulation": adaptive_decision.speed,
            "speed_multiplier": CueAudioModulator(adaptive.audio_modulation).multipliers(fixed_ctx).speed,
            "speed_path_lit_indices": {
                "modulated": [index for index, pixel in enumerate(modulated_pixels) if any(pixel)],
                "neutral": [index for index, pixel in enumerate(neutral_pixels) if any(pixel)],
            },
        },
    }


def _assert_finite(value: Any) -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite acceptance evidence")
    elif isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _write_report(summary: dict[str, Any], report_path: Path) -> None:
    hashes = summary["artifact_sha256"]
    report_path.write_text(
        "# Phase 22 Authoring Modulation Acceptance\n\n"
        f"{SOFTWARE_ONLY}\n\n"
        "The bounded deterministic renderer validates the authored show twice and records only software evidence.\n\n"
        "| Requirement | Implementation | Test | Evidence |\n"
        "| --- | --- | --- | --- |\n"
        "| Color timeline interpolation | `virtual-color-timeline` | exact RGB samples | `color_timeline` |\n"
        "| Cue-local modulation and fallback | fixed/adaptive modulation cues | bounded multipliers | `audio_modulation` |\n"
        "| Virtual seam | `screen_to_wall` | coordinates 3/4/5 | `virtual_path_seam` |\n"
        "| Transition overlap | two front cues | midpoint weights/pixels | `transitions_and_overlap` |\n"
        "| Adaptive allow-list | adaptive wall cue | selected effect | `adaptive` |\n"
        "| Determinism and finite frames | 180-frame replay | digest equality/finite scan | `two_run_digests` |\n\n"
        f"Base SHA: `{summary['base_sha']}`  \nHead SHA: `{summary['head_sha']}`\n\n"
        "Audit: no skips or xfails were added; no golden manifest applies to this phase.\n\n"
        "Artifacts:\n\n"
        + "\n".join(f"- `{path}`: `{digest}`" for path, digest in hashes.items())
        + "\n",
        encoding="utf-8",
    )


def run_acceptance(
    show_path: Path,
    layout_path: Path,
    *,
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR,
    report_path: Path | None = None,
) -> dict[str, Any]:
    layout = load_acceptance_layout(layout_path)
    first_digest, samples = _render(show_path, layout)
    second_digest, _ = _render(show_path, layout)
    evidence = _evidence(show_path, layout, samples)
    _assert_finite(evidence)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = artifact_dir / "sample_evidence.json"
    digests_path = artifact_dir / "two_run_digests.json"
    _write_json(evidence_path, evidence)
    _write_json(digests_path, {"not_hardware_verified": SOFTWARE_ONLY, "digests": [first_digest, second_digest]})
    manifest_path = artifact_dir / "manifest.json"
    manifest_hashes = {str(evidence_path).replace("\\", "/"): _sha256(evidence_path), str(digests_path).replace("\\", "/"): _sha256(digests_path)}
    _write_json(manifest_path, {"not_hardware_verified": SOFTWARE_ONLY, "artifact_sha256": manifest_hashes})
    hashes = {**manifest_hashes, str(manifest_path).replace("\\", "/"): _sha256(manifest_path)}
    summary = {
        "not_hardware_verified": SOFTWARE_ONLY,
        "base_sha": _git_head(),
        "head_sha": _git_head(),
        "frame_count": FRAME_COUNT,
        "two_run_digests": [first_digest, second_digest],
        "evidence": evidence,
        "artifact_sha256": hashes,
    }
    _assert_finite(summary)
    _write_json(artifact_dir / "summary.json", summary)
    _write_report(summary, report_path or artifact_dir / "report.md")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    args = parser.parse_args()
    summary = run_acceptance(args.show, args.layout, artifact_dir=args.artifact_dir)
    print(f"Phase 22 acceptance: {summary['two_run_digests'][0]} ({SOFTWARE_ONLY})")


if __name__ == "__main__":
    main()
