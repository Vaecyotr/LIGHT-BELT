# Phase 5 鈥?RS-485 v2 and UDP v2 Protocol Codecs

## Phase ID

phase-5-v2-protocol-codecs

## Goal

Implement Phase 5 from `docs/IMPLEMENTATION_PLAN.md`: pure RS-485 v2 and UDP v2 codecs, v2 output classes, golden vectors, and generated C/C++ headers while preserving legacy v1 outputs.

## Allowed Files

- light_engine/outputs/rs485_v2.py
- light_engine/outputs/udp_v2.py
- light_engine/outputs/serial_output.py
- light_engine/outputs/udp_output.py
- light_engine/outputs/__init__.py
- firmware/shared/**
- tests/test_rs485_v2.py
- tests/test_udp_v2.py
- tests/test_golden_consistency.py
- tests/test_serial.py
- tests/test_udp.py
- docs/IMPLEMENTATION_PLAN.md
- docs/architecture.md

## Forbidden Files

- firmware/stm32_rgbcct_node/**
- firmware/esp32_ws2811_node/**
- light_engine/analysis/**
- light_engine/media/**
- light_engine/effects/**
- light_engine/mapping/**
- config/**
- .agent/**
- AGENTS.md
- CLAUDE.md

## Acceptance Criteria

- RS-485 v2 is exactly 16 bytes with `A5 5A`, version 2, node ID, sequence low byte, RGB+CCT, fade, flags, and CRC-16/CCITT-FALSE.
- UDP v2 carries magic, version, type, node ID, flags, uint32 sequence, pixel count, payload length, RGB payload, and CRC32.
- Invalid length, CRC, reserved flags, and oversize payloads are rejected.
- Sequence ownership remains in the engine.
- Golden JSON is the single source of truth.
- Generator produces deterministic C/C++ headers.
- Host tests load golden JSON directly.
- v1 output tests continue to pass.
- No hardware-verification claim is made.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_rs485_v2.py tests/test_udp_v2.py tests/test_golden_consistency.py tests/test_serial.py tests/test_udp.py -q
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
.\.python\Scripts\python.exe firmware/shared/generate_golden_headers.py
git diff --check
```

## Commit Message

Phase 5: RS-485 v2 and UDP v2 protocol codecs with golden vectors

