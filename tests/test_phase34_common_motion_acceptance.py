"""Cross-effect acceptance for the Phase 34 common motion-rate contract."""

from __future__ import annotations

import pytest

from light_engine.effects.chase import ChaseEffect
from light_engine.effects.color_wave import ColorWaveEffect
from light_engine.effects.comet import CometEffect
from light_engine.effects.heat_fire import HeatFireEffect
from light_engine.effects.history_stream import HistoryStreamEffect
from light_engine.effects.onset_ripple import OnsetRippleEffect
from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import Cue, CueRenderJob, EffectSpec, TargetResolver, TargetSelector


_SCHEDULE = (
    # normal, increase, sharp decrease, pause, resume
    (0.0, 1.0),
    (1.0, 1.0),
    (2.0, 2.0),
    (3.0, 0.25),
    (4.0, 0.0),
    (5.0, 1.0),
)
_MOTION = (0.0, 1.0, 3.0, 3.25, 3.25, 4.25)


def _job(effect_id: str, params: dict[str, object]) -> CueRenderJob:
    return CueRenderJob(
        Cue(
            id=f"phase34-{effect_id}",
            start=0.0,
            end=10.0,
            target=TargetSelector("digital_strip", id="strip"),
            effect=EffectSpec(mode="fixed", id=effect_id, params=params),
        ),
        0,
        TargetResolver((), (ZoneDef(id="strip", pixel_count=32),)),
    )


def _render_schedule(
    job: CueRenderJob,
    *,
    audio_event: bool = False,
):
    contributions = []
    for sequence, (timestamp, speed) in enumerate(_SCHEDULE, start=1):
        audio = None
        if audio_event:
            audio = AudioFeatures(
                timestamp=timestamp,
                peak=timestamp == 0.0,
                loudness=1.0 if timestamp == 0.0 else 0.0,
                silence=timestamp != 0.0,
            )
        contributions.append(
            job.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1 / 60 if timestamp == 0.0 else 1.0,
                    sequence=sequence,
                    speed=speed,
                    audio_features=audio,
                )
            )
        )
    return contributions


def _brightest_index(contribution) -> int:
    pixels = contribution.digital[0].pixels
    return max(range(len(pixels)), key=lambda index: max(pixels[index]))


@pytest.mark.parametrize(
    ("effect_id", "params", "extract", "expected"),
    [
        (
            "single_dot",
            {"speed": 1.0, "direction": "forward", "color": [1.0, 0.0, 0.0]},
            _brightest_index,
            (0, 1, 3, 3, 3, 4),
        ),
        (
            "flowing_bands",
            {
                "band_width_px": 1,
                "gap_width_px": 1,
                "base_gain": 0.1,
                "highlight_gain": 1.0,
                "steps_per_second": 1.0,
                "color": [1.0, 0.0, 0.0],
            },
            _brightest_index,
            (0, 0, 4, 4, 4, 6),
        ),
        (
            "color_wipe",
            {"speed": 1.0, "color": [1.0, 0.0, 0.0]},
            lambda contribution: sum(
                max(pixel) > 0.0 for pixel in contribution.digital[0].pixels
            ),
            (1, 2, 4, 4, 4, 5),
        ),
    ],
)
def test_piecewise_common_speed_changes_future_slope_for_simple_families(
    effect_id: str,
    params: dict[str, object],
    extract,
    expected: tuple[int, ...],
) -> None:
    values = tuple(extract(frame) for frame in _render_schedule(_job(effect_id, params)))
    assert values == expected
    assert values[3] == values[4]


def test_same_piecewise_schedule_drives_complex_families_from_one_motion_phase() -> None:
    history_job = _job(
        "history_stream",
        {"steps_per_second": 1.0, "color": [1.0, 0.0, 0.0]},
    )
    _render_schedule(history_job)
    assert isinstance(history_job.effect, HistoryStreamEffect)
    assert history_job.effect._last_steps["strip"] == 4

    heat_job = _job(
        "heat_fire",
        {
            "cooling_per_second": 0.0,
            "spark_rate": 0.0,
            "spark_strength": 0.0,
            "diffusion": 0.0,
        },
    )
    _render_schedule(heat_job)
    assert isinstance(heat_job.effect, HeatFireEffect)
    assert heat_job.effect._last_target_tick == int(_MOTION[-1] * heat_job.effect.STEP_HZ)

    ripple_job = _job(
        "onset_ripple",
        {
            "wave_speed_pps": 1.0,
            "wave_width_px": 1.0,
            "decay_seconds": 60.0,
            "color": [1.0, 0.0, 0.0],
        },
    )
    ripple_positions = tuple(
        _brightest_index(frame)
        for frame in _render_schedule(ripple_job, audio_event=True)
    )
    assert isinstance(ripple_job.effect, OnsetRippleEffect)
    assert ripple_positions == (0, 0, 2, 3, 3, 4)

    comet_job = _job(
        "comet",
        {
            "speed": 1.0,
            "tail_length": 0.0,
            "decay": 0.0,
            "count": 2,
            "phase_spacing": 0.0,
            "trajectory": "wrap",
            "color": [1.0, 0.0, 0.0],
        },
    )
    comet_positions = tuple(_brightest_index(frame) for frame in _render_schedule(comet_job))
    assert isinstance(comet_job.effect, CometEffect)
    assert comet_positions == (0, 1, 3, 3, 3, 4)


@pytest.mark.parametrize("effect", [ChaseEffect(), ColorWaveEffect(), CometEffect()])
def test_existing_delta_time_integrated_effects_keep_their_phase_contract(effect) -> None:
    params: dict[str, object]
    if isinstance(effect, ChaseEffect):
        params = {
            "speed": 1.0,
            "width": 1,
            "gap": 31,
            "direction": "forward",
            "trail": 0.0,
            "color_source": "static",
            "beat_boost": 0.0,
            "color": [1.0, 0.0, 0.0],
        }
    elif isinstance(effect, ColorWaveEffect):
        params = {"speed": 1.0, "width": 1.0, "hue_cycle_rate": 0.0}
    else:
        params = {
            "speed": 1.0,
            "tail_length": 0.4,
            "decay": 0.8,
            "color": [1.0, 0.0, 0.0],
        }

    phases = []
    for timestamp, speed in _SCHEDULE:
        effect.process(
            EffectContext(
                timestamp=timestamp,
                delta_time=1 / 60 if timestamp == 0.0 else 1.0,
                speed=speed,
                mode_parameters={
                    "cue_local_time": timestamp,
                    "strip_defs": ({"id": "strip", "pixel_count": 32},),
                    "zone_defs": (),
                    **params,
                },
            )
        )
        if isinstance(effect, ChaseEffect):
            phases.append(effect._position)
        elif isinstance(effect, ColorWaveEffect):
            phases.append(effect._phase)
        else:
            phases.append(effect._positions["strip"])

    expected = (1 / 60, 1 + 1 / 60, 3 + 1 / 60, 3.25 + 1 / 60, 3.25 + 1 / 60, 4.25 + 1 / 60)
    assert phases == pytest.approx(expected)
