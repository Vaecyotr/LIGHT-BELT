# Cabin Lighting V3 operator guide

This is the current software integration guide for the cabin lighting
topology. It describes a **provisional** installation plan: the software
contracts and test evidence are verified, while physical wiring, controller
placement, endpoint assignment, and cross-node timing are **NOT HARDWARE
VERIFIED**.

## Install and choose a mode

Use the repository interpreter on Windows:

```powershell
.\.python\Scripts\python.exe -m pip install -e .
```

`pyserial>=3.5` is a declared production dependency. UDP uses Python's standard
library. A normal developer run uses `outputs.mode: memory` or `fake` only when
that mode is selected explicitly. Neither mode sends a physical frame.

The cabin production profile deliberately contains documentation endpoints
(`192.0.2.x`) and `REPLACE_WITH_RS485_PORT`. Do not replace them until the
actual installation is assigned. In `production` mode an unavailable serial
port, socket, or send fails visibly; it never turns into a memory/fake success.

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  validate-show --show config/shows/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  inspect-topology --show config/shows/cabin-show-v2.yaml
```

The second command is the installation checklist: its JSON is constructed from
validated layout/profile/show data, not from a second hard-coded lookup table.
For every authored path region it prints logical ID, physical label, node ID,
output ID, GPIO, length, host/port placeholder and whether its transport is
enabled. It also prints `zone_32` separately as the one RS-485 RGB+CCT zone.

## Namespaces are intentionally different

| Name | Meaning | Example |
|---|---|---|
| Installation number | Marker on the cabin drawing | `42`, `32` |
| Logical ID | Stable show/layout identifier | `strip_42`, `zone_32` |
| ESP32 node ID | UDP v3 controller identity | node `2` |
| Output ID | One independent UDP v3 output inside that node | output `2` |
| GPIO | ESP32-S3 data pin | GPIO `5` |
| RS-485 address | STM32 protocol address, independently configurable | `17` for `zone_32` |
| Host API target | API-level capability, not a GPIO or node address | implementation-specific |

Never infer one namespace from another. In particular, installation `32` is not
the STM32 address, and `strip_42` does not imply ESP32 node 42 or GPIO 42.

## Provisional digital topology

Each digital row is one independent WS2811 output; no controller output shares
a GPIO or joins three strips as one 300-pixel strip.

| Node | Output / GPIO | Logical strip | Pixel groups |
|---:|---|---|---:|
| 1 | 1 / GPIO4 | `strip_11` | 10 |
| 1 | 2 / GPIO5 | `strip_21` | 10 |
| 1 | 3 / GPIO6 | `strip_31` | 10 |
| 2 | 1 / GPIO4 | `strip_41` | 10 |
| 2 | 2 / GPIO5 | `strip_42` | 20 |
| 2 | 3 / GPIO6 | `strip_43` | 20 |
| 3 | 1 / GPIO4 | `strip_44` | 20 |
| 3 | 2 / GPIO5 | `strip_45` | 20 |
| 3 | 3 / GPIO6 | `strip_93` | 20 |
| 4 | 1 / GPIO4 | `strip_12` | 40 |
| 4 | 2 / GPIO5 | `strip_91` | 20 |
| 4 | 3 / GPIO6 | `strip_92` | 20 |
| 5 | 1 / GPIO4 | `strip_22` | 40 |

This is five ESP32-S3 nodes, 13 WS2811 strips, 260 pixel groups, and one
independent RGB+CCT COB (`zone_32`). Node 5 has GPIO5/6 unused. It is an
initial mapping that can be changed only by updating the validated physical
mapping; it is not a claim that wiring is finished.

UDP v3 sends one self-describing datagram per node per logical frame. Its node
datagrams share the logical sequence and media timestamp. Firmware stages all
valid outputs, then refreshes them together; it does not claim physical
cross-ESP32 synchronization has been verified. UDP v2 remains a legacy codec,
not the cabin production default.

## Show V2 authoring

`config/shows/cabin-show-v2.yaml` is the writable Show v2 example. Its three authored
paths cover all 13 digital strips plus the COB zone:

- `screen_to_top`
- `screen_to_bottom_and_left`
- `screen_to_right_wall`

Targets are typed: `analog_zone + id`, `digital_strip + id`, `digital_set +
ids`, `digital_group + id`, or `virtual_path + id`. They never contain node,
GPIO, host, port, or packet offsets.

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

For each independent output, connect ESP32-S3 GPIO4/5/6 to `A` of an
SN74LVC1T45. Connect `VCCA` and `DIR` to ESP32 3V3, `VCCB` to 5V, and `B` to the
corresponding WS2811 `DI`. `DIR` at 3V3 fixes A -> B direction. Do not use one
GPIO for more than one listed strip.

For every 24V WS2811 strip: red is 24V+, white is GND, green is DI. The three
strips on one controller may share the 24V supply rails, but retain their
independent data paths. Connect 24V V-, every WS2811 ground, ESP32 ground, and
all level-shifter grounds to one common ground. If powering ESP32 from a buck,
connect buck 5V+ to ESP32 5V and buck 5V- to that same common ground.

`zone_32` is not WS2811: it is the RGB+CCT COB controlled through its own STM32
RS-485 address. Confirm driver, fuse sizing, cable gauge, injection points,
heat management, and power budget with qualified electrical work before power
is applied. The topology above is **NOT HARDWARE VERIFIED**.

## Deployment and troubleshooting

1. Keep production endpoints as placeholders until controller IPs/ports and
   RS-485 port are chosen. Use an isolated network during commissioning.
2. Run `validate-show` and `inspect-topology`; archive the JSON with the
   installation record after filling endpoints.
3. Confirm each output in the JSON matches a label on the installed cable
   before enabling power.
4. Commission one node/output at a time with a current-limited supply. Do not
   treat memory/fake tests as hardware evidence.
5. On a production port/socket/send error, stop and correct configuration or
   wiring. The expected behavior is an explicit error and safe black output,
   not automatic fallback.

If an authored target cannot resolve, check the logical ID and target type, not
the installation number. If a virtual path appears to use the wrong GPIO, run
`inspect-topology` against the same profile and show actually used at runtime.
If a node displays a partial frame, investigate UDP loss/CRC/topology/sequence
errors and firmware timeout behavior; software tests cover those contracts but
the physical result remains **NOT HARDWARE VERIFIED**.

## Retained legacy material

The repository keeps V1/V2 plans, historical acceptance reports, layout
fragments, and protocol notes under `docs/history/` because they explain the
development path. They are not current production instructions and must not be
copied into the cabin profile. Use `docs/README.md` to distinguish current,
reference, acceptance, and historical material.
