"""Phase 36 bounded parameter extensions and WLED closure contracts."""

from __future__ import annotations

import colorsys

import pytest

from light_engine.effects import create_effect, get_effect_registration, list_effects
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import EffectContext
from light_engine.show import Cue, CueRenderJob, EffectSpec, TargetResolver, TargetSelector


def _context(**params) -> EffectContext:
    return EffectContext(
        timestamp=1.0,
        delta_time=1.0 / 60.0,
        sequence=36,
        mode_parameters={
            "cue_local_time": 1.0,
            "strip_defs": [{"id": "strip", "pixel_count": 8}],
            **params,
        },
    )


def _pixels(effect_id: str, **params):
    return create_effect(effect_id).process(_context(**params)).strips[0].pixels


def test_step_pulse_default_is_exactly_the_historical_half_period_gate() -> None:
    omitted = _pixels("step_pulse", period=4.0, cue_local_time=1.99)
    explicit = _pixels("step_pulse", period=4.0, duty_cycle=0.5, cue_local_time=1.99)
    assert omitted == explicit
    assert _pixels("step_pulse", period=4.0, duty_cycle=0.25, cue_local_time=2.99) != _pixels(
        "step_pulse", period=4.0, duty_cycle=0.25, cue_local_time=3.0
    )


def test_step_pulse_duty_cycle_is_the_high_fraction_with_low_first_phase() -> None:
    low = (0.125, 0.03125, 0.0)
    high = (0.125, 0.0625, 0.0)
    assert _pixels("step_pulse", duty_cycle=0.0, cue_local_time=3.9) == [low] * 8
    assert _pixels("step_pulse", duty_cycle=1.0, cue_local_time=0.0) == [high] * 8


@pytest.mark.parametrize(
    ("waveform", "expected"),
    [("sine", 1.0), ("triangle", 1.0), ("smoothstep", 1.0)],
)
def test_breath_waveforms_share_the_peak_and_default_sine_is_compatible(
    waveform: str,
    expected: float,
) -> None:
    params = dict(period=4.0, min_brightness=0.0, color=[1.0, 0.0, 0.0], cue_local_time=1.0)
    assert _pixels("breath", waveform=waveform, **params)[0][0] == pytest.approx(expected)
    if waveform == "sine":
        assert _pixels("breath", **params) == _pixels("breath", waveform="sine", **params)


def test_breath_triangle_and_smoothstep_have_distinct_bounded_shoulders() -> None:
    params = dict(period=4.0, min_brightness=0.0, color=[1.0, 0.0, 0.0], cue_local_time=0.5)
    triangle = _pixels("breath", waveform="triangle", **params)[0][0]
    smoothstep = _pixels("breath", waveform="smoothstep", **params)[0][0]
    assert triangle == pytest.approx(0.75)
    assert smoothstep == pytest.approx(0.84375)


def test_color_wipe_defaults_remain_hard_and_linear() -> None:
    params = dict(speed=2.0, color=[1.0, 0.0, 0.0], cue_local_time=1.0)
    omitted = _pixels("color_wipe", **params)
    explicit = _pixels(
        "color_wipe",
        edge_softness_px=0.0,
        progress_curve="linear",
        **params,
    )
    assert omitted == explicit == [(1.0, 0.0, 0.0)] * 3 + [(0.0, 0.0, 0.0)] * 5


def test_color_wipe_soft_edge_and_smoothstep_curve_are_reusable_geometry_controls() -> None:
    soft = _pixels(
        "color_wipe",
        progress_source="cue_progress",
        cue_progress=0.5,
        edge_softness_px=2.0,
        color=[1.0, 0.0, 0.0],
    )
    assert [pixel[0] for pixel in soft] == pytest.approx([1.0, 1.0, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0])

    linear = _pixels(
        "color_wipe",
        progress_source="cue_progress",
        cue_progress=0.25,
        progress_curve="linear",
    )
    eased = _pixels(
        "color_wipe",
        progress_source="cue_progress",
        cue_progress=0.25,
        progress_curve="smoothstep",
    )
    assert sum(pixel != (0.0, 0.0, 0.0) for pixel in linear) == 2
    assert sum(pixel != (0.0, 0.0, 0.0) for pixel in eased) == 1


