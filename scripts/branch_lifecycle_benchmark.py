"""Focused Phase 34 benchmark for hidden ``pre_roll`` branch cost.

This is a software-capacity benchmark, not a real-time scheduler or hardware
test.  Each workload renders one parent cue over an authored virtual path of
nine strips containing about 200 logical groups in total.  Every hidden branch
owns an independent effect instance and targets the same 200 logical pixels,
but is held before its existing ``after`` release point for the whole
measurement.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import platform
import sys
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from light_engine.mapping import ZoneDef
from light_engine.models import EffectContext
from light_engine.show import (
    Cue,
    CueBranchSpec,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetResolver,
    TargetSelector,
    VirtualPathSpec,
    black_base_frame,
)


STRIP_COUNT = 9
# A representative nine-output logical topology with 200 groups total.
STRIP_PIXEL_COUNTS = (22, 22, 22, 22, 22, 22, 22, 22, 24)
TOTAL_PIXELS = sum(STRIP_PIXEL_COUNTS)
FPS = 30.0
BRANCH_COUNTS = (0, 1, 3, 5)
EFFECTS = (
    ("cheap", "chase"),
    ("stateful", "history_stream"),
    ("heavy", "heat_fire"),
)
DEFAULT_OUTPUT = Path("artifacts/runs/phase34-branch-lifecycle/benchmark.json")


@dataclass(frozen=True)
class CaseResult:
    effect_class: str
    effect_id: str
    hidden_branch_count: int
    frames: int
    fps: float
    mean_ms: float
    p95_ms: float
    relative_mean_overhead_percent: float
    tracemalloc_retained_kib: float
    tracemalloc_peak_kib: float


def build_workload(effect_id: str, hidden_branch_count: int) -> tuple[ShowRuntime, tuple[ZoneDef, ...]]:
    """Build one deterministic all-digital workload with unreleased branches."""

    if hidden_branch_count < 0:
        raise ValueError("hidden_branch_count must be >= 0")
    strips = tuple(
        ZoneDef(id=f"strip_{index}", pixel_count=pixel_count)
        for index, pixel_count in enumerate(STRIP_PIXEL_COUNTS)
    )
    path = VirtualPathSpec(
        id="benchmark_path",
        targets=tuple(
            TargetSelector("digital_strip", id=strip.id) for strip in strips
        ),
    )
    branch_target = TargetSelector(
        "digital_set",
        ids=tuple(strip.id for strip in strips),
    )
    branches = tuple(
        CueBranchSpec(
            path_id=path.id,
            after_target_id=strips[-1].id,
            target=branch_target,
            lifecycle="pre_roll",
        )
        for _ in range(hidden_branch_count)
    )
    cue = Cue(
        id=f"benchmark-{effect_id}-{hidden_branch_count}",
        start=0.0,
        end=3600.0,
        target=TargetSelector("virtual_path", id=path.id),
        effect=EffectSpec(mode="fixed", id=effect_id),
        branches=branches,
    )
    show = ShowDefinition(
        schema_version=2,
        id="phase34-branch-lifecycle-benchmark",
        duration=3600.0,
        cues=(cue,),
        virtual_paths=(path,),
    )
    return ShowRuntime(show, TargetResolver((), strips), seed=34), strips


def _render_frame(runtime: ShowRuntime, strips: tuple[ZoneDef, ...], sequence: int) -> None:
    timestamp = sequence / FPS
    base = black_base_frame(
        timestamp=timestamp,
        sequence=sequence,
        analog_zones=(),
        digital_strips=strips,
    )
    runtime.render(
        EffectContext(timestamp=timestamp, delta_time=1.0 / FPS, sequence=sequence),
        base,
    )


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _timing_sample(
    effect_id: str,
    hidden_branch_count: int,
    *,
    warmup_frames: int,
    measured_frames: int,
) -> tuple[float, float, float]:
    runtime, strips = build_workload(effect_id, hidden_branch_count)
    for sequence in range(warmup_frames):
        _render_frame(runtime, strips, sequence)

    durations_ms: list[float] = []
    gc.collect()
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        started = time.perf_counter_ns()
        for offset in range(measured_frames):
            before = time.perf_counter_ns()
            _render_frame(runtime, strips, warmup_frames + offset)
            durations_ms.append((time.perf_counter_ns() - before) / 1_000_000.0)
        elapsed_seconds = (time.perf_counter_ns() - started) / 1_000_000_000.0
    finally:
        if gc_was_enabled:
            gc.enable()
    mean_ms = elapsed_seconds * 1000.0 / measured_frames
    return measured_frames / elapsed_seconds, mean_ms, _percentile(durations_ms, 95.0)


def _memory_sample(
    effect_id: str,
    hidden_branch_count: int,
    *,
    frames: int,
) -> tuple[float, float]:
    gc.collect()
    tracemalloc.start()
    try:
        runtime, strips = build_workload(effect_id, hidden_branch_count)
        for sequence in range(frames):
            _render_frame(runtime, strips, sequence)
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return current / 1024.0, peak / 1024.0


def benchmark_matrix(
    *,
    effects: Iterable[tuple[str, str]] = EFFECTS,
    branch_counts: Iterable[int] = BRANCH_COUNTS,
    warmup_frames: int = 30,
    measured_frames: int = 120,
    memory_frames: int = 3,
    minimum_five_branch_fps: float = 30.0,
) -> dict[str, object]:
    """Measure the complete matrix and return a JSON-serializable report."""

    if min(warmup_frames, measured_frames, memory_frames) < 1:
        raise ValueError("all frame counts must be >= 1")
    effect_items = tuple(effects)
    count_items = tuple(branch_counts)
    cases: list[CaseResult] = []
    baselines: dict[str, float] = {}
    for effect_class, effect_id in effect_items:
        for branch_count in count_items:
            fps, mean_ms, p95_ms = _timing_sample(
                effect_id,
                branch_count,
                warmup_frames=warmup_frames,
                measured_frames=measured_frames,
            )
            retained_kib, peak_kib = _memory_sample(
                effect_id,
                branch_count,
                frames=memory_frames,
            )
            if branch_count == 0:
                baselines[effect_id] = mean_ms
            baseline_ms = baselines.get(effect_id)
            if baseline_ms is None:
                raise ValueError("branch_counts must place zero before nonzero counts")
            overhead = ((mean_ms / baseline_ms) - 1.0) * 100.0
            cases.append(
                CaseResult(
                    effect_class=effect_class,
                    effect_id=effect_id,
                    hidden_branch_count=branch_count,
                    frames=measured_frames,
                    fps=round(fps, 3),
                    mean_ms=round(mean_ms, 3),
                    p95_ms=round(p95_ms, 3),
                    relative_mean_overhead_percent=round(overhead, 1),
                    tracemalloc_retained_kib=round(retained_kib, 1),
                    tracemalloc_peak_kib=round(peak_kib, 1),
                )
            )

    five_branch_fps = [
        case.fps for case in cases if case.hidden_branch_count == 5
    ]
    if not five_branch_fps:
        raise ValueError("branch_counts must include the five-branch gate")
    minimum_observed = min(five_branch_fps)
    return {
        "schema_version": 1,
        "scope": "Phase 34 hidden pre_roll software capacity",
        "hardware_verified": False,
        "environment": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
        },
        "workload": {
            "strip_count": STRIP_COUNT,
            "strip_pixel_counts": list(STRIP_PIXEL_COUNTS),
            "total_pixels_per_effect_instance": TOTAL_PIXELS,
            "parent_cues": 1,
            "hidden_branch_counts": list(count_items),
            "effects": [
                {"class": effect_class, "id": effect_id}
                for effect_class, effect_id in effect_items
            ],
            "warmup_frames": warmup_frames,
            "measured_frames": measured_frames,
            "memory_frames": memory_frames,
        },
        "cases": [asdict(case) for case in cases],
        "five_hidden_branch_gate": {
            "minimum_required_fps": minimum_five_branch_fps,
            "minimum_observed_fps": minimum_observed,
            "passed": minimum_observed >= minimum_five_branch_fps,
            "basis": "minimum across cheap, stateful, and heavy representative effects",
        },
        "limitations": [
            "Current Windows/Python development-machine measurement only.",
            "tracemalloc retained/peak values are Python allocation indicators, not process RSS.",
            "No transport, protocol, firmware, physical timing, or RK3588 behavior is measured.",
            "NOT HARDWARE VERIFIED.",
        ],
    }


def _print_summary(report: dict[str, object]) -> None:
    print("effect       class      hidden       FPS    mean ms     P95 ms   overhead     peak KiB")
    for case in report["cases"]:  # type: ignore[index]
        print(
            f"{case['effect_id']:<12} {case['effect_class']:<10} "
            f"{case['hidden_branch_count']:>6} {case['fps']:>9.3f} "
            f"{case['mean_ms']:>10.3f} {case['p95_ms']:>10.3f} "
            f"{case['relative_mean_overhead_percent']:>9.1f}% "
            f"{case['tracemalloc_peak_kib']:>12.1f}"
        )
    gate = report["five_hidden_branch_gate"]  # type: ignore[index]
    print(
        f"five-hidden minimum: {gate['minimum_observed_fps']:.3f} FPS; "
        f"required: {gate['minimum_required_fps']:.3f} FPS; "
        f"passed={gate['passed']}"
    )
    print("NOT HARDWARE VERIFIED")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warmup-frames", type=int, default=30)
    parser.add_argument("--measured-frames", type=int, default=120)
    parser.add_argument(
        "--memory-frames",
        type=int,
        default=3,
        help="short, separate tracemalloc sample; FPS timing never enables tracemalloc",
    )
    parser.add_argument("--minimum-five-branch-fps", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = benchmark_matrix(
        warmup_frames=args.warmup_frames,
        measured_frames=args.measured_frames,
        memory_frames=args.memory_frames,
        minimum_five_branch_fps=args.minimum_five_branch_fps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _print_summary(report)
    return 0 if report["five_hidden_branch_gate"]["passed"] else 1  # type: ignore[index]


if __name__ == "__main__":
    raise SystemExit(main())
