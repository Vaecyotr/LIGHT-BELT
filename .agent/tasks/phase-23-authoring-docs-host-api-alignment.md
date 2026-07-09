# Phase 23 — Authoring Docs and Host API Alignment

## Phase ID

phase-23-authoring-docs-host-api-alignment

## Goal

Document the new show-authoring capabilities and explicitly align internal `show.yaml` concepts with Host API V1 so show authors, Host Service implementers, and APP developers do not confuse cue fields, target IDs, physical IDs, and API fields.

## Background

Phases 18-22 add operational cue parameters, `color_timeline`, Engine music-control state, `audio_modulation`, and acceptance evidence. The project also has Host API V1 files for APP integration: APPs call Host Service REST/WSS endpoints and do not directly edit `show.yaml` cues or physical mappings. This phase updates documentation only and preserves code behavior.

## Binding Contract References

- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Update or create show authoring documentation for:
  - cue anatomy and field meanings
  - target types and valid target IDs
  - effect modes, effect names, and parameters
  - `color_timeline`
  - `audio_control` vs `audio_modulation`
  - virtual path authoring and physical mapping separation
  - PC/multi-PC debugging notes if not already documented
- Add a Host API alignment section explaining external APP fields versus internal show fields.
- Document that APPs use `target_id`, `effect_type`, `params`, `effect_params`, and `transition_ms`, while internal show uses `target.type/id/ids`, `effect.name`, `cue.effect.parameters`, and `transition.fade_in/fade_out`.
- Document that physical IDs such as `11`, `21`, `41`, `42`, `91`, `92`, `93` are installation IDs and are not Host API target IDs unless future API/schema explicitly exposes them.
- Add examples that are valid against the post-Phase-22 schema.
- Ensure all docs state that software validation is not hardware verification.

## Out of Scope

- Code changes.
- Host API implementation.
- OpenAPI schema edits unless documentation discovered an exact contradiction and a BLOCKER is reported first.
- Final 306-second show authoring.
- Firmware or hardware work.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- `docs/show_306/SHOW_AUTHORING_UNDERSTANDING.md`
- `docs/show_306/AUTHORING_COLOR_TIMELINE.md`
- `docs/show_306/AUDIO_MODULATION.md`
- `docs/show_306/VIRTUAL_PATH_AUTHORING.md`
- `docs/show_306/HOST_API_ALIGNMENT.md`
- `docs/configuration.md`
- `docs/architecture.md`
- `docs/algorithms.md`
- `docs/show_acceptance_report.md`

## Forbidden Files

- `light_engine/**`
- `firmware/**`
- `config/**`
- `tests/**`
- `scripts/**`
- `docs/contracts/**`
- `.agent/**`
- `host_api_v1.md` unless this file is already part of the repository and the task explicitly reports a needed doc-only correction as a BLOCKER first
- `host_api_v1.openapi.yaml` unless this file is already part of the repository and the task explicitly reports a needed doc-only correction as a BLOCKER first
- Any file not required by this Phase

## Binding Quality Constraints

These constraints are part of acceptance, not suggestions:

- MUST follow the planning-baseline contracts listed above. If implementation requires changing a contract, stop and report a BLOCKER; do not edit the contract inside this Phase.
- MUST NOT modify `docs/contracts/**`, `.agent/contracts/**`, `tests/goldens/show_orchestration/v1/**`, `tests/fixtures/audio/show_orchestration_v1/**`, or `scripts/verify_show_orchestration_baseline.py`.
- The report MUST include audit evidence conforming to `.agent/contracts/phase-audit.schema.json`: base/head SHA, changed files, tests added/modified, skip/xfail counts before/after, golden manifest SHA-256, exact command return codes, traceability, artifacts, and blockers.
- MUST NOT add or broaden `pytest.skip`, `pytest.mark.skip`, `xfail`, or equivalent bypasses.
- MUST NOT delete existing tests or weaken assertions.
- MUST NOT document unsupported behavior as implemented.
- Documentation MUST clearly label software validation versus hardware verification.
- Documentation examples MUST match the actual schema after Phase 22.
- If a requirement cannot be satisfied within Allowed Files, stop and report a BLOCKER instead of modifying a forbidden file.
- The phase report MUST include a traceability table: `Requirement | Documentation | Validation | Evidence`.

