"""Focused contracts for the three Phase 32 native effects."""

import pytest

from light_engine.effects import (
    create_effect,
    get_effect_registration,
    list_effects,
    validate_effect_params,
)
from light_engine.effects.heat_fire import HeatFireEffect
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector
from light_engine.show.compositor import CueRenderJob, _apply_origin


def context(effect_params=None, *, time=0.0, delta=1 / 60, audio=None, speed=1.0, intensity=1.0, length=8):
    return EffectContext(
        timestamp=time,
        delta_time=delta,
        sequence=7,
        audio_features=audio,
        speed=speed,
        intensity=intensity,
        mode_parameters={
            "strip_defs": [{"id": "path", "pixel_count": length}],
            "cue_local_time": time,
            **(effect_params or {}),
        },
    )


def levels(frame):
    return [pixel[0] for pixel in frame.strips[0].pixels]


def test_phase32_effects_remain_registered_after_phase33_catalog_extension():
    assert len(list_effects()) == 22
    assert {"flowing_bands", "onset_ripple", "heat_fire"} <= set(list_effects())
    assert "history_stream" in list_effects()
    for effect_id in ("flowing_bands", "onset_ripple", "heat_fire"):
        capability = get_effect_registration(effect_id).capability
        assert capability.common_params == ("color", "speed", "intensity")


@pytest.mark.parametrize(
    "effect_id,params",
    [
        ("flowing_bands", {"steps_per_second": float("nan")}),
        ("flowing_bands", {"phase_offset_steps": -1}),
        ("flowing_bands", {"base_gain": .8, "highlight_gain": .7}),
        ("onset_ripple", {"wave_width_px": 0.0}),
        ("onset_ripple", {"decay_seconds": float("inf")}),
        ("heat_fire", {"spark_rate": 61.0}),
        ("heat_fire", {"diffusion": float("nan")}),
        ("flowing_bands", {"color": [0.0, float("nan"), 0.0]}),
        ("onset_ripple", {"color": [0.0, 0.0, 2.0]}),
        ("heat_fire", {"color": [0.0, 1.0]}),
    ],
)
def test_new_effect_validators_reject_nonfinite_or_out_of_range(effect_id, params):
    with pytest.raises(ValueError):
        validate_effect_params(effect_id, params)


@pytest.mark.parametrize("effect_id", ["flowing_bands", "onset_ripple", "heat_fire"])
def test_registry_rejects_unknown_authored_keys(effect_id):
    with pytest.raises(ValueError, match="unknown effect parameters"):
        validate_effect_params(effect_id, {"wled_slot": 127})


@pytest.mark.parametrize(
    "time,expected",
    [
        (0.0, [.25, 0.0, .25, 0.0, .25, 0.0]),  # A B A B A B
        (1.0, [.75, 0.0, .25, 0.0, .25, 0.0]),  # C B A B A B
        (2.0, [.25, 0.0, .75, 0.0, .25, 0.0]),  # A B C B A B
        (3.0, [.25, 0.0, .25, 0.0, .75, 0.0]),  # A B A B C B
        (4.0, [.75, 0.0, .25, 0.0, .25, 0.0]),  # loop
    ],
)
def test_flowing_bands_product_golden_sequence(time, expected):
    frame = create_effect("flowing_bands").process(
        context(flowing_params(), time=time, length=6)
    )
    assert levels(frame) == pytest.approx(expected)
    assert frame.timestamp == time and frame.sequence == 7


def flowing_params(**overrides):
    params = {
        "band_width_px": 1,
        "gap_width_px": 1,
        "base_gain": .25,
        "highlight_gain": .75,
        "steps_per_second": 1.0,
        "direction": "forward",
        "phase_offset_steps": 0,
        "color": [1.0, 1.0, 1.0],
    }
    params.update(overrides)
    return params


def test_flowing_bands_registry_exposes_only_the_new_authored_contract():
    assert get_effect_registration("flowing_bands").parameter_keys == frozenset({
        "band_width_px", "gap_width_px", "base_gain", "highlight_gain",
        "steps_per_second", "direction", "phase_offset_steps", "color",
        "color_timeline",
    })
    for retired in (
        "speed_pps", "floor_gain", "crest_gain", "edge_softness",
        "phase_offset_cycles",
    ):
        with pytest.raises(ValueError, match="unknown effect parameters"):
            validate_effect_params("flowing_bands", {retired: 1})


