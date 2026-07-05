# Phase 7 — Media Clock Integration

## Phase ID

phase-7-media-clock

## Goal

Complete Phase 7 from `docs/IMPLEMENTATION_PLAN.md`: injectable clock ownership, mpv JSON IPC support, seek/pause/end handling, and explicit failure behavior.

## Allowed Files

- light_engine/clock.py
- light_engine/engine/__init__.py
- light_engine/media/mpv_adapter.py
- light_engine/media/__init__.py
- light_engine/cli/__init__.py
- tests/test_clock.py
- tests/test_clock_integration.py
- tests/test_engine.py
- docs/rk3588_deployment.md
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md

## Forbidden Files

- firmware/**
- light_engine/analysis/**
- light_engine/effects/**
- light_engine/outputs/**
- config/layout.yaml
- .agent/**
- AGENTS.md
- CLAUDE.md

## Acceptance Criteria

- Engine accepts an injected Clock.
- Internal, fake, offline-render, and mpv clock paths remain explicit.
- Seek resets analyzer/effect state without changing sequence ownership.
- Pause behavior is deterministic and tested.
- End-of-media exits cleanly.
- mpv connection or process failure raises an explicit error and never silently falls back.
- Add CLI clock selection and `run-mpv`.
- RK3588 deployment documentation is marked NOT HARDWARE VERIFIED.
- Full test suite remains passing.

## Required Targeted Tests

```powershell
.\.python\python.exe -m pytest tests/test_clock.py tests/test_clock_integration.py tests/test_engine.py -q
```

## Required Full Verification

```powershell
.\.python\python.exe -m pytest -q
git diff --check
```

## Commit Message

Phase 7: Media clock integration with mpv IPC support
