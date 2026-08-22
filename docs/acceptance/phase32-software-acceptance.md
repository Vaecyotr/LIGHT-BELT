# Phase 32 Software Acceptance

Date: 2026-08-21

Implementation base: `320dd90d638fddc63a5cc6a2cfd0cca46f0b4d3e`
on `codex/wt04/github-main/reference`, with the reviewed Phase 32 working-tree
changes described below. No commit was created by this acceptance task.

Status: **SOFTWARE CLOSEOUT ACCEPTED; NOT HARDWARE VERIFIED**

This report accepts only source, configuration, protocol, Host/API and test
contracts. It does not accept multicast delivery, mDNS reachability, DDP or
UDP-v3 receipt, firmware execution, electrical wiring, timing, color accuracy,
or visible strip output.

## Accepted software contracts

- The current production profile is nine independent WLED/DDP nodes. Its strip
  count is derived from `layout.strips`; DDP nodes do not author custom UDP-v3
  `max_udp_payload` or `protocol_version` metadata.
- `config/profiles/udp-v3-nine-strip-maintenance.yaml` remains a separate
  custom-firmware maintenance profile and retains its required UDP-v3 payload
  and protocol metadata. WLED is not claimed to implement this protocol.
- DDP packetization supports long frames, offset continuation, sequence wrap
  that skips zero, and PUSH only on each node's final packet.
- Audio Sync V2 parsing is pinned to WLED v16.0.1 / commit
  `29b389df1c1aaec6ff53aea742d17063b985906c`. Generic `AudioFeatures` preserves
  `raw_level`, normalized `loudness`, 16 spectrum bins, peak, dominant
  frequency and dominant magnitude, and continues deriving rms/bass/mid/
  treble/spectral_flux/onset/beat/silence. `fftBin` is not available through
  the V2 packet. Transmitted spectrum bytes use WLED's clamped `0..254` range
  and normalize by `254.0`; dominant frequency has no global visual meaning.
- The fixed-source Audio Reactive inventory covers 37 explicit effects:
  29 ordinary and 8 particle effects; A/DIRECT_V2 = 34,
  B/V2_APPROXIMATED = 3, C/INPUT_EXTENSION_REQUIRED = 0. This classification
  does not authorize a protocol or palette-framework change.
- The registry exposes 20 RK3588-native effects. Phase 32 adds
  `flowing_bands`, `onset_ripple`, and `heat_fire` without WLED runtime IDs or
  parameter compatibility.
- `flowing_bands` uses a fixed A/black-B pattern. The highlighted A advances
  discretely under the golden sequence `ABABAB`, `CBABAB`, `ABCBAB`,
  `ABABCB`, then loops; reverse, wider bands/gaps, partial tails, phase offset,
  common speed/intensity, color timeline and virtual-path seams are covered.
- Silence or stale audio does not create an onset ripple, but an existing wave
  continues to render from birth time, age and decay. `heat_fire` remains a
  deterministic fixed-step authored-color × heat simulation; no thermal
  palette is claimed.
- Host targets derive from the loaded layout. A synthetic tenth strip passes
  Config/Layout and appears in Host capabilities without a count field or API
  schema edit. OpenAPI `TargetId` is an open runtime-discovered string while
  `EffectType` remains registry controlled.

## Frozen Energy Wakeup regression

- Frozen source: `assets/energy-wakeup/energy-wakeup.yaml`.
- Expected SHA-256 from the pre-closeout audit:
  `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`.
- Final byte/hash, semantic-equality and representative-render results are
  recorded in the T8 table below. Phase 32 code and docs must not author this
  asset.

## Commands and results

| Scope | Command/result |
|---|---|
| Bundled Python identity | rc 0, `PROJECT_PYTHON_OK` |
| T1 audio focused | rc 0, `101 passed in 12.55s`; receiver recheck `14 passed in 2.09s` |
| T3 flowing/registry focused | rc 0, `46 passed, 10 deselected in 0.57s` |
| T4/T5 effect/topology/profile focused | rc 0, `27 passed in 2.66s` |
| Config/mapping/Host regression | rc 0, `186 passed in 315.40s` |
| T6 independent integration audit | rc 0, `128 passed in 4.78s` |
| T6 merged integration gate | rc 0, `143 passed in 13.35s` |
| T8 frozen asset / semantic / representative render | rc 0; SHA-256 `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`; `2 passed in 1.87s` |
| T8 final Phase 32 focused suite | rc 0, `123 passed in 12.06s` |
| T8 firmware/native UDP-v3 | rc 0, `58 Tests 0 Failures 0 Ignored`, `MSVC_NATIVE_TESTS_OK`; Python UDP-v3 chunking is included in the 123-test focused suite |
| Audio Sync V2 transmitted-range correction | rc 0, `102 passed in 6.39s`; covers decoder boundaries, invalid wire value 255, source lifecycle, Engine integration and generic audio models |
| Final repository pytest after the `/254.0` correction | rc 0, `1067 passed, 3 warnings in 560.78s` |
| Final schema/docs/diff review | rc 0; 37 inventory rows; no floating `main` source link; no retired Flowing Bands contract; `git diff --check` clean apart from line-ending conversion warnings |

## Known limitations

- All controller reachability, packet receipt, multicast behavior, WLED Audio
  Reactive usermod setup, actual refresh, visual output and timing remain
  **NOT HARDWARE VERIFIED**.
- Audio Sync V2 does not transmit every possible WLED-local analyzer control.
  The current inventory's B effects therefore require an explicit native
  approximation policy; future source versions must be re-audited.
- Class C is zero for the pinned v16.0.1 explicit inventory. It is not a claim
  that future WLED releases or unregistered/private effects need no new input.
- No WLED palette-ID compatibility, Segment model, FX/SX/IX/FP adapter,
  runtime compatibility layer, or generic particle/plugin framework exists.
- The maintenance UDP-v3 firmware and the WLED/DDP production profile are
  mutually selected at process start; there is no APP hot-switch.
