# Phase 9 — STM32 and ESP32-S3 Firmware Projects

## Phase ID

phase-9-firmware-projects

## Goal

Complete Phase 9 from `docs/IMPLEMENTATION_PLAN.md`: independently buildable PlatformIO projects for the six-channel-addressed STM32 RGB+CCT node and ESP32-S3 WS2811 node, sharing Phase 5 golden vectors.

## Allowed Files

- firmware/**
- .gitignore
- tests/test_golden_consistency.py
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md
- docs/rk3588_deployment.md

## Forbidden Files

- light_engine/**
- config/**
- .agent/**
- AGENTS.md
- CLAUDE.md
- pyproject.toml

## Acceptance Criteria

- STM32 project targets `bluepill_f103c8` and centralizes node ID, five PWM pins, USART1, baud, byte timeout, and safety timeout.
- STM32 parser validates sync, length, node/broadcast address, flags, and CRC before applying a frame.
- STM32 PWM fade is non-blocking and supports R/G/B/WW/CW.
- ESP32-S3 project uses UDP v2, CRC32, complete-frame validation, latest-frame semantics, and one show per valid frame.
- ESP32-S3 uses RMT/FastLED-compatible output and all-black safety timeout.
- `config.example.h` is committed; `config.local.h` is ignored.
- Missing local Wi-Fi credentials still allow CI compilation with clear placeholder behavior.
- Both projects use generated golden headers.
- Both projects compile with PlatformIO.
- All firmware is marked NOT HARDWARE VERIFIED.

## Required Targeted Tests

```powershell
.\.python\python.exe -m pytest tests/test_golden_consistency.py -q
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
```

## Required Full Verification

```powershell
.\.python\python.exe -m pytest -q
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
git diff --check
```

## Commit Message

Phase 9: STM32 and ESP32-S3 firmware projects
