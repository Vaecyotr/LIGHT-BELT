# Cabin Lighting V3 operator guide

> **Legacy notice:** this document retains historical 13-node/260-pixel UDP
> commissioning commands and archived Show paths for replay only. That
> topology is historical archive material, not the current installation or a
> product limit. This is not a current Show-design reference. The immutable
> original Show source is
> `assets/energy-wakeup/energy-wakeup.yaml`; the approved, runnable current
> copy and compatibility baseline is `config/shows/energy-wakeup.yaml`.
> Current topology authority is `CLAUDE.md`.

## Current production and maintenance boundary

Current production is nine independent ESP32 controllers running upstream WLED
and receiving DDP. The tracked source template is
`config/profiles/rk3588-host-service.yaml`; its nine strips
contain 200 pixels in total. **9/200 is only the current profile snapshot**, not
an immutable topology or a protocol, firmware, or product capacity limit.

`config/profiles/udp-v3-nine-strip-maintenance.yaml` is a separate custom
firmware maintenance profile. It does not replace WLED/DDP production and its
`192.0.2.x` endpoints are documentation-only TEST-NET addresses. Changing
between DDP/WLED and UDP v3 requires stopping the Host, selecting the profile,
and restarting it; there is no live application switch. The custom maintenance
firmware, its deployment topology, and all physical behavior are **NOT HARDWARE
VERIFIED**.

The remaining Phase 31 one-ESP-per-strip commands, 13-node/260-pixel table,
scheduled-presentation values, wiring, and flash instructions are retained as
historical maintenance evidence. They are not current production instructions.

## Phase 32 UDP v3 maintenance framing

UDP v3 retains the historical complete-frame message (`message_type = 0x01`)
and adds chunk datagrams (`message_type = 0x03`) when the complete encoding
would exceed a node's configured `max_udp_payload`. All chunks of a logical
frame share node ID, flags, sequence, media timestamp, and apply time. The
receiver may accept chunks out of order, but it exposes nothing until every
pixel of every configured output is present; only then does it queue one
complete frame and perform one physical refresh. Missing, corrupt, conflicting,
wrong-output, wrong-GPIO, wrong-length, or mixed-identity chunks never cause a
partial refresh. See the
[UDP v3 chunk contract](../reference/udp-v3-chunk-contract.md).

The wire and firmware contract supports `MAX_OUTPUTS <= 3`. Tests at `>=101`
pixels, including the 481-pixel tail vector, prove that earlier 100-pixel
assumptions are not product limits;
those values are software contract vectors, not installed-strip claims, and
are **NOT HARDWARE VERIFIED**. The wire count and offset fields are unsigned
16-bit values, while an actual firmware image accepts only its compiled output
IDs, GPIOs, and lengths.

The protocol parser's absolute UDP payload ceiling is 65,507 bytes. Each image
uses the smaller of that image's complete configured-frame size and
`UDP_V3_RECEIVE_BUFFER_BYTES` (default 4,096 bytes) for its receive buffer.
Chunk reassembly allocates RGB storage plus a received-byte map from the
compiled total pixel count (three plus one bytes per configured pixel), owns at
most one incomplete logical frame, and fails initialization explicitly if that
allocation cannot be made. Packet contents cannot enlarge the configured
framebuffer. These are derived resource bounds, not a universal pixel cap.

## Historical UDP archive: install and choose a mode

Use the repository interpreter on Windows:

```powershell
.\.python\Scripts\python.exe -m pip install -e .
```

`pyserial>=3.5` is a declared production dependency. UDP uses Python's standard
library. A normal developer run uses `outputs.mode: memory` or `fake` only when
that mode is selected explicitly. Neither mode sends a physical frame.

