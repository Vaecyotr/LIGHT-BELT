"""Contracts for the short NODE7 / strip_31 smoke test."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-node7-strip31-scheduled-30fps.yaml")
SHOW = Path("config/shows/ws2811-ab-node7-strip31-smoke-18s.yaml")


def _load():
    Config.reset()
    config = Config.get_instance(PROFILE)
    layout = Layout.from_config(config)
    show = load_show(SHOW, TargetCatalog.from_layout(layout))
    return config, layout, show


def _render(runtime, layout, timestamp, sequence):
    return runtime.render(
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


def test_profile_routes_only_node7_strip31() -> None:
    try:
        config, layout, show = _load()

        assert config.get("system.output_fps") == 30.0
        assert config.get("system.smoothing.max_brightness") == 0.35
        assert config.get("outputs.udp_v3.presentation.mode") == "scheduled"
        assert config.get("outputs.udp_v3.presentation.lead_us") == 60000
        assert [(node.node_id, node.host, node.pixel_count) for node in layout.digital_nodes] == [
            (7, "192.168.31.207", 10)
        ]
        assert [
            (
                output.node_id,
                output.output_id,
                output.gpio,
                output.strip_id,
                output.pixel_count,
            )
            for output in layout.digital_outputs
        ] == [(7, 1, 4, "strip_31", 10)]
        assert show.id == "ws2811-ab-node7-strip31-smoke-18s"
        assert show.duration == 18.0
        assert [cue.id for cue in show.cues] == [
            "node7-strip31-red",
            "node7-strip31-green",
            "node7-strip31-blue",
            "node7-strip31-blue-breath",
        ]
        assert all(cue.target.id == "strip_31" for cue in show.cues)
    finally:
        Config.reset()


def test_show_colors_breath_and_black_gaps() -> None:
    try:
        _, layout, show = _load()
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)

        for sequence, (timestamp, expected) in enumerate(
            (
                (0.5, (0.0, 0.0, 0.0)),
                (3.0, (0.65, 0.0, 0.0)),
                (4.5, (0.0, 0.0, 0.0)),
                (6.0, (0.0, 0.65, 0.0)),
                (7.5, (0.0, 0.0, 0.0)),
                (9.0, (0.0, 0.0, 0.65)),
                (10.5, (0.0, 0.0, 0.0)),
            ),
            start=1,
        ):
            frame = _render(runtime, layout, timestamp, sequence)
            strip = frame.strips[0]
            assert strip.strip_id == "strip_31"
            assert all(pixel == expected for pixel in strip.pixels), timestamp

        breath_levels = []
        for sequence, timestamp in enumerate((11.0, 11.5, 12.0, 12.5), start=20):
            strip = _render(runtime, layout, timestamp, sequence).strips[0]
            assert all(red == 0.0 and green == 0.0 for red, green, _blue in strip.pixels)
            breath_levels.append(round(strip.pixels[0][2], 4))
        assert len(set(breath_levels)) >= 2
        assert all(level > 0.0 for level in breath_levels)

        for sequence, timestamp in enumerate((16.5, 17.5), start=30):
            strip = _render(runtime, layout, timestamp, sequence).strips[0]
            assert all(pixel == (0.0, 0.0, 0.0) for pixel in strip.pixels)
    finally:
        Config.reset()


def test_active_frame_maps_to_one_complete_node7_packet() -> None:
    try:
        config, layout, show = _load()
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        logical = _render(runtime, layout, timestamp=9.0, sequence=270)
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
        assert len(datagrams) == 1
        raw, address = datagrams[0]
        assert address == ("192.168.31.207", 9001)
        packet = UdpV3Packet.decode(
            raw,
            expected_node_id=7,
            expected_outputs={1: (4, 10)},
        )
        assert packet is not None
        assert packet.sequence == 270
        assert packet.media_timestamp_us == 9_000_000
        assert len(packet.outputs) == 1
        assert len(packet.outputs[0].pixels) == 10
        assert len(set(packet.outputs[0].pixels)) == 1
        assert packet.outputs[0].pixels[0] != (0, 0, 0)
    finally:
        Config.reset()
