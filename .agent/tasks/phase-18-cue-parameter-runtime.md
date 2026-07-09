# Phase 18 — Cue Parameter Runtime Semantics

## Phase ID

phase-18-cue-parameter-runtime

## Goal

Make the already-validated `cue.effect.parameters` contract operational at runtime: authored cue parameters MUST override effect defaults and visibly affect effect output without changing the show schema or transport protocols.

## Background

Phase 11 added strict show validation and registered V1 effect parameter keys. Phase 14 executes authored cues and injects `cue.effect.parameters` into `EffectContext.mode_parameters` along with `cue_local_time`. However, some effects still primarily read constructor/config defaults, so a parameter can pass validation without actually changing runtime output. Later phases (`color_timeline` and `audio_modulation`) depend on reliable cue-scoped parameter flow. This phase closes that gap before adding new fields.

## Binding Contract References

- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Audit all registered effects and make V1 cue parameters override config/default values at runtime.
- Preserve the existing registered parameter keys exactly unless a BLOCKER is reported.
- Add a small shared parameter-reading utility if it reduces duplication and improves type/range safety.
- Ensure effects use `ctx.mode_parameters` first, then fall back to existing config/constructor defaults.
- Preserve single-effect CLI behavior and existing config-driven defaults when no show parameter is supplied.
- Add regression tests proving each meaningful cue parameter changes output or effect behavior.
- Keep validation strict: unknown parameters MUST still fail in the show loader.

## Out of Scope

- Adding `color_timeline` or any new show field.
- Adding `audio_modulation` or independent audio modulation.
- Changing adaptive selector policy.
- Changing `MusicControlAnalyzer` algorithms.
- Changing output protocols, UDP v2, RS-485 v2, firmware, or hardware behavior.
- Host API implementation or APP-facing REST/WSS behavior.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `light_engine/effects/**`
- `light_engine/show/**`
- `light_engine/models.py`
- `config/effects.yaml`
- `config/show*.yaml`
- `tests/test_effect_parameter_runtime.py`
- `tests/test_effects.py`
- `tests/test_show_config.py`
- `tests/test_show_engine.py`
- `docs/architecture.md`
- `docs/configuration.md`
- `docs/algorithms.md`

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
- New tests MUST assert concrete domain outputs: colors, pixels, periods, directions, weights, exact errors, or deterministic state values. `is not None`/"does not crash" alone is insufficient.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Current V1 Parameter Contract

The following existing parameter keys MUST remain valid and must be audited for runtime behavior:

| Effect | V1 authored-show parameters |
|---|---|
| `static` | `color` |
| `breath` | `period`, `min_brightness`, `color` |
| `color_wave` | `speed`, `width`, `hue_cycle_rate` |
| `chase` | `speed`, `width`, `gap`, `direction`, `trail`, `color_source`, `beat_boost` |
| `comet` | `speed`, `tail_length`, `decay` |
| `audio_pulse` | `attack`, `release`, `color` |
| `bass_pulse` | `attack`, `release`, `color` |
| `spectrum` | `bass_zones`, `mid_zones`, `treble_zones` |
| `video_ambient` | `smoothing` |
| `video_audio_fusion` | `video_weight`, `audio_weight`, `bass_boost`, `treble_limit` |
| `calm` | `period`, `color` |
| `demo` | `cycle_interval`, `effects` |

## Implementation Requirements

- Implement a consistent runtime precedence rule:

```text
cue.effect.parameters > existing effect config/defaults
```

- Effects MAY keep constructor/config defaults, but each frame MUST read cue-scoped overrides from `ctx.mode_parameters` where the V1 contract exposes a key.
- Numeric parameter parsing MUST be finite and bounded. Do not accept booleans as numbers.
- Color parameters MUST be validated as RGB triples in the existing internal authored-show range. Preserve existing behavior if the repository already documents a different range, but report it explicitly.
- `direction` MUST reject unknown values at the earliest existing validation point; runtime must not treat misspellings as `forward`.
- `color_source` MUST use a documented finite set. If the current implementation has undocumented values, document and test the actual set or report a BLOCKER.
- Parameter utility helpers, if added, MUST not introduce permissive coercion.

## Acceptance Criteria

- `static.parameters.color` changes analog and digital output color in show runtime.
- `breath.parameters.period`, `min_brightness`, and `color` change output over time as authored.
- `color_wave.parameters.speed`, `width`, and `hue_cycle_rate` affect pixel output deterministically.
- `chase.parameters.speed`, `width`, `gap`, `direction`, `trail`, `color_source`, and `beat_boost` are either proven operational with concrete tests or reported with a BLOCKER if a registered key is not implementable within scope.
- `comet.parameters.speed`, `tail_length`, and `decay` affect output deterministically.
- `audio_pulse` and `bass_pulse` use authored `attack`, `release`, and `color` when audio features are present.
- `video_ambient.parameters.smoothing` affects temporal smoothing while preserving no-video fallback.
- `video_audio_fusion.parameters.video_weight`, `audio_weight`, `bass_boost`, and `treble_limit` affect fusion output.
- `calm.parameters.period` and `color` affect output.
- `demo.parameters.cycle_interval` and `effects` affect demo sequencing without breaking deterministic seeded behavior.
- Missing cue parameters preserve existing default behavior.
- Unknown parameters still fail strict show validation.
- Existing tests remain green.

## Required Gold Tests

At minimum, add tests proving:

1. A valid show with two `static` cues differing only in `parameters.color` produces different target-scoped output.
2. A valid show with two `chase` cues differing only in `direction` produces reversed movement or reversed pixel ordering evidence.
3. A valid show with two `comet` cues differing only in `tail_length` produces a different number or magnitude distribution of non-black pixels.
4. A valid show with `video_audio_fusion` parameter overrides produces measurably different RGB output with the same synthetic video/audio features.
5. No-parameter effects preserve pre-phase defaults.
6. A misspelled parameter key still fails at the path `show.cues[N].effect.parameters.<key>` or equivalent exact nested path.
7. Parameter tests use concrete output assertions, not only object existence.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_effect_parameter_runtime.py tests/test_effects.py tests/test_show_config.py tests/test_show_engine.py -v
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
- Effect-by-effect parameter audit table: `Effect | Parameter | Runtime source | Test | Evidence`
- What changed
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

Phase 18: Make authored cue parameters runtime-effective
