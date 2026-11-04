"""Contracts for the nine-node WLED/DDP deployment profile."""

from __future__ import annotations

from pathlib import Path
from copy import deepcopy

import pytest
import yaml

from light_engine.config import Config, ConfigError, validate_config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import DigitalStrip, PixelFrame
from light_engine.outputs.ddp_output import DdpOutput
from light_engine.show import TargetCatalog, load_show


WLED_PROFILE = Path("config/profiles/rk3588-host-service.yaml")
UDP_V3_PROFILE = Path("config/profiles/udp-v3-nine-strip-maintenance.yaml")
SHOW = Path("config/shows/energy-wakeup.yaml")
EXPECTED = {
    1: "strip_32", 2: "strip_41", 3: "strip_44",
    4: "strip_12", 5: "strip_22", 6: "strip_31",
    7: "strip_43", 8: "strip_11", 9: "strip_21",
}
EXPECTED_WLED_PIXELS = {
    "strip_32": 10, "strip_31": 10, "strip_41": 10,
    "strip_43": 10, "strip_44": 10, "strip_11": 10,
    "strip_12": 17, "strip_21": 10, "strip_22": 20,
}
EXPECTED_MAINTENANCE_PIXELS = {
    "strip_32": 40, "strip_31": 10, "strip_41": 10,
    "strip_43": 20, "strip_44": 20, "strip_11": 10,
    "strip_12": 40, "strip_21": 10, "strip_22": 40,
}
EXPECTED_VIDEO_ZONES = {
    "strip_32": "left", "strip_31": "left", "strip_41": "right",
    "strip_43": "right", "strip_44": "right", "strip_11": "top",
    "strip_12": "top", "strip_21": "bottom", "strip_22": "bottom",
}


def _profile(path: Path) -> Config:
    Config.reset()
    return Config(path)


def test_default_wled_profile_is_nine_independent_ddp_nodes_without_analog_placeholders() -> None:
    config = _profile(WLED_PROFILE)
    layout = config.get("layout")

    assert config.get("outputs.enabled") == ["ddp"]
    assert layout["zones"] == []
    assert layout["analog_nodes"] == []
    assert layout["digital_output_policy"] == "one_output_wled"
    assert {node["node_id"] for node in layout["digital_nodes"]} == set(EXPECTED)
    assert {
        output["node_id"]: output["strip_id"]
        for output in layout["digital_outputs"]
    } == EXPECTED
    assert {strip["id"]: strip["pixel_count"] for strip in layout["strips"]} == EXPECTED_WLED_PIXELS
    assert sum(EXPECTED_WLED_PIXELS.values()) == 107
    assert {strip["id"]: strip["video_zone"] for strip in layout["strips"]} == EXPECTED_VIDEO_ZONES
    assert {strip["id"]: strip["direction"] for strip in layout["strips"]} == {
        strip_id: "forward" for strip_id in EXPECTED.values()
    }
    assert all("pixel_count" not in node for node in layout["digital_nodes"])
    assert all("pixel_count" not in output for output in layout["digital_outputs"])
    assert all(output["output_id"] == 1 and output["gpio"] == 16 for output in layout["digital_outputs"])
    assert "zone_32_placeholder" not in str(layout)


def test_wled_one_output_policy_rejects_a_second_output() -> None:
    data = deepcopy(_profile(WLED_PROFILE).to_dict())
    data["layout"]["digital_outputs"].append(
        {"node_id": 1, "output_id": 2, "gpio": 2, "strip_id": "strip_32", "pixel_count": 40, "direction": "forward"}
    )
    with pytest.raises(ConfigError, match="one_output_wled"):
        validate_config(data)


def test_wled_mapping_sends_one_ddp_frame_to_each_enabled_node_and_skips_disabled() -> None:
    config = _profile(WLED_PROFILE)
    layout = Layout.from_config(config)
    strips = [
        DigitalStrip(
            strip_id=strip.id,
            pixel_count=strip.pixel_count,
            pixels=[(0.1, 0.2, 0.3)] * strip.pixel_count,
        )
        for strip in layout.strips
    ]
    physical = PhysicalMapping(layout).map(PixelFrame(timestamp=4.0, sequence=9, strips=strips))
    output = DdpOutput()
    output.open()
    output.send_frame(physical)

    sent = output.get_sent_datagrams()
    assert len(sent) == 9
    assert {address for _, address in sent} == {
        (node.host, 4048) for node in layout.digital_nodes
    }

    disabled_layout = Layout.from_config(config)
    disabled_layout.digital_nodes[0] = disabled_layout.digital_nodes[0].__class__(
        **{**disabled_layout.digital_nodes[0].__dict__, "enabled": False}
    )
    disabled_physical = PhysicalMapping(disabled_layout).map(
        PixelFrame(timestamp=4.0, sequence=10, strips=strips)
    )
    output = DdpOutput()
    output.open()
    output.send_frame(disabled_physical)
    assert len(output.get_sent_datagrams()) == 8
    assert all(address[0] != "wled-strip-32.local" for _, address in output.get_sent_datagrams())


def test_ddp_and_udp_v3_maintenance_profiles_share_nine_strip_semantics() -> None:
    ddp = _profile(WLED_PROFILE)
    udp_v3 = _profile(UDP_V3_PROFILE)
    assert ddp.get("outputs.enabled") == ["ddp"]
    assert udp_v3.get("outputs.enabled") == ["udp_v3"]
    assert {item["id"] for item in ddp.get("layout.strips")} == {
        item["id"] for item in udp_v3.get("layout.strips")
    }
    assert {item["id"]: item["pixel_count"] for item in ddp.get("layout.strips")} == EXPECTED_WLED_PIXELS
    assert {item["id"]: item["pixel_count"] for item in udp_v3.get("layout.strips")} == EXPECTED_MAINTENANCE_PIXELS
    assert sum(EXPECTED_MAINTENANCE_PIXELS.values()) == 200
    for profile in (ddp, udp_v3):
        strips = profile.get("layout.strips")
        assert {item["id"]: item["video_zone"] for item in strips} == EXPECTED_VIDEO_ZONES
        assert {item["id"]: item["direction"] for item in strips} == {
            strip_id: "forward" for strip_id in EXPECTED.values()
        }
    assert [item["strip_id"] for item in ddp.get("layout.digital_outputs")] == [
        item["strip_id"] for item in udp_v3.get("layout.digital_outputs")
    ]
    assert udp_v3.get("outputs.udp_v3.presentation.beacon.port") == 9001
    assert {node["port"] for node in udp_v3.get("layout.digital_nodes")} == {9001}


def test_energy_wakeup_has_only_real_digital_targets() -> None:
    config = _profile(WLED_PROFILE)
    layout = Layout.from_config(config)
    load_show(SHOW, TargetCatalog.from_layout(layout))
    show_data = yaml.safe_load(SHOW.read_text(encoding="utf-8"))
    target_ids = {
        item["target"]["id"]
        for item in [*show_data["show"]["brightness_tracks"], *show_data["show"]["cues"]]
        if item["target"]["type"] == "digital_strip"
    }
    assert target_ids <= set(EXPECTED.values())
    assert "zone_32_placeholder" not in SHOW.read_text(encoding="utf-8")
    assert "zone_32_dim" not in SHOW.read_text(encoding="utf-8")
