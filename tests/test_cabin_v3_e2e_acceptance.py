"""Phase 29 evidence-only acceptance for the cabin v3 topology.

The expected topology lives in ``config/cabin_v3_acceptance.yaml`` rather
than being regenerated from the implementation under test.  The test compares
that fixed fixture with the production profile, Show v2 output and UDP v3
packets.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from light_engine.config import Config
from light_engine.mapping import Layout, PhysicalMapping
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.outputs.transform import OutputTransform
from light_engine.outputs.udp_output import UdpOutputV3
from light_engine.outputs.udp_v2 import crc32
from light_engine.outputs.udp_v3 import HEADER_LENGTH, UdpV3Output, UdpV3Packet
from light_engine.show import TargetCatalog, TargetResolver, ShowRuntime, black_base_frame, load_show, validate_show_data


ACCEPTANCE = Path("config/cabin_v3_acceptance.yaml")
PROFILE = Path("config/profiles/cabin_lighting_v3_production.yaml")
SHOW = Path("config/show.cabin-v2.yaml")
GOLDEN = Path("firmware/shared/udp_v3_golden.json")


def _fixture() -> dict:
    return yaml.safe_load(ACCEPTANCE.read_text(encoding="utf-8"))["acceptance"]


def _layout() -> Layout:
    Config.reset()
    return Layout.from_config(Config(PROFILE))


def _catalog(layout: Layout) -> TargetCatalog:
    return TargetCatalog(
        analog_zones={zone.id for zone in layout.zones},
        digital_strips={strip.id for strip in layout.strips},
    )


def _physical_frame(layout: Layout, *, sequence: int = 0xFFFFFFFE, timestamp: float = 123.456) -> PixelFrame:
    return PixelFrame(
        timestamp=timestamp,
        sequence=sequence,
        zones=[ZoneOutput("zone_32", RGBCCTColor(0.1, 0.2, 0.3, 0.4, 0.5))],
        strips=[
            DigitalStrip(
                strip_id=strip.id,
                pixel_count=strip.pixel_count,
                pixels=[((index + 1) / 100.0, 0.25, 0.5)] * strip.pixel_count,
            )
            for index, strip in enumerate(layout.strips)
        ],
    )


def test_fixed_acceptance_fixture_matches_the_complete_production_topology() -> None:
    spec = _fixture()
    layout = _layout()
    outputs = [output for node in spec["digital"]["nodes"] for output in node["outputs"]]

    assert len(layout.strips) == spec["digital"]["total_strips"] == 13
    assert sum(strip.pixel_count for strip in layout.strips) == spec["digital"]["total_pixel_groups"] == 260
    assert [zone.id for zone in layout.zones] == [spec["analog"]["id"]] == ["zone_32"]
    assert [(node.node_id, node.zone_id) for node in layout.analog_nodes] == [(17, "zone_32")]
    assert len(layout.digital_nodes) == len(spec["digital"]["nodes"]) == 5
    assert [(item.node_id, item.output_id, item.gpio, item.strip_id, item.pixel_count) for item in layout.digital_outputs] == [
        (node["node_id"], item["output_id"], item["gpio"], item["strip_id"], item["pixel_count"])
        for node in spec["digital"]["nodes"] for item in node["outputs"]
    ]
    assert {(output["node_id"] if "node_id" in output else node["node_id"], output["gpio"]) for node in spec["digital"]["nodes"] for output in node["outputs"]} == {
        (1, 4), (1, 5), (1, 6), (2, 4), (2, 5), (2, 6), (3, 4), (3, 5), (3, 6),
        (4, 4), (4, 5), (4, 6), (5, 4),
    }


def test_show_paths_cover_every_fixture_across_nodes_and_branch_in_one_frame() -> None:
    spec = _fixture()
    layout = _layout()
    show_data = yaml.safe_load(SHOW.read_text(encoding="utf-8"))
    show = load_show(SHOW, _catalog(layout))
    assert [path.id for path in show.virtual_paths] == spec["virtual_paths"]
    covered = {member.id for path in show.virtual_paths for member in path.targets}
    assert covered == {"zone_32", *(strip.id for strip in layout.strips)}
    mapping = {output.strip_id: output.node_id for output in layout.digital_outputs}
    assert all(len({mapping[member.id] for member in path.targets if member.kind == "digital_strip"}) > 1 for path in show.virtual_paths)

    authored_branch = show_data["show"]["cues"][0]["branches"][0]
    assert authored_branch["after"]["target"] == spec["branch"]["trigger"] == "strip_41"
    assert set(authored_branch["target"]["ids"]) == set(spec["branch"]["same_frame_release"])

    # A fixed, non-black fixture isolates the scheduler assertion from the
    # visual shape of chase.  It does not alter the authored production show.
    branch_cue = show_data["show"]["cues"][0]
    branch_cue["effect"] = {"mode": "fixed", "id": "static", "params": {}}
    branch_cue["color"] = {"mode": "solid", "color": [1.0, 0.0, 0.0]}
    runtime = ShowRuntime(validate_show_data(show_data, _catalog(layout)), TargetResolver.from_layout(layout))
    released_at = 60.0 * 10.0 / 110.0
    before_base = black_base_frame(timestamp=released_at - 0.001, sequence=76, analog_zones=layout.zones, digital_strips=layout.strips)
    before = runtime.render(EffectContext(timestamp=released_at - 0.001, delta_time=0.1, sequence=76), before_base)
    release = spec["branch"]["same_frame_release"]
    assert all(
        all(pixel == (0.0, 0.0, 0.0) for pixel in next(strip for strip in before.strips if strip.strip_id == strip_id).pixels)
        for strip_id in release
    )

    base = black_base_frame(timestamp=released_at, sequence=77, analog_zones=layout.zones, digital_strips=layout.strips)
    frame = runtime.render(EffectContext(timestamp=released_at, delta_time=0.1, sequence=77), base)
    assert all(any(pixel != (0.0, 0.0, 0.0) for pixel in next(strip for strip in frame.strips if strip.strip_id == strip_id).pixels) for strip_id in release)
    assert frame.sequence == base.sequence == 77  # The first release is this same logical frame.


def test_mapping_transport_preserves_independent_outputs_and_shared_logical_identity() -> None:
    layout = _layout()
    physical = PhysicalMapping(layout).map(_physical_frame(layout))
    transport = UdpOutputV3()
    transport.open()
    transport.send_frame(physical)
    datagrams = transport.get_sent_datagrams()
    assert len(datagrams) == 5
    expected = {
        node.node_id: {output.output_id: (output.gpio, len(output.pixels)) for output in physical_node.outputs}
        for node, physical_node in zip(layout.digital_nodes, physical.digital_frames)
    }
    decoded = [UdpV3Packet.decode(raw, expected_node_id=node_id, expected_outputs=expected[node_id]) for raw, (_, _) in datagrams for node_id in [raw[4]]]
    assert all(packet is not None for packet in decoded)
    assert {(packet.sequence, packet.media_timestamp_us) for packet in decoded if packet is not None} == {(0xFFFFFFFE, 123_456_000)}
    assert [len(packet.outputs) for packet in decoded if packet is not None] == [3, 3, 3, 3, 1]
    assert [[len(output.pixels) for output in packet.outputs] for packet in decoded if packet is not None] == [[10, 10, 10], [10, 20, 20], [20, 20, 20], [40, 20, 20], [40]]


def test_golden_is_authoritative_and_codec_rejects_corrupt_unknown_incomplete_and_bounds() -> None:
    spec = _fixture()
    encoded = GOLDEN.read_bytes()
    assert hashlib.sha256(encoded).hexdigest() == spec["golden"]["json_sha256"]
    vector = json.loads(encoded)["vectors"][0]
    raw = bytearray(bytes.fromhex(vector["encoded_hex"]))
    expected = {1: (4, 2), 2: (5, 1)}
    assert UdpV3Packet.decode(bytes(raw), expected_node_id=2, expected_outputs=expected) is not None
    raw[-1] ^= 1
    assert UdpV3Packet.decode(bytes(raw), expected_outputs=expected) is None  # CRC

    raw = bytearray(bytes.fromhex(vector["encoded_hex"]))
    raw[HEADER_LENGTH] = 9  # unknown output id; repair CRC to prove semantic rejection.
    raw[-4:] = crc32(bytes(raw[:-4])).to_bytes(4, "big")
    assert UdpV3Packet.decode(bytes(raw), expected_outputs=expected) is None
    assert UdpV3Packet.decode(bytes.fromhex(vector["encoded_hex"]), expected_outputs={1: (4, 2)}) is None
    assert UdpV3Packet.decode(bytes.fromhex(vector["encoded_hex"]), min_sequence=0x01020305) is None
    assert UdpV3Packet.decode(bytes.fromhex(vector["encoded_hex"]), max_udp_payload=len(bytes(raw)) - 1) is None
    assert len(UdpV3Output(1, 4, ((0, 0, 0),) * 100).pixels) == 100
    with pytest.raises(ValueError, match="100"):
        UdpV3Output(1, 4, ((0, 0, 0),) * 101)


def test_safe_black_frame_encodes_all_configured_outputs_and_replay_is_deterministic() -> None:
    layout = _layout()
    safe = OutputTransform.generate_safe_frame(
        timestamp=2.0,
        sequence=9,
        zone_ids=["zone_32"],
        strips=[{"id": strip.id, "pixel_count": strip.pixel_count} for strip in layout.strips],
    )
    physical = PhysicalMapping(layout).map(safe)
    assert physical.metadata["SAFE_STATE"] is True
    output = UdpOutputV3()
    output.open()
    output.send_frame(physical)
    packets = [UdpV3Packet.decode(raw) for raw, _address in output.get_sent_datagrams()]
    assert all(packet is not None and packet.flags == 1 for packet in packets)
    assert all(channel == 0 for packet in packets if packet is not None for item in packet.outputs for pixel in item.pixels for channel in pixel)

    runtime = ShowRuntime(load_show(SHOW, _catalog(layout)), TargetResolver.from_layout(layout), seed=29)
    def replay() -> str:
        digest = hashlib.sha256()
        for sequence, timestamp in enumerate((0.0, 1.0, 2.0, 5.454545454545454), start=1):
            base = black_base_frame(timestamp=timestamp, sequence=sequence, analog_zones=layout.zones, digital_strips=layout.strips)
            frame = runtime.render(EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence), base)
            digest.update(repr(frame).encode("utf-8"))
        return digest.hexdigest()
    first = replay()
    assert first == _fixture()["deterministic_replay_sha256"]
    runtime.reset()
    assert replay() == first
