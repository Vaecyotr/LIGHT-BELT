"""Offline evidence tests for the single-strip (strip_31) acceptance campaign.

Covers: generator/registry byte-sync, dual-profile validation, full-timeline
finite rendering, render determinism, pinned post-transform digests, contrast
pair A/B distance, and the Part 3 video show with synthetic media features.

All rendering is software-only (no sockets, no hardware claim).  Digest runs
use a fixed-dt offline clock, never a wall-paced clock.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

from light_engine.config import Config
from light_engine.effects.base import create_effect
from light_engine.mapping import Layout
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures
from light_engine.outputs.transform import OutputTransform
from light_engine.show import CueRenderJob, TargetCatalog, TargetResolver, load_show
from light_engine.show.compositor import ShowRuntime, black_base_frame

REPO = Path(__file__).resolve().parents[1]
GENERATOR = REPO / "scripts" / "generate_single_strip_acceptance_show(1).py"
FIXTURE = REPO / "config" / "acceptance" / "single-strip-acceptance-v1"
SHOW = FIXTURE / "show(1).yaml"
VIDEO_SHOW = FIXTURE / "show-video(1).yaml"
MANIFEST = FIXTURE / "coverage-manifest(1).json"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
PROFILE_UDP = REPO / "config" / "profiles" / "udp-v3-nine-strip-maintenance.yaml"
TARGET = "strip_31"
FPS = 15

# Pinned at FPS=15, fixed-dt offline render, post-transform uint8 pixels of
# strip_31, sampled every 900 frames starting at frame 8.  Regenerate with
# artifacts/runs/single-strip-acceptance-v1/compute_digests_scratch.py after an
# intentional generator change.
PINNED_DIGESTS = {
    "0.533": "a3672a6f6f1f1529c42b5855af7eb38ad28945ca5909d999d52a9c5a057a539a",
    "60.533": "7396d0ea39781b037ca1b78af5e5777526a2b8aeaa1c960fe4d5def5d0ccf28e",
    "120.533": "248a50b9669a68226c016449e657b238099acba9a2d9ea8087dbe8bc52e86d40",
    "180.533": "cba978460339eb97b3cec6017628f8dd072f65b7c45e0798951cf06b1c4c31b3",
    "240.533": "a3672a6f6f1f1529c42b5855af7eb38ad28945ca5909d999d52a9c5a057a539a",
    "300.533": "14227f385a2d8b63632a0c73277cde5ff5c954477f1af2294f3cd0b0eb3cb7da",
    "360.533": "c03b9c1a35faa46d288397cbe3b933744881eb2f1927498e36a3959c9864b9a0",
    "420.533": "13701fdcf04bdaa417e71fee8e228e68bb50e785326c3546cd1afb58544aba96",
    "480.533": "4d6b0f3ffbd263ec8ecfbbaf44e3d991cca0b7c02dd3972bf025a58f3e769410",
    "540.533": "7a6e2c59f87d21c1b56ebb5a4dba05c1885675e256acdc18d6e6ad117702c690",
    "600.533": "6d7abc5efab4705b64c913d9135ccaa0ddb9ab8ae515411f1ab890a53979fe6e",
    "660.533": "448e72cc4dafe70482180a8be5bbfcbc3f5e488f65d58342f2cfa1d4d39cfab5",
    "720.533": "a3672a6f6f1f1529c42b5855af7eb38ad28945ca5909d999d52a9c5a057a539a",
    "780.533": "a3672a6f6f1f1529c42b5855af7eb38ad28945ca5909d999d52a9c5a057a539a",
    "840.533": "a3672a6f6f1f1529c42b5855af7eb38ad28945ca5909d999d52a9c5a057a539a",
}


def _load(profile: Path = PROFILE):
    Config.reset()
    config = Config.get_instance(profile)
    layout = Layout.from_config(config)
    catalog = TargetCatalog.from_layout(layout)
    return config, layout, catalog


def _transform(config) -> OutputTransform:
    return OutputTransform(
        global_brightness=config.get("system.smoothing.max_brightness", 0.85),
        gamma=config.get("system.smoothing.gamma", 1.0),
        power_limit=5.0,
        per_zone_warm_bias={},
        per_zone_cool_bias={},
    )


def _render_timeline(show, layout, *, video_features_fn=None, audio_features_fn=None):
    """Render the full timeline at fixed dt; yields (t, logical frame)."""
    runtime = ShowRuntime.from_layout(show, layout)
    strips = list(layout.strips)
    zones = list(layout.zones)
    dt = 1.0 / FPS
    total = int(show.duration * FPS)
    for index in range(total):
        t = index * dt
        ctx = EffectContext(
            timestamp=t,
            delta_time=dt,
            sequence=index,
            audio_features=None if audio_features_fn is None else audio_features_fn(t),
            video_features=None if video_features_fn is None else video_features_fn(t),
            music_control_state=None,
            mode_parameters={"strip_defs": [], "zone_defs": []},
        )
        base = black_base_frame(timestamp=t, sequence=index,
                                analog_zones=zones, digital_strips=strips)
        yield t, runtime.render(ctx, base)


def _strip_pixels(frame, strip_id: str = TARGET):
    return next(s for s in frame.strips if s.strip_id == strip_id).pixels


def _assert_finite(pixels) -> None:
    for pixel in pixels:
        for channel in pixel:
            assert math.isfinite(channel), "non-finite channel in rendered frame"
            assert -1e-6 <= channel <= 1.0 + 1e-6, "channel outside [0, 1]"


def _render_cue_isolated(show, layout, cue, *, fps: int = FPS):
    """Render one cue in isolation (fresh job, cue-local time)."""
    resolver = TargetResolver.from_layout(layout)
    index = show.cues.index(cue)
    job = CueRenderJob(cue, index, resolver)
    duration = cue.end - cue.start
    frames = []
    for sample in range(int(duration * fps)):
        local = min(duration - 1e-6, sample / fps)
        ctx = EffectContext(
            timestamp=cue.start + local,
            delta_time=1.0 / fps,
            sequence=sample,
            audio_features=None,
            video_features=None,
            music_control_state=None,
            mode_parameters={"strip_defs": [], "zone_defs": []},
        )
        contribution = job.render(ctx)
        pixels = next(item for item in contribution.digital
                      if item.strip_id == TARGET).pixels
        frames.append([list(p) for p in pixels])
    return frames


def _cue_metrics() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["cue_metrics"]


def test_generator_output_matches_live_registry() -> None:
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_shows_validate_against_both_production_profiles() -> None:
    for profile in (PROFILE, PROFILE_UDP):
        _, _, catalog = _load(profile)
        assert load_show(SHOW, catalog) is not None
        assert load_show(VIDEO_SHOW, catalog) is not None


def test_show_targets_only_strip_31_and_avoids_uncoverable_grammar() -> None:
    _, layout, catalog = _load()
    show = load_show(SHOW, catalog)
    assert {strip.id for strip in layout.strips} >= {TARGET}
    for cue in show.cues:
        assert cue.target.kind == "digital_strip"
        assert cue.target.id == TARGET
    assert show.virtual_paths == (), "single-strip show must not author virtual paths"
    for cue in show.cues:
        assert not cue.branches, "branches are NOT_COVERABLE_SINGLE_STRIP"
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    statuses = {capability["id"]: capability["status"] for capability in manifest["capabilities"]}
    for capability_id in (
        "show.branches_start_on_release",
        "show.branches_pre_roll",
        "show.virtual_paths_multi_member",
        "color.cross_strip_seam",
        "color.spectrum_simultaneous_zones",
        "color.video_multi_zone_mapping",
        "show.analog_zones_rgbcct",
    ):
        assert statuses[capability_id] == "NOT_COVERABLE_SINGLE_STRIP", capability_id


def test_full_timeline_renders_finite_and_ends_black() -> None:
    _, layout, catalog = _load()
    show = load_show(SHOW, catalog)
    last_pixels = None
    for _, frame in _render_timeline(show, layout):
        pixels = _strip_pixels(frame)
        _assert_finite(pixels)
        last_pixels = pixels
    assert last_pixels is not None
    assert all(max(pixel) <= 0.02 for pixel in last_pixels), "show must end in safe black"


def test_render_is_deterministic_across_runs() -> None:
    _, layout, catalog = _load()
    show = load_show(SHOW, catalog)

    def stream_digest() -> str:
        digest = hashlib.sha256()
        for _, frame in _render_timeline(show, layout):
            payload = json.dumps(
                [[round(c, 6) for c in p] for p in _strip_pixels(frame)],
                separators=(",", ":"),
            )
            digest.update(payload.encode())
        return digest.hexdigest()

    assert stream_digest() == stream_digest()


def test_post_transform_digests_match_pinned_baseline() -> None:
    config, layout, catalog = _load()
    show = load_show(SHOW, catalog)
    transform = _transform(config)
    observed: dict[str, str] = {}
    for t, frame in _render_timeline(show, layout):
        frame_index = round(t * FPS)
        if frame_index % 900 == 8:
            transformed = transform.apply_to_frame(frame)
            strip = next(s for s in transformed.strips if s.strip_id == TARGET)
            payload = json.dumps(strip.to_uint8(), separators=(",", ":"))
            observed[f"{t:.3f}"] = hashlib.sha256(payload.encode()).hexdigest()
    assert observed == PINNED_DIGESTS


def test_contrast_pairs_render_visibly_differently() -> None:
    _, layout, catalog = _load()
    show = load_show(SHOW, catalog)
    metrics = _cue_metrics()
    cue_by_id = {cue.id: cue for cue in show.cues}
    pairs: dict[str, list[str]] = {}
    for cue_id, meta in metrics.items():
        if meta.get("role") in {"contrast_a", "contrast_b"} and cue_id in cue_by_id:
            pairs.setdefault(meta.get("pair", cue_id), []).append(cue_id)

    def frames_of(cue):
        return [[tuple(p) for p in frame] for frame in _render_cue_isolated(show, layout, cue)]

    checked = 0
    for pair_id, members in sorted(pairs.items()):
        assert len(members) == 2, f"pair {pair_id} has {members}"
        first_meta = metrics[members[0]]
        second_meta = metrics[members[1]]
        black_pair = (
            first_meta["metric_class"] == "BLACK_UNTIL_MEDIA"
            and second_meta["metric_class"] == "BLACK_UNTIL_MEDIA"
        )
        if black_pair:
            continue  # A/B evidence deferred to Part 2 live audio
        first = frames_of(cue_by_id[members[0]])
        second = frames_of(cue_by_id[members[1]])
        count = min(len(first), len(second))
        distance = sum(
            abs(a - b)
            for index in range(count)
            for pa, pb in zip(first[index], second[index])
            for a, b in zip(pa, pb)
        ) / max(1, count * 30)
        assert distance >= 0.003, f"contrast pair {pair_id} barely differs (d={distance:.5f})"
        checked += 1
    assert checked >= 12, f"too few offline-verifiable contrast pairs: {checked}"


def _video_features_fn(t: float) -> VideoFeatures:
    if t < 8.0:
        average = (1.0, 0.0, 0.0)
    elif t < 16.0:
        average = (0.0, 1.0, 0.0)
    elif t < 24.0:
        average = (0.0, 0.0, 1.0)
    elif t < 30.0:
        average = (0.9, 0.35, 0.35)
    elif t < 38.0:
        average = (0.04, 0.04, 0.04)
    elif t < 50.0:
        cuts = [(1.0, 0.0, 1.0), (0.0, 1.0, 1.0), (0.0, 1.0, 0.0), (1.0, 1.0, 1.0)]
        average = cuts[int((t - 38.0) // 3.0) % 4]
    elif t < 60.0:
        average = (1.0, 1.0, 1.0)
    else:
        average = (0.0, 0.0, 0.0)
    return VideoFeatures(
        timestamp=t,
        average_rgb=average,
        dominant_rgb=average if t < 30.0 else (0.9, 0.1, 0.1),
        zone_colors={"left": average, "right": average, "top": average,
                     "bottom": average, "center": average},
        brightness=max(average),
        saturation=0.8,
        scene_change=0.0,
    )


def _beat_audio_fn(t: float) -> AudioFeatures:
    phase = t % 1.0
    rms = 0.8 if phase < 0.3 else 0.05
    return AudioFeatures(timestamp=t, rms=rms, loudness=rms, silence=rms <= 0.0,
                         bass=0.7 if phase < 0.3 else 0.05, onset=0.5 if phase < 0.1 else 0.0)


def test_video_show_renders_with_synthetic_media() -> None:
    _, layout, catalog = _load()
    show = load_show(VIDEO_SHOW, catalog)
    samples: dict[str, list[list[float]]] = {}
    for t, frame in _render_timeline(show, layout,
                                     video_features_fn=_video_features_fn,
                                     audio_features_fn=_beat_audio_fn):
        _assert_finite(_strip_pixels(frame))
        for cue in show.cues:
            if cue.start <= t < cue.end:
                samples.setdefault(cue.id, []).append(
                    [list(p) for p in _strip_pixels(frame)]
                )

    def luminance(frames):
        return [[0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2] for p in frame]
                for frame in frames]

    average = luminance(samples["vid_average_steps"])
    assert max(max(frame) for frame in average) >= 0.2
    temporal = sum(abs(average[i - 1][px] - average[i][px])
                   for i in range(1, len(average)) for px in range(10))
    assert temporal / max(1, len(average) * 10) >= 0.002, "average steps must move"

    fusion_only = luminance(samples["vid_fusion_videoonly"])
    assert max(max(frame) for frame in fusion_only) >= 0.2, "white segment must drive fusion"

    fusion_audio = luminance(samples["vid_fusion_audioheavy"])
    delta = sum(abs(fusion_audio[i - 1][px] - fusion_audio[i][px])
                for i in range(1, len(fusion_audio)) for px in range(10))
    assert delta / max(1, len(fusion_audio) * 10) >= 0.002, "audio leg must pulse"

    weights_mod = luminance(samples["vid_fusion_weights_mod"])
    delta = sum(abs(weights_mod[i - 1][px] - weights_mod[i][px])
                for i in range(1, len(weights_mod)) for px in range(10))
    assert max(max(frame) for frame in weights_mod) >= 0.5, "weights_mod must stay visible"
    assert delta / max(1, len(weights_mod) * 10) >= 0.002, "weights_mod must ramp/pulse"
