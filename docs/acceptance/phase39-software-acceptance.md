# Phase 39 Software Acceptance

Status: **software accepted on 2026-08-23; NOT HARDWARE VERIFIED**.

## Scope closed

- Added a Show v2-only, cue-level, explicit `color_source` block with all six
  approved source types.
- Preserved existing `ColorSpec.effect_default`, `solid`, and `palette`
  behavior byte-for-behavior when the new block is omitted. Existing
  `chase`/`twinkle` effect parameters named `color_source` remain distinct.
- Added one reusable internal `ColorSampler` for global, normalized-position,
  and deterministic logical-event sampling.
- Sampled authored and layout virtual paths as one logical coordinate before
  member splitting; no per-member video-zone remap was added.
- Added explicit fixed RGB fallback for all video/audio sources. Phase 39 has
  no retain-previous fallback state.
- Recorded all 22 native effects as GLOBAL, POSITIONAL, EVENT, or
  NOT_APPLICABLE in the live registry and internal metadata exporter.
- Host/APP V1 schemas, models, and frozen projection remain unchanged.

## Evidence

Focused Phase 39 tests:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_phase39_color_source.py
35 passed in 0.53s (exit 0)
```

Phase 39 ownership, branch lifecycle, and compatibility cross-check:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_phase39_color_source.py tests\test_show_v2.py tests\test_effect_registry.py tests\test_phase37_parameter_metadata.py tests\test_effects.py tests\test_twinkle_event_fields_phase33.py tests\test_onset_ripple_phase33.py tests\test_branch_lifecycle_continuity_phase34.py tests\test_phase38_parameter_modulation.py
225 passed in 2.12s (exit 0)
```

Final effect/Show/virtual-path/branch/modulation/Host/APP/Energy cross-gate:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_effects.py tests\test_effect_color_timeline.py tests\test_effect_registry.py tests\test_phase32_native_effects.py tests\test_phase32_effect_closeout.py tests\test_phase33_scalar_color_wipe.py tests\test_twinkle_event_fields_phase33.py tests\test_history_stream_phase33.py tests\test_phase35_coherent_noise_field.py tests\test_phase36_wled_closure.py tests\test_phase37_parameter_metadata.py tests\test_phase38_parameter_modulation.py tests\test_phase39_color_source.py tests\test_common_motion_clock_phase34.py tests\test_simple_effects_motion_phase34.py tests\test_phase34_complex_effect_motion.py tests\test_show_engine.py tests\test_show_v2.py tests\test_virtual_paths.py tests\test_show_engine_audio_modulation.py tests\test_audio_modulation_loader.py tests\test_audio_modulation_runtime.py tests\test_branch_lifecycle_compatibility_phase34.py tests\test_branch_lifecycle_runtime_phase34.py tests\test_branch_lifecycle_continuity_phase34.py tests\test_branch_lifecycle_output_isolation_phase34.py tests\test_phase32_energy_wakeup_non_regression.py tests\test_host_effect_registry.py tests\test_app_host_api_v1_freeze.py tests\test_ws2811_two_node_all_effects_show.py
441 passed, 2 warnings in 17.65s (exit 0)
```

Dedicated frozen APP/Energy/current-Show gate:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_app_host_api_v1_freeze.py tests\test_host_effect_registry.py tests\test_phase32_energy_wakeup_non_regression.py tests\test_show_engine.py
20 passed, 2 warnings in 9.43s (exit 0)
```

The immutable original asset remains unchanged:

```text
Get-FileHash -Algorithm SHA256 assets\energy-wakeup\energy-wakeup.yaml
627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D (exit 0)
git diff --exit-code -- assets\energy-wakeup\energy-wakeup.yaml
no diff (exit 0)
scripts/export_authoring_contract.py exported 22 color_source_support entries
git diff --check: clean (exit 0)
```

Representative software-only benchmark:

```text
.\.python\Scripts\python.exe scripts\benchmark_color_source.py
phase39_color_source frames=600 strips=9 groups=200 layers=6 combined_modulation_cues=1 elapsed_seconds=12.061523 fps=49.745
NOT HARDWARE VERIFIED; current development machine only
```

The six-layer benchmark exercises every ColorSource type, and one compatible
cue simultaneously runs existing `audio_modulation`, Phase 38
`parameter_modulation`, and Phase 39 `color_source`. It exceeds the approved
`> 30 FPS` software floor. It is not an
RK3588 measurement or physical-output acceptance. Final cross-module counts,
APP freeze, Energy Wakeup hash, and immutable-asset checks are recorded above.

## Limitations

- Repository-wide pytest is user-waived for runtime cost; focused and
  cross-module suites are the evidence for this phase.
- No firmware, topology, DDP, ESP32, APP, or physical output behavior changed.
- Physical operation and RK3588 performance remain **NOT HARDWARE VERIFIED**.
