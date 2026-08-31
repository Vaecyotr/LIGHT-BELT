# Single-Strip Visual Acceptance v1

**NOT HARDWARE VERIFIED.** This directory is an acceptance fixture, not an active production Show library. It targets only `strip_31`: 10 logical pixels / 10 WS2811 controllable groups / approximately 50 cm.

## Campaign parts

| Part | Purpose | Cues | Duration |
| --- | --- | ---: | ---: |
| `baseline-show.yaml` | deterministic calibration, effects, color, Show controls, cue-progress modulation, stress | 111 | 12.0 min |
| `live-audio-show.yaml` | speaker → air → one ESP32 mic → WLED Audio Sync V2 → RK3568 → strip_31 | 35 | 5.3 min |
| `video-fusion-show.yaml` | deterministic local video plus optional live WLED audio | 26 | 3.3 min |

Machine coverage is in `coverage-plan.json`; deterministic render evidence is in `../../../artifacts/baselines/single-strip-visual-v1/software-baseline.json`. Hardware coverage counts are {"FALLBACK_ONLY": 2, "FULL": 172, "NOT_COVERABLE_SINGLE_STRIP": 7, "PARTIAL": 30, "UNOBSERVABLE_ON_10_GROUP": 2}. A software `FULL` record never means hardware PASS.

## Generate and validate

```powershell
.\.python\Scripts\python.exe scripts\generate_single_strip_acceptance_campaign.py
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/baseline-show.yaml
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/live-audio-show.yaml
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-v1/video-fusion-show.yaml
```

Optional stimuli go under `artifacts/runs`, never this fixture directory:

```powershell
.\.python\Scripts\python.exe scripts\generate_single_strip_acceptance_campaign.py --stimulus-dir artifacts/runs/single-strip-visual-v1/stimuli
```

## H0–H7 RK3568 physical runbook

### H0 — Electrical and safe start

Operator confirms ESP32, WS2811 power/ground/data, actual ten controllable groups, conservative brightness, and a reachable safe-black command. Do not begin with full-white/high-brightness stress.

### H1 — Target identity

Confirm the Host resolves the expected node for `strip_31`; other nodes may be offline. Do not edit topology. Record resolved host and node 6 mapping.

### H2 — Calibration

Run the `CAL_*` section. Record RGB order, actual group count, first/last logical group, physical forward/reverse direction, DDP update, and blackout.

### H3 — Baseline Show

Run `baseline-show.yaml`. For every human cue record `PASS`, `PARTIAL`, `FAIL`, `UNOBSERVABLE_ON_10_GROUP`, or `NOT_APPLICABLE`, plus actual/expected/difference/reason, photo/video reference, and notes. LIMIT scenes are intentional pathologies and never substitute for IDENTITY.

### H4 — Live audio

Use exactly one WLED Audio Sync sender/microphone. Record its expected IP and WLED `useBandPassFilter`, AGC/gain, and FFT scaling. During the run verify diagnostics show `stale=false`, increasing `packets_valid`, and stable `last_sender`. `audio_available=true` alone is insufficient.

Play the generated WAV through a speaker into air and the ESP32 microphone. **Do not attach it as Engine `--audio`, Host `audio_path`, or audio-only `media_path`: file audio has priority and would silently bypass WLED live input.** Use an external speaker player or `run-mpv --media <stimulus.wav> --show ...`, confirming this path does not call `Engine.load_audio`.

The diagnostic tones are 160/1000/4000 Hz because they avoid default WLED bin boundaries, but the hardware preflight must first record that each tone actually dominates the intended aggregate bin group. Continue with sweep, isolated broadband click, regular and irregular beats, continuous energy, then a short real-music excerpt. Fresh silence, fresh gap, stale zero-valued features, and missing input are different states; authored fallback is not evidence of a live source.

### H5 — Local video

Play the deterministic local AVI with `video-fusion-show.yaml`. Independently confirm file open, clock/timeline movement, and response to known hard cuts. `video_available=true`, black/zero features, or a fallback color alone does not prove live video. Compare average versus dominant only on the prescribed mixed scenes and retain the known shared-smoother limitation.

### H6 — Fusion

Run local video plus speaker audio captured by the same single WLED mic. Compare video-only versus audio-heavy scenes. `treble_limit=0` is the deterministic no-shimmer baseline; live `0` versus `0.10` is the only shimmer contrast. One strip is PARTIAL for multi-region fusion.

### H7 — Safe end and recovery

Allow `SAFE_fade_to_black` and `SAFE_black_hold` to complete, stop playback, confirm `strip_31` is black, restart ESP32/RK3568 only if required, and rerun calibration without topology edits.

## Hardware observation record

```text
cue_id:
result: PASS | PARTIAL | FAIL | UNOBSERVABLE_ON_10_GROUP | NOT_APPLICABLE
expected_observation:
actual_observation:
difference:
possible_reason:
photo_or_video_reference:
operator_notes:
```

Multi-strip seams/branches, cross-strip continuity, simultaneous spectrum zones, multi-region video, multi-node synchronization, packet latch skew, and multi-strip ColorSource continuity are `NOT_COVERABLE_SINGLE_STRIP`. Hardware gates H0–H7 remain `NOT RUN` until physically executed.
