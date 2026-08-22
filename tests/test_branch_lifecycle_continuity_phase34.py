"""Phase 34 pre-roll continuity across representative stateful effects."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from light_engine.effects import BaseEffect, create_effect
from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, EffectContext, PixelFrame
from light_engine.show import (
    Cue,
    CueBranchSpec,
    CueRenderJob,
    EffectSpec,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
)


_COLOR_TIMELINE = {
    "interpolation": "rgb_linear",
    "keyframes": (
        {"time": 0.0, "color": (1.0, 0.0, 0.0)},
        {"time": 1.0, "color": (0.0, 1.0, 0.0)},
        {"time": 2.0, "color": (0.0, 0.0, 1.0)},
    ),
}

_HISTORY_STREAM_PARAMS = {
    "steps_per_second": 2.0,
    "direction": "forward",
    "sample_gain_source": "audio.rms",
    "color_timeline": _COLOR_TIMELINE,
}


_EFFECT_CASES = (
    pytest.param(
        "chase",
        {
            "speed": 2.0,
            "width": 2,
            "gap": 3,
            "trail": 0.2,
            "color_source": "static",
            "color": (1.0, 0.25, 0.05),
        },
        True,
        id="chase",
    ),
    pytest.param(
        "color_wave",
        {"speed": 0.75, "width": 0.4, "hue_cycle_rate": 0.17},
        True,
        id="color-wave",
    ),
    pytest.param(
        "history_stream",
        _HISTORY_STREAM_PARAMS,
        True,
        id="history-stream-changing-color-and-live-audio",
    ),
    pytest.param(
        "twinkle",
        {
            "density": 1.25,
            "fade_time": 0.8,
            "color_source": "solid",
            "color": (0.3, 0.7, 1.0),
            # Opt into the cue-scoped replayable event stream.
            "event_width_px": 1.5,
            "event_gate_source": "audio.rms",
            "birth_gain_source": "audio.bass",
        },
        True,
        id="twinkle",
    ),
    pytest.param(
        "heat_fire",
        {
            "cooling_per_second": 0.3,
            "spark_rate": 60.0,
            "spark_strength": 0.8,
            "diffusion": 0.4,
            "spark_zone_px": 3,
            "color": (1.0, 0.35, 0.05),
        },
        False,
        id="heat-fire-fixed-step",
    ),
    pytest.param(
        "onset_ripple",
        {
            "onset_threshold": 0.35,
            "wave_speed_pps": 1.5,
            "wave_width_px": 3.0,
            "decay_seconds": 8.0,
            "event_origin": "random",
            "propagation": "bidirectional",
            "color": (1.0, 0.2, 0.05),
        },
        True,
        id="onset-ripple-hidden-audio-event",
    ),
    pytest.param(
        "comet",
        {
            "speed": 2.0,
            "tail_length": 0.5,
            "decay": 0.8,
            "count": 1,
            "trajectory": "wrap",
            # An authored color retains the legacy stateful path without
            # depending on process-global random hue selection.
            "color": (0.9, 0.25, 0.05),
        },
        True,
        id="legacy-comet",
    ),
)


class _RecordingEffect(BaseEffect):
    """Observe live inputs while delegating all state to the real effect."""

    def __init__(self, inner: BaseEffect) -> None:
        super().__init__(inner.name)
        self.inner = inner
        self.audio_history: list[AudioFeatures | None] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.audio_history.append(ctx.audio_features)
        return self.inner.process(ctx)

    def reset(self) -> None:
        self.inner.reset()
        self.audio_history.clear()


def _resolver() -> TargetResolver:
    resolver = TargetResolver(
        (),
        (
            ZoneDef(id="path_a", pixel_count=8),
            ZoneDef(id="path_b", pixel_count=8),
            ZoneDef(id="branch", pixel_count=8),
        ),
    )
    resolver.register_authored_paths(
        (
            VirtualPathSpec(
                id="release_path",
                targets=(
                    TargetSelector("digital_strip", id="path_a"),
                    TargetSelector("digital_strip", id="path_b"),
                ),
            ),
        )
    )
    return resolver


def _cue(effect_id: str, params: dict[str, Any]) -> Cue:
    return Cue(
        id="continuity",
        start=0.0,
        end=4.0,
        target=TargetSelector("virtual_path", id="release_path"),
        effect=EffectSpec(mode="fixed", id=effect_id, params=params),
        branches=(
            CueBranchSpec(
                path_id="release_path",
                after_target_id="path_a",
                target=TargetSelector("digital_strip", id="branch"),
                lifecycle="pre_roll",
            ),
        ),
    )


def _audio(timestamp: float, rms: float, *, peak: bool, onset: float) -> AudioFeatures:
    spectrum = (rms,) * 3 + (0.2,) * 7 + (1.0 - rms,) * 6
    return AudioFeatures(
        timestamp=timestamp,
        rms=rms,
        loudness=rms,
        bass=rms,
        mid=0.2,
        treble=1.0 - rms,
        spectral_flux=onset,
        onset=onset,
        peak=peak,
        spectrum=spectrum,
        silence=False,
    )


_SCHEDULE = (
    (0.0, 0.5, 0.10, False, 0.00),
    (0.5, 0.5, 0.80, True, 0.90),
    (1.0, 0.5, 0.35, False, 0.10),
    (1.5, 0.5, 0.65, True, 0.75),
    (2.0, 0.5, 0.20, False, 0.05),
)


def _contexts() -> tuple[EffectContext, ...]:
    return tuple(
        EffectContext(
            timestamp=timestamp,
            delta_time=delta_time,
            sequence=index,
            speed=1.0,
            audio_features=_audio(timestamp, rms, peak=peak, onset=onset),
        )
        for index, (timestamp, delta_time, rms, peak, onset) in enumerate(
            _SCHEDULE, start=1
        )
    )


def _recording_factory(created: list[_RecordingEffect]):
    def factory(name: str) -> _RecordingEffect:
        effect = _RecordingEffect(create_effect(name))
        created.append(effect)
        return effect

    return factory


def _build_jobs(effect_id: str, params: dict[str, Any]):
    resolver = _resolver()
    cue = _cue(effect_id, params)
    branch_effects: list[_RecordingEffect] = []
    reference_effects: list[_RecordingEffect] = []
    parent = CueRenderJob(
        cue,
        0,
        resolver,
        effect_factory=_recording_factory(branch_effects),
        cue_seed=700,
    )
    reference_cue = replace(
        cue,
        id="continuity:branch:0",
        target=TargetSelector("digital_strip", id="branch"),
        branches=(),
    )
    reference = CueRenderJob(
        reference_cue,
        1,
        resolver,
        effect_factory=_recording_factory(reference_effects),
        cue_seed=701,
    )
    return parent, reference, branch_effects, reference_effects


def _play(parent: CueRenderJob, reference: CueRenderJob):
    released = None
    continuous = None
    for index, ctx in enumerate(_contexts()):
        parent.render(ctx)
        branch_contributions = parent.render_branches(ctx)
        continuous = reference.render(ctx)
        if index < len(_SCHEDULE) - 1:
            assert branch_contributions == ()
        else:
            assert len(branch_contributions) == 1
            released = branch_contributions[0]
    assert released is not None
    assert continuous is not None
    return released, continuous


@pytest.mark.parametrize(
    ("effect_id", "params", "fresh_release_must_differ"),
    _EFFECT_CASES,
)
def test_pre_roll_release_matches_continuous_reference_and_replays(
    effect_id: str,
    params: dict[str, Any],
    fresh_release_must_differ: bool,
) -> None:
    parent, reference, branch_effects, _ = _build_jobs(effect_id, params)

    released, continuous = _play(parent, reference)

    assert released == continuous
    hidden_audio = branch_effects[1].audio_history[:-1]
    assert [audio.timestamp for audio in hidden_audio if audio is not None] == [
        0.0,
        0.5,
        1.0,
        1.5,
    ]
    assert [audio.rms for audio in hidden_audio if audio is not None] == pytest.approx(
        [0.10, 0.80, 0.35, 0.65]
    )

    # Reset must reconstruct both the branch's private seed/state and its
    # hidden live-input history, then reveal the same current release frame.
    parent.reset()
    reference.reset()
    replay_released, replay_continuous = _play(parent, reference)
    assert replay_released == released
    assert replay_continuous == continuous

    if fresh_release_must_differ:
        _, fresh, _, _ = _build_jobs(effect_id, params)
        fresh_release = fresh.render(_contexts()[-1])
        assert fresh_release != released


def test_history_stream_pre_roll_preserves_changing_authored_colors_and_live_gains() -> None:
    parent, reference, _, _ = _build_jobs(
        "history_stream", dict(_HISTORY_STREAM_PARAMS)
    )

    released, continuous = _play(parent, reference)

    assert released == continuous
    pixels = released.digital[0].pixels
    expected = (
        (0.0, 0.0, 0.20),
        (0.0, 0.325, 0.325),
        (0.0, 0.35, 0.0),
        (0.4, 0.4, 0.0),
        (0.10, 0.0, 0.0),
    )
    for actual, expected_pixel in zip(pixels[:5], expected):
        assert actual == pytest.approx(expected_pixel)
