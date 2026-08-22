# Current Implementation Plan

Status: **Phase 34 explicit branch lifecycle and pre-roll continuity closeout
software-accepted on 2026-08-22; physical acceptance remains NOT HARDWARE
VERIFIED**.

Product implementation Phases 0-29 are complete. Their original approved plan
is preserved at
`docs/history/implementation/implementation-plan-phases-0-29.md` and is no
longer an active instruction source. Phases 30 and 31 are complete historical
work. Phase 32, Phase 33, and Phase 34 software closeouts are accepted. No
Phase 35 or later work is approved.

## Current Phase 34 closeout: Explicit branch lifecycle and pre-roll continuity

Phase 34 closed with one optional Show v2 branch field:

`lifecycle: start_on_release | pre_roll`

The default is `start_on_release`, preserving every existing branch-bearing
Show and the historical fresh-start release behavior. `pre_roll` is explicit
opt-in: its independent branch effect instance processes live cue inputs from
cue activation while its PixelFrame is discarded, then the already-current
state is revealed on the existing `after` release frame without reset,
reseed, or a second same-frame process call.

Completed closeout scope:

1. Extend the branch model and loader with the optional lifecycle field,
   strict validation, and no Show version bump.
2. Add cue-runtime scheduling that advances hidden pre-roll branches exactly
   once per active engine frame, shares the parent cue motion interval, keeps
   the existing independent deterministic branch seed, and leaves the release
   predicate unchanged.
3. Discard hidden branch contributions before composition and output so they
   cannot affect logical pixels, sequences, DDP/transport, ESP32 output, or
   release feedback.
4. Prove backward-compatible omitted/default behavior, pre-roll continuity for
   representative stateful effects, actual authored timeline and live-audio
   history, reset/replay, same-frame reveal, multiple/mixed branches, and
   unchanged virtual-path semantics.
5. Characterize current-development-machine software cost at approximately
   nine strips / 200 logical groups / 30 FPS for zero, one, three, and five
   hidden pre-roll branches. This is not RK3588 hardware evidence.
6. Document visibility (`after`) separately from simulation start
   (`lifecycle`) and record closeout acceptance evidence.

Closeout boundaries:

- Do not change existing YAML that omits lifecycle, rewrite archived Shows,
  replace virtual paths with pre-roll, synchronize branch randomness to the
  parent, synthesize historical audio/video, or expose hidden frames to output.
- Do not add effect IDs, Show v3, `coherent_noise_field`, generic arbitrary
  modulation, parameter type redesign, Audio Reactive Palette, WLED aliases,
  2D, particles, topology/DDP/ESP32 firmware changes, or Phase 35 work.
- Preserve `assets/energy-wakeup/energy-wakeup.yaml` byte-for-byte. Repository-
  wide pytest is explicitly user-waived for runtime cost; focused and
  cross-module integration tests remain mandatory and the waiver must be
  recorded as an omission, never a pass.

Closeout evidence includes all six acceptance goldens, output isolation, a
161.906 FPS conservative minimum for the five-hidden-branch synthetic workload,
the unchanged 21-effect inventory and immutable asset hash, 403 passing final
focused tests plus the bounded Host subset, authoring documentation, and
explicit **NOT HARDWARE VERIFIED** status. Repository-wide pytest remains
explicitly user-waived. Stop after Phase 34 closeout; Phase 35 remains
unapproved.

## Current Phase 34: Integrated common motion clock

Phase 34 gives all RK3588-native moving effects one cue-scoped integrated
common-motion clock. The final composed common speed is an instantaneous
multiplier of motion rate, not an absolute phase multiplier. Fixed cues
integrate global speed × authored `effect.speed` × audio speed modulation;
adaptive cues preserve selector speed × authored `effect.speed` × audio
speed modulation and the existing composition/clamping order.

Approved scope:

1. Add one internal reusable cue-level motion-clock contract that exposes the
   current and previous integrated motion times plus the corresponding cue
   wall-time interval where fixed-step crossing logic needs it. It is runtime
   state, not authored Show syntax or an authored effect parameter.
