# Phase 38 software acceptance

Date: 2026-08-23  
Scope: internal Show v2 safe effect-parameter modulation  
Hardware status: **NOT HARDWARE VERIFIED**

## Result

**PASS.**

Show v2 now accepts a cue-local `parameter_modulation` list alongside the unchanged
`audio_modulation` block. `modulate` multiplies an explicitly authored base by a mapped multiplier;
`drive` maps the normalized source directly into the authored output bounds. Only the 11 live Registry
parameters whose `ParameterSpec` is exactly `kind=float`, `runtime_mutable=true`, and `modulatable=true`
are accepted. Common brightness/speed/intensity and all enum, boolean, integer, ID, object, unsafe,
unknown, adaptive-effect, missing-base, and duplicate-target bindings fail closed.

Naturally normalized `ScalarSource` inputs preserve the old `sample()` zero-on-absence contract while a new
internal optional sample distinguishes legitimate zero from unavailable audio. Raw level, dominant frequency,
and dominant magnitude require explicit `input_min/input_max`; no global dominant-frequency normalization or
expression evaluator exists. Drive requires an explicit in-range fallback for audio sources. Modulate without
fallback restores its authored base immediately; explicit fallbacks are smoothed normally.

Positive smoothing uses cue delta-time and `1-exp(-dt/tau)`, giving 30/60 FPS elapsed-time equivalence. State
is cue/branch-local and reset/replay deterministic. Focused pre-roll coverage proves hidden branches consume
the actual changing historical `AudioFeatures` frames before release. The legacy common audio modulation
result remains exact when both systems coexist.

The loader validates the Cartesian product of all endpoint/fallback values, including the implicit neutral
multiplier for an unavailable modulate source, through the selected effect's live validator. Runtime final
values are validated again before rendering. This closes cross-target relational hazards such as
`flowing_bands.highlight_gain < base_gain`.

No Host route, OpenAPI field, APP capability, or internal effect ID was added. The Registry remains at 22
effects; APP V1 continues to use its frozen projection.

## Phase 38 files

- `light_engine/effects/__init__.py`
- `light_engine/effects/scalar_source.py`
- `light_engine/show/__init__.py`
- `light_engine/show/models.py`
- `light_engine/show/loader.py`
- `light_engine/show/compositor.py`
- `light_engine/show/parameter_modulation.py`
- `scripts/benchmark_parameter_modulation.py`
- `tests/test_phase38_parameter_modulation.py`
- `docs/reference/effect-reference.md`
- `docs/reference/effect-parameter-metadata.md`
- `docs/reference/parameter-modulation.md`
- `docs/acceptance/phase38-software-acceptance.md`

The worktree also contains the earlier approved Gate 0 and Phases 35-37 changes; they were preserved. The
unrelated untracked `.codex/` directory was not touched.

## Command evidence

| Purpose | Command | RC | Result |
|---|---|---:|---|
| Focused implementation and legacy audio gate | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase38_parameter_modulation.py tests/test_phase37_parameter_metadata.py tests/test_audio_modulation_loader.py tests/test_audio_modulation_runtime.py tests/test_show_engine_audio_modulation.py` | 0 | 52 passed in 1.24s (earlier focused checkpoint). |
| Metadata compatibility focus | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase38_parameter_modulation.py tests/test_phase37_parameter_metadata.py tests/test_effect_registry.py tests/test_effects.py tests/test_show_v2.py tests/test_show_config.py` | 0 | 177 passed in 1.81s. |
| Final effect/runtime/Host compatibility gate | `.\.python\Scripts\python.exe -m pytest -q tests/test_effects.py tests/test_effect_color_timeline.py tests/test_effect_registry.py tests/test_phase32_native_effects.py tests/test_phase32_effect_closeout.py tests/test_phase33_scalar_color_wipe.py tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py tests/test_phase35_coherent_noise_field.py tests/test_phase36_wled_closure.py tests/test_phase37_parameter_metadata.py tests/test_phase38_parameter_modulation.py tests/test_common_motion_clock_phase34.py tests/test_simple_effects_motion_phase34.py tests/test_phase34_complex_effect_motion.py tests/test_show_engine.py tests/test_show_engine_audio_modulation.py tests/test_audio_modulation_loader.py tests/test_audio_modulation_runtime.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py` | 0 | 342 passed, 2 warnings in 9.39s. |
| Show/branch/Energy/APP cross-module gate | `.\.python\Scripts\python.exe -m pytest -q tests/test_show_engine.py tests/test_virtual_paths.py tests/test_show_branch_lifecycle_schema_phase34.py tests/test_branch_lifecycle_compatibility_phase34.py tests/test_branch_lifecycle_runtime_phase34.py tests/test_branch_lifecycle_continuity_phase34.py tests/test_branch_lifecycle_output_isolation_phase34.py tests/test_common_motion_clock_phase34.py tests/test_simple_effects_motion_phase34.py tests/test_phase34_complex_effect_motion.py tests/test_phase32_energy_wakeup_non_regression.py tests/test_phase33_software_acceptance.py tests/test_phase34_common_motion_acceptance.py tests/test_host_effect_registry.py tests/test_app_host_api_v1_freeze.py tests/test_ws2811_two_node_all_effects_show.py` | 0 | 118 passed, 2 warnings in 11.87s. |
| Representative combined modulation benchmark | `.\.python\Scripts\python.exe scripts/benchmark_parameter_modulation.py` | 0 | 600 frames, 9 strips, 200 groups, 1.532140s, **391.609 FPS**. |
| Live Registry count | `.\.python\Scripts\python.exe scripts/export_authoring_contract.py | .\.python\Scripts\python.exe -c "import json,sys; data=json.load(sys.stdin); print('effects=',len(data['effects'])); print('modulatable=',sum(p['modulatable'] for e in data['effects'] for p in e['parameters']))"` | 0 | `effects=22`, `modulatable=11`. |
| Energy asset hash | `Get-FileHash -Algorithm SHA256 assets/energy-wakeup/energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, unchanged. |
| Diff hygiene | `git diff --check` | 0 | No whitespace errors; only expected LF-to-CRLF warnings. |

## Failure loop evidence

The first cross-module gate failed 22 tests with one compatibility root cause: compositor entered the new
Registry path for old injected test renderers (`capture`, `counting`, `solid-counting`) even when the cue did
not declare parameter modulation. The implementation was corrected so Registry lookup and final parameter
validation occur only for an explicitly authored `parameter_modulation` block. The entire failed cross-module
gate was rerun and passed as recorded above; acceptance criteria and tests were not weakened.

Primary metadata review then found two Phase 37 declarations that had unintentionally narrowed established
Show behavior: `chase.width` excluded the renderer's documented zero-width state, and `single_dot.direction`
excluded its documented/configured `bounce` mode. Their live specs were corrected to `minimum: 0` and
`forward|reverse|bounce`, respectively. Direct Registry plus Show-loader regressions were added, followed by
the focused, effect/runtime/Host, and Show/Energy/APP reruns recorded above.

## Limitations

- `parameter_modulation` is Show v2/fixed-effect only. Adaptive effects are rejected because their selected
  effect contract can change at runtime.
- This phase does not add ColorSource or any Phase 39 behavior.
- Repository-wide pytest is explicitly **USER-WAIVED** for this campaign and is not claimed as passing.
- Benchmark evidence is from this development machine, not RK3588 hardware.
- No firmware, transport, powered lighting, timing, or visible output was tested; all hardware behavior remains
  **NOT HARDWARE VERIFIED**.