## Required Documentation Content

### Show authoring layer

Must explain:

- `show.yaml` is the internal authored show format.
- `cue.id` is a cue name, not a physical or API target.
- `target.type` valid values:

```text
analog_zone
digital_strip
analog_group
digital_group
virtual_path
all_analog
all_digital
all
```

- `target.id` and `target.ids` semantics.
- `effect.mode` values `fixed` and `adaptive`.
- supported effect names.
- `cue.effect.parameters` and the current parameter table.
- `transition.fade_in/fade_out/blend` and their unit/meaning.
- `audio_control` as adaptive/tempo policy.
- `audio_modulation` as independent parameter modulation.
- `color_timeline` as cue-local manual color curve.

### Physical layout layer

Must explain:

- Physical IDs such as `11`, `21`, `31`, `41`, `42`, `43`, `44`, `45`, `91`, `92`, `93` are installation identifiers.
- Physical IDs are mapped through layout/target registry to internal targets.
- Physical IDs are not automatically legal `target.id` values.
- 91/92/93 should remain in the planning model even if later disabled or removed from a virtual path.

### Virtual path layer

Must explain:

- `virtual_path` is a continuous visual coordinate system over multiple WS2811 segments.
- Effects run once over the virtual path and are then split back to physical segments.
- This is not ESP32-to-ESP32 color forwarding.
- RGB+CCT segments cannot provide true per-pixel motion; they can only approximate a path with whole-zone response.

### Host API V1 alignment

Must include this mapping table or equivalent:

| Internal show concept | Host API V1 concept |
|---|---|
| `show.id` | `show_id` |
| `show.duration` seconds | `duration_ms` milliseconds |
| `effect.name` | `effect_type` |
| `cue.effect.parameters` | `params` + `effect_params` |
| `target.type: virtual_path`, `id: screen_to_wall` | `target_id: virtual_path.screen_to_wall` |
| `transition.fade_in/fade_out` | `transition_ms`, not exactly the same semantics |
| physical ID `41` | not directly exposed unless a future API adds it |

Must state:

```text
APP does not directly edit cues.
APP does not directly send physical IDs.
APP does not directly address ESP32 node_id, GPIO, pixel offset, RS-485 frames, or UDP payloads.
Host Service maps APP target_id/effect_type/params into internal runtime commands.
```

## Acceptance Criteria

- Documentation clearly separates show authoring, Host API, physical layout, virtual path, and firmware/output layers.
- Documentation contains valid examples for `color_timeline` and `audio_modulation`.
- Documentation contains an accurate current effect parameter table.
- Documentation explains `audio_control` versus `audio_modulation` without conflating them.
- Documentation explains why APP developers can follow Host API V1 while internal show authors follow show.yaml docs.
- Documentation does not claim hardware verification.
- Documentation examples are either validated by existing tests/examples or explicitly marked as conceptual if they are not executable.

## Required Targeted Tests

Documentation-only phase. Run at minimum:

```powershell
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show.example.yaml
.\.python\Scripts\python.exe -m light_engine validate-show --show config/show_authoring_modulation_acceptance.yaml
```

If the repository has documentation lint/check commands, run them and report results. Do not add new tooling in this phase.

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
git diff --check
git status --short
git diff --stat
```

## Required Report

The implementation or repair agent must report:

- Modified documentation files
- What changed
- Documentation examples added or updated
- Host API alignment summary
- Exact commands run
- Return codes
- Validation results
- Full test result
- Skip/xfail counts before and after
- Golden manifest SHA-256 or explanation if no locked manifest is used by this phase
- Traceability table: `Requirement | Documentation | Validation | Evidence`
- `git diff --stat`
- Unresolved issues or BLOCKERs
- Suggested commit message

## Commit Message

Phase 23: Document authoring modulation and Host API alignment