2. Preserve forward monotonicity, same-timestamp idempotence, pause at speed
   zero, continuous resume, constant-speed equivalence, explicit rejection of
   non-finite state, and the existing backward-time reset-and-replay rule.
3. Make every branch released from one cue consume the parent cue's current
   motion phase. Adaptive effect selection changes do not reset that phase.
4. Migrate absolute-time/common-speed motion in `single_dot`, `theater_phase`,
   `flowing_bands`, time-driven `color_wipe`, `history_stream`, `heat_fire`,
   `onset_ripple`, and the multi-emitter comet branch. Preserve external
   `ScalarSource` color-wipe progress and the legacy stateful single-emitter
   comet branch.
5. Keep history color-timeline sampling on cue wall time at each crossed motion
   boundary; do not synthesize historical live-audio samples. Keep onset-ripple
   decay on cue wall time while propagation uses motion time.
6. Add focused runtime, migrated-effect, cross-effect, reset/replay,
   variable-frame-rate, origin, virtual-path, registry/Host/Show, and immutable
   Energy Wakeup regression coverage plus software-only benchmark evidence.

Phase 34 boundaries:

- Do not change existing common-control composition, clamping, audio smoothing,
  adaptive music classification, effect-specific speed units, Show v2 authoring
  syntax, common-origin composition, or virtual-path behavior.
- Do not add or rename effect IDs. Do not implement `coherent_noise_field`,
  generic arbitrary audio-to-parameter modulation, typed parameter-registry
  redesign, Audio Reactive Palette, expression evaluation, WLED aliases, 2D,
  particles, topology/DDP changes, ESP32 firmware changes, or Phase 35 work.
- Preserve `assets/energy-wakeup/energy-wakeup.yaml` byte-for-byte. Live audio
  history is never synthesized. All hardware behavior remains **NOT HARDWARE
  VERIFIED**.

Phase 34 completion gates:

- Dynamic speed changes only the future slope: it cannot move phase backward,
  teleport emitters, or create a catch-up stall. Speed zero freezes and resume
  continues from the frozen phase.
- Constant speed `S` produces `motion_time == cue_local_time * S` within
  floating-point tolerance, including a cue first rendered after its start.
- Reset plus replay reconstructs the clock; repeated timestamps are
  idempotent; released branches share the parent cue phase.
- Every targeted absolute-time formula is migrated, while already-continuous
  delta-time integrations and external scalar progress remain compatible.
- Focused Phase 32/33, Show/registry/Host/virtual-path, immutable-asset, diff,
  and benchmark checks pass. Per the approving user instruction for this run,
  repository-wide pytest is omitted because of its runtime cost and this
  limitation is recorded in acceptance evidence.

Stop after Phase 34 software acceptance. Do not prepare Phase 35.

Phase 34 software gates passed through the focused runtime, migrated-effect,
Phase 32/33, Show/registry/Host/virtual-path, immutable-asset, diff, and
benchmark checks recorded in
`docs/acceptance/phase34-software-acceptance.md`. Repository-wide pytest was
explicitly waived by the approving user for this run because of its runtime
cost; that omission remains a documented limitation rather than an implied
full-suite pass. No firmware or physical behavior was changed or hardware
verified. Stop here; Phase 35 is not approved.

## Completed Phase 33: Composable 1D primitives

Phase 33 increases native RK3588 1D visual coverage by extending reusable
primitives rather than adding WLED mode aliases or coupled audio/effect IDs.
Existing effect defaults and the approved Show remain behavior-compatible.

Approved scope:

1. Add a generic `ScalarSource` V1 that returns a normalized `[0,1]` value from
   `cue_progress` or already-normalized `AudioFeatures` fields. It may expose
   indexed spectrum bins, but must not invent normalization for
   `dominant_frequency`, add an expression language, or use arbitrary Python
   evaluation.
2. Extend `color_wipe` with optional external scalar progress and live-control
   slew while preserving its time-driven default and the common compositor
   origin mechanism.
3. Extend `comet` with `count`, `phase_spacing`, and
   `trajectory=wrap|bounce|sine`, including a clean zero-trail mode, while
   preserving the single-emitter default exactly.
