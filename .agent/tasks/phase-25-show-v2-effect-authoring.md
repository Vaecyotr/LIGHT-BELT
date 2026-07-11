# Phase 25 — Show V2 and Effect Authoring

## Phase ID

phase-25-show-v2-effect-authoring

## Goal

Introduce canonical Show v2 authoring for unambiguous targets, independently selectable colors, reusable effects, multi-region virtual paths, and bounded cue branching while retaining read-only Show v1 compatibility.

## Background

Show v1 uses `effect.name` and target fields whose meaning depends on context. The cabin needs paths spanning analog and digital regions and a specific bounded behavior: propagation through `strip_41` may release 42/43/44/45/93 simultaneously. This is not authorization for a general graph executor.

## Binding Contract References

- `CLAUDE.md`
- `docs/CLOSED_LOOP_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md` Phase 25
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add strict Show v2 models, normalization, loader errors with exact paths, and v1-to-v2 read-only normalization. New serialization/examples MUST emit v2 only.
- Canonical selectors: `analog_zone + id`, `digital_strip + id`, `digital_set + ids`, `digital_group + id`, and `virtual_path + id`; reject mismatched `id`/`ids` shapes and unknown types.
- Replace canonical `effect.name/parameters` with `effect.id/params`; build a registry contract so adding an effect requires an ID, parameter validator, and renderer without editing target dispatch.
- Add cue-level ColorSpec modes `effect_default`, `solid`, and `palette`. Effect IDs MUST NOT imply a fixed authored color; effects may supply defaults that authored ColorSpec overrides.
- Define at least three paths covering all 14 runs: screen-to-top, screen-to-bottom-and-left, and screen-to-right-wall.
- Add bounded cue branching that releases 42/43/44/45/93 simultaneously after propagation reaches the configured end of `strip_41`.
- Support per-path/per-branch origins `start`, `end`, `center`, and `edges` with deterministic validation and rendering.
- Preserve brightness ownership in `OutputTransform`, Engine sequence ownership, existing analysis, audio modulation, and adaptive selection behavior.

## Out of Scope

- UDP v3, physical node/GPIO fields, firmware, general DAG execution, Host API implementation, or hardware verification.
- Removing v1 parsing or rewriting v1 fixtures as v2 merely to pass tests.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- light_engine/show/**
- light_engine/effects/**
- light_engine/mapping/virtual.py
- light_engine/mapping/resolve.py
- light_engine/engine/**
- light_engine/models.py
- config/show*.yaml
- config/effects.yaml
- tests/test_show*.py
- tests/test_effect*.py
- tests/test_virtual*.py
- tests/goldens/show_orchestration/v2/**
- docs/show_306/**

## Forbidden Files

- firmware/**
- light_engine/outputs/**
- light_engine/mapping/physical.py
- artifacts/**
- .agent/**
- scripts/**
- docs/contracts/**

## Binding Quality Constraints

- Unknown fields MUST fail recursively; compatibility normalization MUST be explicit and covered by regression tests.
- A virtual path may reference analog and digital logical targets, but no logical model may acquire node IDs, GPIO, host, port, or packet offsets.
- Branch timing MUST be derived deterministically from cue/path progress and MUST NOT use wall-clock races.
- No skips/xfails, test-detection branches, silent validation fallback, or double brightness application.

## Acceptance Criteria

- Valid v2 examples load into typed models and v1 fixtures normalize without changing their rendered meaning.
- Every selector, ColorSpec mode, origin, and branch shape has positive and exact negative tests.
- `strip_41` completion releases all five configured branches in the same logical frame.
- An effect can run with its default color, solid override, or palette override without a new effect implementation.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_show_config.py tests/test_show_engine.py tests/test_effect_registry.py tests/test_effect_color_timeline.py tests/test_physical_mapping.py -q
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

Report schema/API changes, v1 compatibility behavior, effect extension steps, color behavior, branch timing evidence, tests and benchmark with exact return codes/count/time, traceability, limitations, and `git diff --stat`.

## Commit Message

Phase 25: Add Show v2 effect and path authoring
