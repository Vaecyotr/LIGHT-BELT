from __future__ import annotations

import hashlib
import random
from pathlib import Path

import pytest

import light_engine.show.compositor as compositor
from light_engine.config import Config
from light_engine.effects import create_effect
from light_engine.mapping import Layout
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures
from light_engine.outputs.transform import OutputTransform
from light_engine.show import (
    ShowRuntime,
    TargetCatalog,
    black_base_frame,
    compose_frame,
    load_show,
)

REPO = Path(__file__).resolve().parents[1]
SHOW_PATH = REPO / "config" / "acceptance" / "single-strip-ppt-showcase-v1" / "show.yaml"
PROFILE = REPO / "config" / "profiles" / "rk3588-host-service.yaml"
TARGET = "strip_31"
FPS = 30
SEED = 31108


@pytest.fixture(scope="module")
def loaded():
    Config.reset()
    config = Config.get_instance(PROFILE)
    layout = Layout.from_config(config)
    show = load_show(SHOW_PATH, TargetCatalog.from_layout(layout))
    return config, layout, show


def _cue(show, cue_id):
    return next(cue for cue in show.cues if cue.id == cue_id)


def test_structure_registry_topology_and_exact_timeline(loaded):
    config, layout, show = loaded
    assert show.id == "single-strip-ppt-showcase-v1"
    assert show.duration == pytest.approx(116.0)
    assert len(show.cues) == 21
    assert config.get("system.output_fps") == pytest.approx(30.0)
    assert all(cue.target.kind == "digital_strip" and cue.target.id == TARGET for cue in show.cues)
    strip = next(item for item in layout.strips if item.id == TARGET)
    assert strip.pixel_count == 10
    assert sum(item.pixel_count for item in layout.strips) == 107
    assert all(cue.audio_control is None and cue.audio_modulation is None for cue in show.cues)
    assert all(cue.effect.id in {"static", "comet", "color_wave", "twinkle", "heat_fire", "coherent_noise_field"} for cue in show.cues)
    assert all(cue.effect.speed == pytest.approx(1.0) for cue in show.cues)

    expected = {
        "BLACK_start": (0, 2), "COMET_cool_single_wrap": (2, 8),
        "COMET_blue_double_bounce": (8, 15), "COMET_purple_double_wrap": (15, 22),
        "BLACK_after_comet": (22, 22.5), "WAVE_sine": (22.5, 29),
        "WAVE_triangle": (29, 35.5), "WAVE_saw": (35.5, 42.5),
        "BLACK_after_wave": (42.5, 43), "TWINKLE_low": (43, 49),
        "TWINKLE_mid": (49, 56), "TWINKLE_high": (56, 63),
        "BLACK_after_twinkle": (63, 63.5), "FIRE_low": (63.5, 70.5),
        "FIRE_mid": (70.5, 77.5), "FIRE_high": (77.5, 83.5),
        "BLACK_after_fire": (83.5, 84), "FINALE_noise": (84, 114),
        "FINALE_twinkle": (90, 114), "FINALE_comet": (98, 114),
        "BLACK_end": (114, 116),
    }
    assert len(expected) == len(show.cues)
    for cue_id, (start, end) in expected.items():
        cue = _cue(show, cue_id)
        assert (cue.start, cue.end) == pytest.approx((start, end))
        assert cue.start * FPS == round(cue.start * FPS)
        assert cue.end * FPS == round(cue.end * FPS)

    comet = [_cue(show, name) for name in ("COMET_cool_single_wrap", "COMET_blue_double_bounce", "COMET_purple_double_wrap")]
    assert [c.effect.params for c in comet] == [
        {"speed": 2.5, "count": 1, "trajectory": "wrap", "tail_length": 0.25, "decay": 0.8, "phase_spacing": 1},
        {"speed": 3.0, "count": 2, "trajectory": "bounce", "tail_length": 0.2, "decay": 0.8, "phase_spacing": 0.5},
        {"speed": 4.5, "count": 2, "trajectory": "wrap", "tail_length": 0.15, "decay": 0.8, "phase_spacing": 0.5},
    ]
    waves = [_cue(show, name) for name in ("WAVE_sine", "WAVE_triangle", "WAVE_saw")]
    assert [(c.effect.params["waveform"], c.effect.params["speed"], c.effect.params["width"], c.effect.params["hue_span_degrees"]) for c in waves] == [
        ("sine", 0.35, 0.9, 140), ("triangle", 0.75, 0.8, 240), ("saw", -0.8, 0.75, 360)
    ]
    twinkles = [_cue(show, name) for name in ("TWINKLE_low", "TWINKLE_mid", "TWINKLE_high")]
    assert [(c.effect.params["density"], c.effect.params["fade_time"]) for c in twinkles] == [(0.12, 0.9), (0.35, 0.7), (0.6, 0.5)]
    assert all(c.effect.params["event_width_px"] == 1 and c.effect.params["blur_radius_px"] == 0 for c in twinkles)
    assert all(c.effect.params["color_source"] == "palette" for c in twinkles)
    assert all(c.color.mode == "palette" and len(c.color.palette) == 3 for c in twinkles)
    assert twinkles[0].color.palette == ((0.95, 0.82, 0.55), (0.03, 0.2, 1.0), (0.55, 0.05, 0.9))
    fires = [_cue(show, name) for name in ("FIRE_low", "FIRE_mid", "FIRE_high")]
    assert [(c.effect.params["spark_rate"], c.effect.params["spark_strength"], c.effect.params["cooling_per_second"], c.effect.params["diffusion"], c.effect.params["spark_zone_px"]) for c in fires] == [(4, .7, 1.2, .3, 2), (8, .9, .8, .35, 2), (12, .95, .65, .45, 2)]
    noise = _cue(show, "FINALE_noise")
    assert noise.effect.intensity == pytest.approx(.25)
    assert noise.transition.blend == "replace" and noise.transition.fade_out == pytest.approx(4)
    assert noise.color_source.type == "spatial_palette"
    assert noise.color_source.palette == ((0.02, 0.08, 0.55), (0.0, 0.7, 0.85), (0.45, 0.05, 0.8))
    assert noise.effect.params == {"feature_size_px": 3.2, "drift_rate": .3, "contrast": 1.15, "floor_gain": .08, "ceiling_gain": .65}
    assert _cue(show, "FINALE_twinkle").transition.blend == "add"
    assert _cue(show, "FINALE_comet").transition.blend == "add"
    assert all(_cue(show, name).transition.fade_out == pytest.approx(4) for name in ("FINALE_noise", "FINALE_twinkle", "FINALE_comet"))


