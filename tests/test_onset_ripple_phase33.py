"""Focused Phase 33 contracts for the onset_ripple primitive."""

from __future__ import annotations

import pytest

from light_engine.effects.onset_ripple import (
    OnsetRippleEffect,
    validate_onset_ripple_params,
)
from light_engine.mapping import ZoneDef
from light_engine.mapping.virtual import build_virtual_paths
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import Cue, EffectSpec, TargetResolver, TargetSelector
from light_engine.show.compositor import CueRenderJob


def _ctx(
    time: float,
    *,
    audio: AudioFeatures | None,
    count: int = 12,
    seed_params: dict[str, object] | None = None,
    strip_defs: tuple[dict[str, object], ...] | None = None,
) -> EffectContext:
    params: dict[str, object] = {
        "cue_local_time": time,
        "strip_defs": strip_defs or ({"id": "path", "pixel_count": count},),
        "wave_speed_pps": 3.0,
        "wave_width_px": 1.2,
        "decay_seconds": 5.0,
        "color": [1.0, 1.0, 1.0],
    }
    params.update(seed_params or {})
    return EffectContext(
        timestamp=time,
        sequence=1,
        delta_time=0.1,
        audio_features=audio,
        mode_parameters=params,
    )


def _event(*, peak: bool = True, onset: float = 0.0) -> AudioFeatures:
    return AudioFeatures(
        timestamp=0.0,
        onset=onset,
        peak=peak,
        loudness=1.0,
        silence=False,
    )


def test_legacy_defaults_are_identical_to_explicit_options() -> None:
    audio = _event()
    implicit = OnsetRippleEffect(seed=7)
    explicit = OnsetRippleEffect(seed=7)
    implicit_frame = implicit.process(_ctx(0.0, audio=audio))
    explicit_frame = explicit.process(
        _ctx(
            0.0,
            audio=audio,
            seed_params={
                "event_origin": "fixed",
                "propagation": "one_way",
                "wrap": False,
            },
        )
    )
    assert implicit_frame.strips[0].pixels == explicit_frame.strips[0].pixels
    assert implicit._waves == explicit._waves
    assert implicit._waves[0].origin == 0.0


def test_random_origin_is_cue_seeded_and_replays_after_reset() -> None:
    params = {"event_origin": "random"}
    first = OnsetRippleEffect(seed=1234)
    replay = OnsetRippleEffect(seed=1234)
    first_frame = first.process(_ctx(0.0, audio=_event(), seed_params=params))
    replay_frame = replay.process(_ctx(0.0, audio=_event(), seed_params=params))
    assert first._waves[0].origin > 0.0
    assert first._waves[0].origin == replay._waves[0].origin
    assert first_frame.strips[0].pixels == replay_frame.strips[0].pixels
    first.reset()
    reset_frame = first.process(_ctx(0.0, audio=_event(), seed_params=params))
    assert reset_frame.strips[0].pixels == first_frame.strips[0].pixels


def test_random_origin_maps_to_every_independent_path_and_replays() -> None:
    paths = (
        {"id": "short", "pixel_count": 3},
        {"id": "long", "pixel_count": 10},
    )
    params = {"event_origin": "random"}
    effect = OnsetRippleEffect(seed=1)
    replay = OnsetRippleEffect(seed=1)

    frame = effect.process(
        _ctx(0.0, audio=_event(), seed_params=params, strip_defs=paths)
    )
    replay_frame = replay.process(
        _ctx(0.0, audio=_event(), seed_params=params, strip_defs=paths)
    )

    # A wave stores one relative event location, not an absolute pixel index
    # calculated from the longest selected strip.
    normalized_origin = effect._waves[0].origin
    assert 0.0 <= normalized_origin < 1.0
    assert all(0.0 <= normalized_origin * path["pixel_count"] < path["pixel_count"] for path in paths)
    assert all(any(max(pixel) > 0.0 for pixel in strip.pixels) for strip in frame.strips)
    assert frame.strips[0].strip_id == "short"
    assert frame.strips[1].strip_id == "long"
    assert frame.strips[0].pixels == replay_frame.strips[0].pixels
    assert frame.strips[1].pixels == replay_frame.strips[1].pixels


