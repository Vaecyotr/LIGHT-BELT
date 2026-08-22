"""Focused Phase 32 topology derivation and DDP packetization contracts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from light_engine.config import Config, ConfigError, validate_config
from light_engine.mapping import Layout
from light_engine.mapping.physical import (
    DigitalNodeFrame,
    PhysicalFrame,
    PhysicalMapping,
)
from light_engine.models import PixelFrame
from light_engine.outputs.ddp_output import (
    DDP_FLAGS_PUSH,
    DDP_HEADER_LEN,
    DdpOutput,
    encode_ddp_packets,
)
from scripts import resolve_nodes
from host_services.layout_vocab import derive_capabilities_targets, derive_target_ids


PROFILE = Path("config/profiles/rk3588-host-service.yaml")
UDP_V3_PROFILE = Path("config/profiles/udp-v3-nine-strip-maintenance.yaml")
OPENAPI = Path("docs/reference/host-api-v1.openapi.yaml")


def _offset(packet: bytes) -> int:
    return int.from_bytes(packet[4:8], "big")


def _payload_length(packet: bytes) -> int:
    return int.from_bytes(packet[8:10], "big")


def _one_node_data(pixel_count: int) -> dict:
    config = Config(PROFILE)
    data = deepcopy(config.to_dict())
    data["layout"].update(
        {
            "strips": [
                {
                    "id": "strip_test",
                    "type": "digital",
                    "pixel_count": pixel_count,
                    "video_zone": "center",
                    "direction": "forward",
                }
            ],
            "digital_nodes": [
                {
                    "node_id": 1,
                    "host": "wled-strip-test.local",
                    "port": 4048,
                }
            ],
            "digital_outputs": [
                {
                    "node_id": 1,
                    "output_id": 1,
                    "gpio": 16,
                    "strip_id": "strip_test",
                    "direction": "forward",
                }
            ],
            "video_zone_map": {"center": ["strip_test"]},
        }
    )
    return data


def test_active_profiles_derive_strip_count_and_keep_transport_metadata_scoped() -> None:
    production = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    maintenance = yaml.safe_load(UDP_V3_PROFILE.read_text(encoding="utf-8"))

    assert "total_strips" not in production["layout"]
    assert "total_strips" not in maintenance["layout"]
    assert all(
        "max_udp_payload" not in node and "protocol_version" not in node
        for node in production["layout"]["digital_nodes"]
    )
    assert all(
        node["max_udp_payload"] == 1400 and node["protocol_version"] == 3
        for node in maintenance["layout"]["digital_nodes"]
    )


def test_openapi_target_id_is_runtime_discovered_not_a_closed_enum() -> None:
    document = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    target_id = document["components"]["schemas"]["TargetId"]

    assert target_id["type"] == "string"
    assert "enum" not in target_id
    assert "strip_extra" in target_id["examples"]


def test_udp_v3_requires_its_payload_budget_while_ddp_does_not() -> None:
    data = _one_node_data(17)
    data["outputs"]["enabled"] = ["udp_v3"]

    with pytest.raises(ConfigError, match="max_udp_payload"):
        validate_config(data)


@pytest.mark.parametrize("pixel_count", [1, 17, 40, 144, 480, 481])
def test_v3_runtime_lengths_are_derived_only_from_logical_strip(pixel_count: int) -> None:
    data = _one_node_data(pixel_count)

    validate_config(data)
    config = Config(PROFILE)
    config._data = data
    layout = Layout.from_config(config)

    assert "pixel_count" not in data["layout"]["digital_nodes"][0]
    assert "pixel_count" not in data["layout"]["digital_outputs"][0]
    assert layout.digital_outputs[0].pixel_count == pixel_count
    assert layout.digital_nodes[0].pixel_count == pixel_count

    physical = PhysicalMapping(layout).map(PixelFrame(timestamp=0.0, sequence=1))
    assert physical.digital_frames[0].max_udp_payload == 4096


def test_udp_v3_config_and_layout_accept_481_pixels_via_chunking() -> None:
    data = _one_node_data(481)
    data["outputs"]["enabled"] = ["udp_v3"]
    data["layout"]["digital_nodes"][0].update(
        {"max_udp_payload": 1400, "protocol_version": 3}
    )

    validate_config(data)
    config = Config(PROFILE)
    config._data = data
    layout = Layout.from_config(config)

    assert layout.digital_nodes[0].pixel_count == 481
    assert layout.digital_outputs[0].pixel_count == 481
    assert layout.digital_nodes[0].max_udp_payload == 1400


@pytest.mark.parametrize("max_udp_payload", [1, 45, 65_508])
def test_udp_v3_config_rejects_payload_budget_outside_chunk_contract(
    max_udp_payload: int,
) -> None:
    data = _one_node_data(481)
    data["outputs"]["enabled"] = ["udp_v3"]
    data["layout"]["digital_nodes"][0]["protocol_version"] = 3
    data["layout"]["digital_nodes"][0]["max_udp_payload"] = max_udp_payload

    with pytest.raises(ConfigError, match="one UDP v3 RGB pixel chunk"):
        validate_config(data)


def test_udp_v3_config_accepts_minimum_one_pixel_chunk_budget() -> None:
    data = _one_node_data(481)
    data["outputs"]["enabled"] = ["udp_v3"]
    data["layout"]["digital_nodes"][0]["protocol_version"] = 3
    data["layout"]["digital_nodes"][0]["max_udp_payload"] = 46

    validate_config(data)


def test_ddp_does_not_apply_udp_v3_chunk_payload_minimum() -> None:
    data = _one_node_data(481)
    data["layout"]["digital_nodes"][0]["max_udp_payload"] = 45

    validate_config(data)
    config = Config(PROFILE)
    config._data = data
    layout = Layout.from_config(config)

    assert layout.digital_nodes[0].pixel_count == 481
    assert layout.digital_nodes[0].max_udp_payload == 45


def test_current_profile_plus_one_node_requires_only_profile_data() -> None:
    config = Config(PROFILE)
    data = deepcopy(config.to_dict())
    data["layout"]["strips"].append(
        {
            "id": "strip_extra",
            "type": "digital",
            "pixel_count": 17,
            "video_zone": "center",
            "direction": "forward",
        }
    )
    data["layout"]["digital_nodes"].append(
        {
            "node_id": 10,
            "host": "wled-strip-extra.local",
            "port": 4048,
        }
    )
    data["layout"]["digital_outputs"].append(
        {
            "node_id": 10,
            "output_id": 1,
            "gpio": 16,
            "strip_id": "strip_extra",
            "direction": "forward",
        }
    )

    validate_config(data)
    config._data = data
    layout = Layout.from_config(config)

    assert len(layout.digital_nodes) == 10
    assert layout.digital_nodes[-1].pixel_count == 17
    assert layout.digital_outputs[-1].pixel_count == 17
    assert "total_strips" not in data["layout"]
    assert "max_udp_payload" not in data["layout"]["digital_nodes"][-1]
    assert "protocol_version" not in data["layout"]["digital_nodes"][-1]
    assert "strip_extra" in derive_target_ids(layout)
    assert any(
        item["target_id"] == "strip_extra"
        for item in derive_capabilities_targets(layout)
    )


def test_resolver_accepts_current_profile_plus_one_node(tmp_path: Path) -> None:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    profile["layout"]["strips"].append(
        {"id": "strip_extra", "type": "digital", "pixel_count": 17}
    )
    profile["layout"]["digital_nodes"].append(
        {
            "node_id": 10,
            "host": "wled-strip-extra.local",
            "port": 4048,
        }
    )
    profile["layout"]["digital_outputs"].append(
        {
            "node_id": 10,
            "output_id": 1,
            "gpio": 16,
            "strip_id": "strip_extra",
        }
    )
    template = tmp_path / "template.yaml"
    output = tmp_path / "runtime" / "profile.yaml"
    template.write_text(yaml.safe_dump(profile), encoding="utf-8")

    disabled = resolve_nodes.resolve_profile(
        template,
        output,
        lambda command, timeout: f"{command[-1]}\t192.0.2.10\n",
    )

    resolved = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert disabled == 0
    assert len(resolved["layout"]["digital_nodes"]) == 10


@pytest.mark.parametrize(
    ("pixel_count", "lengths", "offsets"),
    [
        (480, [1440], [0]),
        (481, [1440, 3], [0, 1440]),
    ],
)
def test_ddp_480_and_481_pixel_boundaries(
    pixel_count: int, lengths: list[int], offsets: list[int]
) -> None:
    packets = encode_ddp_packets([(1, 2, 3)] * pixel_count, sequence=14)

    assert [_payload_length(packet) for packet in packets] == lengths
    assert [_offset(packet) for packet in packets] == offsets
    assert [packet[1] for packet in packets] == list(range(14, 14 + len(packets)))
    assert [bool(packet[0] & DDP_FLAGS_PUSH) for packet in packets] == [
        False
    ] * (len(packets) - 1) + [True]
    assert all(len(packet) == DDP_HEADER_LEN + length for packet, length in zip(packets, lengths))


def test_ddp_long_frame_sequences_wrap_skip_zero_and_only_final_packet_pushes() -> None:
    packets = encode_ddp_packets([(1, 2, 3)] * 1000, sequence=15)

    assert [_payload_length(packet) for packet in packets] == [1440, 1440, 120]
    assert [_offset(packet) for packet in packets] == [0, 1440, 2880]
    assert [packet[1] for packet in packets] == [15, 1, 2]
    assert [bool(packet[0] & DDP_FLAGS_PUSH) for packet in packets] == [
        False,
        False,
        True,
    ]


def test_ddp_multi_node_packet_sequences_restart_from_shared_logical_sequence() -> None:
    output = DdpOutput()
    output.open()
    output.send_frame(
        PhysicalFrame(
            sequence=15,
            timestamp=0.0,
            digital_frames=[
                DigitalNodeFrame(
                    node_id=1,
                    host="192.0.2.1",
                    port=4048,
                    pixels=[(1.0, 0.0, 0.0)] * 481,
                ),
                DigitalNodeFrame(
                    node_id=2,
                    host="192.0.2.2",
                    port=4048,
                    pixels=[(0.0, 1.0, 0.0)] * 17,
                ),
            ],
        )
    )

    sent = output.get_sent_datagrams()
    assert [address for _, address in sent] == [
        ("192.0.2.1", 4048),
        ("192.0.2.1", 4048),
        ("192.0.2.2", 4048),
    ]
    assert [packet[1] for packet, _ in sent] == [15, 1, 15]
    assert [bool(packet[0] & DDP_FLAGS_PUSH) for packet, _ in sent] == [
        False,
        True,
        True,
    ]
