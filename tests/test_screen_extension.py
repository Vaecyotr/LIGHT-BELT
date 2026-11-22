from pathlib import Path

import numpy as np
import pytest

from light_engine.analysis.video import VideoAnalyzer
from light_engine.cli import _configure_engine_show
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.effects import create_effect
from light_engine.models import AudioFeatures, EffectContext, MusicControlState, VideoFeatures
from light_engine.show.compositor import black_base_frame


def _mapped(image, rms):
    config = Config.get_instance(Path("config/profiles/rk3588-host-service.yaml"))
    engine = Engine(config)
    _configure_engine_show(engine, "config/examples/regional-av-preview.yaml")
    video = VideoAnalyzer(config).analyze(image, 1)
    ctx = EffectContext(
        timestamp=1, delta_time=1, sequence=1, video_features=video,
        audio_features=AudioFeatures(timestamp=1, rms=rms, silence=rms == 0),
        music_control_state=MusicControlState(timestamp=1),
        mode_parameters={"strip_defs": engine._strip_defs, "zone_defs": engine._zone_defs},
    )
    base = black_base_frame(timestamp=1, sequence=1, analog_zones=engine._layout.zones,
                            digital_strips=engine._layout.strips)
    logical = engine._show_runtime.render(ctx, base)
    physical = engine._physical_mapping.map(engine._output_transform.apply_to_frame(logical))
    return {strip.strip_id: np.asarray(strip.pixels)
            for node in physical.digital_frames for strip in node.outputs}


def test_all_nine_strips_follow_local_edge_positions_and_sound_only_adds_light():
    # Four independent light patches; gaps are dark within each single strip.
    image = np.zeros((90, 160, 3), dtype=np.uint8)
    image[:15, 64:80] = (20, 100, 230)
    image[-15:, 96:112] = (120, 50, 10)
    image[18:27, :20] = (30, 155, 40)
    image[54:63, -20:] = (110, 25, 60)
    silent, sounding = _mapped(image, 0), _mapped(image, 0.8)
    peak_interval = {"strip_11": (0.4, 0.5), "strip_12": (0.4, 0.5),
                     "strip_21": (0.6, 0.7), "strip_22": (0.6, 0.7),
                     "strip_31": (0.2, 0.3), "strip_32": (0.2, 0.3),
                     "strip_41": (0.6, 0.7), "strip_43": (0.6, 0.7),
                     "strip_44": (0.6, 0.7)}
    assert silent.keys() == sounding.keys() == peak_interval.keys()
    for sid, pixels in silent.items():
        n = len(pixels)
        peak = int(np.argmax(pixels.max(axis=1)))
        low, high = peak_interval[sid]
        assert low - 0.5/n <= (peak + 0.5)/n <= high + 0.5/n
        dark = pixels.max(axis=1) == 0
        assert np.any(dark) and np.all(sounding[sid][dark] == 0)
        assert np.all(sounding[sid] >= pixels)
        assert sounding[sid][peak].max() > pixels[peak].max()
        np.testing.assert_allclose(sounding[sid][peak] / sounding[sid][peak].max(),
                                   pixels[peak] / pixels[peak].max(), atol=1e-6)


def test_letterbox_does_not_dim_edge_groups_of_a_dark_colored_picture():
    image = np.full((90, 160, 3), (36, 16, 4), dtype=np.uint8)
    image[:9] = image[-9:] = 0
    features = VideoAnalyzer(Config()).analyze(image, 0)
    for colors in features.edge_profiles.values():
        np.testing.assert_allclose(np.asarray(colors) * 255, np.tile([4, 16, 36], (len(colors), 1)),
                                   atol=1e-3)


@pytest.mark.parametrize("effect_id", ["video_ambient", "video_audio_fusion"])
def test_edge_profile_respects_reversed_logical_strip_direction(effect_id):
    profile = ((0.6, 0.1, 0.1), (0.2, 0.2, 0.2), (0.1, 0.1, 0.6))
    video = VideoFeatures(0, (0, 0, 0), (0, 0, 0), edge_profiles={"left": profile})
    strips = [{"id": d, "direction": d, "pixel_count": 3, "video_zone": "left"}
              for d in ("forward", "reverse")]
    ctx = EffectContext(timestamp=0, delta_time=1.0, video_features=video,
                        mode_parameters={"strip_defs": strips})
    forward, reverse = create_effect(effect_id).process(ctx).strips
    assert forward.pixels[0][0] > forward.pixels[0][2]
    assert forward.pixels[-1][2] > forward.pixels[-1][0]
    np.testing.assert_allclose(reverse.pixels, forward.pixels[::-1])