4. Extend `onset_ripple` with deterministic fixed/random event origins,
   one-way/bidirectional propagation, and optional wrapping. Silence or stale
   audio creates no new wave, while an active wave continues aging normally.
   A random origin is one deterministic normalized relative coordinate mapped
   independently to each logical path length; a `virtual_path` remains one
   continuous logical path.
5. Extend `twinkle` with event width, blur radius, and optional scalar event
   gate. A scalar birth-gain source may be added only through the same
   `ScalarSource` contract, without a second binding abstraction.
6. Add exactly one new native effect ID, `history_stream`: each fixed-rate
   sample enters a bounded logical-path history and older samples advance
   through space. Authored `ColorSpec`/`color_timeline` provides sample color;
   optional `ScalarSource` provides gain. State follows logical path length,
   reset/seek/replay is deterministic, and a `virtual_path` is advanced as one
   continuous path before splitting.
7. Integrate the accepted behavior through the effect registry, Show loader,
   Host capability metadata, OpenAPI only where the existing architecture
   requires it, effect reference documentation, and Phase 33 software
   acceptance evidence.

Phase 33 boundaries:

- Do not add WLED compatibility IDs, FX/SX/IX/FP, Segment semantics, palette
  IDs, fixed WLED timing constants, or WLED public field names.
- Do not implement `coherent_noise_field`, an Audio Reactive Palette or other
  audio color-source framework, global dominant-frequency color mapping,
  arbitrary expression bindings, 2D effects, particle systems, GIF/image,
  Copy Segment, ballistics/fireworks, semantic/game effects, topology or DDP
  redesign, or new ESP32 firmware behavior.
- Effects and scalar inputs remain hardware-agnostic. Physical node, GPIO,
  host, port, offset, and transport information do not enter renderer state.
- Preserve `assets/energy-wakeup/energy-wakeup.yaml` byte-for-byte. Do not
  start, prepare, or partially implement Phase 34.
- WLED may be inspected only as a visual-mechanism reference pinned to
  v16.0.1 commit `29b389df1c1aaec6ff53aea742d17063b985906c`.

Phase 33 completion gates:

- The approved Show and all legacy effect defaults remain behavior-compatible;
  invalid sources/parameters plus NaN and infinity fail explicitly.
- Scalar sources, `color_wipe`, `comet`, `twinkle`, `onset_ripple`, and
  `history_stream` have focused deterministic reset/seek/replay and
  `virtual_path` coverage appropriate to their state models.
- 30/60 FPS equivalence is covered where fixed-time state advancement applies;
  known `history_stream` samples preserve spatial order in both directions and
  across variable path lengths and partial steps.
- Only `history_stream` adds an effect ID, and no forbidden noise, audio-palette,
  WLED-alias, firmware, topology, or later-phase work is introduced.
- Focused, Wave integration, and final full pytest suites pass. The immutable
  Energy Wakeup asset hash is unchanged. Final acceptance records HEAD,
  modified files, exact commands/return codes/counts/elapsed times,
  `git diff --stat`, limitations, and all physical claims as **NOT HARDWARE
  VERIFIED**.

All Phase 33 software gates and the closeout fix gates passed with 1187 tests.
The closeout fixes the different-length independent-path random-origin boundary
bug and applies the authoritative ESP32 / WLED / RK3588 terminology to active
project documentation. The required benchmark and full command evidence are
recorded in `docs/acceptance/phase33-software-acceptance.md`. No firmware or
physical behavior was changed or hardware-verified. Stop here; Phase 34 is not
approved.

## Completed Phase 32: WLED-native portability and deployment purity closeout

Phase 32 establishes a repeatable clean-room path from ordinary WLED effects
and WLED Audio Reactive effects to RK3588-native effects. It does not add WLED
runtime compatibility, FX/SX/IX/FP aliases, Segment semantics, WLED palette ID
compatibility, or a speculative plugin/particle/audio framework.

The implemented software scope is:

1. Receive the fixed WLED v16.0.1 Audio Sync V2 packet and preserve generic
   `raw_level`, `loudness`, 16 spectrum bins, peak, dominant frequency and
   dominant magnitude while continuing to derive legacy LIGHT-BELT audio features.
   `fftBin` is not present on this wire contract; dominant frequency has no
   global color meaning.
