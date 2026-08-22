# Phase 34 Integrated Common Motion Clock — Software Acceptance

Date: 2026-08-22

Baseline HEAD: `320dd90d638fddc63a5cc6a2cfd0cca46f0b4d3e`

Worktree: `A:\BaiduNetdiskDownload\LIGHT-BELT\.agent-worktrees\WT04-github-main-reference`

## Decision and scope

Phase 34 software acceptance is complete at its approved stop boundary. One
cue-scoped `CueMotionClock` integrates the final composed common speed and
publishes an immutable `MotionInterval` to renderers. Released branches share
the parent cue clock. Common speed is now an instantaneous motion-rate
multiplier: dynamic changes affect future slope only, zero pauses, and resume
continues from the frozen phase. Constant speed remains equivalent to
`cue_local_time × speed`.

The migrated set is `single_dot`, `theater_phase`, `flowing_bands`, default
time-driven `color_wipe`, `history_stream`, `heat_fire`, `onset_ripple`, and
the stateless/multi-emitter comet branch. External `color_wipe` ScalarSource
progress and the legacy single-emitter comet branch are unchanged. No effect
ID, authored parameter, Show v2 syntax, topology, DDP, protocol, or ESP32
firmware behavior was added or changed.

The user explicitly directed this run to omit repository-wide pytest because
of its runtime cost. Accordingly, no full-suite pass is claimed. Validation
used the Phase-focused and adjacent regression suites below.

## Authoritative runtime semantics

- Fixed cue speed composition remains global/input speed × authored
  `effect.speed` × audio speed multiplier, followed by the existing clamp.
- Adaptive cue composition remains selector speed × authored `effect.speed` ×
  audio speed multiplier, followed by the same clamp.
- The current interval's final composed speed advances cue motion. Repeated
  timestamps return the existing interval and do not advance twice.
- A fixed cue first rendered after its start bootstraps constant-speed motion
  from cue-local zero. Dynamic live-audio history is not synthesized.
- Backward timestamps still require reset and replay from the beginning.
- `history_stream` maps crossed motion boundaries back into the current cue
  wall-time interval for authored timeline sampling; current live scalar gain
  is reused without inventing prior audio samples.
- `onset_ripple` propagation uses motion age while `decay_seconds` uses real
  cue age. Color timelines remain cue wall time.

## Verification evidence

| Check | Command | RC | Result |
| --- | --- | ---: | --- |
| Bundled Python | `.\.python\Scripts\python.exe -c "...AGENTS.md interpreter assertion..."` | 0 | `PROJECT_PYTHON_OK`; package loaded from this worktree |
| Wave 1 isolated clock | `.\.python\Scripts\python.exe -m pytest -q tests\test_common_motion_clock_phase34.py` | 0 | 19 passed, 0.58s |
| Primary Wave 1 gate | `.\.python\Scripts\python.exe -m pytest -q tests\test_common_motion_clock_phase34.py tests\test_show_common_effect_controls.py tests\test_show_engine_audio_modulation.py tests\test_adaptive_selector.py tests\test_show_v2.py tests\test_models.py tests\test_virtual_paths.py` | 0 | 140 passed, 1.28s |
| Simple migrations | `.\.python\Scripts\python.exe -m pytest -q tests\test_simple_effects_motion_phase34.py tests\test_common_motion_clock_phase34.py tests\test_effects.py tests\test_phase32_native_effects.py tests\test_phase33_scalar_color_wipe.py` | 0 | 147 passed, 1.06s |
| Complex migrations | `.\.python\Scripts\python.exe -m pytest -q tests\test_phase34_complex_effect_motion.py tests\test_common_motion_clock_phase34.py tests\test_history_stream_phase33.py tests\test_phase32_native_effects.py tests\test_onset_ripple_phase33.py tests\test_comet_moving_emitters.py tests\test_effects.py tests\test_ws2811_two_node_virtual_path_comet_show.py` | 0 | 173 passed, 1.35s |
| Combined Wave 2 gate | Phase 34 core/simple/complex plus effects, Phase 32/33, audio/adaptive, Show and virtual-path focused files | 0 | 264 passed, 2.02s |
| Cross-effect acceptance | `.\.python\Scripts\python.exe -m pytest -q tests\test_phase34_common_motion_acceptance.py` | 0 | 7 passed, 0.54s |
| Phase 34 + Phase 32/33 final | Phase 34 tests plus Phase 32/33 effect/acceptance/non-regression files | 0 | 204 passed, 5.86s |
| Show / registry / virtual path | Effect registry, Host registry, Show v2/common controls/audio modulation/adaptive/virtual-path focused files | 0 | 108 passed, 1.83s |
| Host integration | `.\.python\Scripts\python.exe -m pytest -q tests\test_host_service_api.py -k "capabilities or effects_set_with_color or shows_listed"` | 0 | 3 passed, 71 deselected, 3 warnings, 1.20s |
| Final coherent focused suite | The preceding Phase 34, Phase 32/33, Show, registry and virtual-path files in one invocation | 0 | **312 passed, 7.44s** |
| Immutable Show | `Get-FileHash -Algorithm SHA256 assets\energy-wakeup\energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, identical to Phase 33 |
| Software benchmark | `.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800` | 0 | 1800 frames / 60.62s; 134.1 FPS; P50 7.23ms; P95 10.35ms; P99 10.82ms; 0 drops |
| Tracked diff whitespace | `git diff --check` | 0 | No whitespace error; Windows LF/CRLF conversion warnings only |
| New Phase 34 file whitespace | PowerShell trailing-whitespace scan over the six new Phase 34 files | 0 | `UNTRACKED_PHASE34_WHITESPACE_OK` |
| Residual coupling scan | `rg` for wall/cue time multiplied directly by `ctx.speed` in `light_engine/effects` | 1 (no match) | No migrated effect retains absolute-time/current-speed multiplication |
| Effect ID inventory | Bundled-Python `list_effects()` assertion | 0 | 21 existing IDs, unchanged |

During integration, one 264-test run returned RC 1 because the first unified
helper revision changed the Phase 33 direct-call, paused `history_stream`
sample policy. That compatibility behavior was restored, and the same 264-test
set then passed. The initially broad final focused command was manually stopped
after its unrelated full Host API portion proved slow; it is not counted as
passing evidence. The relevant Host endpoints were rerun explicitly as shown
above.

## Compatibility and limitations

- The immutable approved Show source is unchanged byte-for-byte.
- No new effect ID exists; all origin transforms remain compositor-owned and
  virtual paths remain continuous logical paths.
- Existing delta-time integrations in chase, color wave, and legacy comet were
  retained and covered by cross-effect regression.
- CueAudioModulator smoothing and AdaptiveEffectSelector calculations were not
  changed.
- Repository-wide pytest was not run by explicit user instruction; this is the
  principal remaining software-validation limitation.
- The benchmark is current Windows/Python evidence only. RK3588 performance,
  visible output, timing, wiring, and every physical claim remain **NOT
  HARDWARE VERIFIED**.
- No ESP32 build was required or run because Phase 34 did not change firmware.

The final whole-worktree tracked `git diff --stat` was `161 files changed,
3912 insertions(+), 11113 deletions(-)`. This includes the large uncommitted
Phase 31–33/governance baseline present before Phase 34 and excludes untracked
files, so it is not a Phase 34-only size claim. Final status remained dirty and
the branch remained 41 commits ahead of `origin/main`; no file was staged,
committed, pushed, or reverted.

Stop after Phase 34. Phase 35 is not approved or prepared.
