# Phase 4 鈥?Extended OutputTransform and Three-Tier Health Statistics

## Phase ID

phase-4-output-transform-health

## Goal

Complete Phase 4 from `docs/IMPLEMENTATION_PLAN.md`: extend `OutputTransform`, implement the approved three-tier output-health model, add health summaries, and send one safe frame during engine shutdown.

## Allowed Files

- light_engine/outputs/**
- light_engine/engine/__init__.py
- light_engine/cli/__init__.py
- tests/test_output_transform.py
- tests/test_output_health.py
- tests/test_engine.py
- tests/test_simulator.py
- tests/test_serial.py
- tests/test_udp.py
- tests/test_pipeline.py
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md

## Forbidden Files

- firmware/**
- light_engine/analysis/**
- light_engine/media/**
- light_engine/effects/**
- light_engine/mapping/**
- light_engine/models.py
- config/**
- .agent/**
- AGENTS.md
- CLAUDE.md
- pyproject.toml

## Acceptance Criteria

- Preserve single ownership of global brightness in `OutputTransform`.
- Add deterministic power limiting, gamma, per-zone WW/CW bias, and safe-frame generation.
- Never mutate input frames.
- Add `logical_frames_submitted`, `logical_frames_sent`, `packets_sent`, `frames_dropped`, `packets_dropped`, `last_error`, and `last_success_time`.
- `send_all()` increments only submitted counts.
- Backends own sent and packet counts without double counting.
- Add JSON-serializable `health_summary(outputs)`.
- Relevant CLI paths print final health summaries.
- Engine shutdown attempts exactly one all-black safe frame and always closes resources.
- Existing tests remain passing.
- No hardware-verification claim is made.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_output_transform.py tests/test_output_health.py tests/test_engine.py tests/test_serial.py tests/test_udp.py tests/test_simulator.py -q
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
```

## Commit Message

Phase 4: Extended OutputTransform and three-tier health statistics