def test_random_origin_is_coherent_for_independent_equal_length_paths() -> None:
    frame = OnsetRippleEffect(seed=7).process(
        _ctx(
            0.0,
            audio=_event(),
            seed_params={"event_origin": "random"},
            strip_defs=(
                {"id": "left", "pixel_count": 6},
                {"id": "right", "pixel_count": 6},
            ),
        )
    )

    assert frame.strips[0].pixels == frame.strips[1].pixels


def test_bidirectional_propagation_reaches_both_sides_of_random_origin() -> None:
    params = {"event_origin": "random", "wave_speed_pps": 5.0}
    one_way = OnsetRippleEffect(seed=5)
    both = OnsetRippleEffect(seed=5)
    one_way.process(_ctx(0.0, audio=_event(), seed_params=params))
    both.process(
        _ctx(
            0.0,
            audio=_event(),
            seed_params={**params, "propagation": "bidirectional"},
        )
    )
    one_frame = one_way.process(_ctx(0.2, audio=None, seed_params=params))
    both_frame = both.process(
        _ctx(0.2, audio=None, seed_params={**params, "propagation": "bidirectional"})
    )
    assert both_frame.strips[0].pixels != one_frame.strips[0].pixels
    assert sum(max(pixel) > 0.0 for pixel in both_frame.strips[0].pixels) >= sum(
        max(pixel) > 0.0 for pixel in one_frame.strips[0].pixels
    )


def test_wrap_reaches_seam_after_front_leaves_end() -> None:
    params = {"wave_speed_pps": 6.0, "wave_width_px": 1.0}
    no_wrap = OnsetRippleEffect(seed=1)
    wrap = OnsetRippleEffect(seed=1)
    no_wrap.process(_ctx(0.0, audio=_event(), seed_params=params))
    wrap.process(_ctx(0.0, audio=_event(), seed_params={**params, "wrap": True}))
    no_wrap_frame = no_wrap.process(_ctx(2.0, audio=None, seed_params=params))
    wrap_frame = wrap.process(
        _ctx(2.0, audio=None, seed_params={**params, "wrap": True})
    )
    assert max(no_wrap_frame.strips[0].pixels[0]) == 0.0
    assert max(wrap_frame.strips[0].pixels[0]) > 0.0


def test_silence_and_stale_audio_do_not_birth_waves_but_active_wave_ages() -> None:
    effect = OnsetRippleEffect(seed=1)
    born = effect.process(_ctx(0.0, audio=_event()))
    effect.process(_ctx(0.25, audio=AudioFeatures(timestamp=0.25)))
    silent = effect.process(
        _ctx(
            0.5,
            audio=AudioFeatures(
                timestamp=0.5, onset=1.0, peak=True, loudness=1.0, silence=True
            ),
        )
    )
    assert len(effect._waves) == 1
    assert silent.strips[0].pixels != born.strips[0].pixels


def test_backward_seek_and_reset_replay_deterministically() -> None:
    params = {"event_origin": "random", "propagation": "bidirectional", "wrap": True}
    effect = OnsetRippleEffect(seed=99)
    effect.process(_ctx(1.0, audio=_event(), seed_params=params))
    backward = effect.process(_ctx(0.5, audio=_event(), seed_params=params))
    fresh = OnsetRippleEffect(seed=99).process(
        _ctx(0.5, audio=_event(), seed_params=params)
    )
    assert backward.strips[0].pixels == fresh.strips[0].pixels
    effect.reset()
    replay = effect.process(_ctx(0.5, audio=_event(), seed_params=params))
    assert replay.strips[0].pixels == fresh.strips[0].pixels


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("event_origin", "other"),
        ("propagation", "both"),
        ("wrap", 1),
    ],
)
def test_invalid_wave_options_fail_explicitly(key: str, value: object) -> None:
    with pytest.raises(ValueError):
        validate_onset_ripple_params({key: value})


