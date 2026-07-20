"""Contract for WLED two-output-as-one 40-pixel demo."""

from pathlib import Path

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import EffectContext
from light_engine.outputs.ddp_output import DDP_FLAGS_PUSH, DDP_HEADER_LEN, DDP_TYPE_RGB24, DdpOutput
from light_engine.outputs.transform import OutputTransform
from light_engine.show import ShowRuntime, TargetCatalog, black_base_frame, load_show


PROFILE = Path("config/profiles/wled-two-output-20-20-as-one.yaml")
SHOW = Path("config/shows/wled-two-output-20-20-as-one-demo.yaml")
FPS = 30.0


def _lit_counts(frame) -> tuple[int, int]:
    strips = {strip.strip_id: strip for strip in frame.strips}
    left = sum(1 for pixel in strips["strip_left"].pixels if max(pixel) > 0.01)
    right = sum(1 for pixel in strips["strip_right"].pixels if max(pixel) > 0.01)
    return left, right


def test_two_wled_outputs_are_rendered_as_one_40_pixel_virtual_path() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)

        assert config.get("outputs.enabled") == ["ddp"]
        assert config.get("layout.digital_nodes")[0]["host"] == "192.168.31.58"
        assert config.get("layout.digital_nodes")[0]["pixel_count"] == 40
        assert tuple(target.id for target in show.virtual_paths[0].targets) == (
            "strip_left",
            "strip_right",
        )

        samples = {}
        for index in range(int(show.duration * FPS)):
            timestamp = (index + 1) / FPS
            frame = runtime.render(
                EffectContext(timestamp=timestamp, delta_time=1.0 / FPS, sequence=index + 1),
                black_base_frame(
                    timestamp=timestamp,
                    sequence=index + 1,
                    analog_zones=layout.zones,
                    digital_strips=layout.strips,
                ),
            )
            for sample in (1.0, 4.0, 7.0, 10.0, 13.0, 16.0):
                if sample not in samples and timestamp >= sample:
                    samples[sample] = _lit_counts(frame)

        assert samples[1.0][0] > 0 and samples[1.0][1] == 0
        assert samples[4.0][0] == 20 and samples[4.0][1] > 0
        assert samples[7.0] == (20, 20)
        assert samples[10.0][0] == 0 and samples[10.0][1] > 0
        assert samples[13.0][0] > 0 and samples[13.0][1] == 20
        assert samples[16.0] == (20, 20)
    finally:
        Config.reset()


def test_two_wled_outputs_are_concatenated_into_one_ddp_payload() -> None:
    Config.reset()
    try:
        config = Config.get_instance(PROFILE)
        layout = Layout.from_config(config)
        show = load_show(SHOW, TargetCatalog.from_layout(layout))
        runtime = ShowRuntime.from_layout(show, layout, seed=20260717)
        transform_config = config.get("outputs.transform")
        transform = OutputTransform(
            global_brightness=config.get("system.smoothing.max_brightness"),
            gamma=config.get("system.smoothing.gamma"),
            power_limit=transform_config["power_limit"],
            per_zone_warm_bias=transform_config["per_zone_warm_bias"],
            per_zone_cool_bias=transform_config["per_zone_cool_bias"],
        )
        logical = runtime.render(
            EffectContext(timestamp=3.2, delta_time=1.0 / FPS, sequence=96),
            black_base_frame(
                timestamp=3.2,
                sequence=96,
                analog_zones=layout.zones,
                digital_strips=layout.strips,
            ),
        )
        physical = PhysicalMapping(layout).map(transform.apply_to_frame(logical))
        output = DdpOutput()
        output.open()
        output.send_frame(physical)

        sent = output.get_sent_datagrams()
        assert len(sent) == 1
        packet, address = sent[0]
        assert address == ("192.168.31.58", 4048)
        assert packet[0] & DDP_FLAGS_PUSH
        assert packet[2] == DDP_TYPE_RGB24
        assert packet[8:10] == (120).to_bytes(2, "big")
        assert len(packet[DDP_HEADER_LEN:]) == 40 * 3
    finally:
        Config.reset()
