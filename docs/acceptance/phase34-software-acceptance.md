# Phase 34 Branch Lifecycle Benchmark

Historical software benchmark for the Show v2 pre-roll branch lifecycle. It records a development-machine measurement and does not establish performance on RK3588 or physical lighting hardware.

## Environment and workload

- Environment: Windows 10 build 10.0.26200, CPython 3.11.9.
- Fixture: nine logical strips with 22, 22, 22, 22, 22, 22, 22, 22, and 24 groups (200 total), one visible parent cue, and 0, 1, 3, or 5 hidden `pre_roll` branches.
- Timing: 30 warmup frames and 120 measured frames. The separate three-frame `tracemalloc` sample is excluded from FPS timing.
- Representative effects: `chase` (cheap), `history_stream` (stateful), and `heat_fire` (heavy).

## Five hidden branches

| Effect | FPS | Mean | P95 | Mean overhead vs 0 branches | Peak allocation indicator |
| --- | ---: | ---: | ---: | ---: | ---: |
| `chase` | 224.523 | 4.454 ms | 5.495 ms | 271.0% | 258.8 KiB |
| `history_stream` | 252.653 | 3.958 ms | 4.539 ms | 259.4% | 259.7 KiB |
| `heat_fire` | 161.906 | 6.176 ms | 7.283 ms | 349.3% | 295.0 KiB |

The minimum across the representative effects was 161.906 FPS, above the benchmark's 30 FPS software gate on that development machine. Allocation values are Python `tracemalloc` indicators, not process RSS. The result does not measure RK3588 performance, transport, firmware, physical timing, or light output: **NOT HARDWARE VERIFIED**.

## Reproduction

Run from the repository root with the bundled interpreter:

```powershell
.\.python\Scripts\python.exe scripts\benchmarks\branch_lifecycle_benchmark.py --warmup-frames 30 --measured-frames 120 --memory-frames 3 --minimum-five-branch-fps 30 --output tmp\phase34-branch-lifecycle-benchmark.json
```

The script's default workload builds the same nine-strip, 200-group fixture. It prints the measured summary and writes the complete matrix to the selected output path.
