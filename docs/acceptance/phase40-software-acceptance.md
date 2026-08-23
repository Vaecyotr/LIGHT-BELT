# Phase 40 Software Contract Closure Acceptance

Status: **software accepted on 2026-08-23; NOT HARDWARE VERIFIED**.

## Closed contract

- Host APP API V1 remains the frozen playback/control facade established by
  Gate 0. The APP requires no modification for Phases 35-40, and internal
  effects, typed metadata, modulation, ColorSource, virtual-path, and branch
  lifecycle internals are not advertised through it.
- The RK3588-native 1D lighting authoring language is **CLOSED/FROZEN**. Bug
  fixes and compatibility-required additions remain allowed; proactive new
  primitive/effect migration and casual Show-contract redesign do not.
- The final internal registry contains exactly 22 effects, 111 typed authorable
  parameters, and 11 conservatively approved modulatable float parameters.
- The six opt-in ColorSource types are `timeline`, `spatial_palette`,
  `video_average`, `video_dominant`, `audio_spectrum_palette`, and
  `dominant_frequency_palette`.
- Old Show YAML, old `ColorSpec` modes, old effect defaults, existing
  `audio_modulation`, branch default `start_on_release`, virtual paths, and the
  Energy Wakeup Show remain compatibility baselines.
- The authoritative navigation map is
  `docs/current/show-authoring-source-index.md`. The downstream teammate-manual
  work instruction is
  `docs/current/ANTIGRAVITY_SHOW_AUTHORING_MANUAL_TASK.md`; it is intentionally
  not the manual itself.

## APP V1 historical compatibility baseline and boundary

- **Known-good APP V1 baseline**:
  - Source repository: `https://github.com/zxlzzz/LIGHT-BELT`
  - Source commit: `0380e4e1ecb926148d9afc07b7f95f6ad0aa4c6b` (`0380e4e`)
  - Source date: `2026-08-19`
  - Reason: Last known-good pre-Phase32 integration state; APP + Host + Show playback were operational.
- **Contract principles**:
  - This is an immutable historical compatibility baseline.
  - The internal `EffectRegistry` is richer (22 effects, 111 ParameterSpecs, parameter modulation, ColorSource).
  - The APP-facing V1 vocabulary is strictly frozen and does not automatically expand as the internal registry grows.
  - New internal effects are not required to be known, parsed, or presented by the APP.
  - No new API version is introduced; Host API remains V1.
  - The APP is responsible for Show selection, play, pause, resume, stop, seek, overall brightness scale, volume, mute, and status display.
  - The APP is NOT responsible for per-strip effect authoring, parameter modulation, ColorSource, virtual paths, branches, or motion clocks; advanced lighting features remain encapsulated in Show YAML and RK3588 `light_engine`.
  - Machine-readable provenance is codified in fixture `tests/fixtures/app_v1/pre_phase32_0380e4e.json` and executed in `tests/test_app_host_api_v1_freeze.py`.
- **Target catalog cleanup**:
  - Legacy candidate/early targets (`ceiling_left`, `ceiling_right`, `wall_left`, `wall_right`, `front`, `rear`, `screen`, `screen_surround`, `virtual_path.screen_to_wall`) are documented as superseded historical records and removed from current documentation examples.
  - Active targets are dynamically profile-derived (`strip_<label>`, `all`, `starry_sky`).

## Final evidence

Final bounded campaign regression:

```text
.\.python\Scripts\python.exe -m pytest -q <35 focused test modules covering
Show, old configuration, effects, Phases 32-40, Energy, virtual paths,
branch lifecycle, motion, modulation, ColorSource, Host, and APP>
481 passed, 2 warnings in 18.63s (exit 0)
```

Final APP V1 freeze:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_app_host_api_v1_freeze.py tests\test_host_effect_registry.py tests\test_host_service_api.py -k "app_host_api_v1_freeze or host_effect_registry or capabilities or ws_ticket_url_uses_request_host or shows_no_media_path"
16 passed, 71 deselected, 3 warnings in 1.74s (exit 0)
```

Authoring discovery and guide dry-review gate:

```text
.\.python\Scripts\python.exe -m pytest -q tests\test_phase37_parameter_metadata.py tests\test_phase38_parameter_modulation.py tests\test_phase39_color_source.py tests\test_phase40_software_contract_closure.py tests\test_virtual_paths.py tests\test_show_branch_lifecycle_schema_phase34.py tests\test_branch_lifecycle_runtime_phase34.py tests\test_app_host_api_v1_freeze.py
111 passed, 2 warnings in 2.79s (exit 0)
```

The live authoring exporter completed with exit 0 and mechanically reported 22
effects, 111 parameters, 11 modulatable parameters, and all four ColorSource
support classifications. The guide's links and commands expose all six
ColorSource types, normalized and raw-domain modulation sources, branch
lifecycle, virtual-path behavior, and the frozen APP boundary.

Final representative software-only benchmark:

```text
.\.python\Scripts\python.exe scripts\benchmark_color_source.py
phase39_color_source frames=600 strips=9 groups=200 layers=6 combined_modulation_cues=1 elapsed_seconds=11.395325 fps=52.653
NOT HARDWARE VERIFIED; current development machine only
```

The benchmark combines all six ColorSource types; one cue simultaneously runs
existing `audio_modulation`, Phase 38 `parameter_modulation`, and Phase 39
`color_source`. It exceeds the approved 30 FPS development-machine software
floor. It is not an RK3588 or physical-output measurement.

Immutable Energy Wakeup source:

```text
Get-FileHash -Algorithm SHA256 assets\energy-wakeup\energy-wakeup.yaml
627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D (exit 0)
git diff --exit-code -- assets\energy-wakeup\energy-wakeup.yaml
no diff (exit 0)
```

## Limitations

- Repository-wide pytest is explicitly **USER-WAIVED** for runtime cost. The
  bounded regression gates above are the test evidence; no full-suite pass is
  claimed.
- The frozen `scene.applied` APP WebSocket vocabulary value is documented as
  reserved/unobserved; the current Host does not emit it and no new behavior
  was added in Phase 40.
- No ESP32 firmware, DDP behavior, physical topology, installed wiring, visible
  output, or timing behavior was changed or verified.
- All physical operation and RK3588 performance remain **NOT HARDWARE
  VERIFIED**.
- No commit was created.
