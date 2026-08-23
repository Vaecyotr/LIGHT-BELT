# Phase 36 software acceptance

Date: 2026-08-23  
Baseline HEAD: `2db411e1e952c5011ed2bfa865097cba306178aa`  
Scope: final WLED v16.0.1 1D closure; software only  
Hardware status: **NOT HARDWARE VERIFIED**

## Result

**PASS — WLED 1D portability research CLOSED.**

The original 25-family audit is closed in
`docs/reference/wled-1d-closure-phase36.md`: `COVERED=13`,
`COVERED_BY_PHASE35=1`, `BOUNDED_PARAM_EXTENSION=4`,
`DEFER_TO_COLORSOURCE_PHASE39=2`, `OUT_OF_SCOPE=5`, and `NEW_PRIMITIVE=0`.
No WLED aliases or new effect IDs were added; the internal registry remains 22 effects.

Implemented optional extensions:

- `step_pulse.duty_cycle`, conventional HIGH fraction with low-first phase, default `0.5`;
- `breath.waveform`, `sine|triangle|smoothstep`, default `sine`;
- `color_wipe.edge_softness_px` and `progress_curve=linear|smoothstep`, defaults `0` / `linear`;
- `color_wave.waveform=linear|sine|triangle|saw` and `hue_span_degrees`, defaults `linear` / `120`.

Focused tests mechanically compare every omitted parameter with its explicit historical default,
exercise alternatives, reject invalid values, preserve one-path-before-split `virtual_path` behavior,
and prove the registry stays at 22 effects.

## Retry record

1. The first new focused run returned 1: 11 new tests failed because their fixture supplied
   `delta_time=0`, which `EffectContext` correctly rejects. The fixture was repaired to use a
   positive 1/60-second tick; production code was not weakened.
2. Primary review found that `duty_cycle` initially described the LOW fraction. It was corrected
   to the conventional HIGH fraction while retaining the low-first phase. Boundary tests now prove
   `0` is always low, `1` always high, and `0.5` preserves the historical transition.

## Command evidence

| Purpose | Command | RC | Result |
|---|---|---:|---|
| Bundled interpreter gate | `.\.python\Scripts\python.exe -c "...PROJECT_PYTHON_OK..."` | 0 | Bundled interpreter and workspace-local `light_engine` verified. |
| Pre-change bounded baseline | `.\.python\Scripts\python.exe -m pytest -q tests/test_effects.py tests/test_effect_registry.py tests/test_phase33_scalar_color_wipe.py tests/test_phase34_common_motion_acceptance.py tests/test_phase35_coherent_noise_field.py tests/test_app_host_api_v1_freeze.py` | 0 | 133 passed, 2 warnings, 1.89s. |
| Initial focused run | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase36_wled_closure.py tests/test_effects.py tests/test_effect_registry.py tests/test_phase33_scalar_color_wipe.py` | 1 | 11 fixture failures, 118 passed, 1.44s; repaired as above. |
| Repaired focused + adjacent | same four-file command | 0 | 129 passed, 0.87s. |
| Final effect/adjacent/immutable-APP gate | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase36_wled_closure.py tests/test_effects.py tests/test_effect_registry.py tests/test_phase33_scalar_color_wipe.py tests/test_phase34_common_motion_acceptance.py tests/test_phase35_coherent_noise_field.py tests/test_phase32_energy_wakeup_non_regression.py tests/test_app_host_api_v1_freeze.py` | 0 | 159 passed, 2 warnings, 5.87s. |
| Final Phase 36 focused file | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase36_wled_closure.py` | 0 | 24 passed, 0.47s. |
| Cross compatibility gate | `.\.python\Scripts\python.exe -m pytest -q tests/test_show_v2.py tests/test_show_config.py tests/test_show_common_effect_controls.py tests/test_virtual_paths.py tests/test_show_branch_lifecycle_schema_phase34.py tests/test_branch_lifecycle_compatibility_phase34.py tests/test_phase32_energy_wakeup_non_regression.py tests/test_phase33_software_acceptance.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py tests/test_ws2811_two_node_all_effects_show.py` | 0 | 106 passed, 2 warnings, 7.06s. |
| Immutable Show hash | `Get-FileHash -Algorithm SHA256 assets/energy-wakeup/energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, unchanged. |
| Effect inventory | bundled Python `list_effects()` inspection | 0 | Exactly 22 internal effects. |
| Diff hygiene | `git diff --check` | 0 | No whitespace errors; Git emitted only expected CRLF conversion warnings. |

Repository-wide pytest is explicitly **USER-WAIVED** due runtime cost and was not run. Phase 36
does not require a campaign performance benchmark; benchmarks are assigned after Phases 35, 38,
39, and 40. Firmware and physical transport behavior were not changed or tested.

## Compatibility conclusion

- Energy Wakeup source is byte-identical and its focused load/replay tests pass.
- Old YAML without Phase 36 fields remains valid.
- Existing default effect output remains compatible; the four extensions are opt-in.
- Existing `audio_modulation`, ColorSpec, branch default/lifecycle, common motion and
  `virtual_path` behavior remain compatible in the selected cross suites.
- APP Host API V1 freeze passes; no APP changes or internal metadata exposure are required.
- No firmware, topology, protocol, DDP, or hardware behavior changed.
