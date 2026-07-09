# Phase 19 — Authored Color Timeline Curves

## Phase ID

phase-19-color-timeline-authoring

## Goal

Add strict show-authoring support for cue-local color keyframes so authors can define smooth, continuous color changes inside one cue, instead of approximating them with many overlapping fixed-color cues.

## Background

Phase 18 makes cue parameters operational at runtime. Authored 5:06 shows need manual color direction over time: warm-to-cool shifts, multi-step color arcs, and color changes on both analog RGB+CCT zones and WS2811 digital effects. Current `transition.fade_in/fade_out` controls cue entrance/exit, not the internal color evolution of an effect. This phase introduces `color_timeline` as an authored effect parameter with strict validation and deterministic interpolation.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Extend V1 authored-show parameter metadata to allow `color_timeline` for explicitly supported effects.
- Add immutable/validated parsing for cue-local color timelines.
- Implement deterministic RGB linear interpolation over `cue_local_time`.
- Support color timelines for analog-friendly and digital-friendly effects.
- Preserve existing `color` parameter behavior when `color_timeline` is absent.
- Add documentation and examples for authored color timelines.
- Add tests for strict validation, interpolation, boundary clamping, and real effect output changes.

## Out of Scope

- Independent audio modulation.
- MusicControlAnalyzer or Engine music-state changes.
- HSV interpolation unless implemented as a documented optional extension after `rgb_linear` is complete.
- GUI/color editor.
- Host API implementation or changes to `host_api_v1`.
- Real hardware verification.
- Firmware changes.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `light_engine/show/**`
- `light_engine/effects/**`
- `light_engine/color/**`
- `light_engine/models.py`
- `config/show*.yaml`
- `tests/test_color_timeline.py`
- `tests/test_effect_color_timeline.py`
- `tests/test_show_config.py`
- `tests/test_show_engine.py`
- `tests/test_effects.py`
- `docs/configuration.md`
- `docs/architecture.md`
- `docs/algorithms.md`
- `docs/show_306/**`

## Forbidden Files

- `firmware/**`
- `light_engine/outputs/**`
- `light_engine/analysis/**`
- `light_engine/media/**`
- `light_engine/clock.py`
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
- New tests MUST assert concrete colors, pixels, interpolation values, cue-local timestamps, and exact validation errors.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Authored Schema

Add `color_timeline` as an effect parameter for supported effects:

```yaml
effect:
  mode: "fixed"
  name: "static"
  parameters:
    color_timeline:
      interpolation: "rgb_linear"
      keyframes:
        - time: 0.0
          color: [1.0, 0.25, 0.05]
        - time: 8.0
          color: [1.0, 0.75, 0.20]
        - time: 18.0
          color: [0.20, 0.45, 1.0]
```

### Required Semantics

- `keyframes[].time` is cue-local time in seconds, measured from `cue.start`.
- Color arrays are internal authored RGB triples in `[0.0, 1.0]`.
- `interpolation` MUST initially support `rgb_linear`.
- Before the first keyframe, output the first keyframe color.
- After the last keyframe, output the last keyframe color.
- Between keyframes, linearly interpolate each RGB channel.
- Repeated timestamps are invalid.
- Keyframe times MUST be strictly increasing.
- Non-finite values, booleans-as-numbers, numeric strings, malformed colors, and out-of-range channels MUST fail strict validation.

## Supported Effects

This phase MUST support `color_timeline` for:

```text
static
breath
calm
audio_pulse
bass_pulse
chase
comet
```

For `chase` and `comet`, the color timeline MUST be interpreted as the authored/manual color over cue time. If an existing `color_source` is set to a non-manual source such as `video` or `rainbow`, either reject the combination with an exact validation error or implement and document deterministic precedence. Silent ambiguity is forbidden.

## Parameter Metadata Requirements

- Extend registered parameter keys for the supported effects to include `color_timeline`.
- If `chase`/`comet` need a `color` parameter to make manual color behavior consistent, add it only with tests and documentation. Otherwise, implement `color_timeline` directly without broadening unrelated parameters.
- Unknown `color_timeline` fields MUST fail recursively, e.g. `show.cues[2].effect.parameters.color_timeline.foo`.

## Acceptance Criteria

- A valid `color_timeline` loads into typed/immutable show models or an equivalent validated runtime representation.
- Invalid timelines fail with path-aware errors.
- `static` changes color over time inside one cue without requiring multiple cues.
- `breath` uses the timeline as its base color while preserving its brightness envelope.
- `calm` uses the timeline as its base color while preserving its own timing behavior.
- `audio_pulse` and `bass_pulse` use the timeline as base color while preserving audio envelope behavior.
- `chase` and `comet` can run on digital/virtual-path targets while their authored/manual color changes over cue time.
- Existing shows without `color_timeline` behave as before.
- `transition.fade_in/fade_out` still controls cue entry/exit and is not confused with internal color interpolation.

## Required Gold Tests

At minimum, tests MUST prove:

1. At cue-local time equal to the first keyframe, the output color equals the first keyframe exactly within numeric tolerance.
2. At the midpoint between two keyframes, RGB output equals the exact linear interpolation.
3. After the last keyframe, output clamps to the final keyframe.
4. A `static` cue changes target-scoped output at two different timestamps without changing cue identity.
5. A `breath` cue preserves brightness modulation while its underlying hue/base RGB changes according to the timeline.
6. A `comet` or `chase` cue on a virtual-path target changes authored color over time while preserving motion.
7. Missing/empty keyframes, one-keyframe timelines, non-increasing times, malformed colors, unknown interpolation, and unknown nested fields fail with exact paths.
8. A legacy show using only `color` still validates and renders as before.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_color_timeline.py tests/test_effect_color_timeline.py tests/test_show_config.py tests/test_show_engine.py tests/test_effects.py -v
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
- Color timeline schema and validation matrix
- Interpolation formula and boundary behavior
- Supported effects and precedence rules with `color` / `color_source`
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

Phase 19: Add authored color timeline curves
