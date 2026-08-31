from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_single_strip_acceptance_campaign import (
    BASELINE_DIR,
    IDENTITY_METRIC_EVALUATORS,
    OUTPUT_DIR,
    generate,
)


@pytest.fixture(scope="module")
def plan():
    return json.loads((OUTPUT_DIR / "coverage-plan.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def baseline():
    return json.loads((BASELINE_DIR / "software-baseline.json").read_text(encoding="utf-8"))


def test_obs_01_identity_cues_have_family_specific_observable_signal(plan, baseline):
    metrics = baseline["cue_metrics"]
    identities = [row for row in plan["human_cues"] if row["role"] == "IDENTITY"]
    assert len(identities) == 22
    declared_metrics = {row["observability_metric"] for row in identities}
    assert declared_metrics == set(IDENTITY_METRIC_EVALUATORS)
    assert set(baseline["identity_observability"]) == {row["cue_id"] for row in identities}
    for row in identities:
        observed = metrics[row["cue_id"]]
        evidence = baseline["identity_observability"][row["cue_id"]]
        assert observed["frame_count"] > 0
        assert evidence["metric"] == row["observability_metric"]
        assert evidence["checks"]
        assert all(evidence["checks"].values()), row["cue_id"]
        assert evidence["result"] == "PASS"


def test_obs_01b_audio_video_and_history_semantics_are_not_generic_motion_checks(baseline):
    metrics = baseline["cue_metrics"]
    bass = metrics["FX_bass_pulse_IDENTITY"]["phase_mean_brightness"]
    assert bass["0"] >= max(bass["1"], bass["2"]) * 1.5

    routing = baseline["spectrum_band_routing"]
    assert set(routing) == {"bass", "mid", "treble"}
    assert all(item["result"] == "PASS" and all(item["checks"].values()) for item in routing.values())

    fusion = metrics["FX_video_audio_fusion_IDENTITY"]
    assert fusion["fusion_audio_axis_distance"] >= 0.02
    assert fusion["fusion_video_axis_distance"] >= 0.05

    history = metrics["FX_history_stream_IDENTITY"]
    assert history["history_expected_order_distance"] == pytest.approx(0.0, abs=1e-12)
    for actual, expected in zip(history["history_actual_order_rgb"], history["history_expected_order_rgb"]):
        assert actual == pytest.approx(expected)


def test_obs_02_contrast_pairs_are_measurably_distinct(baseline):
    distances = baseline["ab_sequence_distances"]
    assert distances
    for pair, distance in distances.items():
        if pair.startswith("live_only:"):
            assert distance > 0
        else:
            assert distance >= 0.01, (pair, distance)


def test_obs_02b_control_and_video_pairs_are_real_ab_evidence(baseline):
    distances = baseline["ab_sequence_distances"]
    assert distances["control:common_speed"] >= 0.01
    assert distances["control:common_intensity"] >= 0.05
    assert distances["video_color:average_vs_dominant"] >= 0.05


def test_obs_03_static_does_not_false_fail_for_low_temporal_variance(baseline):
    static = baseline["cue_metrics"]["FX_static_IDENTITY"]
    assert static["unique_frame_count"] == 1
    assert static["temporal_distance_max"] == 0
    assert static["brightness_max"] > 0.02


def test_obs_04_movement_effects_actually_move_on_ten_groups(baseline):
    metrics = baseline["cue_metrics"]
    assert metrics["FX_single_dot_IDENTITY"]["centroid_max"] - metrics["FX_single_dot_IDENTITY"]["centroid_min"] >= 8.0
    assert metrics["FX_comet_IDENTITY"]["centroid_max"] - metrics["FX_comet_IDENTITY"]["centroid_min"] >= 7.0
    assert metrics["FX_color_wipe_IDENTITY"]["lit_group_count_max"] - metrics["FX_color_wipe_IDENTITY"]["lit_group_count_min"] >= 8
    assert metrics["FX_theater_phase_IDENTITY"]["unique_frame_count"] == 3
    assert metrics["FX_chase_IDENTITY"]["unique_frame_count"] > 5


def test_obs_05_stateful_effects_have_sufficient_warmup(plan, baseline):
    rows = {row["cue_id"]: row for row in plan["human_cues"]}
    required = {
        "FX_heat_fire_IDENTITY": 3.0,
        "FX_history_stream_IDENTITY": 5.0,
        "FX_twinkle_IDENTITY": 1.0,
        "FX_video_ambient_IDENTITY": 1.0,
        "FX_video_audio_fusion_IDENTITY": 1.5,
    }
    for cue_id, minimum in required.items():
        assert rows[cue_id]["warmup_seconds"] >= minimum
        assert baseline["cue_metrics"][cue_id]["warmup_seconds_excluded"] >= minimum


def test_obs_06_selected_limit_cues_demonstrate_intended_pathology(baseline):
    metrics = baseline["cue_metrics"]
    assert metrics["FX_breath_LIMIT_min_full"]["unique_frame_count"] == 1
    assert metrics["FX_chase_LIMIT_full_width"]["lit_group_count_min"] >= 9
    assert metrics["FX_chase_LIMIT_full_width"]["lit_group_count_max"] == 10
    assert metrics["FX_coherent_noise_field_LIMIT_contrast_zero"]["spatial_variance_max"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["FX_history_stream_LIMIT_uniform_history"]["all_white_fraction"] > 0.5


def test_obs_07_no_accidental_all_black_identity_cue(plan, baseline):
    for row in plan["human_cues"]:
        if row["role"] == "IDENTITY":
            assert baseline["cue_metrics"][row["cue_id"]]["all_black_fraction"] < 0.2, row["cue_id"]


def test_obs_08_no_accidental_all_white_saturation_hides_identity(plan, baseline):
    for row in plan["human_cues"]:
        if row["role"] == "IDENTITY":
            assert baseline["cue_metrics"][row["cue_id"]]["all_white_fraction"] < 0.1, row["cue_id"]


def test_obs_09_a_b_pairs_are_not_functional_duplicates(baseline):
    duplicates = {pair: distance for pair, distance in baseline["ab_sequence_distances"].items() if distance == 0}
    assert duplicates == {}


def test_obs_10_deterministic_rerender_metrics_reproduce(tmp_path, baseline):
    generated = generate(tmp_path / "fixture", tmp_path / "baseline")
    rerender = json.loads(Path(generated["software_baseline"]).read_text(encoding="utf-8"))
    assert rerender == baseline
