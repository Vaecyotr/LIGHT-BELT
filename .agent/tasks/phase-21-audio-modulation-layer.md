# Phase 21 — Cue-Local Audio Modulation Layer

## Phase ID

phase-21-audio-modulation-layer

## Goal

Add `audio_modulation` as a cue-local, independent modulation layer so fixed or adaptive effects can keep their authored identity while audio modulates brightness, speed, and intensity in a bounded deterministic way.

## Background

Phase 20 wires `MusicControlState` into Engine runtime. Phase 16 adaptive selection can choose effects based on music, but authored shows also need a different behavior: keep the chosen effect fixed while music only changes brightness, speed, or dynamic intensity. This phase adds that parallel modulation layer without changing output protocols or requiring APP/Host API changes.

## Binding Contract References

- `docs/contracts/MUSIC_CONTROL_CONTRACT.md`
- `docs/contracts/FRAME_CONTRACT.md`
- `docs/contracts/COMPOSE_CONTRACT.md`
- `docs/contracts/TIME_CONTRACT.md`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add strict show-schema support for optional cue-level `audio_modulation`.
- Add typed/immutable models for modulation specs.
- Implement bounded source resolution from `MusicControlState` and `AudioFeatures`.
- Implement cue-local modulation channels:
  - `brightness`
  - `speed`
  - `intensity`
- Apply `speed` and `intensity` before effect processing via scoped `EffectContext`.
- Apply `brightness` only to the current cue contribution after effect processing and before transition/composition.
- Preserve `audio_control` and adaptive selector behavior.
- Preserve no-audio fallback: all multipliers are exactly `1.0`.
- Add deterministic tests for loader validation, runtime math, scoped behavior, and composition.

## Out of Scope

- Modulating hue, saturation, `tail_length`, `width`, `gap`, `start`, or `end`.
- Beat-trigger events or one-shot triggers.
- Host API additions.
- Firmware, UDP v2, RS-485 v2, or output protocol changes.
- Music feature algorithm changes.
- Real hardware verification.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `light_engine/show/**`
- `light_engine/models.py`
- `light_engine/effects/**`
- `config/show*.yaml`
- `tests/test_audio_modulation_loader.py`
- `tests/test_audio_modulation_runtime.py`
- `tests/test_show_engine_audio_modulation.py`
- `tests/test_show_config.py`
- `tests/test_show_engine.py`
- `tests/test_adaptive_selector.py`
- `docs/configuration.md`
- `docs/architecture.md`
- `docs/algorithms.md`
- `docs/show_306/**`

## Forbidden Files

- `firmware/**`
- `light_engine/outputs/**`
- `light_engine/analysis/music_control.py`
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
- New tests MUST assert concrete multipliers, output colors/pixels, context speed/intensity values, exact validation errors, and cue scoping.
- Existing backward-compatible behavior MUST be covered by regression tests.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Implementation | Test | Evidence`.
- Automated success proves software behavior only. It MUST NOT claim hardware verification unless the phase explicitly performs documented hardware tests.

## Authored Schema

Add optional `audio_modulation` at cue level, beside `effect`, `transition`, and `audio_control`:

```yaml
audio_modulation:
  enabled: true
  brightness:
    source: "music.energy"
    amount: 0.30
    min_multiplier: 0.75
    max_multiplier: 1.30
    smoothing_seconds: 0.25
  speed:
    source: "music.beat_strength"
    amount: 0.35
    min_multiplier: 0.80
    max_multiplier: 1.50
    smoothing_seconds: 0.20
  intensity:
    source: "music.bass_pulse"
    amount: 0.50
    min_multiplier: 0.70
    max_multiplier: 1.60
    smoothing_seconds: 0.20
