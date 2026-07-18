"""Contract for the two-node data-edge versus LED-load discriminator Show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-edge-load-discriminator-60s.yaml")
FPS = 15.0
BLACK = (0, 0, 0)
NODE_SPECS = {2: ("192.168.31.202", 10), 8: ("192.168.31.208", 20)}


def _phase(timestamp: float) -> str | None:
    if 5.0 <= timestamp < 25.0:
        return "a"
    if 30.0 <= timestamp < 50.0:
        return "b"
    return None


def test_discriminator_holds_load_while_alternating_changed_content() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        blue_levels = {
            "a": {2: set(), 8: set()},
            "b": {2: set(), 8: set()},
        }

        assert show.duration == 60.0
        assert config.get("system.output_fps") == FPS
        for index in range(int(show.duration * FPS) - 1):
            timestamp = (index + 1) / FPS
            sequence = index + 1
            logical = runtime.render(
                EffectContext(
                    timestamp=timestamp,
                    delta_time=1.0 / FPS,
                    sequence=sequence,
                ),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=sequence,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            output.send_frame(mapping.map(transform.apply_to_frame(logical)))

            phase = _phase(timestamp)
            for raw, address in output.get_sent_datagrams()[-2:]:
                node_id = 2 if address[0].endswith(".202") else 8
                host, pixel_count = NODE_SPECS[node_id]
                packet = UdpV3Packet.decode(
                    raw,
                    expected_node_id=node_id,
                    expected_outputs={1: (4, pixel_count)},
                )
                assert address == (host, 9001)
                assert packet is not None
                pixels = packet.outputs[0].pixels
                assert len(set(pixels)) == 1
                if phase is None:
                    assert pixels == (BLACK,) * pixel_count
                else:
                    red, green, blue = pixels[0]
                    assert red == green == 0
                    assert blue > 0
                    blue_levels[phase][node_id].add(blue)

        # Phase A changes Node 2 content while Node 8 repeats one static payload.
        assert len(blue_levels["a"][2]) >= 20
        assert len(blue_levels["a"][8]) == 1
        # Phase B reverses that relationship without removing two-strip LED load.
        assert len(blue_levels["b"][2]) == 1
        assert len(blue_levels["b"][8]) >= 20
        assert blue_levels["a"][8] == blue_levels["b"][2]
    finally:
        Config.reset()
