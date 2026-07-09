# Phase 20 — Engine Music Control State Integration

## Phase ID

phase-20-engine-music-control-state

## Goal

Wire the existing `MusicControlAnalyzer` into the main Engine runtime so every show-rendered frame can receive a real `EffectContext.music_control_state` derived from current audio features.

## Background

Phase 15 added deterministic music-control features and `MusicControlState`. Phase 16 added cue-bounded adaptive selection that can use `MusicControlState`. Current `EffectContext` already has a `music_control_state` field, but the main Engine path updates only `AudioFeatures`; it does not consistently compute and pass `MusicControlState` into show rendering. Independent audio modulation depends on this runtime data path, so it must be connected before adding `audio_modulation`.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Instantiate and maintain `MusicControlAnalyzer` inside Engine when audio or synthetic audio features are available.
- Update `MusicControlState` whenever new `AudioFeatures` are produced.
- Pass the latest `MusicControlState` into `EffectContext.music_control_state` for both single-effect and show-runtime paths.
- Reset music-control analyzer state on Engine reset, seek/timeline reset, and replay.
- Preserve existing `AudioFeatures` behavior.
- Preserve no-audio behavior without crashes or fabricated high-confidence music state.
- Add tests proving Engine runtime receives real music-control state and resets it correctly.

## Out of Scope

- Adding `audio_modulation` show schema.
- Changing music feature algorithms.
- Changing adaptive selector policy beyond enabling it to receive real state.
- Changing effect parameter behavior.
- Changing output protocols or firmware.
- Host API implementation.
- Real hardware verification.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `light_engine/engine/**`
- `light_engine/analysis/__init__.py`
- `light_engine/analysis/music_control.py`
- `light_engine/models.py`
- `tests/test_engine_music_control_state.py`
- `tests/test_music_control.py`
- `tests/test_show_engine.py`
- `tests/test_engine.py`
- `docs/architecture.md`
- `docs/algorithms.md`

## Forbidden Files

- `firmware/**`
- `light_engine/outputs/**`
- `light_engine/show/loader.py`
- `light_engine/show/models.py`
- `light_engine/effects/**`
- `light_engine/media/**`
- `docs/contracts/**`
- `.agent/**`
- `scripts/agent_*.py`
- `tests/fixtures/audio/show_orchestration_v1/**`
- `tests/goldens/show_orchestration/v1/**`
- Any file not required by this Phase

## Binding Quality Constraints

These constraints are part of acceptance, not suggestions:

- MUST follow the planning-baseline contracts listed above. If implementation requires changing a contract, stop and report a BLOCKER; do not edit the contract inside this Phase.
- MUST NOT modify `docs/contracts/**`, `.agent/contracts/**`, `tests/goldens/show_orchestration/v1/**`, `tests/fixtures/audio/show_orchestration_v1/**`, or `scripts/verify_show_orchestration_baseline.py`.
- The report MUST include audit evidence conforming to `.agent/contracts/phase-audit.schema.json`: base/head SHA, changed files, tests added/modified, skip/xfail counts before/after, golden manifest SHA-256, exact command return codes, traceability, artifacts, and blockers.
- MUST NOT add or broaden `pytest.skip`, `pytest.mark.skip`, `xfail`, or equivalent bypasses.
- MUST NOT delete existing tests, weaken assertions, reduce test coverage intentionally, or change expected values merely to match an incorrect implementation.
- MUST NOT add production branches that detect tests, fixture names, or CI environments.
- MUST NOT silently accept invalid configuration or silently fall back after a validation error.
- New tests MUST assert concrete `MusicControlState` fields, reset behavior, timestamps, and bounded values. `is not None` alone is insufficient.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Required Runtime Semantics

- Engine MUST maintain a latest music-control state separate from latest raw audio features.
- When `_get_audio_features()` or synthetic audio returns `AudioFeatures`, Engine MUST feed it into `MusicControlAnalyzer` and store the resulting `MusicControlState`.
- `EffectContext` construction MUST include the latest `music_control_state`.
- Repeated timestamps/paused frames MUST not create artificial analysis advancement.
- Engine reset and seek-detected timeline reset MUST reset both raw audio analyzer state and music-control analyzer state.
- No audio source means `music_control_state` stays `None`, unless existing contracts require an explicit low-energy state. If using an explicit low-energy state, document and test it.
- Music-control state memory MUST remain bounded as required by the music-control contract.

## Acceptance Criteria

- With audio input, show-rendered effects can observe non-None `ctx.music_control_state` whose timestamp tracks the latest audio feature timestamp.
- With synthetic audio input, Engine produces deterministic music-control states across repeated runs with the same seed.
- With no audio input, Engine renders without errors and does not fabricate strong tempo/beat evidence.
- Reset/replay clears music-control history and reproduces the same initial sequence.
- Seek/timeline reset clears music-control analyzer state.
- Adaptive selector integration benefits from real `MusicControlState` without changing fixed cue behavior.
- Existing `AudioFeatures` tests and Engine tests remain green.

## Required Gold Tests

At minimum, tests MUST prove:

1. A spy/recording effect receives `ctx.music_control_state` when Engine is run with audio features.
2. The state contains finite bounded fields such as `energy`, `beat_strength`, and `tempo_confidence`.
3. Engine reset clears the analyzer such that replay from start is deterministic.
4. No-audio Engine runs with `music_control_state is None` or documented safe low-energy state, and the choice is tested.
5. A seek/backward-time reset calls the music-control reset path.
6. Existing single-effect path and show-runtime path both receive consistent context behavior.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_engine_music_control_state.py tests/test_music_control.py tests/test_show_engine.py tests/test_engine.py -v
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

The implementation or repair agent must report:

- Modified files
- Engine data-flow summary: `AudioFeatures -> MusicControlAnalyzer -> MusicControlState -> EffectContext`
- Reset/seek behavior evidence
- No-audio behavior decision
- Tests added or updated
- Exact commands run
- Return codes
- Targeted test results
- Full test result
- Benchmark result
- Skip/xfail counts before and after
- Golden manifest SHA-256 or explanation if no locked manifest is used by this phase
- Traceability table: `Requirement | Implementation | Test | Evidence`
- `git diff --stat`
- Unresolved issues or BLOCKERs
- Suggested commit message

## Commit Message

Phase 20: Feed music control state through Engine
