"""Contracts for the exploratory two-node capability-boundary Show."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import random

import yaml

from light_engine.config import Config
from light_engine.data.generators import SyntheticDataSource
from light_engine.effects import list_effects
from light_engine.mapping import Layout
from light_engine.models import EffectContext
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


SHOW = Path("config/shows/ws2811-two-node-capability-boundary-272s.yaml")
PROFILES = {
    5.0: Path("config/profiles/ws2811-ab-two-node-41-42-immediate-5fps.yaml"),
    15.0: Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml"),
    30.0: Path("config/profiles/ws2811-ab-two-node-41-42-immediate-30fps.yaml"),
}
RELAY_PREFIX = "relay-"


def _load(profile: Path):
    Config.reset()
    config = Config.get_instance(profile)
    layout = Layout.from_config(config)
    show = load_show(SHOW, TargetCatalog.from_layout(layout))
    return config, layout, show


def _signature(frame) -> tuple[float, ...]:
    strips = {strip.strip_id: strip for strip in frame.strips}
    return tuple(
        round(channel, 4)
        for strip_id in ("strip_41", "strip_42")
        for pixel in strips[strip_id].pixels
        for channel in pixel
    )


def test_frequency_profiles_change_only_output_fps() -> None:
    normalized = []
    for expected_fps, path in PROFILES.items():
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data["system"]["output_fps"] == expected_fps
        copy = deepcopy(data)
        copy["system"]["output_fps"] = "cadence-under-test"
        normalized.append(copy)

    assert normalized[1:] == normalized[:-1]


def test_show_covers_registry_and_authors_every_effect_as_one_two_node_relay() -> None:
    try:
        _, layout, show = _load(PROFILES[15.0])
        relay_cues = [cue for cue in show.cues if cue.id.startswith(RELAY_PREFIX)]

        assert show.id == "ws2811-two-node-capability-boundary-272s"
        assert show.duration == 272.0
        assert tuple(member.id for member in show.virtual_paths[0].targets) == (
            "strip_41",
            "strip_42",
        )
        assert [strip.pixel_count for strip in layout.strips] == [10, 20]
        assert len(relay_cues) == 17
        assert {cue.effect.id for cue in relay_cues} == set(list_effects())
        assert all(cue.target.kind == "virtual_path" for cue in relay_cues)
        assert all(cue.target.id == "node2-node8-relay" for cue in relay_cues)
        assert all(cue.end - cue.start == 12.0 for cue in relay_cues)

        tracks = {track.target.id: track for track in show.brightness_tracks}
        assert set(tracks) == {"strip_41", "strip_42"}
        node2 = {keyframe.time: keyframe.value for keyframe in tracks["strip_41"].keyframes}
        node8 = {keyframe.time: keyframe.value for keyframe in tracks["strip_42"].keyframes}
        for cue in relay_cues:
            assert (node2[cue.start], node8[cue.start]) == (1.0, 0.35)
            assert (node2[cue.start + 6.0], node8[cue.start + 6.0]) == (0.7, 0.7)
            assert (node2[cue.end - 0.1], node8[cue.end - 0.1]) == (0.35, 1.0)

        speed_cues = {
            cue.id: cue.effect.params["speed"]
            for cue in show.cues
            if cue.id.startswith("speed-")
        }
        assert speed_cues == {
            "speed-slow-1pps": 1.0,
            "speed-medium-3pps": 3.0,
            "speed-fast-6pps": 6.0,
        }
    finally:
        Config.reset()


def test_preflight_has_no_white_or_three_channel_anchor() -> None:
    try:
        _, _, show = _load(PROFILES[15.0])
        anchors = {
            cue.id: cue.color.color
            for cue in show.cues
            if cue.id.startswith("anchor-")
        }

        assert anchors["anchor-low-blue-repeat"] == (0.0, 0.0, 0.20)
        assert "anchor-neutral" not in anchors
        assert all(
            sum(channel > 0.0 for channel in color) <= 2
            for color in anchors.values()
        )
    finally:
        Config.reset()


def test_preflight_payloads_match_at_common_5_15_30_fps_timestamps() -> None:
    traces = {}
    try:
        for fps, profile in PROFILES.items():
            _, layout, show = _load(profile)
            runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
            trace = {}
            for sequence in range(1, int(50.0 * fps)):
                timestamp = sequence / fps
                common_index = round(timestamp * 5.0)
                if abs(timestamp - common_index / 5.0) > 1e-9:
                    continue
                frame = runtime.render(
                    EffectContext(
                        timestamp=timestamp,
                        delta_time=1.0 / fps,
                        sequence=sequence,
                    ),
                    black_base_frame(
                        timestamp=timestamp,
                        sequence=sequence,
                        analog_zones=layout.zones,
                        digital_strips=layout.strips,
                    ),
                )
                trace[common_index] = _signature(frame)
            traces[fps] = trace

        assert traces[5.0] == traces[15.0] == traces[30.0]
    finally:
        Config.reset()


def test_every_authored_separator_and_final_tail_render_black() -> None:
    try:
        _, layout, show = _load(PROFILES[15.0])
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
        relay_cues = [cue for cue in show.cues if cue.id.startswith(RELAY_PREFIX)]
        sample_times = [
            0.5,
            3.5,
            6.5,
            9.5,
            12.5,
            15.5,
            18.5,
            19.5,
            26.5,
            33.5,
            40.5,
            49.5,
            *(cue.end + 0.5 for cue in relay_cues[:-1]),
            270.5,
            271.5,
        ]
        previous = 0.0
        for sequence, timestamp in enumerate(sample_times, start=1):
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=timestamp - previous,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            previous = timestamp
            assert all(value == 0.0 for value in _signature(frame)), timestamp
    finally:
        Config.reset()


def test_every_relay_effect_changes_and_reaches_both_physical_strips() -> None:
    previous_random = random.getstate()
    random.seed(20260717)
    try:
        _, layout, show = _load(PROFILES[5.0])
        # Remove the handoff tracks for this assertion so track interpolation
        # cannot make an otherwise-static effect look self-changing.
        runtime = ShowRuntime.from_layout(
            replace(show, brightness_tracks=()),
            layout,
            seed=20260717,
        )
        media = SyntheticDataSource(seed=20260717)
        relay_cues = [cue for cue in show.cues if cue.id.startswith(RELAY_PREFIX)]
        signatures = {cue.id: set() for cue in relay_cues}
        peak_energy = {
            cue.id: {"strip_41": 0.0, "strip_42": 0.0}
            for cue in relay_cues
        }

        fps = 5.0
        for sequence in range(1, int(show.duration * fps)):
            timestamp = sequence / fps
            frame = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / fps,
                    sequence=sequence,
                    video_features=media.get_video_features(timestamp),
                    audio_features=media.get_audio_features(timestamp),
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            cue = next(
                (item for item in relay_cues if item.start <= timestamp < item.end),
                None,
            )
            if cue is None:
                continue

            strips = {strip.strip_id: strip for strip in frame.strips}
            signatures[cue.id].add(_signature(frame))
            for strip_id in ("strip_41", "strip_42"):
                energy = sum(max(pixel) for pixel in strips[strip_id].pixels)
                peak_energy[cue.id][strip_id] = max(
                    peak_energy[cue.id][strip_id], energy
                )

        for cue in relay_cues:
            assert len(signatures[cue.id]) >= 2, cue.id
            assert peak_energy[cue.id]["strip_41"] > 0.0, cue.id
            assert peak_energy[cue.id]["strip_42"] > 0.0, cue.id
    finally:
        Config.reset()
        random.setstate(previous_random)
