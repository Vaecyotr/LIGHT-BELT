"""Structural checks for the reproducible Phase 34 pre-roll benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.branch_lifecycle_benchmark import (
    STRIP_COUNT,
    STRIP_PIXEL_COUNTS,
    TOTAL_PIXELS,
    benchmark_matrix,
    build_workload,
)


def test_benchmark_fixture_is_nine_strips_two_hundred_total_and_keeps_five_branches_hidden() -> None:
    runtime, strips = build_workload("chase", 5)

    assert len(strips) == STRIP_COUNT == 9
    assert tuple(strip.pixel_count for strip in strips) == STRIP_PIXEL_COUNTS
    assert sum(strip.pixel_count for strip in strips) == TOTAL_PIXELS == 200
    cue = runtime.show.cues[0]
    assert len(cue.branches) == 5
    assert {branch.lifecycle for branch in cue.branches} == {"pre_roll"}
    assert {branch.after_target_id for branch in cue.branches} == {strips[-1].id}
    assert all(branch.target.ids == tuple(strip.id for strip in strips) for branch in cue.branches)
    assert runtime.jobs[0]._branch_jobs[0].release_progress == 1.0


def test_benchmark_smoke_report_has_timing_overhead_and_memory_indicators() -> None:
    report = benchmark_matrix(
        effects=(("cheap", "static"),),
        branch_counts=(0, 5),
        warmup_frames=1,
        measured_frames=3,
        memory_frames=1,
        minimum_five_branch_fps=0.0,
    )

    cases = report["cases"]
    assert len(cases) == 2
    assert [case["hidden_branch_count"] for case in cases] == [0, 5]
    assert cases[0]["relative_mean_overhead_percent"] == 0.0
    for case in cases:
        assert case["fps"] > 0.0
        assert case["mean_ms"] > 0.0
        assert case["p95_ms"] > 0.0
        assert case["tracemalloc_retained_kib"] > 0.0
        assert case["tracemalloc_peak_kib"] >= case["tracemalloc_retained_kib"]
    assert report["five_hidden_branch_gate"]["passed"] is True
    assert report["hardware_verified"] is False


def test_adopted_benchmark_evidence_records_the_conservative_gate() -> None:
    evidence = json.loads(
        Path("artifacts/baselines/phase34-branch-lifecycle/benchmark.json").read_text(
            encoding="utf-8"
        )
    )

    assert evidence["workload"]["strip_count"] == 9
    assert sum(evidence["workload"]["strip_pixel_counts"]) == 200
    assert evidence["workload"]["hidden_branch_counts"] == [0, 1, 3, 5]
    assert evidence["workload"]["effects"] == [
        {"class": "cheap", "id": "chase"},
        {"class": "stateful", "id": "history_stream"},
        {"class": "heavy", "id": "heat_fire"},
    ]
    gate = evidence["five_hidden_branch_gate"]
    assert gate["minimum_observed_fps"] >= gate["minimum_required_fps"] == 30.0
    assert gate["passed"] is True
    assert evidence["hardware_verified"] is False