def test_color_wave_linear_120_degree_defaults_reproduce_historical_formula() -> None:
    params = dict(speed=0.0, width=0.5, hue_cycle_rate=0.0)
    omitted = _pixels("color_wave", **params)
    explicit = _pixels(
        "color_wave",
        waveform="linear",
        hue_span_degrees=120.0,
        **params,
    )
    expected = [colorsys.hsv_to_rgb(((index / 8) / 0.5 * 120.0) / 360.0, 1.0, 1.0) for index in range(8)]
    assert omitted == explicit
    assert omitted == pytest.approx(expected)


@pytest.mark.parametrize("waveform", ["sine", "triangle", "saw"])
def test_color_wave_non_default_waveforms_are_bounded_and_distinct(waveform: str) -> None:
    linear = _pixels("color_wave", speed=0.0, width=0.5, hue_cycle_rate=0.0)
    shaped = _pixels(
        "color_wave",
        speed=0.0,
        width=0.5,
        hue_cycle_rate=0.0,
        waveform=waveform,
        hue_span_degrees=180.0,
    )
    assert shaped != pytest.approx(linear)
    assert all(0.0 <= channel <= 1.0 for pixel in shaped for channel in pixel)


@pytest.mark.parametrize(
    ("effect_id", "params", "message"),
    [
        ("step_pulse", {"duty_cycle": -0.01}, "duty_cycle"),
        ("step_pulse", {"duty_cycle": float("nan")}, "duty_cycle"),
        ("breath", {"waveform": "square"}, "waveform"),
        ("breath", {"waveform": []}, "waveform"),
        ("color_wipe", {"edge_softness_px": -1.0}, "edge_softness_px"),
        ("color_wipe", {"progress_curve": "cubic"}, "progress_curve"),
        ("color_wipe", {"progress_curve": []}, "progress_curve"),
        ("color_wave", {"waveform": "noise"}, "waveform"),
        ("color_wave", {"hue_span_degrees": 361.0}, "hue_span_degrees"),
        ("color_wave", {"hue_span_degrees": float("inf")}, "hue_span_degrees"),
    ],
)
def test_phase36_validators_reject_invalid_authored_values(effect_id, params, message) -> None:
    with pytest.raises(ValueError, match=message):
        get_effect_registration(effect_id).validator(params)


def test_phase36_registry_adds_parameters_without_effect_aliases() -> None:
    assert len(list_effects()) == 22
    assert "duty_cycle" in get_effect_registration("step_pulse").parameter_keys
    assert "waveform" in get_effect_registration("breath").parameter_keys
    assert get_effect_registration("color_wipe").parameter_keys >= {
        "edge_softness_px",
        "progress_curve",
    }
    assert get_effect_registration("color_wave").parameter_keys >= {
        "waveform",
        "hue_span_degrees",
    }


def test_soft_wipe_renders_one_virtual_path_before_common_origin_transform() -> None:
    path = build_virtual_paths(
        [
            {
                "id": "joined",
                "segments": [
                    {"strip_id": "left", "pixel_count": 3, "direction": "forward"},
                    {"strip_id": "right", "pixel_count": 5, "direction": "forward"},
                ],
            }
        ],
        {"left": 3, "right": 5},
    )[0]
    resolver = TargetResolver(
        (),
        (ZoneDef("left", pixel_count=3), ZoneDef("right", pixel_count=5)),
        virtual_paths=(path,),
    )
    base = dict(
        id="soft-wipe",
        start=0.0,
        end=10.0,
        target=TargetSelector("virtual_path", id="joined"),
        effect=EffectSpec(
            mode="fixed",
            id="color_wipe",
            params={
                "progress_source": "cue_progress",
                "edge_softness_px": 2.0,
                "color": [1.0, 0.0, 0.0],
            },
        ),
    )
    context = EffectContext(timestamp=5.0, delta_time=1.0 / 60.0, sequence=36)
    start = CueRenderJob(Cue(**base, origin="start"), 0, resolver).render(context)
    end = CueRenderJob(Cue(**base, origin="end"), 0, resolver).render(context)
    start_pixels = tuple(pixel for strip in start.digital for pixel in strip.pixels)
    end_pixels = tuple(pixel for strip in end.digital for pixel in strip.pixels)
    assert [pixel[0] for pixel in start_pixels] == pytest.approx(
        [1.0, 1.0, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0]
    )
    assert end_pixels == tuple(reversed(start_pixels))
