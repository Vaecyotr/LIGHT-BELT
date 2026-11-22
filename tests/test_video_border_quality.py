import numpy as np
import pytest

from light_engine.analysis.video import VideoAnalyzer
from light_engine.config import Config


def test_dark_content_contributes_to_average():
    analyzer = VideoAnalyzer(Config())
    frame = np.zeros((90, 160, 3), dtype=np.uint8)
    frame[:, :80, 2] = 200
    mask = analyzer._black_border_mask(frame)
    assert analyzer._average_color(frame, mask) == pytest.approx((100 / 255, 0, 0))


def test_black_bars_are_excluded_but_content_edges_are_preserved():
    analyzer = VideoAnalyzer(Config())
    frame = np.full((90, 160, 3), (40, 80, 120), dtype=np.uint8)
    frame[:9] = 0
    frame[-9:] = 0
    mask = analyzer._black_border_mask(frame)
    assert analyzer._average_color(frame, mask) == pytest.approx((120 / 255, 80 / 255, 40 / 255), abs=1e-5)
    assert mask[9:-9].all()
    assert not mask[:9].any()


def test_dark_uniform_scene_is_not_mistaken_for_borders():
    analyzer = VideoAnalyzer(Config())
    frame = np.full((90, 160, 3), (3, 5, 8), dtype=np.uint8)
    mask = analyzer._black_border_mask(frame)
    assert mask.all()
    assert analyzer._average_color(frame, mask) == pytest.approx((8 / 255, 5 / 255, 3 / 255), abs=1e-5)


def test_dominant_color_preserves_actual_pixel_values():
    analyzer = VideoAnalyzer(Config())
    frame = np.full((90, 160, 3), (23, 55, 201), dtype=np.uint8)
    assert analyzer._dominant_color(frame, np.ones((90, 160), dtype=bool)) == pytest.approx(
        (201 / 255, 55 / 255, 23 / 255)
    )


def test_subtitle_does_not_override_dominant_picture_color():
    analyzer = VideoAnalyzer(Config())
    frame = np.full((90, 160, 3), (160, 70, 20), dtype=np.uint8)
    frame[70:75, 40:120] = 255
    dominant = analyzer._dominant_color(frame, analyzer._black_border_mask(frame))
    assert dominant == pytest.approx((20 / 255, 70 / 255, 160 / 255))


def test_pixel_difference_alone_does_not_distinguish_cut_and_motion():
    cut = VideoAnalyzer(Config())
    red = np.full((90, 160, 3), (0, 0, 255), dtype=np.uint8)
    green = np.full((90, 160, 3), (0, 130, 0), dtype=np.uint8)
    cut.analyze(red, 0.0)
    after_cut = cut.analyze(green, 0.1)
    cut_strength = after_cut.scene_change
    assert after_cut.average_rgb == pytest.approx((0, 130/255, 0))

    motion = VideoAnalyzer(Config())
    stripes = np.zeros((90, 160, 3), dtype=np.uint8)
    stripes[:, ::2] = 255
    motion.analyze(stripes, 0.0)
    motion_strength = motion.analyze(np.roll(stripes, 1, axis=1), 0.1).scene_change
    assert cut_strength > 0.4
    assert motion_strength > cut_strength


def test_active_picture_brightness_is_independent_of_letterbox():
    full = np.full((90, 160, 3), (30, 90, 170), dtype=np.uint8)
    boxed = full.copy()
    boxed[:9] = boxed[-9:] = 0
    a = VideoAnalyzer(Config()).analyze(full, 0)
    b = VideoAnalyzer(Config()).analyze(boxed, 0)
    assert (b.brightness, b.saturation) == pytest.approx((a.brightness, a.saturation))
