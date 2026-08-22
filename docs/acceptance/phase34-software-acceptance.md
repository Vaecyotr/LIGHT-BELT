# Phase 34 Integrated Common Motion Clock — Software Acceptance

Date: 2026-08-22

Baseline HEAD: `320dd90d638fddc63a5cc6a2cfd0cca46f0b4d3e`

Branch-lifecycle closeout baseline HEAD:
`0962d74e7b29f0874843a8b4870933308ee0bbb7`

Worktree: `A:\BaiduNetdiskDownload\LIGHT-BELT\.agent-worktrees\WT04-github-main-reference`

## Decision and scope

Phase 34 software acceptance, including the explicit branch-lifecycle
closeout, is complete at its approved stop boundary. One cue-scoped
`CueMotionClock` integrates the final composed common speed and publishes an
immutable `MotionInterval` to renderers. Branches share the parent cue clock.
Common speed is an instantaneous motion-rate multiplier: dynamic changes
affect future slope only, zero pauses, and resume continues from the frozen
phase. Constant speed remains equivalent to `cue_local_time × speed`.

The original migrated set is `single_dot`, `theater_phase`, `flowing_bands`, default
time-driven `color_wipe`, `history_stream`, `heat_fire`, `onset_ripple`, and
the stateless/multi-emitter comet branch. External `color_wipe` ScalarSource
progress and the legacy single-emitter comet branch remain unchanged. The
closeout adds only optional Show v2 branch field `lifecycle`; it does not bump
the Show version. No effect ID, effect parameter, topology, DDP, protocol, or
ESP32 firmware behavior was added or changed.

The user explicitly directed this run to omit repository-wide pytest because
of its runtime cost. Accordingly, no full-suite pass is claimed. Validation
used the Phase-focused and adjacent regression suites below.

## Branch lifecycle closeout semantics

Branch visibility and branch simulation start are independent decisions:

- The existing `after` path-member predicate still controls the first visible
  frame. Its path-progress calculation is unchanged.
- Omitted `lifecycle` defaults to `start_on_release`. This preserves old YAML:
  the branch does not process while hidden, and release is its first process.
- Explicit `lifecycle: pre_roll` processes the branch exactly once on every
  observed active cue frame, starting at cue activation. Contributions are
  discarded before composition until release. The release frame uses that
  frame's single already-current update without reset, reseed, or replay.
- A hidden pre-roll branch receives live cue time, the shared motion interval,
  common speed, audio/video features, authored color timeline, ScalarSource,
  and existing effect-specific inputs. Missing historical live input is never
  synthesized; backward seek still requires reset plus replay.
- Parent and branches remain independent effect instances with their existing
  deterministic seeds. Pre-roll does not force their random state to match.
- `virtual_path` remains the spatial-continuity mechanism. Lifecycle neither
  joins paths nor changes path mapping, origin, targets, or release progress.
- Hidden rendering has only host CPU/state cost. It does not enter the final
  composite, allocate a logical output sequence, trigger a transport send, or
  reach an ESP32.

The software goldens prove omitted/default equivalence, fresh-on-release,
same-frame single processing, reset/replay, chase and six other state models,
changing authored `history_stream` colors, actual time-varying audio history,
multiple/mixed branches, never-released branches, virtual-path orthogonality,
and output/sequence isolation.

## Branch lifecycle performance evidence

The reproducible fixture uses nine logical strips with
`22,22,22,22,22,22,22,22,24` groups (200 total), one visible parent, and
`0/1/3/5` unreleased pre-roll branches. Timing excludes the separate short
`tracemalloc` sample. The five-hidden-branch results are:

The full 12-case report is
`artifacts/baselines/phase34-branch-lifecycle/benchmark.json`.

| Representative effect | FPS | Mean | P95 | Mean overhead vs 0 branches | Peak allocation indicator |
| --- | ---: | ---: | ---: | ---: | ---: |
| `chase` (cheap) | 224.523 | 4.454 ms | 5.495 ms | 271.0% | 258.8 KiB |
| `history_stream` (stateful) | 252.653 | 3.958 ms | 4.539 ms | 259.4% | 259.7 KiB |
| `heat_fire` (heavy) | 161.906 | 6.176 ms | 7.283 ms | 349.3% | 295.0 KiB |

The conservative minimum is **161.906 FPS**, so the current-development-machine
30 FPS software gate passes. This is not an RK3588 measurement and is **NOT
HARDWARE VERIFIED**.

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
| Closeout focused baseline | `.\.python\Scripts\python.exe -m pytest -q tests\test_show_v2.py tests\test_common_motion_clock_phase34.py tests\test_virtual_paths.py tests\test_compositor.py tests\test_show_config.py` | 0 | 91 passed, 1.32s |
| Closeout Wave 1 gate | Lifecycle schema/runtime/compatibility plus Show, motion, virtual-path, compositor and config focused files | 0 | 108 passed, 1.45s |
| Closeout Wave 2 gate | All lifecycle files plus adjacent motion/state, virtual-path, compositor, Show runtime files | 0 | 165 passed, 4.58s |
| Closeout final focused suite | 26 explicitly selected lifecycle, Phase 34, adjacent Phase 32/33, Show, virtual-path, registry and immutable-Show files | 0 | **403 passed, 7.97s** |
| Closeout Host integration | `.\.python\Scripts\python.exe -m pytest -q tests\test_host_service_api.py -k "capabilities or effects_set_with_color or shows_listed"` | 0 | 3 passed, 71 deselected, 3 warnings, 1.37s |
| Branch lifecycle benchmark | `.\.python\Scripts\python.exe scripts\branch_lifecycle_benchmark.py --warmup-frames 30 --measured-frames 120 --memory-frames 3 --minimum-five-branch-fps 30 --output artifacts\baselines\phase34-branch-lifecycle\benchmark.json` | 0 | Five-branch minimum 161.906 FPS; gate passed |
| Immutable Show after closeout | `Get-FileHash -Algorithm SHA256 assets\energy-wakeup\energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`, unchanged |
| Closeout effect inventory | Bundled-Python `list_effects()` assertion | 0 | 21 existing IDs; no `coherent_noise_field` |
| Closeout tracked whitespace | `git diff --check` | 0 | No whitespace error; LF/CRLF conversion warnings only |
| Closeout new-file whitespace | PowerShell trailing-whitespace scan over eight new files | 0 | `NEW_CLOSEOUT_FILES_WHITESPACE_OK` |
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

During the lifecycle closeout, the first continuity-matrix revisions returned
RC 1 because of test-harness `delta_time` and nested-approximation errors; no
production defect was involved, and the corrected file passed 8 tests. An
initial performance fixture mistakenly used 1,800 total logical groups and
returned RC 1 with a 20.044 FPS minimum; a still heavier 30-frame memory sample
was stopped safely. Both were rejected as out of scope when the authoritative
requirement was reread. The corrected nine-strip, 200-total-group benchmark is
the passing evidence recorded above.

## Compatibility and limitations

- The immutable approved Show source and archived branch-bearing Show are
  unchanged byte-for-byte; the archived Show loads with the omitted lifecycle
  default and retains fresh-on-release behavior.
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

The Phase 34 branch-lifecycle closeout staged diff at commit review was **14
files changed, 1,899 insertions, 38 deletions**. The unrelated untracked
`.codex/` directory was deliberately excluded.

Stop after Phase 34. Phase 35 is not approved or prepared.
