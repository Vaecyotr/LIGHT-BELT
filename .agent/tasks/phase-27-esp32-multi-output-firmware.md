# Phase 27 — ESP32 Multi-output Firmware

## Phase ID

phase-27-esp32-multi-output-firmware

## Goal

Upgrade the ESP32-S3 firmware to decode one complete UDP v3 node frame, maintain independent GPIO4/5/6 strip buffers, and refresh all addressed outputs only after complete validation.

## Background

Each WS2811 run is electrically independent through its own SN74LVC1T45. A node may control one, two, or three strips; it must never reinterpret them as one continuous strip or expose a partial frame.

## Binding Contract References

- `CLAUDE.md`
- `docs/CLOSED_LOOP_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md` Phase 27
- `firmware/shared/udp_v3_golden.json`
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Add configurable output descriptors for up to GPIO4/5/6 with unique output IDs and individual lengths from 1 to 100.
- Decode and validate the entire UDP v3 packet, CRC, node ID, output set, lengths, sequence, and payload before changing any displayed buffer.
- Stage every addressed output and invoke the multi-output refresh operation once per accepted complete node frame.
- Reject duplicate/unknown outputs, malformed lengths, CRC failures, duplicate or older sequences, and incomplete configured output sets without displaying a half-frame.
- Keep the last complete frame on rejected traffic; enter all-black safe state after configured receive timeout.
- Parse but do not require reserved `apply_at_us` for initial immediate-refresh behavior.
- Consume the generated UDP v3 Golden Header and add native protocol/state tests plus ESP32-S3 build coverage.
- Update firmware README/config examples with independent-strip wiring and `NOT HARDWARE VERIFIED` labels.

## Out of Scope

- Host protocol/mapping changes, final Wi-Fi credentials, measured cross-node synchronization guarantees, or changing STM32 firmware.
- Combining strip buffers or sharing one GPIO between strips.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- firmware/esp32_ws2811_node/**
- firmware/shared/udp_v3_golden.h
- tests/test_firmware_builds.py
- docs/hardware-integration.md

## Forbidden Files

- light_engine/**
- config/**
- firmware/stm32_rgbcct_node/**
- firmware/shared/udp_v3_golden.json
- firmware/shared/generate_golden_headers.py
- artifacts/**
- .agent/**
- docs/contracts/**

## Binding Quality Constraints

- Firmware MUST perform no visible buffer update before full packet validation.
- Sequence comparison MUST handle uint32 wrap consistently with Host tests.
- Safe state is all black; production firmware MUST NOT silently substitute fake transport or placeholder success.
- Hardware behavior not exercised on a physical ESP32 and strips MUST be labeled `NOT HARDWARE VERIFIED`.

## Acceptance Criteria

- Native tests prove one-, two-, and three-output frames remain independent and refresh once.
- Invalid, duplicate, stale, incomplete, and oversized packets do not display partial data.
- Timeout produces black on every configured output.
- Native tests and ESP32-S3 PlatformIO build pass from the isolated worktree.

## Required Targeted Tests

```powershell
pio test -d firmware/esp32_ws2811_node -e native
pio run -d firmware/esp32_ws2811_node
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q
pio test -d firmware/esp32_ws2811_node -e native
pio run -d firmware/esp32_ws2811_node
git diff --check
git status --short
git diff --stat
```

## Required Report

Report firmware layout, validation/sequence/safe-state behavior, refresh evidence, exact build/test commands and return codes, test count/time, traceability, hardware limitations, and `git diff --stat`.

## Commit Message

Phase 27: Add ESP32 multi-output UDP v3 firmware