def test_virtual_path_is_rendered_as_one_continuous_logical_strip() -> None:
    effect = OnsetRippleEffect(seed=3)
    frame = effect.process(
        _ctx(
            0.0,
            audio=_event(),
            count=10,
            seed_params={"event_origin": "random", "wrap": True},
        )
    )
    assert [strip.strip_id for strip in frame.strips] == ["path"]
    assert len(frame.strips[0].pixels) == 10


def _joined_path_job(*, origin: str = "start") -> CueRenderJob:
    strips = (ZoneDef(id="left", pixel_count=4), ZoneDef(id="right", pixel_count=4))
    path = build_virtual_paths(
        [
            {
                "id": "joined",
                "segments": [
                    {"strip_id": "left", "pixel_count": 4, "direction": "forward"},
                    {"strip_id": "right", "pixel_count": 4, "direction": "forward"},
                ],
            }
        ],
        {"left": 4, "right": 4},
    )[0]
    resolver = TargetResolver((), strips, virtual_paths=(path,))
    cue = Cue(
        id="ripple-joined",
        start=0.0,
        end=3.0,
        target=TargetSelector("virtual_path", id="joined"),
        effect=EffectSpec(
            mode="fixed",
            id="onset_ripple",
            params={
                "event_origin": "fixed",
                "propagation": "one_way",
                "wrap": False,
                "wave_speed_pps": 4.0,
                "wave_width_px": 1.5,
                "decay_seconds": 5.0,
                "color": [1.0, 1.0, 1.0],
            },
        ),
        origin=origin,
    )
    return CueRenderJob(cue, 0, resolver)


def _joined_event_context(time: float, *, event: bool) -> EffectContext:
    return EffectContext(
        timestamp=time,
        delta_time=1 / 60,
        sequence=9,
        audio_features=_event() if event else None,
    )


def test_real_virtual_path_ripple_crosses_member_seam_without_restart() -> None:
    job = _joined_path_job()
    job.render(_joined_event_context(0.0, event=True))
    contribution = job.render(_joined_event_context(1.0, event=False))

    assert [item.strip_id for item in contribution.digital] == ["left", "right"]
    left, right = contribution.digital
    # At t=1 the one-way front is exactly global coordinate 4, the member
    # boundary. Both adjacent centers therefore have the same authored gain.
    assert left.pixels[-1] == pytest.approx(right.pixels[0])
    assert max(left.pixels[-1]) > 0.0
    assert max(right.pixels[0]) > 0.0
    assert left.source_start == right.source_start == 0
    assert len(left.pixels) == len(right.pixels) == 4

    # Reassembling the two sparse contributions reproduces one renderer pass
    # over the complete eight-pixel logical path, rather than two four-pixel
    # passes whose local clocks would restart at the seam.
    reassembled = tuple(left.pixels + right.pixels)
    direct = OnsetRippleEffect(seed=17)
    direct_params = {
        "event_origin": "fixed",
        "propagation": "one_way",
        "wrap": False,
        "wave_speed_pps": 4.0,
        "wave_width_px": 1.5,
        "decay_seconds": 5.0,
        "color": [1.0, 1.0, 1.0],
    }
    direct.process(_ctx(0.0, audio=_event(), count=8, seed_params=direct_params))
    direct_frame = direct.process(
        _ctx(1.0, audio=None, count=8, seed_params=direct_params)
    )
    assert reassembled == tuple(direct_frame.strips[0].pixels)


def test_common_origin_remaps_once_after_event_origin_rendering() -> None:
    start_job = _joined_path_job(origin="start")
    end_job = _joined_path_job(origin="end")
    start_job.render(_joined_event_context(0.0, event=True))
    end_job.render(_joined_event_context(0.0, event=True))
    start = start_job.render(_joined_event_context(0.25, event=False))
    end = end_job.render(_joined_event_context(0.25, event=False))
    start_pixels = tuple(start.digital[0].pixels + start.digital[1].pixels)
    end_pixels = tuple(end.digital[0].pixels + end.digital[1].pixels)

    # event_origin remains fixed at logical start; only the compositor's
    # common origin reverses the completed continuous path.
    assert end_pixels == tuple(reversed(start_pixels))