The archived cabin profile deliberately contains documentation endpoints
(`192.0.2.x`) and `REPLACE_WITH_RS485_PORT`. The archived nine-strip Phase 31
field profile is `config/profile-archive/ws2811-installed-one-esp-per-strip.yaml`
and uses the assigned `192.168.31.x` endpoints. The archived complete
thirteen-strip digital profile is
`config/profile-archive/cabin-lighting-v3-site-local.yaml`. Both site
profiles are UDP-only and deliberately leave RS-485 disabled. They do not
control or accept the independent `zone_32` COB. In `production` mode an
unavailable socket or send fails visibly; it never turns into a memory/fake
success.

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/cabin-lighting-v3-production.yaml `
  validate-show --show config/shows/archive/cabin-v2/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/cabin-lighting-v3-production.yaml `
  inspect-topology --show config/shows/archive/cabin-v2/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/ws2811-installed-one-esp-per-strip.yaml `
  validate-show --show config/shows/archive/ws2811-commissioning/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/ws2811-installed-one-esp-per-strip.yaml `
  inspect-topology --show config/shows/archive/ws2811-commissioning/ws2811-stage3-installed-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/cabin-lighting-v3-site-local.yaml `
  validate-show --show config/shows/archive/ws2811-commissioning/ws2811-stage3-full-300s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/cabin-lighting-v3-site-local.yaml `
  inspect-topology --show config/shows/archive/ws2811-commissioning/ws2811-stage3-full-300s.yaml
```

Each `inspect-topology` command is an installation checklist: its JSON is
constructed from validated layout/profile/show data, not from a second
hard-coded lookup table. For every authored path region it prints logical ID,
physical label, node ID, output ID, GPIO, length, host/port and whether its
transport is enabled. It prints `zone_32` separately with transport disabled in
the UDP-only site profiles; that row is not COB acceptance evidence.

## Historical archived UDP replay

Run exactly the profile/show pair that was validated and inspected. The first
command sends nine UDP v3 datagrams per logical frame; the second sends thirteen.

Archived Phase 31 nine-node field subset:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/ws2811-installed-one-esp-per-strip.yaml run `
  --show config/shows/archive/ws2811-commissioning/ws2811-stage3-installed-300s.yaml
```

Complete thirteen-node digital target:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profile-archive/cabin-lighting-v3-site-local.yaml run `
  --show config/shows/archive/ws2811-commissioning/ws2811-stage3-full-300s.yaml
