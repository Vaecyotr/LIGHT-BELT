# Phase 10 鈥?End-to-End Acceptance

## Phase ID

phase-10-e2e-acceptance

## Goal

Complete Phase 10 from `docs/IMPLEMENTATION_PLAN.md`: a deterministic ten-second video-and-audio, no-hardware, end-to-end acceptance path and final evidence report.

## Allowed Files

- tests/test_e2e_acceptance.py
- tests/fixtures/**
- scripts/**
- docs/acceptance_report.md
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md
- docs/rk3588_deployment.md

## Forbidden Files

- firmware/**
- light_engine/**
- config/**
- .agent/**
- AGENTS.md
- CLAUDE.md
- pyproject.toml

## Acceptance Criteria

- Generate or use deterministic ten-second video and audio fixtures.
- Run `video_audio_fusion` through fake RS-485 v2, fake UDP v2, and JSON outputs.
- Produce approximately 300鈥?01 logical frames at 30 FPS.
- Each normal frame produces six RS-485 packets and one UDP datagram.
- Same-frame sequence values agree across protocols.
- All protocol packets decode successfully.
- No NaN or infinity appears.
- Latest-frame queues do not accumulate stale frames.
- Exactly one all-black SAFE_STATE frame is emitted at shutdown.
- Full Python tests pass.
- Both firmware projects compile.
- Acceptance report includes commands, return codes, test totals, benchmark P50/P95/P99, limitations, and NOT HARDWARE VERIFIED.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_e2e_acceptance.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
git diff --check
```

## Commit Message

Phase 10: End-to-end acceptance tests

