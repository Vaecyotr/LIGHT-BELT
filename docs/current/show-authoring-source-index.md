# Show authoring source index

## Contract status

The RK3588 1D lighting authoring language is **CLOSED/FROZEN**.  Bug fixes and
compatibility-required additions remain possible, but do not proactively add
effects/primitives or casually redesign the Show contract.  This is a software
authoring-contract statement, not hardware or product-release verification.

## Authority and current material

1. [CLAUDE.md](../../CLAUDE.md) — permanent project facts, deployment
   terminology, architecture invariants, and the current Show boundary.
2. [CLOSED_LOOP_SPEC.md](../CLOSED_LOOP_SPEC.md) — target architecture and
   acceptance constraints.
3. [IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) — approved work and
   closure evidence.
4. [Show v2 authoring](show-v2-authoring.md) — canonical writable YAML syntax,
   cue/target/common-control semantics, motion, virtual paths, and branches.
5. The live registry and focused tests — implemented behavior and evidence.

Historical documents and `config/shows/archive/` are regression evidence only;
they are not current authoring contract.  The immutable original is
[`assets/energy-wakeup/energy-wakeup.yaml`](../../assets/energy-wakeup/energy-wakeup.yaml);
the only current runnable compatibility baseline is
[`config/shows/energy-wakeup.yaml`](../../config/shows/energy-wakeup.yaml).

## Authoring language

- [Effect reference](../reference/effect-reference.md) — teammate-readable
  catalog of the final effects, common controls, `ScalarSource`, and effect
  semantics.
- [Live typed authoring contract](../reference/effect-parameter-metadata.md)
  — immutable `ParameterSpec` rules and the command that exports the live
  registry as JSON; use this for exact parameter names, kinds, bounds, choices,
  runtime mutability, and modulatable flags.
- [`scripts/export_authoring_contract.py`](../../scripts/export_authoring_contract.py)
  — the live, machine-readable registry exporter; it is internal and not a
  Host API surface.
- [Parameter modulation](../reference/parameter-modulation.md) — opt-in
  effect-local `modulate`/`drive`, source vocabulary, raw-domain bounds,
  fallback, smoothing, validation, and replay semantics.
- [ColorSource](../reference/color-source.md) — opt-in cue-level dynamic color
  sources, required fallbacks, support classifications, and virtual-path
  sampling rules.  Its implementation is
  [`light_engine/show/color_source.py`](../../light_engine/show/color_source.py).
- [`light_engine/effects/scalar_source.py`](../../light_engine/effects/scalar_source.py)
  — the normalized `ScalarSource` vocabulary used by effects.
- [`light_engine/models.py`](../../light_engine/models.py) — authoritative
  `AudioFeatures`, `VideoFeatures`, and `EffectContext` field models consumed by
  Show runtime features.
- [WLED Audio Sync V2 reference](../reference/wled-audio-sync-v2.md) —
  `AudioFeatures`, live-input provenance, 16-band spectrum, and stale/reset
  behavior; it does not define a global audio-to-color meaning.

## Spatial and lifecycle semantics

- [Show v2 authoring: targets, virtual paths, branches, lifecycle](show-v2-authoring.md)
  — canonical explanation and YAML examples for target resolution,
  `virtual_path`, `after`, `start_on_release`, and `pre_roll`.
- [`light_engine/show/models.py`](../../light_engine/show/models.py) and
  [`light_engine/show/loader.py`](../../light_engine/show/loader.py) — final
  schema and validation source when prose needs confirmation.
- [`tests/test_virtual_paths.py`](../../tests/test_virtual_paths.py),
  [`tests/test_show_branch_lifecycle_schema_phase34.py`](../../tests/test_show_branch_lifecycle_schema_phase34.py),
  and [`tests/test_branch_lifecycle_runtime_phase34.py`](../../tests/test_branch_lifecycle_runtime_phase34.py)
  — focused compatibility and edge-case evidence.

## Physical targets, APP boundary, and examples

- [`config/layout.yaml`](../../config/layout.yaml) — package default / compatibility
  logical layout catalog (software reference; not the nine-node physical production deployment truth).
- [`config/profiles/rk3588-host-service.yaml`](../../config/profiles/rk3588-host-service.yaml)
  and [`config/README.md`](../../config/README.md) — authoritative source for the current
  nine-ESP32 Host production profile and runtime deployment targets. Physical transport
  remains in profiles, never in Show targets; deployment claims are **NOT HARDWARE VERIFIED**.
- [`config/shows/README.md`](../../config/shows/README.md) — current Show
  admission rules and the current-versus-archive boundary.
- [`config/examples/minimal-show-v1.yaml`](../../config/examples/minimal-show-v1.yaml),
  [`config/examples/teacher-demo-show-v2.yaml`](../../config/examples/teacher-demo-show-v2.yaml),
  and [`config/examples/cabin-show-fork-v2.yaml`](../../config/examples/cabin-show-fork-v2.yaml)
  — one v1 compatibility example plus current v2 teaching examples; new
  authoring emits v2, and all claims must be validated against the sources
  above.
- [Host API V1](../reference/host-api-v1.md) and
  [OpenAPI V1](../reference/host-api-v1.openapi.yaml) — frozen APP playback /
  control facade.  It does not expose effect metadata, per-effect authoring,
  `virtual_path`, lifecycle, modulation, or `ColorSource`.
- [`tests/test_app_host_api_v1_freeze.py`](../../tests/test_app_host_api_v1_freeze.py)
  — executable proof of the APP boundary.
