# Phase 37 software acceptance

Date: 2026-08-23  
Scope: internal typed effect-parameter metadata; software only  
Hardware status: **NOT HARDWARE VERIFIED**

## Result

**PASS.**

The 22-effect internal registry now owns immutable `ParameterSpec` tuples. Each specification records
name, kind, optional numeric bounds/enum choices/unit, `runtime_mutable`, `modulatable`, and description.
`EffectRegistration.parameter_keys` is a derived compatibility property, so the Show loader cannot have a
separately maintained allowed-key list.

The registry applies generic typed metadata validation before existing effect-specific validators. Existing
validators retain relational and effect-specific checks; the registry wrapper still rejects validator output
outside the registered specs. This prevents accepted parameter names, types, scalar bounds and enum choices
from silently drifting away from exported metadata.

`scripts/export_authoring_contract.py` writes machine-readable JSON directly from the live registry. It is a
repository-local developer tool, not a Host endpoint. APP V1 has no metadata exposure and needs no change.
The export includes the complete stable `capability.common_params` sequence as well as the derived
`common_controls` subset.

## Conservative modulatable set

`breath.min_brightness`; `color_wave.hue_span_degrees`; all four
`video_audio_fusion` weights/limits; `color_wipe.edge_softness_px`;
`flowing_bands.base_gain`; `flowing_bands.highlight_gain`; `onset_ripple.floor_gain`; and
`coherent_noise_field.contrast`.

All common `brightness`, `speed`, and `intensity` controls are explicitly excluded. Other values can be
runtime-readable but remain non-modulatable when a live change affects state history, population, trajectory,
event lifetime or phase continuity.

## Command evidence

| Purpose | Command | RC | Result |
|---|---|---:|---|
| Focused metadata/optional-source/Host freeze | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase37_parameter_metadata.py tests/test_effect_registry.py tests/test_phase33_scalar_color_wipe.py tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py` | 0 | 117 passed, 2 warnings, 2.75s. |
| Effect/runtime integration | `.\.python\Scripts\python.exe -m pytest -q tests/test_effects.py tests/test_effect_color_timeline.py tests/test_effect_registry.py tests/test_phase32_native_effects.py tests/test_phase32_effect_closeout.py tests/test_phase33_scalar_color_wipe.py tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py tests/test_phase35_coherent_noise_field.py tests/test_phase36_wled_closure.py tests/test_phase37_parameter_metadata.py tests/test_common_motion_clock_phase34.py tests/test_simple_effects_motion_phase34.py tests/test_phase34_complex_effect_motion.py tests/test_show_engine.py tests/test_show_engine_audio_modulation.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py` | 0 | 298 passed, 2 warnings, 8.82s. |
| Show/legacy compatibility | `.\.python\Scripts\python.exe -m pytest -q tests/test_show_v2.py tests/test_show_config.py tests/test_show_common_effect_controls.py tests/test_virtual_paths.py tests/test_show_branch_lifecycle_schema_phase34.py tests/test_branch_lifecycle_compatibility_phase34.py tests/test_phase32_energy_wakeup_non_regression.py tests/test_phase33_software_acceptance.py tests/test_phase34_common_motion_acceptance.py tests/test_audio_modulation_loader.py tests/test_phase33_scalar_color_wipe.py tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py tests/test_ws2811_two_node_all_effects_show.py` | 0 | 187 passed, 2 warnings, 8.27s. |
| Exporter smoke check | `.\.python\Scripts\python.exe scripts/export_authoring_contract.py` | 0 | Valid live-registry JSON with 22 effects. |
| Energy asset hash | `Get-FileHash -Algorithm SHA256 assets/energy-wakeup/energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, unchanged. |
| Diff hygiene | `git diff --check` | 0 | No whitespace errors (Git emitted expected CRLF warnings only). |

The temporary failure during the first cross-module run was an existing Host-contract assertion that expected
the legacy wording `speed must be in ...`. Generic range validation initially returned `<=`; it was repaired
to preserve the bounded-range wording. The repaired full cross gate above passes.

## Limitations

- No Phase 38 parameter-modulation YAML/runtime exists yet.
- No Phase 39 ColorSource work exists yet.
- Registry metadata intentionally does not duplicate Config/renderer defaults.
- Repository-wide pytest is explicitly **USER-WAIVED**; it is not a pass claim.
- No firmware, transport or physical behavior changed; all hardware behavior remains **NOT HARDWARE VERIFIED**.
