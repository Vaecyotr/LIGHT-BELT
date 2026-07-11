# Phase 29 — V3 End-to-end Acceptance

## Phase ID

phase-29-v3-e2e-acceptance

## Goal

Produce deterministic software acceptance evidence for the complete cabin Show v2, multi-output mapping, UDP v3, and firmware contract without modifying production behavior.

## Background

This is an evidence-only gate. Missing functionality is a BLOCKER to report back to the owning Phase, not permission to patch production code in acceptance.

## Binding Contract References

- `CLAUDE.md`
- `docs/CLOSED_LOOP_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md` Phase 29
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add acceptance config/fixtures/tests for 13 digital strips totaling 260 groups and one RGB+CCT `zone_32`.
- Verify three or more virtual paths cover all 14 runs and traverse multiple ESP32 nodes.
- Verify completion of `strip_41` releases 42/43/44/45/93 in the same logical frame.
- Verify per-node complete multi-output frames, independent lengths, single refresh ownership, shared sequence/media timestamp, and v3 Golden consistency.
- Verify CRC failure, unknown output, incomplete output set, duplicate/stale/out-of-order sequence, uint32 wrap, maximum length, timeout, and safe black behavior.
- Run deterministic replay, full pytest, benchmark, Golden generation/check, native firmware tests, and PlatformIO firmware builds.
- Publish evidence split into software verified, not hardware verified, and configurable/final wiring decisions.

## Out of Scope

- Any production code, firmware source, authoritative contract, protocol, schema, dependency, or runtime config fix.
- Claiming real ESP32, WS2811, STM32, RS-485, network, power, or synchronization verification.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- tests/test_cabin_v3_e2e_acceptance.py
- tests/fixtures/cabin_v3/**
- config/cabin_v3_acceptance.yaml
- config/show_cabin_v3_acceptance.yaml
- artifacts/cabin_v3_acceptance/**
- docs/cabin_v3_acceptance_report.md

## Forbidden Files

- light_engine/**
- firmware/**
- pyproject.toml
- config/layout.yaml
- config/outputs.yaml
- config/show.example.yaml
- docs/CLOSED_LOOP_SPEC.md
- docs/IMPLEMENTATION_PLAN.md
- CLAUDE.md
- .agent/**
- scripts/**
- tests/goldens/show_orchestration/v1/**

## Binding Quality Constraints

- Acceptance MUST fail on missing behavior; it MUST NOT weaken assertions, regenerate expected values from the implementation under test, add skips/xfails, or modify production code.
- Golden JSON/header hashes and every command return code MUST be recorded.
- Performance evidence MUST state machine dependence and MUST NOT be presented as hardware timing verification.

## Acceptance Criteria

- All topology, branch, sequence, timestamp, protocol, error, safety, build, and deterministic replay assertions pass.
- The acceptance report accounts for exactly 13 digital strips, 260 groups, one analog zone, five provisional ESP32 nodes, and every configured GPIO.
- No forbidden file changes.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_cabin_v3_e2e_acceptance.py -v
pio test -d firmware/esp32_ws2811_node -e native
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
pio test -d firmware/esp32_ws2811_node -e native
pio run -d firmware/esp32_ws2811_node
pio run -d firmware/stm32_rgbcct_node
git diff --check
git status --short
git diff --stat
```

## Required Report

Report topology totals, branch and cross-node evidence, protocol/Golden hashes, deterministic replay digest, exact commands/return codes/test count/time/benchmark/build results, traceability, three-way verification classification, blockers, and `git diff --stat`.

## Commit Message

Phase 29: Add cabin UDP v3 acceptance evidence
