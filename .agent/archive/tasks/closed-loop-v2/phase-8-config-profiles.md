# Phase 8 鈥?Configuration Upgrade and Dual Profiles

## Phase ID

phase-8-config-profiles

## Goal

Complete Phase 8 from `docs/IMPLEMENTATION_PLAN.md`: strict v2 configuration validation, Windows and RK3588 profiles, and PhysicalFrame views for JSON and simulator outputs.

## Allowed Files

- config/**
- light_engine/config/**
- light_engine/outputs/json_output.py
- light_engine/simulator/**
- light_engine/cli/__init__.py
- tests/test_config.py
- tests/test_config_validation.py
- tests/test_json_output.py
- tests/test_simulator.py
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md
- docs/rk3588_deployment.md

## Forbidden Files

- firmware/**
- light_engine/analysis/**
- light_engine/media/**
- light_engine/effects/**
- .agent/**
- AGENTS.md
- CLAUDE.md

## Acceptance Criteria

- Add complete analog-node, digital-node, and digital-segment configuration.
- Add output mode, exit safe state, clock mode, and platform fields.
- Add Windows development and RK3588 production profiles.
- Invalid config errors include path, field, value, and expected constraint.
- JSON output serializes PhysicalFrame node grouping.
- Simulator displays physical node grouping.
- Logical-region information remains available through metadata where required.
- Both profiles load successfully in tests.
- Production profile does not claim real-device verification.
- Full test suite remains passing.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_config.py tests/test_config_validation.py tests/test_json_output.py tests/test_simulator.py -q
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
```

## Commit Message

Phase 8: Configuration upgrade with dual profiles and PhysicalFrame views

