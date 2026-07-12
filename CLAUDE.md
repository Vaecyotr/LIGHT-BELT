# LIGHT-BELT project instructions

## Mission

Build a reliable RK3588-hosted, video/music-driven lighting controller for the
2100 mm x 1000 mm x 1800 mm cabin installation:

- 13 independently driven 24V WS2811 RGB strips through ESP32-S3 controllers
- one 24V common-anode RGB+CCT COB zone through one STM32 RS-485 node

The cabin dimensions, placements, lengths, group counts, controller allocation,
electrical plan, and synchronization behavior are `NOT HARDWARE VERIFIED`.
They are the approved configurable contract, not proof of installed wiring.

RK3588 is the only production brain. RK3568 is backup/testing only.

## Hardware truth

Analog COB is not RGBW. It is six-wire common-anode RGB+CCT:

`+24V / R / G / B / WW / CW`

The only target analog run is physical label `32`, with logical ID `zone_32`.
It uses one configurable STM32 RS-485 node. Physical label `32` does not force
the STM32 bus address. This allocation is `NOT HARDWARE VERIFIED`.

Target digital logical IDs are `strip_<physical-label>` for physical labels
`11`, `12`, `21`, `22`, `31`, `41`, `42`, `43`, `44`, `45`, `91`, `92`, and
`93`. Physical label, logical ID, ESP32 node ID, GPIO, protocol node ID, and
Host API target ID are distinct concepts and must not be inferred from one
another.

### Cabin topology contract

All placement, length, and WS2811 group values in this table are
`NOT HARDWARE VERIFIED` and must remain configurable.

| Physical label | Logical ID | Placement | Technology | Length | Groups |
|---|---|---|---|---:|---:|
| 11 | `strip_11` | screen surround | WS2811 | 0.5 m | 10 |
| 12 | `strip_12` | ceiling edge | WS2811 | 2 m | 40 |
| 21 | `strip_21` | screen surround | WS2811 | 0.5 m | 10 |
| 22 | `strip_22` | floor/wall edge | WS2811 | 2 m | 40 |
| 31 | `strip_31` | screen surround | WS2811 | 0.5 m | 10 |
| 32 | `zone_32` | left porthole/door | RGB+CCT COB | configurable | n/a |
| 41 | `strip_41` | screen surround | WS2811 | 0.5 m | 10 |
| 42 | `strip_42` | right-wall wave | WS2811 | 1 m | 20 |
| 43 | `strip_43` | right-wall wave | WS2811 | 1 m | 20 |
| 44 | `strip_44` | right-wall wave | WS2811 | 1 m | 20 |
| 45 | `strip_45` | right-wall wave | WS2811 | 1 m | 20 |
| 91 | `strip_91` | reserved/removable run | WS2811 | 1 m | 20 |
| 92 | `strip_92` | reserved/removable run | WS2811 | 1 m | 20 |
| 93 | `strip_93` | reserved/removable run | WS2811 | 1 m | 20 |

The 13 digital runs total 260 independently addressable WS2811 groups.

### Provisional controller and electrical contract

This five-node allocation is `NOT HARDWARE VERIFIED`, is not final wiring, and
must remain configurable.

| ESP32 node | GPIO4 | GPIO5 | GPIO6 |
|---:|---|---|---|
| 1 | `strip_11` | `strip_21` | `strip_31` |
| 2 | `strip_41` | `strip_42` | `strip_43` |
| 3 | `strip_44` | `strip_45` | `strip_93` |
| 4 | `strip_12` | `strip_91` | `strip_92` |
| 5 | `strip_22` | unused | unused |

Each strip has an independent data output through an SN74LVC1T45. The strips
use parallel 24V power, the level shifters use a 5V B-side logic supply, and
all supplies/controllers require a common ground. This electrical plan is
`NOT HARDWARE VERIFIED`; final power segmentation is unknown and configurable.
Final GPIO wiring, IP addresses, protocol node IDs, Host API target IDs, power
segmentation, and real synchronization performance are also configurable and
`NOT HARDWARE VERIFIED`.

## Architectural invariants

