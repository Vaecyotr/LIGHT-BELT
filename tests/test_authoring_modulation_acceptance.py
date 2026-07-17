from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from scripts.authoring_modulation_acceptance import run_acceptance


SHOW = Path("config/acceptance/authoring-modulation-v1/show.yaml")
LAYOUT = Path("config/acceptance/authoring-modulation-v1/layout.yaml")


def test_phase_22_authoring_modulation_acceptance(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "authoring-modulation-v1"
    report_path = tmp_path / "authoring-modulation-v1-report.md"
    summary = run_acceptance(
        SHOW,
        LAYOUT,
        artifact_dir=artifact_dir,
        report_path=report_path,
    )

    assert summary["not_hardware_verified"] == "NOT HARDWARE VERIFIED"
    assert summary["frame_count"] == 180
    assert summary["two_run_digests"][0] == summary["two_run_digests"][1]

    colors = summary["evidence"]["color_timeline"]
    for actual, expected in zip(
        [item["front_pixel_0"] for item in colors],
        ([1.0, 0.0, 0.0], [0.5, 0.5, 0.0], [0.0, 1.0, 0.0]),
    ):
        assert actual == pytest.approx(expected)

    modulation = summary["evidence"]["audio_modulation"]
    assert modulation["active"] == pytest.approx({"brightness": 1.4, "speed": 1.3, "intensity": 0.9})
    assert modulation["no_audio"] == {"brightness": 1.0, "speed": 1.0, "intensity": 1.0}
    assert modulation["fixed_effect"] == "static"
    assert modulation["fixed_sample_pixel"] == pytest.approx([0.56, 0.28, 0.14])

    seam = summary["evidence"]["virtual_path_seam"]
    assert [item["destination"] for item in seam] == [
        {"strip_id": "front", "pixel_index": 3},
        {"strip_id": "wall_right", "pixel_index": 3},
        {"strip_id": "wall_right", "pixel_index": 2},
    ]
    for item in seam:
        assert item["pixel"] == pytest.approx([0.5, 0.5, 0.0])

    transition = summary["evidence"]["transitions_and_overlap"]
    assert transition["fade_in_midpoint_weight"] == pytest.approx(0.5)
    assert transition["fade_out_midpoint_weight"] == pytest.approx(0.5)
    assert transition["overlap_base_weight"] == pytest.approx(0.5)
    assert transition["front_pixel_at_fade_in_midpoint"] == pytest.approx([0.33, 0.165, 0.0825])
    assert transition["front_pixel_at_fade_out_midpoint"] == pytest.approx([0.38, 0.19, 0.095])

    adaptive = summary["evidence"]["adaptive"]
    assert adaptive["music_state"] == "energetic"
    assert adaptive["selected_effect"] == "chase"
    assert adaptive["selected_effect"] in set(adaptive["allowed_effects"].values())
    assert adaptive["speed_before_modulation"] > 0.0
    assert adaptive["speed_multiplier"] == pytest.approx(1.3)
    assert adaptive["speed_path_lit_indices"] == {"modulated": [], "neutral": [3]}

    for path, expected in summary["artifact_sha256"].items():
        actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        assert actual == expected
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_sha256"].items() <= summary["artifact_sha256"].items()
    assert "NOT HARDWARE VERIFIED" in (artifact_dir / "summary.json").read_text(encoding="utf-8")
    assert "NOT HARDWARE VERIFIED" in report_path.read_text(encoding="utf-8")
    _assert_finite(summary)


def _assert_finite(value: object) -> None:
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for child in value.values():
            _assert_finite(child)
    elif isinstance(value, list):
        for child in value:
            _assert_finite(child)
