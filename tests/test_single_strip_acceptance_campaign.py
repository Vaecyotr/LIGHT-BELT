from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

import pytest
import yaml

from light_engine.config import Config
from light_engine.effects import list_effect_registrations
from light_engine.mapping import Layout
from light_engine.show import TargetCatalog, load_show
from scripts.generate_single_strip_acceptance_campaign import (
    ALLOWED_COVERAGE,
    BASELINE_DIR,
    EFFECT_DESIGN,
    OUTPUT_DIR,
    PROFILE_PATH,
    TARGET_ID,
    generate,
    scalar_sources,
)


SHOW_FILES = ("baseline-show.yaml", "live-audio-show.yaml", "video-fusion-show.yaml")


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plan():
    return _json(OUTPUT_DIR / "coverage-plan.json")


@pytest.fixture(scope="module")
def baseline():
    return _json(BASELINE_DIR / "software-baseline.json")


def _shows():
    return {
        name: yaml.safe_load((OUTPUT_DIR / name).read_text(encoding="utf-8"))
        for name in SHOW_FILES
    }


def test_acc_01_generator_is_deterministic_and_checked_in_outputs_match(tmp_path):
    first_out, first_base = tmp_path / "first", tmp_path / "first-baseline"
    second_out, second_base = tmp_path / "second", tmp_path / "second-baseline"
    generate(first_out, first_base)
    generate(second_out, second_base)
    relative_files = [*SHOW_FILES, "coverage-plan.json", "README.md"]
    for name in relative_files:
        first = (first_out / name).read_bytes()
        assert first == (second_out / name).read_bytes()
        assert first == (OUTPUT_DIR / name).read_bytes()
    evidence = (first_base / "software-baseline.json").read_bytes()
    assert evidence == (second_base / "software-baseline.json").read_bytes()
    assert evidence == (BASELINE_DIR / "software-baseline.json").read_bytes()


def test_acc_02_all_three_shows_validate_against_live_profile():
    Config.reset()
    config = Config.get_instance(PROFILE_PATH)
    layout = Layout.from_config(config)
    catalog = TargetCatalog.from_layout(layout)
    loaded = [load_show(OUTPUT_DIR / name, catalog) for name in SHOW_FILES]
    assert [show.id for show in loaded] == [
        "single-strip-visual-v1-baseline",
        "single-strip-visual-v1-audio",
        "single-strip-visual-v1-video",
    ]


def test_acc_03_04_17_only_live_strip_31_is_targeted_and_topology_is_not_redefined():
    shows = _shows()
    for document in shows.values():
        show = document["show"]
        assert "virtual_paths" not in show
        for cue in show["cues"]:
            assert cue["target"] == {"type": "digital_strip", "id": TARGET_ID}
        for track in show.get("brightness_tracks", []):
            assert track["target"] == {"type": "digital_strip", "id": TARGET_ID}
    profile = yaml.safe_load(PROFILE_PATH.read_text(encoding="utf-8"))
    strip = next(item for item in profile["layout"]["strips"] if item["id"] == TARGET_ID)
    assert strip["type"] == "digital"
    assert strip["pixel_count"] == 10
    assert len(profile["layout"]["strips"]) == 9


def test_acc_05_06_effect_inventory_equals_live_registry_and_each_effect_has_identity(plan):
    live = list_effect_registrations()
    assert [item["id"] for item in plan["effect_inventory"]] == [item.id for item in live]
    assert set(EFFECT_DESIGN) == {item.id for item in live}
    assert all(item["identity_cue_ids"] for item in plan["effect_inventory"])


def test_acc_07_every_effect_has_a_distinct_contrast_pair(plan, baseline):
    contrast_rows = [row for row in plan["human_cues"] if row["role"] == "CONTRAST"]
    pair_counts: dict[str, int] = {}
    for row in contrast_rows:
        if row["pair_id"]:
            pair_counts[row["pair_id"]] = pair_counts.get(row["pair_id"], 0) + 1
    assert all(count == 2 for count in pair_counts.values())
    expected_effects = set(EFFECT_DESIGN)
    represented = {pair.split(":", 1)[0] for pair in pair_counts if not pair.startswith("live_only:")}
    assert expected_effects <= represented
    assert all(math.isfinite(value) and value > 0 for value in baseline["ab_sequence_distances"].values())