```

### Required Fields and Defaults

- `enabled`: required boolean.
- Each channel is optional, but if present it MUST include a valid `source`.
- `amount`: finite number, minimum `0.0`. Default MAY be `0.0` only if documented.
- `min_multiplier`: finite number, `> 0.0`.
- `max_multiplier`: finite number, `> 0.0`, `>= min_multiplier`.
- `smoothing_seconds`: finite number, `>= 0.0`.
- If `enabled: false`, all channels MUST produce multiplier `1.0`.

## Supported Sources

First version MUST support the following sources:

### `MusicControlState` sources

```text
music.energy
music.energy_trend
music.beat_strength
music.bass_pulse
music.bass_ambient
music.transient
music.spectral_motion
music.tempo_confidence
music.beat_regularity
```

### `AudioFeatures` sources

```text
audio.rms
audio.bass
audio.mid
audio.treble
audio.spectral_flux
audio.onset
```

Do not use boolean `audio.beat` as a continuous source in this phase.

## Modulation Math

For sources whose natural range is `[0,1]`:

```text
raw_multiplier = 1.0 + amount * source_value
multiplier = clamp(raw_multiplier, min_multiplier, max_multiplier)
```

For `music.energy_trend`, which may be `[-1,1]`, either:

1. Map it deterministically into `[0,1]` and document the mapping, or
2. Reject it as a source for this phase and report a BLOCKER if it cannot be handled cleanly.

Smoothing MUST be deterministic and stateful per cue/channel:

```text
if smoothing_seconds == 0:
    smoothed = target
else:
    alpha = clamp(delta_time / smoothing_seconds, 0, 1)
    smoothed = previous + alpha * (target - previous)
```

No modulation multiplier may become NaN or infinity.

## Required Render Order

The show runtime MUST apply modulation in this order:

```text
1. Resolve active cue.
2. Resolve target.
3. Compute speed/intensity multipliers for this cue.
4. Create scoped EffectContext with speed and intensity multiplied.
5. Run effect.process(scoped_ctx).
6. Convert output into the cue's target-scoped contribution.
7. Apply brightness multiplier only to this cue contribution.
8. Apply transition weight and blend through existing compositor semantics.
```

Important: brightness modulation MUST NOT mutate the base frame or other cue contributions.

## Relationship to `audio_control`

- `audio_control` remains the adaptive-selection/tempo-sync policy.
- `audio_modulation` is independent cue-local parameter modulation.
- Fixed cues can use `audio_modulation` without automatic effect switching.
- Adaptive cues can also use `audio_modulation`; adaptive selection happens first, modulation happens after the selected effect and base speed are known.

## Acceptance Criteria

- Loader accepts valid `audio_modulation` and returns an immutable/typed spec or equivalent validated representation.
- Loader rejects unknown fields, unknown channels, unknown sources, invalid numeric values, inverted min/max, and non-boolean `enabled` with exact paths.
- Fixed cue + brightness modulation changes only that cue's contribution brightness.
- Fixed cue + speed modulation changes `EffectContext.speed` seen by the effect.
- Fixed cue + intensity modulation changes `EffectContext.intensity` seen by the effect.
- No audio or missing `music_control_state` produces exact multipliers of `1.0` and preserves authored base output.
- Adaptive cues still select only within YAML policy and can then be modulated.
- Multiple overlapping cues do not leak modulation state into each other.
- Reset/replay reproduces the same modulation output sequence.
- Existing shows without `audio_modulation` behave exactly as before.

## Required Gold Tests

At minimum, tests MUST prove:

1. `brightness` modulation with `music.energy = 1.0` and `amount = 0.30` yields multiplier `1.30` when max permits it.
2. `max_multiplier` clamps a too-large computed multiplier.
3. `min_multiplier` is respected for any source mapping that could lower a multiplier.
4. `speed` modulation is visible to a recording effect through `ctx.speed`.
5. `intensity` modulation is visible to a recording effect through `ctx.intensity`.
6. A cue with `audio_modulation.enabled: false` behaves as if no modulation exists.
7. No-audio fallback yields the same frame digest as the same cue without `audio_modulation`.
8. Two overlapping cues with different modulation specs produce independent contributions.
9. Adaptive + modulation order is deterministic and documented.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_audio_modulation_loader.py tests/test_audio_modulation_runtime.py tests/test_show_engine_audio_modulation.py tests/test_show_config.py tests/test_show_engine.py tests/test_adaptive_selector.py -v
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
- `audio_modulation` schema and validation matrix
- Source catalog and source range handling
- Exact modulation formulas and smoothing behavior
- Render-order proof
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

Phase 21: Add cue-local audio modulation layer