def _replay(loaded, media=False, capture=False):
    config, layout, show = loaded
    transform = OutputTransform(global_brightness=config.get("system.smoothing.max_brightness"), gamma=config.get("system.smoothing.gamma"), power_limit=config.get("outputs.transform.power_limit", 5.0), per_zone_warm_bias=config.get("outputs.transform.per_zone_warm_bias", {}), per_zone_cool_bias=config.get("outputs.transform.per_zone_cool_bias", {}))
    original = compositor.compose_frame
    captured = {}
    if capture:
        def record(base, contributions):
            captured[base.timestamp] = tuple(contributions)
            return original(base, contributions)
        compositor.compose_frame = record
    digest = hashlib.sha256()
    samples = {cue.id: [] for cue in show.cues}
    tail = []
    random_state = random.getstate()
    random.seed(SEED)
    try:
        runtime = ShowRuntime.from_layout(show, layout, seed=SEED, effect_factory=create_effect)
        for index in range(int(show.duration * FPS)):
            timestamp = index / FPS
            base = black_base_frame(timestamp=timestamp, sequence=index, analog_zones=layout.zones, digital_strips=layout.strips)
            audio = AudioFeatures(timestamp=timestamp, rms=.5, loudness=.5, onset=0.0) if media else None
            video = VideoFeatures(timestamp=timestamp, average_rgb=(.2, .4, .6), dominant_rgb=(.8, .1, .2), brightness=.7, saturation=.8) if media else None
            frame = transform.apply_to_frame(runtime.render(EffectContext(timestamp=timestamp, delta_time=1 / FPS, sequence=index, audio_features=audio, video_features=video), base))
            for strip in frame.strips:
                pixels = strip.to_uint8()
                if strip.strip_id == TARGET:
                    digest.update(bytes(channel for pixel in pixels for channel in pixel))
                    for cue in show.cues:
                        if cue.start <= timestamp < cue.end and index % 10 == 0:
                            samples[cue.id].append(pixels)
                else:
                    assert all(pixel == (0, 0, 0) for pixel in pixels)
            if timestamp >= 114:
                tail.append(next(strip.to_uint8() for strip in frame.strips if strip.strip_id == TARGET))
        return digest.hexdigest(), samples, tail, captured
    finally:
        random.setstate(random_state)
        compositor.compose_frame = original


def test_full_116_second_replay_is_deterministic_media_free_and_safe(loaded):
    first = _replay(loaded, capture=True)
    second = _replay(loaded)
    media = _replay(loaded, media=True)
    assert first[0] == second[0] == media[0]
    assert len(first[2]) == 60
    assert all(pixel == (0, 0, 0) for frame in first[2] for pixel in frame)
    for cue_id, frames in first[1].items():
        assert frames, cue_id
        assert any(frame != frames[0] for frame in frames[1:]) or cue_id.startswith("BLACK_")


def test_finale_contributions_are_visible_and_fade_together(loaded):
    _, _, show = loaded
    _, _, _, captured = _replay(loaded, capture=True)
    for timestamp in (99, 105, 109, 111, 113):
        contributions = {item.cue_id: item for item in captured[timestamp]}
        assert {"FINALE_noise", "FINALE_twinkle", "FINALE_comet"} <= contributions.keys()
        base = black_base_frame(timestamp=timestamp, sequence=round(timestamp * FPS), analog_zones=loaded[1].zones, digital_strips=loaded[1].strips)
        full = compose_frame(base, list(contributions.values()))
        full_pixels = next(strip.pixels for strip in full.strips if strip.strip_id == TARGET)
        for cue_id in ("FINALE_noise", "FINALE_twinkle", "FINALE_comet"):
            without = compose_frame(base, [item for key, item in contributions.items() if key != cue_id])
            without_pixels = next(strip.pixels for strip in without.strips if strip.strip_id == TARGET)
            assert any(a != b for a, b in zip(full_pixels, without_pixels)), cue_id
    for timestamp in (110, 111, 112, 113):
        weights = [item.weight for item in captured[timestamp] if item.cue_id in {"FINALE_noise", "FINALE_twinkle", "FINALE_comet"}]
        assert len(weights) == 3
        assert weights[0] == pytest.approx(weights[1]) == pytest.approx(weights[2])
    for timestamp in (114, 115):
        assert not [item for item in captured.get(timestamp, ()) if item.cue_id.startswith("FINALE_")]