- Analysis and effects are hardware-agnostic.
- Effects produce logical frames; physical mapping produces node frames.
- One logical frame owns one shared sequence and media timestamp.
- RS-485 and UDP use that same sequence.
- Protocol codecs are pure and testable without hardware.
- Production transport failures must be explicit; never silently fall back to memory and report success.
- Fake/memory transports require explicit config or dependency injection.
- Output queues keep only the latest complete logical frame.
- Do not interleave packets from different logical frames.
- A digital physical node receives one complete UDP frame and refreshes once.
- Apply brightness exactly once.
- Do not claim hardware verification without real evidence.

## Protocols

RS-485 v2 is the documented 16-byte RGB+CCT frame using:

- sync `A5 5A`
- version 2
- node ID
- sequence
- R/G/B/WW/CW
- fade
- flags
- CRC-16/CCITT-FALSE

UDP v2 is the implemented legacy codec: one `pixel_count` and one continuous
RGB pixel payload per ESP32 node, with version, node ID, sequence, payload
length, and CRC32. Its codec, tests, and golden vectors remain unchanged.

UDP v3 is the target multi-output protocol introduced in Phase 26. It carries
one complete node frame with independent per-output lengths/payloads. Separate
strips must not be represented as one electrically concatenated strip; the
ESP32 applies every output and refreshes once per logical frame. New cabin
production profiles default to v3 after Phase 26, while v2 remains legacy.

Keep protocol golden vectors shared between host and firmware documentation/tests.

## Compatibility

- Preserve the validated video/audio analyzers and effects unless a test proves change is required.
- Keep Windows development/simulation working.
- Support RK3588 ARM64 Linux.
- Use config for hardware-specific values.
- If public models are migrated, update all callers and tests consistently; do not leave mixed RGBW/RGB+CCT semantics.

## Windows Python interpreter

On Windows, this repository must use only the bundled interpreter:

`.\\.python\\Scripts\\python.exe`

Never invoke any of the following on Windows:

* `python`
* `python3`
* `py`
* a Python executable outside this repository
* a Python executable from the C: drive

All Python commands must begin with:

`.\\.python\\Scripts\\python.exe`

Before the first Python command in each Claude Code session, verify the interpreter.
Codex on Windows may remap the repository into a sandbox path such as
`C:\Users\CodexSandboxOffline\.codex\.sandbox\cwd\<sandbox-id>`, so do not
require `sys.executable` to contain the original drive path or repository
directory name.

`.\\.python\\Scripts\\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"`

The command is valid when it was invoked as `.\\.python\\Scripts\\python.exe`,
the current workspace contains `.python\\Scripts\\python.exe` (or the legacy
`.python\\python.exe`), at least one of those candidate paths resolves to the
same file as `sys.executable` (tolerating Windows Junctions that share a venv
across worktrees), `light_engine` imports successfully, and the imported
package file is also under the current workspace mapping.

If the bundled interpreter does not exist or cannot run, stop and report the error. Do not fall back to another Python installation.

## Verification

Before editing:

`.\\.python\\Scripts\\python.exe -m pytest -q`

After each coherent change, run relevant tests using the same bundled interpreter.

Before finishing, run:

`.\\.python\\Scripts\\python.exe -m pytest -q`

`.\\.python\\Scripts\\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800`

If firmware projects exist or are added:

`pio run -d firmware/stm32_rgbcct_node`

`pio run -d firmware/esp32_ws2811_node`

Show commands and results. Never delete or weaken tests just to pass.


## Working method

For repository-wide changes, explore and produce a plan before implementation. Address root causes, keep changes incremental, and document assumptions. Ask only about blocker decisions that change wire format, hardware pinout, or safety behavior.

## Documentation precedence

When project documents conflict, use this order of authority:

1. `CLAUDE.md`: permanent project facts and invariants.
2. `docs/CLOSED_LOOP_SPEC.md`: target architecture and acceptance criteria.
3. `docs/IMPLEMENTATION_PLAN.md`: the currently approved work only.
4. Current source code and tests: implemented behavior and evidence.

The following documents describe the legacy v1 implementation and are not
the target architecture:

- `docs/history/legacy-prototype/protocol-v1.md`
- `docs/history/legacy-prototype/architecture.md`
- `docs/history/legacy-prototype/hardware-integration.md`
- `docs/history/legacy-prototype/configuration.md`

Do not implement RGBW, 11-byte serial v1, per-strip UDP fragmentation, or
WS2812B as the new target merely because they appear in legacy documents.
Preserve them only where explicitly required for migration or legacy mode.

