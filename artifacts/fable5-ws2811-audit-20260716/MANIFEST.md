# Fable5 WS2811 audit bundle

Captured on 2026-07-16 from the dirty working tree at:

`A:\BaiduNetdiskDownload\LIGHT-BELT\.agent-worktrees\ws2811-show-stability`

Branch: `codex/one-esp-per-strip`

The files intentionally preserve the current uncommitted onsite investigation
state. They are copies only; the source working tree was not modified.

## Core SPI and build path

- `firmware/esp32_ws2811_node/src/cadence_spi6_diagnostic.cpp`
  contains SPI6 diagnostics. SPI4 is not a separate diagnostic source: the
  same file switches under `LIGHT_BELT_SPI4_CADENCE_DIAGNOSTIC`.
- `firmware/esp32_ws2811_node/src/cadence_diagnostic.cpp` is the FastLED
  cadence comparison.
- `firmware/esp32_ws2811_node/src/ws2811_spi6_encoder.cpp/.h` is the SPI6
  bit encoder and guard construction.
- `firmware/esp32_ws2811_node/src/ws2811_spi_encoder.cpp/.h` is the SPI4
  encoder selected by the shared diagnostic file.
- `firmware/esp32_ws2811_node/src/spi_ws2811_backend.cpp/.h` is the shared
  production SPI backend, including DMA buffers and synchronous submission.
- `firmware/esp32_ws2811_node/src/led_output.cpp/.h` connects frame admission,
  encoding, identical-frame suppression, and physical refresh.
- `firmware/esp32_ws2811_node/src/main.cpp` contains backend selection and the
  emergency/session admission path.
- `firmware/esp32_ws2811_node/platformio.ini` contains all relevant diagnostic
  environments and pins FastLED exactly to `3.10.3`.
- `firmware/esp32_ws2811_node/test/test_protocol.cpp` contains the SPI encoder
  vectors and guard/length tests.

## Optional emergency path

- `frame_state.cpp/.h`, `runtime_stats.h`, and `config.h` support the emergency
  admission, KEY handling, counters, and build-time policy.
- `config/profiles/ws2811-ab-node2-strip41-immediate.yaml` is the immediate
  Node 2 profile.

## Host 0x25 derivation

- `config/shows/ws2811-ab-strip41-rgb-static-steps.yaml` authors channel level
  `0.65`.
- The immediate profile sets brightness `0.35` and gamma `1.30`.
- `light_engine/outputs/transform.py` applies `(channel * brightness) ** gamma`.
- `light_engine/models.py` and `light_engine/outputs/udp_output.py` quantize
  normalized RGB with `round(value * 255)`.
- Therefore `round((0.65 * 0.35) ** 1.30 * 255) = 37 = 0x25`.

## Scope note

Hardware evidence labels the shared production SPI6 path **NOT HARDWARE
VERIFIED**. This bundle is for code audit and must not be treated as production
or hardware acceptance evidence.
