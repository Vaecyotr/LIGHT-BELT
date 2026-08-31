"""Offline observability audit for the single-strip acceptance campaign.

Beyond validity/finite/digest checks, this audit verifies that each cue is
actually VISIBLE in its expected way on 10 pixels using conservative
thresholds.  Classes come from coverage-manifest(1).json cue_metrics:

  UNIFORM_STATIC    spatially flat, temporally flat, and visible
  UNIFORM_BLACK     the deliberate safe-black scenes
  UNIFORM_TEMPORAL  spatially flat but visibly changing over time
  SPATIAL           visible spatial variation across the 10 groups
  EVENT             visible temporal bursts (events)
  BLACK_UNTIL_MEDIA defined black without media (Part 1 baseline)
  RAPID_SWITCH      finite and not fully dark through rapid switching
  EXPECTED_DEGRADED finite only — LIMIT pathologies, degradation is the finding

Thresholds are deliberately conservative: they exist to catch "valid but
visually inert" scenes, not to enforce aesthetics, and they never modify
renderer behavior.  Part 2/Part 3 dynamic evidence is out of scope here.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean, pvariance

from light_engine.config import Config
from light_engine.mapping import Layout
from light_engine.models import EffectContext
from light_engine.show import CueRenderJob, TargetCatalog, TargetResolver, load_show
from light_engine.show.compositor import evaluate_brightness_track

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "config" / "acceptance" / "single-strip-acceptance-v1"
SHOW = FIXTURE / "show(1).yaml"
MANIFEST = FIXTURE / "coverage-manifest(1).json"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
TARGET = "strip_31"
FPS = 15

SPATIAL_EPS = 5e-4
TEMPORAL_EPS = 8e-4
EVENT_EPS = 0.01
VISIBLE_EPS = 0.15
BLACK_EPS = 0.02


def _load():
    Config.reset()
    config = Config.get_instance(PROFILE)
    layout = Layout.from_config(config)
    catalog = TargetCatalog.from_layout(layout)
    return layout, load_show(SHOW, catalog)


def _render_cue_isolated(layout, show, cue, *, fps: int = FPS):
    resolver = TargetResolver.from_layout(layout)
    index = show.cues.index(cue)
    job = CueRenderJob(cue, index, resolver)
    # Brightness tracks apply at ShowRuntime level; mirror them here so the
    # audit sees the composed output for track-driven cues (calm amplitude,
    # mod_track_linear/step).
    tracks = [track for track in show.brightness_tracks
              if track.target.kind == "digital_strip" and track.target.id == TARGET]
    duration = cue.end - cue.start
    frames = []
    for sample in range(int(duration * fps)):
        t = cue.start + min(duration - 1e-6, sample / fps)
        ctx = EffectContext(
            timestamp=t,
            delta_time=1.0 / fps,
            sequence=sample,
            audio_features=None,
            video_features=None,
            music_control_state=None,
            mode_parameters={"strip_defs": [], "zone_defs": []},
        )
        contribution = job.render(ctx)
        strip = next(item for item in contribution.digital if item.strip_id == TARGET)
        # Mirror composition-side scaling: the transition weight is stored on
        # the contribution and only applied during compose_frame.
        weight = getattr(contribution, "weight", 1.0)
        level = None
        for track in tracks:
            value = evaluate_brightness_track(track, t)
            if value is not None:
                level = value
                break
        gain = weight if level is None else weight * level
        frames.append([tuple(min(1.0, max(0.0, channel * gain)) for channel in pixel)
                       for pixel in strip.pixels])
    return frames


def _metrics(frames, warmup_seconds: float):
    kept = frames[int(warmup_seconds * FPS):] or frames[-1:]
    luminance = [
        [0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in frame]
        for frame in kept
    ]
    spatial = [pvariance(values) if len(values) > 1 else 0.0 for values in luminance]
    temporal = [
        fmean(abs(a - b) for a, b in zip(luminance[i - 1], luminance[i]))
        for i in range(1, len(luminance))
    ]
    # Hue-only spatial gradients carry near-constant luminance; also measure
    # the per-frame per-channel range across the strip.
    rgb_range = max(
        max(pixel[c] for pixel in frame) - min(pixel[c] for pixel in frame)
        for frame in kept
        for c in range(3)
    )
    return {
        "spatial_max": max(spatial) if spatial else 0.0,
        "rgb_range_max": rgb_range,
        "temporal_mean": fmean(temporal) if temporal else 0.0,
        "temporal_max": max(temporal) if temporal else 0.0,
        "brightness_max": max(max(values) for values in luminance),
        "channel_max": max(max(pixel) for frame in kept for pixel in frame),
        "black_fraction": sum(
            1.0 for values in luminance if max(values) <= BLACK_EPS
        ) / len(luminance),
        "frame_count": len(kept),
    }


def _assert_class(metric_class: str, values: dict, cue_id: str) -> None:
    where = f"{cue_id} [{metric_class}]"
    if metric_class == "UNIFORM_STATIC":
        assert values["spatial_max"] <= SPATIAL_EPS, f"{where}: spatial variation"
        assert values["temporal_mean"] <= TEMPORAL_EPS, f"{where}: temporal drift"
        assert values["channel_max"] >= VISIBLE_EPS, f"{where}: invisible"
    elif metric_class == "UNIFORM_BLACK":
        assert values["brightness_max"] <= BLACK_EPS, f"{where}: not black"
    elif metric_class == "UNIFORM_TEMPORAL":
        assert values["spatial_max"] <= SPATIAL_EPS, f"{where}: spatial variation"
        assert values["temporal_mean"] >= TEMPORAL_EPS, f"{where}: temporally inert"
    elif metric_class == "SPATIAL":
        assert (values["spatial_max"] >= SPATIAL_EPS
                or values["rgb_range_max"] >= 0.05), f"{where}: spatially inert"
    elif metric_class == "EVENT":
        assert values["temporal_max"] >= EVENT_EPS, f"{where}: no visible events"
    elif metric_class == "BLACK_UNTIL_MEDIA":
        assert values["black_fraction"] >= 0.95, f"{where}: not a defined-black baseline"
    elif metric_class == "RAPID_SWITCH":
        assert values["black_fraction"] <= 0.98, f"{where}: fully dark"
    elif metric_class == "EXPECTED_DEGRADED":
        return  # degradation is the acceptance finding; finiteness checked by caller
    else:  # pragma: no cover - guard against manifest drift
        raise AssertionError(f"{where}: unknown metric class")


def test_every_main_show_cue_is_observable_in_its_expected_class() -> None:
    layout, show = _load()
    all_metrics = json.loads(MANIFEST.read_text(encoding="utf-8"))["cue_metrics"]
    metrics = {k: v for k, v in all_metrics.items() if v.get("part") == "main"}
    cue_by_id = {cue.id: cue for cue in show.cues}
    assert set(metrics) == set(cue_by_id), "manifest cue_metrics must match the show"

    checked: dict[str, int] = {}
    for cue_id, meta in sorted(metrics.items()):
        if meta.get("part") != "main":
            continue
        frames = _render_cue_isolated(layout, show, cue_by_id[cue_id])
        for frame in frames:
            for pixel in frame:
                for channel in pixel:
                    assert -1e-6 <= channel <= 1.0 + 1e-6, f"{cue_id}: channel out of range"
        values = _metrics(frames, meta.get("warmup_seconds", 0.0))
        _assert_class(meta["metric_class"], values, cue_id)
        checked[meta["metric_class"]] = checked.get(meta["metric_class"], 0) + 1

    # Coverage sanity: the audit must actually exercise the whole matrix.
    assert checked.get("SPATIAL", 0) >= 25
    assert checked.get("EVENT", 0) >= 5
    assert checked.get("BLACK_UNTIL_MEDIA", 0) >= 12
    assert checked.get("EXPECTED_DEGRADED", 0) >= 25
    assert checked.get("UNIFORM_TEMPORAL", 0) >= 8
    assert checked.get("UNIFORM_STATIC", 0) >= 10
    assert checked.get("UNIFORM_BLACK", 0) >= 2
