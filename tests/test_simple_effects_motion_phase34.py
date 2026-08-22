"""Phase 34 contracts for simple time-driven effects."""

from __future__ import annotations

import pytest

from light_engine.effects import create_effect
from light_engine.mapping import ZoneDef
from light_engine.models import EffectContext
from light_engine.motion import CueMotionClock
from light_engine.show import Cue, CueRenderJob, EffectSpec, TargetResolver, TargetSelector, VirtualPathSpec


_EFFECT_PARAMS = {
    "single_dot": {"speed": 1.0, "direction": "forward", "color": [1.0, 0.0, 0.0]},
    "theater_phase": {"speed": 1.0, "color": [1.0, 0.0, 0.0]},
    "flowing_bands": {
        "band_width_px": 1,
        "gap_width_px": 1,
        "base_gain": 0.25,
        "highlight_gain": 0.75,
        "steps_per_second": 1.0,
        "direction": "forward",
        "phase_offset_steps": 0,
        "color": [1.0, 0.0, 0.0],
    },
    "color_wipe": {"speed": 1.0, "color": [1.0, 0.0, 0.0]},
}


def _context(
    effect_id: str,
    *,
    cue_time: float,
    common_speed: float = 1.0,
    motion=None,
    length: int = 64,
) -> EffectContext:
    return EffectContext(
        timestamp=cue_time,
        delta_time=1 / 60,
        speed=common_speed,
        mode_parameters={
            **_EFFECT_PARAMS[effect_id],
            "cue_local_time": cue_time,
            "strip_defs": [{"id": "strip", "pixel_count": length}],
            "zone_defs": [],
        },
        motion=motion,
    )


def _pixels(effect_id: str, ctx: EffectContext):
    return create_effect(effect_id).process(ctx).strips[0].pixels


@pytest.mark.parametrize("effect_id", tuple(_EFFECT_PARAMS))
def test_constant_speed_motion_matches_phase33_legacy_golden(effect_id: str) -> None:
    """A constant common speed produces the exact pre-Phase-34 frame."""

    clock = CueMotionClock()
    motion = clock.advance(1.5, 2.0)

    moved = _pixels(
        effect_id,
        _context(effect_id, cue_time=1.5, common_speed=2.0, motion=motion),
    )
    legacy = _pixels(effect_id, _context(effect_id, cue_time=1.5, common_speed=2.0))

    assert moved == legacy
    red = (1.0, 0.0, 0.0)
    if effect_id == "single_dot":
        assert moved.count(red) == 1
        assert moved.index(red) == 3
    elif effect_id == "theater_phase":
        assert [index for index, pixel in enumerate(moved) if pixel == red] == list(
            range(0, 64, 3)
        )
    elif effect_id == "flowing_bands":
        assert [pixel[0] for pixel in moved[:6]] == pytest.approx(
            [0.25, 0.0, 0.25, 0.0, 0.75, 0.0]
        )
    else:
        assert moved[:4] == [red] * 4
        assert moved[4:] == [(0.0, 0.0, 0.0)] * 60


@pytest.mark.parametrize("effect_id", tuple(_EFFECT_PARAMS))
def test_speed_down_and_up_advance_from_integrated_phase_without_teleport(effect_id: str) -> None:
    clock = CueMotionClock()
    samples = ((0.0, 1.0), (1.0, 1.0), (2.0, 0.25), (3.0, 2.0), (4.0, 1.0))

    for cue_time, common_speed in samples:
        motion = clock.advance(cue_time, common_speed)
        actual = _pixels(
            effect_id,
            _context(
                effect_id,
                cue_time=cue_time,
                common_speed=common_speed,
                motion=motion,
            ),
        )
        expected = _pixels(effect_id, _context(effect_id, cue_time=motion.motion_time))
        assert actual == expected

    assert clock.current is not None
    assert clock.current.motion_time == pytest.approx(4.25)


@pytest.mark.parametrize("effect_id", tuple(_EFFECT_PARAMS))
def test_zero_speed_pause_and_resume_hold_the_same_phase(effect_id: str) -> None:
    clock = CueMotionClock()
    rendered = []
    for cue_time, common_speed in ((0.0, 1.0), (1.0, 1.0), (2.0, 0.0), (4.0, 0.0), (5.0, 1.0)):
        motion = clock.advance(cue_time, common_speed)
        rendered.append(
            _pixels(
                effect_id,
                _context(
                    effect_id,
                    cue_time=cue_time,
                    common_speed=common_speed,
                    motion=motion,
                ),
            )
        )

    assert rendered[1] == rendered[2] == rendered[3]
    assert rendered[-1] == _pixels(effect_id, _context(effect_id, cue_time=2.0))


@pytest.mark.parametrize("effect_id", tuple(_EFFECT_PARAMS))
def test_motion_frames_are_equivalent_at_30_and_60_fps(effect_id: str) -> None:
    def render_at(fps: int):
        clock = CueMotionClock()
        frame = None
        for step in range(fps + 1):
            cue_time = step / fps
            motion = clock.advance(cue_time, 1.5)
            frame = _pixels(
                effect_id,
                _context(
                    effect_id,
                    cue_time=cue_time,
                    common_speed=1.5,
                    motion=motion,
                ),
            )
        return frame

    assert render_at(30) == render_at(60)


def test_time_driven_color_wipe_keeps_compositor_owned_origin_across_virtual_path() -> None:
    path = VirtualPathSpec(
        id="joined",
        targets=(
            TargetSelector("digital_strip", id="a"),
            TargetSelector("digital_strip", id="b"),
        ),
    )
    resolver = TargetResolver((), (ZoneDef(id="a", pixel_count=2), ZoneDef(id="b", pixel_count=3)))
    resolver.register_authored_paths((path,))
    cue = Cue(
        id="wipe",
        start=0.0,
        end=10.0,
        target=TargetSelector("virtual_path", id="joined"),
        origin="end",
        effect=EffectSpec(mode="fixed", id="color_wipe", params=_EFFECT_PARAMS["color_wipe"]),
    )
    job = CueRenderJob(cue, 0, resolver)

    job.render(EffectContext(timestamp=0.0, delta_time=1 / 60, speed=1.0))
    job.render(EffectContext(timestamp=1.0, delta_time=1 / 60, speed=2.0))
    contribution = job.render(EffectContext(timestamp=2.0, delta_time=1 / 60, speed=0.5))

    # Motion is 2.5 seconds: three path pixels are lit, then compositor-owned
    # ``origin=end`` flips that continuous virtual-path result exactly once.
    assert contribution.digital[0].pixels == ((0.0, 0.0, 0.0),) * 2
    assert contribution.digital[1].pixels == ((1.0, 0.0, 0.0),) * 3