```

These were historical custom-firmware UDP runbooks, not current production
commands or hardware evidence. Do not use either command as evidence
for `zone_32`; commission the COB separately with an explicitly configured and
enabled RS-485 transport.

## Namespaces are intentionally different

| Name | Meaning | Example |
|---|---|---|
| Installation number | Marker on the cabin drawing | `42`, `32` |
| Logical ID | Stable show/layout identifier | `strip_42`, `zone_32` |
| ESP32 node ID | UDP v3 controller identity | node `8` for `strip_42` |
| Output ID | One independent UDP v3 output inside that node | historical output `1` |
| GPIO | ESP32-S3 data pin | historical GPIO `4` |
| RS-485 address | STM32 protocol address, independently configurable | `17` for `zone_32` |
| Host API target | API-level capability, not a GPIO or node address | implementation-specific |

Never infer one namespace from another. In particular, installation `32` is not
the STM32 address, and `strip_42` does not imply ESP32 node 42 or GPIO 42.

## Historical Phase 31 13/260 digital topology

Each row records one historical ESP32-S3 and one independent WS2811 data path.
Every listed node used `output_id: 1` on GPIO4.

| Node | Output / GPIO | Logical strip | Pixel groups | Site IPv4 | Field now |
|---:|---|---|---:|---|---|
| 1 | 1 / GPIO4 | `strip_11` | 10 | `192.168.31.201` | yes |
| 2 | 1 / GPIO4 | `strip_41` | 10 | `192.168.31.202` | yes |
| 3 | 1 / GPIO4 | `strip_44` | 20 | `192.168.31.203` | no |
| 4 | 1 / GPIO4 | `strip_12` | 40 | `192.168.31.204` | yes |
| 5 | 1 / GPIO4 | `strip_22` | 40 | `192.168.31.205` | yes |
| 6 | 1 / GPIO4 | `strip_21` | 10 | `192.168.31.206` | yes |
| 7 | 1 / GPIO4 | `strip_31` | 10 | `192.168.31.207` | yes |
| 8 | 1 / GPIO4 | `strip_42` | 20 | `192.168.31.208` | yes |
| 9 | 1 / GPIO4 | `strip_91` | 20 | `192.168.31.209` | yes |
| 10 | 1 / GPIO4 | `strip_92` | 20 | `192.168.31.210` | yes |
| 11 | 1 / GPIO4 | `strip_43` | 20 | `192.168.31.211` | no |
| 12 | 1 / GPIO4 | `strip_45` | 20 | `192.168.31.212` | no |
| 13 | 1 / GPIO4 | `strip_93` | 20 | `192.168.31.213` | no |

The historical complete target was 13 ESP32-S3 nodes, 13 WS2811 strips, 260
pixel groups, and one independent RGB+CCT COB (`zone_32`). Its archived field
subset contained exactly nodes 1, 2, 4, 5, 6, 7, 8, 9, and 10. Neither count
describes current WLED/DDP production or a supported maximum.

UDP v3 sends one self-describing datagram per node per logical frame. All node
datagrams share the logical sequence, media timestamp, and apply deadline. The
codec and firmware retain the general one-to-three-output contract, while the
historical Phase 31 datagrams contain exactly one output descriptor. UDP v2
remains a legacy codec.

### Historical scheduled presentation contract

Both site profiles use `presentation.mode: scheduled`. The Host reads one
monotonic clock, broadcasts clock beacons to `192.168.31.255:9001`, and assigns
the same `apply_at_us = host_monotonic_us + 20000` to every node packet for one
logical frame. It sends five startup beacons 10 ms apart, then at most one
beacon every 500 ms while frames are submitted. `SCHEDULED_APPLY` and nonzero
`apply_at_us` always travel together.

Those were the archived formal profile values, not a hardware-accepted timing
set. The robust Node 2 A/B used a 60 ms lead, 100 ms beacon interval, and 32
startup beacons 50 ms apart. Reconciling the formal profiles is a P1 Scheduled
hardware gate; do not change them during Immediate output commissioning.

For the sequence-1 session KEY, Host first encodes every node datagram. Only
after all encodes succeed does it send three complete rounds 2 ms apart. A
given node receives byte-identical raw packets in those rounds, and every
node/round retains the same apply and media time. Firmware counts later copies
as `session_key_dupes` and treats them idempotently. Successful KEY preparation
admits the generation. If its later timed output fails, the backend restores
the previous frame or black and the next complete scheduled frame can recover;
the firmware does not attempt a second late wire transaction.

Each historical custom-firmware ESP32 estimates `local esp_timer - Host monotonic` from the
minimum offset in its bounded beacon window. It rejects scheduled frames until
the clock is ready, pre-encodes a complete frame without touching GPIO, and
starts the fixed GPIO4 SPI transaction early enough for the shared deadline to
mean guaranteed WS2811 latch completion. The retained candidate uses 3.2 MHz
four-bit `1000`/`1100` encoding with symmetric 200-byte (500 us) low guards.
Complete encoded wire times are:

| Groups | Encoded bytes | Wire time | Start relative to shared apply |
|---:|---:|---:|---:|
| 10 | 520 | 1300 us | `apply_at - 1300 us` |
| 20 | 640 | 1600 us | `apply_at - 1600 us` |
| 40 | 880 | 2200 us | `apply_at - 2200 us` |

All retained `esp32-s3-node-N` images require scheduled frames and fail
closed instead of displaying immediate frames. Explicit legacy Node 2
diagnostic images remain immediate and must not be used to evaluate strict
synchronization. The software contract is implemented, but real multi-node
latch skew is **NOT HARDWARE VERIFIED** until powered nodes are captured with
a logic analyzer.

The output task checks safe timeout at the start of every loop even while
scheduled frames are continuously queued. If the scheduled SPI transaction
fails, firmware does not blindly transmit it again after the validated start
deadline; it fails closed and recovers the committed frame or safe black.

## Show V2 authoring

`config/shows/archive/cabin-v2/cabin-show-v2.yaml` is the archived Show v2 example. Its three authored
paths cover all 13 digital strips plus the COB zone:

- `screen_to_top`
- `screen_to_bottom_and_left`
- `screen_to_right_wall`

Targets are typed: `analog_zone + id`, `digital_strip + id`, `digital_set +
ids`, `digital_group + id`, or `virtual_path + id`. They never contain node,
GPIO, host, port, or packet offsets.

Phase 31 does not require cue or timeline rewrites. Shows keep the same
`strip_*` targets; the selected physical profile changes node, endpoint, and
GPIO resolution. `ws2811-stage3-installed-300s.yaml` is the archived nine-strip
commissioning scope. `ws2811-stage3-full-300s.yaml` is the corresponding
archived thirteen-strip digital scope. Neither staged show contains the analog
COB.

An effect is `effect.id` plus `effect.params`. Add a new effect by registering
its stable ID, parameter validation, renderer, and tests. Color is independent
through `ColorSpec`: `effect_default`, `solid`, or `palette`. Therefore an
effect may retain its own default color or be overridden per cue without adding
new effect IDs.

Origins are `start`, `end`, `center`, or `edges`. A cue may override the
origin declared by an authored virtual path. The bounded `strip_41` release in
the example starts `strip_42`, `strip_43`, `strip_44`, `strip_45`, and
`strip_93` from the same logical frame after `strip_41` completes. It is not a
general-purpose graph executor.

## ESP32-S3 WS2811 wiring plan

For each historical custom-firmware node, connect ESP32-S3 GPIO4 to `A` of that node's
SN74LVC1T45. Connect `VCCA` and `DIR` to ESP32 3V3, `VCCB` to 5V, and `B` to the
corresponding WS2811 `DI`. `DIR` at 3V3 fixes A -> B direction. GPIO5 and GPIO6
were not outputs in the Phase 31 one-strip configuration.

For every 24V WS2811 strip: red is 24V+, white is GND, green is DI. Connect 24V
V-, every WS2811 ground, ESP32 ground, and all level-shifter grounds to one
common ground. If powering ESP32 from a buck, connect buck 5V+ to ESP32 5V and
buck 5V- to that same common ground. Power segmentation, protection, cable
gauge, and injection remain installation decisions requiring real validation.

`zone_32` is not WS2811: it is the RGB+CCT COB controlled through its own STM32
RS-485 address. Confirm driver, fuse sizing, cable gauge, injection points,
heat management, and power budget with qualified electrical work before power
is applied. The topology above is **NOT HARDWARE VERIFIED**.

## Deployment and troubleshooting

1. Freeze a node/strip/MAC/IP/firmware record for the selected deployment set.
   Use an isolated network during commissioning.
2. Run `validate-show` and `inspect-topology` against the exact profile and show
   selected for the run; archive the JSON before enabling physical output.
3. Confirm every active row resolves once to output 1 / GPIO4 and matches the
   label on its controller and installed cable.
4. With physical output disabled, flash, label, and commission one node at a
   time using a current-limited supply. Verify black, red, green, blue, timeout,
   and recovery. Do not treat memory/fake tests as hardware evidence.
5. Power down before moving data connections. Change wiring and Host profile as
   one maintenance action; do not run a mixture of old multi-output firmware,
   new single-output firmware, old profile, and new wiring.
6. Bring up the whole selected set and verify isolation, shared sequence and
   apply deadline, beacon reception, `clock_ready=1`, scheduled commits,
   all-black behavior, and its matching 300-second show. Capture at least
   representative 10-, 20-, and 40-group GPIO4 data paths with a logic
   analyzer and retain the measured latch skew. A nine-node run does not
   accept nodes 3, 11, 12, or 13; neither UDP-only run accepts `zone_32`.
7. On any failure, stop output and roll back profile, firmware set, and wiring
   together. Production errors must remain explicit; there is no automatic
   fallback to a fake or memory transport.

If an authored target cannot resolve, check the logical ID and target type, not
the installation number. If a virtual path appears to use the wrong GPIO, run
`inspect-topology` against the same profile and show actually used at runtime.
If a node displays a partial frame, investigate UDP loss/CRC/topology/sequence
errors and firmware timeout behavior; software tests cover those contracts but
the physical result remains **NOT HARDWARE VERIFIED**.

For a historical scheduled node, `clock_not_ready`, `scheduled_late`,
`scheduled_start_late`, `scheduled_invalid`, `scheduled_cancelled`, or
`immediate_dropped` increasing is a scheduling failure, not permission to fall
back to immediate output. Check the broadcast address, Host/node subnet,
beacon counters, clock uncertainty, firmware environment, and captured
deadline error before rerunning the show.

`session_key_dupes` normally increases during the two redundant KEY copies;
it must not accompany repeated generation resets or multiple physical commits.

## Retained legacy material

The repository keeps V1/V2 plans, historical acceptance reports, layout
fragments, and protocol notes under `docs/history/` because they explain the
development path. They are not current production instructions and must not be
copied into the cabin profile. Use `docs/README.md` to distinguish current,
reference, acceptance, and historical material.
