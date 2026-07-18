# WS2811 Two-Node Capability-Boundary Show

Status: exploratory field tool; **NOT HARDWARE VERIFIED**.

## Fixed field baseline

This Show keeps the best current diagnostic parameters fixed:

| Item | Node 2 / strip 41 | Node 8 / strip 42 |
|---|---|---|
| Host endpoint | `192.168.31.202:9001` | `192.168.31.208:9001` |
| Output | output 1, GPIO4, 10 groups | output 1, GPIO4, 20 groups |
| Presentation | Immediate | Immediate |
| Host transform | max brightness `0.35`, gamma `1.30` | same |
| Field firmware | guarded SPI4 + exact-content dedupe | same + 30 ms non-skipped Immediate offset |

The retained firmware uses 3.2 MHz guarded SPI4 (`0=1000`, `1=1100`, 500 us
low guards). These settings are the current field checkpoint, not a production
acceptance. Node 2 can still show rare wrong-color events when it is the only
active transmitter.

## What the Show separates

The authored Show is
`config/shows/ws2811-two-node-capability-boundary-272s.yaml`.

| Time | Boundary under observation |
|---:|---|
| 0-20 s | Black gaps plus red, green, blue, cyan, amber, and low-blue repeat anchors; no white cue |
| 20-41 s | One dot over the 30-group path at 1, 3, and 6 groups/s |
| 41-50 s | Two-state blue pulse; compare visible state changes with Host/node counters |
| 50-270 s | All 17 registered effects, one 12-second block each, with one-second black separators |
| 270-272 s | Authored black tail before the exit SAFE frame |

Every relay block renders one logical 30-group path in this order:

`NODE2 / strip_41[0..9] -> NODE8 / strip_42[0..19]`

Spatial effects therefore cross the logical node boundary without restarting
at strip 42. Two brightness tracks also move emphasis from Node 2 (`1.0/0.35`)
through equal emphasis (`0.7/0.7`) to Node 8 (`0.35/1.0`). That makes the
handoff visible for full-frame effects such as `static`, `breath`, and media
effects. Effects that support `color_timeline` move from blue through cyan to
amber.

This continuity is logical, not a physical seam-timing acceptance. The current
Node 8 diagnostic firmware delays non-skipped Immediate writes by 30 ms, so a
moving feature can show a short physical gap or overlap at the strip boundary.
The installed strip directions have also not been independently mapped on
hardware.

The relay order and authored adjustment surface are:

| Time | Effect | Adjustable dimension exercised here | Relay behavior |
|---:|---|---|---|
| 50-62 s | `static` | `color_timeline` | Full-path color change plus emphasis handoff |
| 63-75 s | `breath` | period `4.0`, floor `0.20`, `color_timeline` | Brightness breath continues through handoff |
| 76-88 s | `color_wave` | speed `0.65`, width `0.45`, hue rate `0.08` | One 30-group wave buffer crosses the seam |
| 89-101 s | `chase` | speed `4.0`, width `2`, gap `5`, trail `0.20`, rainbow | Chase phase continues across the seam |
| 102-114 s | `comet` | speed `4.0`, tail `0.30`, decay `0.84` | Comet head and tail cross the seam |
| 115-127 s | `audio_pulse` | attack `0.20`, release `0.35`, `color_timeline` | Generated audio drives one full path |
| 128-140 s | `bass_pulse` | attack `0.35`, release `0.50`, `color_timeline` | Generated bass drives one full path |
| 141-153 s | `spectrum` | virtual path assigned to treble band | Generated treble drives both path regions |
| 154-166 s | `video_ambient` | smoothing `0.20` | Generated center-video color fills the path |
| 167-179 s | `video_audio_fusion` | video/audio weights, bass boost, treble limit | Generated fused media fills the path |
| 180-192 s | `calm` | period `8.0`, `color_timeline` | Slow color drift continues through handoff |
| 193-205 s | `color_wipe` | speed `3.0`, `color_timeline` | Fill reaches strip 42 after strip 41 |
| 206-218 s | `twinkle` | density `0.40`, fade `0.80`, solid color timeline | Sparks share one 30-group coordinate space |
| 219-231 s | `demo` | cycle `2.0`, six-effect child list | Child effects cycle while emphasis transfers |
| 232-244 s | `step_pulse` | period `2.0`, exact blue/amber levels | Discrete full-path state changes transfer |
| 245-257 s | `single_dot` | speed `4.5`, forward, `color_timeline` | One exact dot repeatedly crosses the seam |
| 258-270 s | `theater_phase` | speed `3.0`, `color_timeline` | Three-phase mask remains global across the seam |

With no `--video` or `--audio` arguments, `run` supplies deterministic
generated media, so `audio_pulse`, `bass_pulse`, `spectrum`, `video_ambient`,
and `video_audio_fusion` remain active. A real-media run is a separate test and
must not be compared as a cadence-only A/B.

## Cadence matrix

Output FPS is an Engine/profile property and cannot change inside a cue. Run
the unchanged Show with these profiles:

| Profile | Purpose | 50-second preflight frames | Full-show frames |
|---|---|---:|---:|
| `ws2811-ab-two-node-41-42-immediate-5fps.yaml` | Low-cadence control | about 250 | about 1360 |
| `ws2811-ab-two-node-41-42-immediate-15fps.yaml` | Current best field rate | about 750 | about 4080 |
| `ws2811-ab-two-node-41-42-immediate-30fps.yaml` | Stress boundary | about 1500 | about 8160 |

For a cadence-only A/B, compare only the deterministic 0-50 second preflight.
Its static anchors, cue-time dot positions, and cue-time two-state pulse are
identical at common 0.2-second sample times across 5/15/30 FPS. The 50-270
second effect relay is a combined renderer/transport stress sweep: `comet`,
video smoothing, random effects, and other stateful renderers can produce
different intermediate frames when FPS changes, even with the same Show.
Do not use the full relay for bit-exact cross-FPS comparison.

The Host still sends one complete logical UDP frame per Engine frame. Exact
content dedupe can reduce ESP32 physical SPI writes for unchanged frames, so
compare `received` with Host cadence and compare `spi_ok` plus
`identical_skipped` with physical refresh behavior. Do not expect `spi_ok` to
equal `received`. Random effects are not seeded by the production `run`
command, so separate physical runs are visual boundary checks rather than
frame-for-frame or event-for-event oracles.

## Commands

Validate the 15 FPS baseline before touching hardware:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml `
  validate-show --show config/shows/ws2811-two-node-capability-boundary-272s.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml `
  inspect-topology --show config/shows/ws2811-two-node-capability-boundary-272s.yaml
```

Run only the 50-second color/speed/cadence preflight first:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml `
  run --show config/shows/ws2811-two-node-capability-boundary-272s.yaml `
  --duration 50
```

Run the complete effect relay only after the preflight remains visually usable:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/ws2811-ab-two-node-41-42-immediate-15fps.yaml `
  run --show config/shows/ws2811-two-node-capability-boundary-272s.yaml
```

For the 5/15/30 FPS A/B, change only the profile filename. Stop other senders,
record both nodes' counters before and after each run, preserve the separated
data/ground routing and 10 kohm DI pull-downs, and return both strips to black
between runs. Any wrong color, unintended lit group, black-gap violation,
freeze, or latch is a physical failure even when Host and node counters pass.
