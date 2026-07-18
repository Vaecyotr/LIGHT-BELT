"""Contract for the static-prearm cross-node coupling discriminator Show."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v3 import UdpV3Packet
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml")
SHOW = Path("config/shows/ws2811-ab-two-node-static-prearm-coupling-85s.yaml")
FPS = 15.0
BLACK = (0, 0, 0)
NODE_SPECS = {2: ("192.168.31.202", 10), 8: ("192.168.31.208", 20)}


def _state(node_id: int, timestamp: float) -> str:
    if node_id == 2:
        if 15.0 <= timestamp < 35.0:
            return "breath"
        if 45.0 <= timestamp < 80.0:
            return "static"
    elif 5.0 <= timestamp < 40.0:
        return "static"
    elif 55.0 <= timestamp < 75.0:
        return "breath"
    return "black"


def test_static_payload_stays_unchanged_before_during_and_after_other_breath() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        assert show.duration == 85.0
        assert [
            (cue.id, cue.start, cue.end, cue.target.id, cue.effect.id)
            for cue in show.cues
        ] == [
            ("phase-a-strip42-prearmed-blue-static", 5.0, 40.0, "strip_42", "static"),
            ("phase-a-strip41-blue-breath", 15.0, 35.0, "strip_41", "breath"),
            ("phase-b-strip41-prearmed-blue-static", 45.0, 80.0, "strip_41", "static"),
            ("phase-b-strip42-blue-breath", 55.0, 75.0, "strip_42", "breath"),
        ]
        assert all(cue.color.color == (0.0, 0.0, 0.65) for cue in show.cues)

        runtime = ShowRuntime.from_layout(show, layout, seed=20260718)
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=config.get("outputs.transform.power_limit"),
        )
        mapping = PhysicalMapping(layout)
        output = UdpOutputV3()
        output.open()
        levels = {
            "static": {2: set(), 8: set()},
            "breath": {2: set(), 8: set()},
        }

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
                state = _state(node_id, timestamp)
                if state == "black":
                    assert pixels == (BLACK,) * pixel_count
                else:
                    red, green, blue = pixels[0]
                    assert red == green == 0
                    assert blue > 0
                    levels[state][node_id].add(blue)

        assert len(levels["static"][2]) == 1
        assert len(levels["static"][8]) == 1
        assert levels["static"][2] == levels["static"][8]
        assert len(levels["breath"][2]) >= 20
        assert len(levels["breath"][8]) >= 20
    finally:
        Config.reset()
