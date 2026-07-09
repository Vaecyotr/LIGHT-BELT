# Phase 22 — Authoring Modulation Acceptance

## Phase ID

phase-22-authoring-modulation-acceptance

## Goal

Create a deterministic software acceptance suite proving authored color timelines and cue-local audio modulation work together across analog zones, digital strips, virtual paths, fixed cues, adaptive cues, transitions, and composition.

## Background

Phases 18-21 add runtime cue parameter semantics, color timelines, Engine music-control state, and `audio_modulation`. Those features must be validated together before they are used in the real 5:06 show. This phase produces fixture shows, offline artifacts, frame digests, and tests. It remains software-only and must not claim hardware validation.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add a deterministic acceptance show fixture exercising color timelines and audio modulation.
- Add deterministic procedural or existing fixture inputs sufficient to trigger modulation paths without regenerating locked audio fixtures.
- Add an acceptance script that renders fixed sample windows and emits JSON evidence artifacts.
- Add tests validating the artifacts and frame digests.
- Verify color interpolation, brightness modulation, speed/intensity context modulation, transitions, virtual-path mapping, and no-audio fallback.
- Measure software performance capacity.
- Document the acceptance evidence as software-only.

## Out of Scope

- Final 306-second teacher show authoring.
- Hardware or real ESP32/STM32 tests.
- Firmware changes.
- Host API implementation.
- RK3588 deployment.
- Changing core schemas except for small fixture-support fixes if a BLOCKER is found and the prior phase missed it.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `config/show_authoring_modulation_acceptance.yaml`
- `scripts/show_authoring_modulation_acceptance.py`
- `tests/test_show_authoring_modulation_acceptance.py`
- `tests/fixtures/show/**`
- `tests/fixtures/audio/acceptance/**`
- `tests/fixtures/video/**`
- `artifacts/show_authoring_modulation_acceptance/**`
- `docs/show_acceptance_report.md`
- `docs/architecture.md`
- `docs/configuration.md`
- `light_engine/show/**` only for BLOCKER fixes directly tied to Phase 18-21 regressions
- `light_engine/effects/**` only for BLOCKER fixes directly tied to Phase 18-21 regressions

## Forbidden Files

- `firmware/**`
- `light_engine/outputs/rs485_v2.py`
- `light_engine/outputs/udp_v2.py`
- `light_engine/analysis/music_control.py` unless reporting a BLOCKER that Phase 20 is incomplete
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
- New tests MUST assert concrete samples, frame digests, timestamps, colors, multipliers, and exact acceptance metrics.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Acceptance Show Requirements

Add `config/show_authoring_modulation_acceptance.yaml` with at least:

1. An RGB+CCT analog target using `static + color_timeline`.
2. A digital strip target using `chase + color_timeline`.
3. A virtual path target using `comet + color_timeline + audio_modulation`.
4. A fixed cue using brightness modulation.
5. A fixed cue using speed modulation.
6. A fixed cue using intensity modulation.
7. An adaptive cue using existing `audio_control` to prove compatibility.
8. At least one overlap proving transition/blend semantics still work.
9. A no-audio fallback case or separately rendered no-audio variant.

## Acceptance Script Requirements

Add `scripts/show_authoring_modulation_acceptance.py` or equivalent. It MUST:

- Validate the acceptance show before rendering.
- Render deterministic sample frames offline without opening serial, UDP sockets, or hardware outputs.
- Capture specific sample times for color timeline start/mid/end.
- Capture modulation multipliers or output evidence for brightness/speed/intensity.
- Capture virtual-path seam evidence near segment boundaries.
- Capture no-audio fallback evidence.
- Emit deterministic artifacts under:

```text
artifacts/show_authoring_modulation_acceptance/
```

Required artifact files:

```text
summary.json
color_timeline_samples.json
audio_modulation_samples.json
virtual_path_samples.json
frame_digest.json
```

Each artifact MUST be deterministic across two runs and included in report with SHA-256.

## Acceptance Criteria

- Acceptance show passes `validate-show`.
- Offline acceptance script exits with return code 0.
- Two consecutive runs produce identical `frame_digest.json`.
- Color timeline samples match expected interpolation values within documented tolerance.
- Audio modulation samples prove brightness, speed, and intensity paths are active.
- No-audio fallback produces exact unity modulation multipliers and expected stable output.
- Virtual-path sample proves the effect crosses a seam without restarting per physical segment.
- Adaptive cue still respects allowed mapping and does not select outside YAML policy.
- Processing capacity remains above 30 FPS for the acceptance fixture.
- No NaN or infinity appears in artifacts.
- Artifacts and report explicitly state this is software validation only.

## Required Gold Tests

At minimum, tests MUST prove:

1. `summary.json` exists and declares schema/version/phase ID.
2. `color_timeline_samples.json` contains expected start/mid/end RGB samples.
3. `audio_modulation_samples.json` contains expected multiplier samples and source values.
4. `virtual_path_samples.json` contains seam-crossing evidence.
5. `frame_digest.json` is stable across two acceptance renders.
6. Acceptance metrics include effective FPS or processing capacity and pass threshold.
7. No artifact contains NaN/Inf.
8. The report text does not claim hardware validation.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_show_authoring_modulation_acceptance.py -v
.\.python\Scripts\python.exe scripts\show_authoring_modulation_acceptance.py
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show_authoring_modulation_acceptance.yaml
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

The implementation or repair agent must report:

- Modified files
- Acceptance show cue summary
- Artifact paths and SHA-256 hashes
- Color timeline sample table
- Audio modulation sample table
- Virtual-path seam evidence
- No-audio fallback evidence
- Performance result
- Tests added or updated
- Exact commands run
- Return codes
- Targeted test results
- Full test result
- Skip/xfail counts before and after
- Golden manifest SHA-256 or explanation if no locked manifest is used by this phase
- Traceability table: `Requirement | Implementation | Test | Evidence`
- `git diff --stat`
- Unresolved issues or BLOCKERs
- Suggested commit message

## Commit Message

Phase 22: Add authoring modulation acceptance suite