def test_acc_08_all_parameter_specs_have_executed_machine_boundary_records(plan):
    live_count = sum(len(item.parameter_specs) for item in list_effect_registrations())
    assert len(plan["parameter_inventory"]) == live_count == 111
    for item in plan["parameter_inventory"]:
        assert item["machine_coverage"] == "FULL"
        assert {case["id"] for case in item["machine_cases"]} >= {"omitted_default", "representative", "invalid_type"}
        assert all(case["expected"] == case["observed"] for case in item["machine_cases"])
        if item["kind"] in {"float", "integer"}:
            assert {"nan", "positive_inf", "negative_inf"} <= {case["id"] for case in item["machine_cases"]}


def test_acc_09_all_live_modulatable_parameters_have_cues(plan):
    live = {
        f"{registration.id}.{spec.name}"
        for registration in list_effect_registrations()
        for spec in registration.parameter_specs
        if spec.modulatable
    }
    manifest = {item["id"] for item in plan["modulatable_inventory"]}
    assert manifest == live
    assert len(manifest) == 11
    assert all(item["cue_ids"] for item in plan["modulatable_inventory"])
    evidence = plan["parameter_modulation_machine_evidence"]
    assert {item["target"] for item in evidence} == live
    assert {item["mode"] for item in evidence} == {"drive", "modulate"}
    assert all(item["result"] == "PASS" for item in evidence)
    assert all(item["observed_value"] == pytest.approx(item["expected_value"]) for item in evidence)
    for item in plan["modulatable_inventory"]:
        target_evidence = [record for record in evidence if record["target"] == item["id"]]
        assert item["modes"] == sorted({record["mode"] for record in target_evidence})
        assert set(item["machine_evidence_ids"]) == {record["id"] for record in target_evidence}


def test_acc_10_all_live_color_sources_have_explicit_consumer_and_fallback_records(plan):
    inventory = {item["type"]: item for item in plan["color_source_inventory"]}
    assert set(inventory) == {
        "timeline", "spatial_palette", "video_average", "video_dominant",
        "audio_spectrum_palette", "dominant_frequency_palette",
    }
    assert "EVENT" in inventory["timeline"]["consumer_families"]
    assert "POSITIONAL" in inventory["spatial_palette"]["consumer_families"]
    assert all(item["cue_ids"] for item in inventory.values())
    assert all(
        item["fallback_required"]
        for key, item in inventory.items()
        if key in {"video_average", "video_dominant", "audio_spectrum_palette", "dominant_frequency_palette"}
    )


def test_acc_11_12_all_scalar_sources_and_native_consumers_have_records(plan):
    inventory = plan["scalar_source_inventory"]
    assert [item["source"] for item in inventory] == scalar_sources()
    assert len(inventory) == 25
    evidence = {item["source"]: item for item in plan["scalar_source_machine_evidence"]}
    assert set(evidence) == set(scalar_sources())
    assert all(item["result"] == "PASS" for item in evidence.values())
    assert all(item["observed_value"] == item["injected_value"] for item in evidence.values())
    assert evidence["cue_progress"]["missing_optional"] == 0.0
    for source, item in evidence.items():
        if source != "cue_progress":
            assert item["missing_optional"] is None
        assert item["missing_sample"] == 0.0
    assert set(inventory[0]["consumer_fields"]) == {
        "color_wipe.progress_source", "twinkle.event_gate_source",
        "twinkle.birth_gain_source", "history_stream.sample_gain_source",
        "parameter_modulation",
    }
    assert all(item["machine_evidence_id"] == evidence[item["source"]]["id"] for item in inventory)
    assert next(item for item in inventory if item["source"] == "audio.spectrum[15]")["cue_ids"] == []
    assert len(plan["parameter_modulation_source_inventory"]) == 28


def test_acc_12b_show_controls_use_real_overlap_priority_and_common_fields(plan):
    shows = _shows()
    cues = {cue["id"]: cue for cue in shows["baseline-show.yaml"]["show"]["cues"]}
    assert cues["CONTROL_blend_replace_base"]["start"] == cues["CONTROL_blend_replace_overlay"]["start"]
    assert cues["CONTROL_blend_add_base"]["start"] == cues["CONTROL_blend_add_overlay"]["start"]
    assert cues["CONTROL_priority_blue_wins_blue"]["priority"] > cues["CONTROL_priority_blue_wins_red"]["priority"]
    assert cues["CONTROL_priority_red_wins_red"]["priority"] > cues["CONTROL_priority_red_wins_blue"]["priority"]
    assert cues["CONTROL_common_speed_low"]["effect"]["speed"] == 0.5
    assert cues["CONTROL_common_speed_high"]["effect"]["speed"] == 2.0
    assert cues["CONTROL_common_speed_low"]["effect"]["params"]["speed"] == 2.0
    assert cues["CONTROL_common_intensity_low"]["effect"]["intensity"] == 0.25
    assert cues["CONTROL_common_intensity_high"]["effect"]["intensity"] == 1.0
    evidence = {item["id"]: item for item in plan["show_control_machine_evidence"]}
    assert set(evidence) == {"show_control:blend", "show_control:priority", "show_control:common_speed", "show_control:common_intensity"}
    assert all(item["result"] == "PASS" for item in evidence.values())
    capability_ids = {item["id"] for item in plan["capabilities"]}
    assert {"show:transition", "show:blend", "show:priority", "show:common_speed", "show:common_intensity"} <= capability_ids


