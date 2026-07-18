"""Contracts for the exploratory four-node capability-boundary Show."""

from pathlib import Path
import random

from light_engine.config import Config
from light_engine.data.generators import SyntheticDataSource
from light_engine.effects import list_effects
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-four-node-2-6-7-8-scheduled-30fps.yaml")
SHOW = Path("config/shows/ws2811-four-node-capability-boundary-272s.yaml")
STRIP_ORDER = ("strip_41", "strip_42", "strip_21", "strip_31")
NODE_SPECS = {
    2: ("192.168.31.202", "strip_41", 10),
    6: ("192.168.31.199", "strip_21", 10),
    7: ("192.168.31.207", "strip_31", 10),
    8: ("192.168.31.208", "strip_42", 20),
}


def _load():
    Config.reset()
    config = Config.get_instance(PROFILE)
    layout = Layout.from_config(config)
    show = load_show(SHOW, TargetCatalog.from_layout(layout))
    return config, layout, show


def _signature(frame) -> tuple[float, ...]:
    strips = {strip.strip_id: strip for strip in frame.strips}
    return tuple(
        round(channel, 4)
        for strip_id in STRIP_ORDER
        for pixel in strips[strip_id].pixels
        for channel in pixel
    )


def test_profile_and_show_bind_exactly_four_current_nodes() -> None:
    try:
        config, layout, show = _load()

        assert config.get("system.output_fps") == 30.0
        assert config.get("system.smoothing.max_brightness") == 0.35
        assert config.get("outputs.udp_v3.presentation.mode") == "scheduled"
        assert config.get("outputs.udp_v3.presentation.lead_us") == 60000
        assert config.get(
            "outputs.udp_v3.presentation.beacon.interval_us"
        ) == 100000
        assert {
            node.node_id: (node.host, node.pixel_count)
            for node in layout.digital_nodes
        } == {
            node_id: (host, pixel_count)
            for node_id, (host, _strip_id, pixel_count) in NODE_SPECS.items()
        }
        assert {
            output.node_id: (
                output.output_id,
                output.gpio,
                output.strip_id,
                output.pixel_count,
            )
            for output in layout.digital_outputs
        } == {
            node_id: (1, 4, strip_id, pixel_count)
            for node_id, (_host, strip_id, pixel_count) in NODE_SPECS.items()
        }

        assert show.id == "ws2811-four-node-capability-boundary-272s"
        assert show.duration == 272.0
        assert show.brightness_tracks == ()
        assert tuple(
            target.id for target in show.virtual_paths[0].targets
        ) == STRIP_ORDER

        relay_cues = [cue for cue in show.cues if cue.id.startswith("relay-")]
        assert len(relay_cues) == 17
        assert {cue.effect.id for cue in relay_cues} == set(list_effects())
        assert all(cue.end - cue.start == 12.0 for cue in relay_cues)
        assert all(cue.target.id == "node2-node8-node6-node7-relay" for cue in relay_cues)

        identifiers = {
            cue.id: cue.target.id
            for cue in show.cues
            if cue.id.startswith("identify-")
        }
        assert identifiers == {
            "identify-node2-strip41-red": "strip_41",
            "identify-node8-strip42-green": "strip_42",
            "identify-node6-strip21-blue": "strip_21",
            "identify-node7-strip31-cyan": "strip_31",
        }
        assert {
            cue.id: cue.effect.params["speed"]
            for cue in show.cues
            if cue.id.startswith("speed-")
        } == {
            "speed-slow-2pps": 2.0,
            "speed-medium-5pps": 5.0,
            "speed-fast-10pps": 10.0,
        }
    finally:
        Config.reset()


def test_every_separator_and_final_tail_render_black() -> None:
    try:
        _, layout, show = _load()
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        relay_cues = [cue for cue in show.cues if cue.id.startswith("relay-")]
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


def test_simultaneous_anchor_maps_to_four_complete_udp_packets() -> None:
    try:
        config, layout, show = _load()
        timestamp = 13.5
        sequence = 405
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        logical = runtime.render(
            EffectContext(
                timestamp=timestamp,
                delta_time=1.0 / 30.0,
                sequence=sequence,
            ),
            black_base_frame(
                timestamp=timestamp,
                sequence=sequence,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            ),
        )
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        output = UdpOutputV3()
        output.open()
        output.send_frame(
            PhysicalMapping(layout).map(transform.apply_to_frame(logical))
        )

        datagrams = output.get_sent_datagrams()
        assert len(datagrams) == 4
        seen = set()
        for raw, address in datagrams:
            node_id = next(
                item for item, spec in NODE_SPECS.items() if address[0] == spec[0]
            )
            host, _strip_id, pixel_count = NODE_SPECS[node_id]
            assert address == (host, 9001)
            packet = UdpV3Packet.decode(
                raw,
                expected_node_id=node_id,
                expected_outputs={1: (4, pixel_count)},
            )
            assert packet is not None
            assert packet.sequence == sequence
            assert packet.media_timestamp_us == 13_500_000
            assert len(packet.outputs) == 1
            assert len(set(packet.outputs[0].pixels)) == 1
            assert packet.outputs[0].pixels[0] != (0, 0, 0)
            seen.add(node_id)
        assert seen == set(NODE_SPECS)
    finally:
        Config.reset()


def test_every_relay_effect_changes_and_reaches_all_four_strips() -> None:
    previous_random = random.getstate()
    random.seed(20260718)
    try:
        _, layout, show = _load()
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        media = SyntheticDataSource(seed=20260718)
        relay_cues = [cue for cue in show.cues if cue.id.startswith("relay-")]
        signatures = {cue.id: set() for cue in relay_cues}
        peak_energy = {
            cue.id: {strip_id: 0.0 for strip_id in STRIP_ORDER}
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
            for strip_id in STRIP_ORDER:
                energy = sum(max(pixel) for pixel in strips[strip_id].pixels)
                peak_energy[cue.id][strip_id] = max(
                    peak_energy[cue.id][strip_id], energy
                )

        for cue in relay_cues:
            assert len(signatures[cue.id]) >= 2, cue.id
            assert all(
                peak_energy[cue.id][strip_id] > 0.0
                for strip_id in STRIP_ORDER
            ), cue.id
    finally:
        Config.reset()
        random.setstate(previous_random)