def test_flowing_bands_reverse_wider_bands_and_partial_tail():
    reverse = create_effect("flowing_bands").process(
        context(flowing_params(direction="reverse"), time=1.0, length=6)
    )
    assert levels(reverse) == pytest.approx([.25, 0.0, .25, 0.0, .75, 0.0])

    wider = flowing_params(band_width_px=3, gap_width_px=2)
    first = create_effect("flowing_bands").process(context(wider, time=1.0, length=15))
    second = create_effect("flowing_bands").process(context(wider, time=2.0, length=15))
    partial = create_effect("flowing_bands").process(context(wider, time=3.0, length=12))
    assert levels(first) == pytest.approx(
        [.75, .75, .75, 0.0, 0.0, .25, .25, .25, 0.0, 0.0, .25, .25, .25, 0.0, 0.0]
    )
    assert levels(second) == pytest.approx(
        [.25, .25, .25, 0.0, 0.0, .75, .75, .75, 0.0, 0.0, .25, .25, .25, 0.0, 0.0]
    )
    assert levels(partial) == pytest.approx(
        [.25, .25, .25, 0.0, 0.0, .25, .25, .25, 0.0, 0.0, .75, .75]
    )


def test_flowing_bands_phase_offset_and_common_controls_are_deterministic():
    effect = create_effect("flowing_bands")
    params = flowing_params(color=[1.0, .5, .25])
    direct = effect.process(context(params, time=2.0, speed=.5, intensity=.5, length=6))
    replay = effect.process(context(params, time=2.0, speed=.5, intensity=.5, length=6))
    fast = effect.process(context(params, time=2.0, speed=1.0, intensity=1.0, length=6))
    offset = effect.process(
        context(flowing_params(phase_offset_steps=2), time=0.0, length=6)
    )
    assert direct.strips[0].pixels == replay.strips[0].pixels
    assert direct.strips[0].pixels != fast.strips[0].pixels
    assert levels(direct) == pytest.approx([.375, 0.0, .125, 0.0, .125, 0.0])
    assert levels(offset) == pytest.approx([.25, 0.0, .75, 0.0, .25, 0.0])
    saturated = effect.process(context(params, time=2.0, intensity=10.0, length=6))
    assert saturated.all_pixels_valid()


def test_flowing_bands_virtual_path_seam_does_not_restart_pattern_or_highlight():
    strips = (ZoneDef(id="left", pixel_count=3), ZoneDef(id="right", pixel_count=3))
    path = build_virtual_paths(
        [{
            "id": "joined",
            "segments": [
                {"strip_id": "left", "pixel_count": 3, "direction": "forward"},
                {"strip_id": "right", "pixel_count": 3, "direction": "forward"},
            ],
        }],
        {"left": 3, "right": 3},
    )[0]
    resolver = TargetResolver((), strips, virtual_paths=(path,))
    cue = Cue(
        id="continuous-bands",
        start=0.0,
        end=5.0,
        target=TargetSelector("virtual_path", id="joined"),
        effect=EffectSpec(mode="fixed", id="flowing_bands", params=flowing_params()),
    )
    contribution = CueRenderJob(cue, 0, resolver).render(
        EffectContext(timestamp=2.0, delta_time=1 / 60, sequence=7)
    )

    assert [pixel[0] for pixel in contribution.digital[0].pixels] == pytest.approx(
        [.25, 0.0, .75]
    )
    assert [pixel[0] for pixel in contribution.digital[1].pixels] == pytest.approx(
        [0.0, .25, 0.0]
    )


def test_flowing_bands_consumes_resolved_color_timeline():
    timeline = {
        "interpolation": "rgb_linear",
        "keyframes": (
            {"time": 0.0, "color": (1.0, 0.0, 0.0)},
            {"time": 2.0, "color": (0.0, 0.0, 1.0)},
        ),
    }
    cue = Cue(
        id="timeline-bands",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip"),
        effect=EffectSpec(
            mode="fixed",
            id="flowing_bands",
            params=flowing_params(steps_per_second=0.0, color_timeline=timeline),
        ),
    )
    contribution = CueRenderJob(
        cue,
        0,
        TargetResolver((), (ZoneDef(id="strip", pixel_count=2),)),
    ).render(EffectContext(timestamp=1.0, delta_time=1 / 60, sequence=7))

    assert contribution.digital[0].pixels[0] == pytest.approx((.125, 0.0, .125))
    assert contribution.digital[0].pixels[1] == (0.0, 0.0, 0.0)


