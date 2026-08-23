# Phase 35 Coherent Noise Field — Software Acceptance

Date: 2026-08-23

## Scope and result

Phase 35 adds exactly one internal RK3588-native effect ID,
`coherent_noise_field`, increasing the engine registry from 21 to 22 effects.
It combines a clean-room two-dimensional coherent value-noise primitive with a
logical one-dimensional renderer. The primitive accepts separate spatial and
temporal coordinates, a deterministic seed, and has no process-global RNG,
WLED/FastLED source, mode alias, palette, timing constant, or hardware
topology dependency.

The temporal coordinate is exactly Phase 34 integrated `motion_time ×
drift_rate`. Therefore pause freezes the field and a later speed change affects
only future motion slope. `color_timeline` remains compositor-owned cue wall
time. The compositor also remains the sole owner of origin and virtual-path
composition; virtual paths render continuously before splitting.

Analog zones use a deterministic sample at logical coordinate `0.5`, yielding
the default non-black fallback without assigning a physical coordinate. This
is software behavior only; all physical behavior is **NOT HARDWARE VERIFIED**.

APP V1 capability and OpenAPI effect vocabulary remain deliberately frozen:
`coherent_noise_field` is an internal registry capability and is absent from
the released APP projection.

## Verification evidence

| Check | Command | RC | Result |
| --- | --- | ---: | --- |
| Focused Phase 35 / registry / APP-freeze / Show / virtual-path / motion gate | `.\.python\Scripts\python.exe -m pytest -q tests\test_phase35_coherent_noise_field.py tests\test_effects.py tests\test_phase32_native_effects.py tests\test_phase33_software_acceptance.py tests\test_effect_registry.py tests\test_host_effect_registry.py tests\test_app_host_api_v1_freeze.py tests\test_virtual_paths.py tests\test_show_v2.py tests\test_simple_effects_motion_phase34.py tests\test_phase34_common_motion_acceptance.py` | 0 | 203 passed, 2 inherited FastAPI deprecation warnings, 3.08s on the primary rerun |
| Current-scale software benchmark | `.\.python\Scripts\python.exe -m light_engine benchmark --effect coherent_noise_field --frames 600` | 0 | 72.0 FPS; P50 14.25 ms; P95 18.05 ms; P99 18.68 ms; 0 output drops; comfortably exceeds 30 FPS on a 632-pixel synthetic workload |
| Full repository suite | `.\.python\Scripts\python.exe -m pytest -q` | incomplete / USER-WAIVED | An inadvertent invocation collected 1,310 tests and was stopped around 39%. The campaign explicitly waives repository-wide pytest for runtime cost, so no full-suite result is required or claimed. |
| Immutable Energy Wakeup asset | `Get-FileHash -Algorithm SHA256 assets\energy-wakeup\energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, unchanged. |
| Whitespace | `git diff --check` | 0 | No whitespace errors; Git reported only pre-existing LF/CRLF conversion warnings. |

## Focused coverage

The Phase 35 test module proves deterministic seed derivation, different cue
decorrelation, bounded finite output, spatial and temporal local coherence,
distant temporal change, feature-size mapping, contrast behavior, gain bounds,
pause/resume and dynamically integrated motion, reset/replay, one-pixel paths,
deterministic non-black analog fallback, invalid parameter rejection,
color-timeline wall-clock behavior, virtual seams, and compositor-owned origin.

## Limitations

- This is current Windows/Python software evidence only, not an RK3588
  measurement.
- Repository-wide pytest is explicitly **USER-WAIVED** for this campaign. The
  focused Phase 35 and adjacent integration gate is the only suite pass
  claimed here.
- No firmware, protocol, DDP, physical topology, or ESP32 behavior changed.
- No physical visual output was inspected. All such behavior remains
  **NOT HARDWARE VERIFIED**.