def test_acc_13_media_fallback_is_never_counted_full(plan):
    fallback_rows = [row for row in plan["human_cues"] if "fallback" in row["cue_id"].lower()]
    assert fallback_rows
    assert all(row["single_strip_hardware_coverage"] == "FALLBACK_ONLY" for row in fallback_rows)
    assert plan["hardware_verified"] is False


def test_acc_13b_fallback_and_video_average_dominant_are_executed(baseline):
    assert baseline["cue_metrics"]["AUD_COLOR_fallback"]["first_pixel_rgb"] == pytest.approx([0.72, 0.04, 0.46])
    assert baseline["cue_metrics"]["VID_COLOR_fallback"]["first_pixel_rgb"] == pytest.approx([0.72, 0.04, 0.46])
    assert baseline["ab_sequence_distances"]["video_color:average_vs_dominant"] >= 0.05


def test_acc_14_single_strip_limitations_cannot_be_full(plan):
    limits = [cap for cap in plan["capabilities"] if cap["category"] == "single_strip_limit"]
    assert len(limits) >= 7
    assert all(cap["single_strip_hardware_coverage"] == "NOT_COVERABLE_SINGLE_STRIP" for cap in limits)
    assert all(cap["software_coverage"] != "FULL" for cap in limits)


def test_acc_15_cue_ids_are_semantic_and_unique(plan):
    cue_ids = [row["cue_id"] for row in plan["human_cues"]]
    assert len(cue_ids) == len(set(cue_ids))
    assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]+", cue_id) for cue_id in cue_ids)
    assert not any(re.fullmatch(r"(?:cue|test|demo)_?\d+", cue_id, re.I) for cue_id in cue_ids)


def test_acc_16_all_shows_end_with_fade_black_and_black_hold():
    expected_prefixes = {
        "baseline-show.yaml": "BASELINE",
        "live-audio-show.yaml": "AUDIO",
        "video-fusion-show.yaml": "VIDEO",
    }
    for name, document in _shows().items():
        final = document["show"]["cues"][-2:]
        prefix = expected_prefixes[name]
        assert [cue["id"] for cue in final] == [f"{prefix}_SAFE_fade_to_black", f"{prefix}_SAFE_black_hold"]
        assert all(cue["effect"]["id"] == "static" for cue in final)
        fade, hold = final
        assert fade["effect"]["params"]["color"] != [0.0, 0.0, 0.0]
        assert fade["transition"]["fade_out"] == fade["end"] - fade["start"]
        assert hold["effect"]["params"]["color"] == [0.0, 0.0, 0.0]
        assert hold["transition"]["fade_in"] == 0.0


def test_acc_18_19_coverage_has_no_orphan_or_missing_generated_cue(plan):
    generated = {row["cue_id"] for row in plan["human_cues"]}
    referenced = {cue_id for cap in plan["capabilities"] for cue_id in cap["cue_ids"]}
    assert referenced == generated


def test_acc_20_all_generated_frames_are_finite_and_evidence_is_software_only(baseline):
    assert baseline["hardware_verified"] is False
    assert baseline["evidence_kind"] == "deterministic software observability only"
    assert len(baseline["cue_metrics"]) == sum(baseline["cue_counts"].values())
    for metrics in baseline["cue_metrics"].values():
        assert metrics["finite"] is True
        for key, value in metrics.items():
            if isinstance(value, float):
                assert math.isfinite(value), key


def test_generated_show_hashes_match_software_baseline(baseline):
    mapping = {
        "baseline": "baseline-show.yaml",
        "audio": "live-audio-show.yaml",
        "video": "video-fusion-show.yaml",
    }
    assert baseline["show_sha256"] == {
        part: hashlib.sha256((OUTPUT_DIR / filename).read_bytes()).hexdigest()
        for part, filename in mapping.items()
    }


def test_all_coverage_classifications_are_from_the_closed_vocabulary(plan):
    values = {
        value
        for capability in plan["capabilities"]
        for value in (capability["software_coverage"], capability["single_strip_hardware_coverage"])
    }
    assert values <= ALLOWED_COVERAGE