2. Maintain the fixed-source Audio Reactive inventory in
   `docs/reference/wled-audio-reactive-effect-inventory.md`, with migration
   classes A/B/C and no automatic protocol extension.
3. Register and test the RK3588-native `flowing_bands`, `onset_ripple`, and
   `heat_fire` effects. `flowing_bands` uses a fixed A/black-B pattern whose
   highlighted A advances discretely; silence prevents new onset ripples but
   does not hide an existing wave; `heat_fire` remains authored color × heat,
   not a thermal palette.
4. Keep DDP production transport metadata separate from custom UDP v3
   maintenance metadata. Strip count and Host target vocabulary derive from
   the current layout; OpenAPI `TargetId` remains a runtime-discovered string.
5. Preserve the frozen Energy Wakeup asset and record software-only acceptance
   in `docs/acceptance/phase32-software-acceptance.md`.

All WLED source evidence is pinned to v16.0.1 or its full commit. Network,
firmware, timing and visible-output claims remain **NOT HARDWARE VERIFIED**.

## Current deployment override

This section supersedes the Phase 31 production wording below. The sole
current/default deployment is DDP to nine independent ESP32 nodes with no
analog zones/nodes or RS-485: `1/strip_32/40`, `2/strip_41/10`,
`3/strip_44/20`, `4/strip_12/40`, `5/strip_22/40`, `6/strip_31/10`,
`7/strip_43/20`, `8/strip_11/10`, and `9/strip_21/10`. Each board has exactly
`output_id: 1`; GPIO16 is topology metadata only. **NOT HARDWARE VERIFIED.**

Real-mode Host startup selects `config/runtime/wled-ddp-mdns.yaml` by default
and resolves only that WLED runtime Profile through Avahi
`wled-strip-<label>.local` names. A missing mDNS result disables only that
node, while the API keeps the nine-strip vocabulary. No old-IP/cache, HTTP,
MAC-derived-name, or subnet-scan fallback is permitted.

UDP v3 is custom-firmware maintenance only through
`config/profiles/udp-v3-nine-strip-maintenance.yaml`; WLED is not a UDP v3
receiver. Stop output, set `ENGINE_PROFILE_PATH`, and restart the Host to
switch Profile. The APP has no hot-switch. The Phase 31 material below is
historical compatibility, not current production. **NOT HARDWARE VERIFIED.**

## Historical Phase 31: One ESP32 per WS2811 strip

Replace the provisional five-controller, multi-output production topology with
one ESP32-S3 per physical WS2811 strip. The complete target has 13 digital
nodes; every production node has exactly one output, `output_id: 1`, on GPIO4.

| Node | Logical strip | Groups | Output | GPIO | Site IPv4 |
|---:|---|---:|---:|---:|---|
| 1 | `strip_11` | 10 | 1 | 4 | `192.168.31.201` |
| 2 | `strip_41` | 10 | 1 | 4 | `192.168.31.202` |
| 3 | `strip_44` | 20 | 1 | 4 | `192.168.31.203` |
| 4 | `strip_12` | 40 | 1 | 4 | `192.168.31.204` |
| 5 | `strip_22` | 40 | 1 | 4 | `192.168.31.205` |
| 6 | `strip_21` | 10 | 1 | 4 | `192.168.31.206` |
| 7 | `strip_31` | 10 | 1 | 4 | `192.168.31.207` |
| 8 | `strip_42` | 20 | 1 | 4 | `192.168.31.208` |
| 9 | `strip_91` | 20 | 1 | 4 | `192.168.31.209` |
| 10 | `strip_92` | 20 | 1 | 4 | `192.168.31.210` |
| 11 | `strip_43` | 20 | 1 | 4 | `192.168.31.211` |
| 12 | `strip_45` | 20 | 1 | 4 | `192.168.31.212` |
| 13 | `strip_93` | 20 | 1 | 4 | `192.168.31.213` |

The current field subset is exactly nodes `1`, `2`, `4`, `5`, `6`, `7`, `8`,
`9`, and `10`, covering nine installed strips. Nodes `3`, `11`, `12`, and `13`
remain part of the complete target but must not be represented as connected in
the nine-node field profile.

