from __future__ import annotations

import re
from pathlib import Path

import yaml


PROFILE = Path("config/profiles/cabin-lighting-v3-site-local.yaml")
NODE_CONFIG_DIR = Path("firmware/esp32_ws2811_node/src/node_configs")
DEFINE_RE = re.compile(r"^#define\s+([A-Z0-9_]+)\s+(\d+)\s*$", re.MULTILINE)


def _defines(path: Path) -> dict[str, int]:
    return {
        name: int(value)
        for name, value in DEFINE_RE.findall(path.read_text(encoding="utf-8"))
    }


def test_site_esp32_headers_match_complete_udp_v3_mapping() -> None:
    profile = yaml.safe_load(PROFILE.read_text(encoding="utf-8"))
    nodes = {item["node_id"]: item for item in profile["layout"]["digital_nodes"]}
    outputs: dict[int, list[dict]] = {node_id: [] for node_id in nodes}
    for output in profile["layout"]["digital_outputs"]:
        outputs[output["node_id"]].append(output)

    assert set(nodes) == {1, 2, 3, 4, 5}
    for node_id, node in nodes.items():
        configured = _defines(NODE_CONFIG_DIR / f"node_{node_id}.h")
        expected = sorted(outputs[node_id], key=lambda item: item["output_id"])

        assert configured["NODE_ID"] == node_id
        assert configured["OUTPUT_COUNT"] == len(expected)
        assert sum(item["pixel_count"] for item in expected) == node["pixel_count"]
        for index, output in enumerate(expected):
            assert configured[f"OUTPUT_{index}_ID"] == output["output_id"]
            assert configured[f"OUTPUT_{index}_GPIO"] == output["gpio"]
            assert configured[f"OUTPUT_{index}_PIXELS"] == output["pixel_count"]
