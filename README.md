# Light Engine

## Current cabin integration

The current cabin target is 13 independent 24V WS2811 strips (260 pixel
groups) across five provisional ESP32-S3 nodes plus one RGB+CCT COB zone on a
separate STM32 RS-485 address. The software topology and tests are available;
installation, endpoints, wiring and synchronization are **NOT HARDWARE
VERIFIED**. Start with [the Cabin Lighting V3 operator guide](docs/CABIN_LIGHTING_V3_OPERATOR_GUIDE.md).

Use the Windows bundled interpreter:

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/profiles/cabin_lighting_v3_production.yaml validate-show --show config/show.cabin-v2.yaml
.\.python\Scripts\python.exe -m light_engine --config config/profiles/cabin_lighting_v3_production.yaml inspect-topology --show config/show.cabin-v2.yaml
```

The profile intentionally uses non-routable IP placeholders and a serial-port
placeholder. Production transport errors are explicit; memory/fake operation
is selected only in configuration.

Video/music driven multi-zone lighting algorithm prototype for immersive pressurized oxygen chamber.

## Historical prototype overview

The material below is retained as a development-history overview. Where it
uses V1/V2 output names, old test counts, or generic layouts, it is not a
current cabin production instruction. Use the operator guide above for the
current architecture.

This prototype implements the RK3588-side lighting algorithm and software simulator. It does NOT require actual hardware (STM32, ESP32, LED strips) to run.

**Historical status at the time of this overview**: Algorithm prototype with
synthetic data and media file support.

## Quick Start

### Prerequisites

- Python 3.11+ (embedded Python included in `.python/`)
- Dependencies pre-installed in `.python/`

### Run Demo (synthetic data, no media files needed)

```bash
PYTHONPATH=. .python/python.exe -m light_engine demo
```

### Run with Video File

```bash
PYTHONPATH=. .python/python.exe -m light_engine run --video /path/to/video.mp4
```

### Run with Audio File

```bash
PYTHONPATH=. .python/python.exe -m light_engine run --audio /path/to/audio.wav
```

### Run with Video + Audio

```bash
PYTHONPATH=. .python/python.exe -m light_engine run --video /path/to/video.mp4 --audio /path/to/audio.wav --effect video_audio_fusion
```

### Terminal Simulator

```bash
PYTHONPATH=. .python/python.exe -m light_engine simulator
```

### Export to JSONL (Headless)

```bash
PYTHONPATH=. .python/python.exe -m light_engine export --video /path/to/video.mp4 --audio /path/to/audio.wav --output output.jsonl
```

### Run Tests

```bash
PYTHONPATH=. .python/python.exe -m pytest tests/
```

### Benchmark

```bash
PYTHONPATH=. .python/python.exe -m light_engine benchmark
```

## Configuration

Configuration files are in `config/`:
- `system.yaml` — frame rates, audio, smoothing, video, logging
- `layout.yaml` — zones, strips, video zone mapping
- `effects.yaml` — active effect and per-effect parameters
- `outputs.yaml` — output backends (simulator, json, null, udp, serial)

Override config directory: `LIGHT_ENGINE_CONFIG_DIR=/path/to/config`

## Architecture

```
light_engine/
├── models.py       — Data models (VideoFeatures, AudioFeatures, PixelFrame, etc.)
├── config/         — Configuration loading and validation
├── color/          — RGB/HSV/RGBW conversion, gamma, interpolation
├── media/          — VideoReader, AudioReader
├── analysis/       — VideoAnalyzer, AudioAnalyzer
├── effects/        — 12 lighting effects (BaseEffect interface)
├── engine/         — Main loop, feature fusion, output routing
├── mapping/        — Layout, zone/strip definitions
├── outputs/        — LightOutput abstraction + Null/Json/Simulator/UDP/Serial
├── simulator/      — Terminal-based strip visualization
├── data/           — Synthetic data sources for demo/testing
├── cli/            — CLI commands: demo, run, simulator, export, benchmark
└── util/           — Smoothers, envelopes, history, noise gate
```

## Effects (P0: 8 required)

| Effect | Description |
|--------|-------------|
| `static` | Constant color |
| `breath` | Slow brightness oscillation |
| `color_wave` | Color flows continuously along strips |
| `chase` | Running light with configurable patterns |
| `comet` | Meteor with decaying tail |
| `audio_pulse` | Brightness follows music RMS energy |
| `bass_pulse` | Bass-driven pulse |
| `spectrum` | Frequency bands mapped to zones |
| `video_ambient` | Strip colors follow video zone colors |
| `video_audio_fusion` | Video color + audio energy fusion |
| `calm` | Low-stimulation slow color drift |
| `demo` | Auto-cycles through effects |

## No-Hardware Operation

- `.\.python\python.exe -m light_engine demo` — uses synthetic data, no media files
- `.\.python\python.exe -m light_engine simulator` — terminal visualization, no GUI
- `.\.python\python.exe -m light_engine export` — JSONL export for offline analysis
- `.\.python\python.exe -m light_engine benchmark` — performance testing with NullOutput

## Verified / Unverified

**Verified** (current machine):
- All 100 tests pass
- Engine runs with synthetic data
- All 12 effects produce valid output
- Terminal simulator displays strips
- JSONL export works

**Unverified** (requires hardware):
- RK3588 ARM64 performance (target: 30 FPS)
- UDP communication with ESP32-S3
- Serial/RS-485 with STM32
- Actual LED strip output
- PyAV/librosa ARM64 compatibility

## License

Proprietary — internal prototype.