The table's IPv4 values are the archived custom-firmware site contract. The complete site profile
`config/profile-archive/cabin-lighting-v3-site-local.yaml` and the archived nine-node field profile implement
those addresses. The generic `config/profile-archive/cabin-lighting-v3-production.yaml` remains an
offline production-shape template with non-routable `192.0.2.x` TEST-NET
endpoints and `REPLACE_WITH_RS485_PORT`; preserving that explicit failure
boundary is not a different site allocation.

All physical assignments and observed behavior remain **NOT HARDWARE
VERIFIED** until recorded against real hardware.

Phase 31 production packets share logical sequence, media timestamp, and one
Host-monotonic `apply_at_us` 20 ms in the future. The Host emits broadcast
clock beacons; firmware estimates the local-minus-Host offset from the minimum
sample in a bounded window, prepares the frame before its deadline, and
subtracts the complete 3.2 MHz four-bit SPI wire time from the common
latch-completion deadline. The fixed GPIO4 production candidate encodes
`0=1000` and `1=1100` with 500 us low guards before and after the payload. The
complete durations are 1300 us for 10 groups, 1600 us for 20 groups, and 2200
us for 40 groups. The candidate remains **NOT HARDWARE VERIFIED**.
Production node images require scheduled frames;
explicit legacy diagnostic images remain immediate.

For a scheduled session start, Host encodes every target node before the first
send and transmits three complete rounds 2 ms apart. Each node receives the
same raw KEY packet and all packets retain one apply/media identity. Firmware
deduplicates that identity without creating extra session generations. A fully
prepared KEY admits its generation; a later timed-output failure rolls back
physically while the next complete scheduled frame remains able to recover.
The output loop checks safe timeout before each queue pass. Scheduled SPI
failure is rolled back and is not blindly retried after its validated start
deadline.

This scheduling contract is implemented in software. It is not evidence of
actual simultaneous light output: powered cross-node latch skew remains **NOT
HARDWARE VERIFIED** until captured with a logic analyzer.

## Approved scope

1. Add a parallel field profile at
   `config/profile-archive/ws2811-installed-one-esp-per-strip.yaml` for the exact
   nine-node field subset; do not silently repurpose an old multi-output
   diagnostic profile.
2. Migrate the complete cabin production topology to the 13-node node/strip/
   groups/output/GPIO mapping above. Apply the table's site IPv4 values in
   `config/profile-archive/cabin-lighting-v3-site-local.yaml`; retain explicit TEST-NET endpoints in
   the generic offline `config/profile-archive/cabin-lighting-v3-production.yaml` template.
3. Provide firmware node configurations for nodes 1-13 with one output each,
   `output_id: 1`, GPIO4, and the matching group count and site IPv4 suffix.
4. Keep UDP v3's general codec and firmware capability for one to three
   independent outputs. The Phase 31 production topology uses one descriptor;
   it does not narrow or replace the wire protocol.
5. Preserve all logical IDs, layouts, virtual paths, cue timing, effects, and
   Show v2 target semantics. Shows continue to address `strip_*`, never node,
   output, GPIO, or IP values.
6. Update current documentation and hardware acceptance instructions. Preserve
   historical plans and old acceptance reports as evidence of their original
   topology.
7. Add topology, firmware-contract, show-compatibility, and staged-profile
   tests covering both the complete target and current field subset.
8. Schedule production UDP v3 frames against one Host monotonic clock with a
   20 ms shared apply deadline, broadcast clock beacons, fail-closed firmware
   clock readiness, and per-strip encoded-wire compensation. Preserve
   immediate application only in explicit diagnostic environments.
9. Make the scheduled sequence-1 KEY frame atomic across nodes: encode all
   node datagrams first, send three identical rounds 2 ms apart, deduplicate
   repeated apply/media identity in firmware, reject generation-zero non-KEY
   traffic, and retain session admission after successful KEY preparation so
   the next complete frame can recover from a timed-output failure.

## Boundaries

- Do not change UDP v2 or the documented UDP v3 frame/beacon layouts, CRC,
  sequence ownership, queue semantics, timeout safety, production transport
  failure behavior, or the shared logical-frame/apply-time contract.
