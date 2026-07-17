# Deferred Hybrid Cached/Live Playback Requirements

Status: **DEFERRED**. This is a non-authoritative future requirements record.
It does not approve implementation and must not override
`docs/IMPLEMENTATION_PLAN.md`.

All timing, synchronization, storage, and physical-output behavior described
here is **NOT HARDWARE VERIFIED**.

## Current Priority and Stop Boundary

The current product priority is reliable playback of the existing fixed
five-minute program through the present host-rendered frame path. Current
active physical scope is:

- ESP32 node 1: `strip_11`, `strip_21`, `strip_31`
- ESP32 node 2: `strip_41`, `strip_42`
- ESP32 node 4: `strip_12`, `strip_91`, `strip_92`
- ESP32 node 5: `strip_22`

Immediate work should concentrate on correct per-node color order, stable
dynamic WS2811 output, complete-frame ownership, cross-node timing, and a full
five-minute physical run without random color changes, partial frames, or
unexpected blackouts.

The current priority does **not** include cached show packages, one-hour live
media, cached/live mode switching, or new disconnect semantics. Those items
remain deferred until a separately approved implementation phase exists.

## Future Product Requirements

Future playback should support two modes behind one common node firmware and
one authoritative host effect implementation:

1. **Cached fixed-media playback.** The host pre-renders a deterministic show
   into node-specific RGB frame packages, uploads and verifies them, then arms
   every node for a scheduled common start.
2. **Live analyzed playback.** The host analyzes long-running video and music
   while they play and streams complete node frames with media timestamps and
   scheduled application times.
3. **Atomic mode switching.** The host prepares every node, waits for all
   required readiness acknowledgements, and schedules one future switch time.
   A failed preparation must leave every node in the existing mode.
4. **Mode-specific disconnect behavior.** Cached playback may continue to the
   end of its verified package. Live playback may hold briefly and then enter
   the configured safe state. The final policy remains deferred.

## Candidate Architecture

- Firmware is installed independently from show content. Changing a show must
  not require reflashing every controller.
- Fixed shows are uploaded as versioned data packages, not duplicated effect
  code. Each package identifies the show, node, topology, frame rate, frame
  count, duration, and content hash.
- Upload uses inactive storage followed by validation and atomic activation;
  partially uploaded packages are never playable.
- A host-owned media clock remains authoritative. Nodes estimate host time,
  schedule a future start or switch, and periodically correct drift.
- Frame index derives from synchronized media time. A late node seeks to the
  current frame rather than replaying a backlog.
- Every node continues to stage one complete logical frame before physical
  output. A playback-mode change must not interleave frames from two sessions.
- Effects and analysis remain on the host. ESP32 nodes remain physical playback
  executors and must not acquire a second, divergent effect implementation.

For the currently active 180 WS2811 groups, five minutes of raw RGB at 30 FPS
is approximately 4.86 MB across all active nodes. The largest active node
package is approximately 2.16 MB before package metadata or compression. These
are planning estimates, not accepted storage measurements.

## Synchronization Principle

Simultaneous flashing or reset is not a synchronization mechanism. Deployment
time, reset time, Wi-Fi association, and oscillator drift differ between
controllers. Future cached playback requires a prepare/ready/arm protocol and a
common scheduled start time. Pause, seek, resume, node restart, and media switch
behavior must be defined against the same media clock.

## Re-entry Gates

Work on this deferred design may begin only after a new approved phase defines:

- fixed-package binary format, storage partitioning, upload, hash, and rollback;
- clock synchronization method and measurable cross-node error bounds;
- cached/live state machine and atomic switch protocol;
- pause, seek, resume, restart, and disconnect behavior;
- interaction with the analog RGB+CCT node and media player;
- software tests plus explicit real-hardware acceptance evidence.
