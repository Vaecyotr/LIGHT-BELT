# Antigravity task: author the teammate Show manual

## Role and boundary

Produce a complete, practical Show-authoring manual for teammates who did not
build the engine.  Do not modify production code.  Do not rely on memory:
inspect this final repository.  This task is to create the manual, not to
change the released APP V1 contract.  The APP is a playback/control client;
Show YAML plus the RK3588 runtime own advanced lighting authoring.

The lighting authoring language is **CLOSED/FROZEN**: document its current
behavior accurately.  Do not propose proactive effect migration or a casual
Show-contract redesign.  Hardware claims must remain **NOT HARDWARE VERIFIED**
unless the repository supplies real hardware evidence.

## Terminology standard

Use exact, standard entity terminology across all authoring documentation:

- **RK3588**: Central host controller (中央主控) running the `light_engine` and Host service.
- **ESP32**: Our digital LED strip controller nodes (我们自己的数字灯带控制节点).
- **WLED**: Upstream open-source project / firmware reference; formal name for upstream algorithms, effects, and protocol reference (e.g., `ESP32 running WLED firmware`, `WLED Audio Sync V2`, `WLED v16.0.1 reference`).

Strictly prohibited:
- Do not use WT04 to refer to RK3588.
- Do not use WLED to refer to our own ESP32 nodes.
- Do not call WLED itself an obsolete term.

## Source authority

Resolve conflicts in this order:

1. [CLAUDE.md](../../CLAUDE.md)
2. [CLOSED_LOOP_SPEC.md](../CLOSED_LOOP_SPEC.md)
3. [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md)
4. [current Show authoring documentation](show-v2-authoring.md)
5. live EffectRegistry / exported authoring contract
6. current implementation
7. focused tests and examples

Historical/archive material is evidence only, not current contract.  In
particular, do not infer current behavior from archived Shows or obsolete
reports.  Use [the authoring source index](show-authoring-source-index.md) as
the navigation map for every source below.

## Required discovery before writing

Run these commands from the repository root using the bundled interpreter, and
read the linked sources.  Do not invent an effect, parameter, enum choice, or
source that is absent from their results.

```powershell
# The definitive effect and parameter inventory (save/review its JSON output).
.\.python\Scripts\python.exe scripts\export_authoring_contract.py

# Exact Show syntax, targets, common controls, motion, branches, and paths.
Get-Content -Raw docs\current\show-v2-authoring.md

# Human-oriented effect and typed-parameter references.
Get-Content -Raw docs\reference\effect-reference.md
Get-Content -Raw docs\reference\effect-parameter-metadata.md

# Inputs and opt-in advanced authoring blocks.
Get-Content -Raw docs\reference\parameter-modulation.md
Get-Content -Raw docs\reference\color-source.md
Get-Content -Raw docs\reference\wled-audio-sync-v2.md
Get-Content -Raw light_engine\effects\scalar_source.py
Get-Content -Raw light_engine\models.py

# Validation and compatibility edge cases.
.\.python\Scripts\python.exe -m pytest -q tests/test_phase37_parameter_metadata.py tests/test_phase38_parameter_modulation.py tests/test_phase39_color_source.py tests/test_virtual_paths.py tests/test_show_branch_lifecycle_schema_phase34.py tests/test_branch_lifecycle_runtime_phase34.py tests/test_app_host_api_v1_freeze.py

# Current target catalog, active Show boundary, examples, and frozen APP facade.
Get-Content -Raw config\layout.yaml
Get-Content -Raw config\README.md
Get-Content -Raw config\profiles\rk3588-host-service.yaml
Get-Content -Raw config\shows\README.md
Get-Content -Raw config\shows\energy-wakeup.yaml
Get-Content -Raw config\examples\minimal-show-v1.yaml
Get-Content -Raw config\examples\teacher-demo-show-v2.yaml
Get-Content -Raw config\examples\cabin-show-fork-v2.yaml
Get-Content -Raw docs\reference\host-api-v1.md
Get-Content -Raw docs\reference\host-api-v1.openapi.yaml
```

Before drafting, mechanically enumerate the exporter JSON's every final effect
ID and every effect-specific parameter, identify common controls, and identify
only the `modulatable: true` parameters.  Enumerate `ScalarSource` values,
every parameter-modulation source (including raw-domain rules), all six
`ColorSource` types, branch lifecycle choices, target/path behavior, and cue
YAML structure.  Inspect several current examples and the listed validation
tests for edge cases.  No effect may be omitted and no parameter may be
invented.

## Required manual order

Write the manual in this exact conceptual order; explain concepts before their
advanced combinations.

1. What the system is
2. Minimal mental model
3. What the APP controls vs what Show YAML controls
4. Anatomy of one Show
5. Anatomy of one cue
6. Targets / strip IDs / logical paths
7. Common controls
8. Four common spatial origins
9. Motion speed semantics
10. Complete effect catalog
11. For **every** effect: appearance; when to use it; every accepted parameter;
    meaning; authoritative range/choices; interaction with common speed and
    intensity; `ColorSource` support; modulation support; `virtual_path`
    behavior; and a minimal YAML example
12. ScalarSource
13. Existing `audio_modulation`
14. `parameter_modulation`
15. `modulate` vs `drive`
16. Dominant-frequency explicit normalization
17. ColorSource
18. Spatial palettes
19. Audio-driven colors
20. Video-driven colors
21. `virtual_path`
22. Branch `after`
23. `start_on_release`
24. `pre_roll`
25. Color timeline
26. Combining multiple mechanisms
27. Several complete practical recipes
28. Invalid/unsafe combinations
29. Debugging and validation
30. Glossary

Do not make the effect catalog a giant uncontextualized parameter dump.

## Explanation standard

Write for lighting-goal-aware teammates, not engine implementers.  For every
important concept cover: what it is, why it exists, what the user sees, how to
author it, and what it does **not** mean.  Use small concrete YAML examples.
Explicitly distinguish:

- manual base parameter vs modulation;
- `speed` vs internal `motion_time`;
- `virtual_path` vs branch;
- branch release time vs lifecycle simulation start;
- audio data vs authored visual meaning;
- APP playback control vs Show authoring;
- ColorSource color sampling vs base renderer brightness envelope: ColorSource dynamically samples RGB colors, but the underlying effect renderer retains its spatial/temporal brightness envelope (such as chase trail fade, breath pulse curve, comet decay). Authors must understand that full-brightness ColorSource input can still appear dimmed or shaped by the effect's intensity envelope.

Preserve compatibility language: old `ColorSpec` (`effect_default`, `solid`,
`palette`) is unchanged; `ColorSource` is a separate opt-in block.  Do not say
low frequency has a global color, do not claim the APP edits individual effects,
and describe Energy Wakeup only as an existing compatible Show—not as the
system's definition or limit.

## Verification and required final checklist

Before finalizing, mechanically compare the manual against the exporter and
the discovery commands.  Include a final coverage checklist proving:

- every registered effect is documented exactly once;
- every authorable parameter spec is represented;
- enum choices agree with the live registry;
- each common control, `ScalarSource`, modulation source, and all six
  `ColorSource` types is covered;
- accurate hardware/software terminology is used (RK3588 central host, ESP32 nodes, WLED upstream reference; no WT04 for RK3588, no WLED for our nodes);
- ColorSource color sampling vs base renderer brightness envelope is clearly explained;
- no claim says the APP edits individual effects;
- no global low-frequency color meaning is claimed; and
- Energy Wakeup is only an existing compatible Show.

If any item cannot be substantiated from the listed discovery sources, correct
the manual rather than guessing.

