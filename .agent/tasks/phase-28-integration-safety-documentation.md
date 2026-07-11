# Phase 28 — Integration, Safety, and Documentation

## Phase ID

phase-28-integration-safety-documentation

## Goal

Finish production integration, dependency declarations, inspectability, examples, and operator documentation for the Show v2 and UDP v3 cabin architecture without changing its locked contracts.

## Background

The implementation must be operable without guessing whether an authored region resolves to a logical strip, physical ESP32 output, or GPIO. Production transports must fail explicitly and development transports must be selected explicitly.

## Binding Contract References

- `CLAUDE.md`
- `docs/CLOSED_LOOP_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md` Phase 28
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Declare required production packages, including pyserial, in project metadata and validate supported installation paths.
- Make production transport initialization failures explicit; memory/fake transports require explicit configuration or dependency injection.
- Update cabin Show v2, layout, output, development, and production examples with no real secrets, final IPs, or serial paths.
- Add/extend an inspect command that traces each virtual-path region through logical ID, physical label, node ID, output ID, GPIO, length, host/port placeholder, and enabled state.
- Document ID namespaces, effect extension, ColorSpec authoring, branch/origin behavior, ESP32 wiring, power/common-ground requirements, deployment, and troubleshooting.
- Audit legacy examples/docs: retain useful development history, label superseded material clearly, and remove only files proven redundant and unreferenced.

## Out of Scope

- Show/protocol/firmware redesign, new Host API endpoints, final site wiring values, hardware validation, or rewriting acceptance baselines.
- Silent fallback of any production output.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- pyproject.toml
- light_engine/config/**
- light_engine/outputs/**
- light_engine/cli/**
- light_engine/__main__.py
- config/**
- examples/**
- docs/**
- README.md
- INSTALL_AND_RUN.md
- tests/test_config_validation.py
- tests/test_output_safety.py
- tests/test_cli.py
- tests/test_inspect*.py

## Forbidden Files

- firmware/**
- light_engine/show/**
- light_engine/effects/**
- light_engine/mapping/**
- artifacts/**
- .agent/**
- docs/contracts/**
- tests/goldens/**

## Binding Quality Constraints

- Inspect output MUST be derived from validated config, never a duplicated hardcoded mapping table.
- Examples MUST use schema fields actually implemented by prior Phases.
- Production failures MUST be observable and test-covered; no test/environment-name branches or fake success.
- Deletion requires an explicit unreferenced/generated/obsolete justification in the report.

## Acceptance Criteria

- A user can validate and inspect the cabin config and identify the exact provisional ESP32/GPIO for every strip.
- Production dependency and failure tests pass; development memory mode remains explicit and usable.
- Documentation clearly separates confirmed software behavior, provisional wiring, and `NOT HARDWARE VERIFIED` behavior.
- Legacy material that remains cannot be mistaken for current architecture.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_config_validation.py tests/test_output_safety.py tests/test_cli.py -q
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Report dependency changes, inspect evidence for all 14 runs, examples/docs updated, retained/deleted legacy inventory with reasons, exact commands/return codes/test count/time/benchmark, traceability, limitations, and `git diff --stat`.

## Commit Message

Phase 28: Complete cabin integration and documentation