def audio(*, loudness=.5, bass=.4, high=.3, onset=.8, peak=False, silence=False):
    spectrum = (bass,) * 3 + (0.2,) * 7 + (high,) * 6
    return AudioFeatures(
        timestamp=0.0,
        loudness=loudness,
        spectrum=spectrum,
        onset=onset,
        peak=peak,
        silence=silence,
    )


def ripple_frame(features):
    params = {"wave_speed_pps": 0.0, "wave_width_px": 3.0, "color": [1.0, 1.0, 1.0]}
    return create_effect("onset_ripple").process(context(params, audio=features))


def test_onset_ripple_generic_audio_dimensions_change_final_frame():
    baseline = ripple_frame(audio())
    variants = [
        ripple_frame(audio(silence=True)),
        ripple_frame(audio(bass=.9)),
        ripple_frame(audio(high=.9)),
        ripple_frame(audio(onset=.5)),
        ripple_frame(audio(peak=True)),
    ]
    assert all(frame.strips[0].pixels != baseline.strips[0].pixels for frame in variants)


def test_onset_ripple_only_births_on_upward_edges_and_evicts_oldest_at_sixteen():
    effect = create_effect("onset_ripple")
    high = audio(onset=.8)
    low = audio(onset=.0)
    effect.process(context(audio=high, time=0.0))
    effect.process(context(audio=high, time=.01))
    assert len(effect._waves) == 1
    for index in range(20):
        effect.process(context(audio=low, time=1 + index * .02))
        effect.process(context(audio=high, time=1.01 + index * .02))
    assert len(effect._waves) == 16
    births = [wave.born for wave in effect._waves]
    assert births == sorted(births) and births[0] > 1.0


def test_onset_ripple_origin_is_owned_by_compositor():
    start = ripple_frame(audio(peak=True))
    centered = _apply_origin(start, "center")
    assert max(levels(start)) == pytest.approx(levels(start)[0])
    assert levels(centered) != levels(start)
    assert levels(centered) == pytest.approx(list(reversed(levels(centered))))


def fire_context(time, *, delta, length=12):
    return context(
        {
            "cooling_per_second": .4,
            "spark_rate": 60.0,
            "spark_strength": .8,
            "diffusion": .45,
            "spark_zone_px": 3,
            "color": [1.0, .4, .1],
        },
        time=time,
        delta=delta,
        length=length,
    )


def test_heat_fire_fixed_step_is_equivalent_at_30_and_60_fps():
    at_30 = HeatFireEffect(seed=123)
    at_60 = HeatFireEffect(seed=123)
    frame_30 = frame_60 = None
    for tick in range(1, 31):
        frame_30 = at_30.process(fire_context(tick / 30, delta=1 / 30))
    for tick in range(1, 61):
        frame_60 = at_60.process(fire_context(tick / 60, delta=1 / 60))
    assert frame_30.strips[0].pixels == pytest.approx(frame_60.strips[0].pixels)


def test_heat_fire_backward_seek_reset_and_replay_are_deterministic():
    effect = HeatFireEffect(seed=456)
    effect.process(fire_context(2.0, delta=2.0))
    backward = effect.process(fire_context(1.0, delta=1.0))
    fresh = HeatFireEffect(seed=456).process(fire_context(1.0, delta=1.0))
    assert backward.strips[0].pixels == pytest.approx(fresh.strips[0].pixels)
    effect.reset()
    replay = effect.process(fire_context(1.0, delta=1.0))
    assert replay.strips[0].pixels == pytest.approx(fresh.strips[0].pixels)


def test_heat_fire_reconstructs_variable_length_state_without_invalid_pixels():
    effect = HeatFireEffect(seed=789)
    effect.process(fire_context(.5, delta=.5, length=3))
    resized = effect.process(fire_context(1.0, delta=.5, length=17))
    assert len(resized.strips[0].pixels) == 17
    assert resized.all_pixels_valid()