- Do not place physical topology in `DigitalStrip`, effects, analysis, Show v2
  cues, or logical target IDs. Physical details remain in profiles, mapping,
  `PhysicalFrame`, protocol, transport, and firmware layers.
- Do not re-author a show merely because a strip moved to another controller.
- Do not remove general UDP v3 multi-output support or its golden vectors and
  tests. Production `output_count == 1` is a topology rule, not a protocol rule.
- Do not mix old five-node frames, old multi-output firmware, or old wiring with
  the Phase 31 topology during a live run.
- Do not overwrite history or claim that an untested endpoint, pin, power plan,
  refresh skew, or visible result is hardware verified.
- Historical Phase 31 execution stopped at its own approved boundary. The
  current Phase 32 closeout above supersedes that old stopping point; do not
  begin Phase 33 or later work without explicit approval.

## Atomic field cutover

The field transition is one controlled change, not an incremental live mix:

1. Freeze the node/strip/MAC/IP/firmware record and archive validation output.
2. With production output disabled, flash and label every controller in the
   selected deployment set and commission each node in isolation.
3. Validate the selected profile and shows offline; confirm that every active
   logical strip resolves exactly once and that all active nodes use output 1,
   GPIO4, UDP v3, and unique endpoints.
4. Power down the lighting system. Change physical data connections and select
   `config/profile-archive/ws2811-installed-one-esp-per-strip.yaml` while outputs remain disabled.
5. Power and test the entire selected set, including all-black, primary colors,
   isolation, timeout, shared sequence/apply capture, beacon readiness,
   scheduled-commit diagnostics, logic-analyzer latch skew, and the 300-second
   show.
6. On any gate failure, stop output and roll back the profile, firmware set, and
   wiring together. Never retain a partially mixed topology.

The complete 13-node profile and the current nine-node field profile are
different deployment sets. A nine-node acceptance run cannot be presented as
acceptance of nodes 3, 11, 12, or 13.

## Phase 31 completion gates

- The complete production mapping contains exactly nodes 1-13 and all 13
  `strip_*` logical IDs exactly once, matching the table above.
- The field profile contains exactly nodes 1, 2, 4, 5, 6, 7, 8, 9, and 10 and
  their nine assigned strips, with no placeholder output for an absent node.
- Every Phase 31 production/field digital node has one output with
  `output_id: 1`, GPIO4, the correct group count, UDP v3, a unique node ID, and
  the correct endpoint for its deployment profile.
- Firmware node configurations 1-13 match the complete mapping and build from
  a clean output directory. General UDP v3 one-to-three-output codec coverage
  remains green.
- Existing shows resolve the same logical targets and produce the same logical
  strip content before and after remapping. No cue timing, effect, logical ID,
  or virtual-path edit is required for the topology migration.
- Validation rejects duplicate nodes/endpoints/outputs, missing mapped strips,
  wrong group counts, and any Phase 31 production node using an output other
  than output 1 on GPIO4.
- Production profiles schedule one shared apply deadline 20 ms ahead and emit
  Host-monotonic broadcast beacons. Production firmware rejects immediate
  frames, fails closed while its bounded minimum-offset clock is not ready,
  prepares before GPIO output, and compensates complete 10/20/40-group wire
  times as 1300/1600/2200 us. Diagnostic images retain immediate behavior.
- Session-start sequence 1 is encoded for every node before any send, repeated
  for three rounds at 2 ms spacing, and idempotently deduplicated by common
  apply/media identity. Successful KEY preparation admits the generation; a
  timed-output failure rolls back while the next complete frame can recover.
  Safe timeout is checked each output loop, and scheduled SPI failure never
  triggers an unplanned second transaction after deadline.
- Relevant tests, the full repository test suite, the required benchmark, and
  the ESP32 firmware build pass and are reported with actual commands and
  return codes.
- The atomic cutover checklist is documented. Any physical result not backed by
  a powered logic-analyzer and real-hardware record remains **NOT HARDWARE
  VERIFIED**.

This was the original Phase 31 stopping condition. Phase 32 does not rewrite
the historical gates above.
