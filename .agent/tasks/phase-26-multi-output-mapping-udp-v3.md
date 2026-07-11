# Phase 26 — Multi-output Mapping and UDP V3

## Phase ID

phase-26-multi-output-mapping-udp-v3

## Goal

Map independent logical strips to explicit node outputs and add a pure self-describing UDP v3 codec that transports one complete multi-output frame per ESP32 node.

## Background

UDP v2 represents one concatenated pixel payload. The approved topology requires up to three independent GPIO outputs per ESP32, true strip lengths, a shared logical sequence/timestamp, and no hardware fields inside `DigitalStrip`.

## Binding Contract References

- `CLAUDE.md`
- `docs/CLOSED_LOOP_SPEC.md`
- `docs/IMPLEMENTATION_PLAN.md` Phase 26
- `docs/contracts/QUALITY_GATE_CONTRACT.md`

## In Scope

- Extend physical mapping/config so each digital strip resolves to `node_id`, `output_id`, GPIO, and exact pixel length only at the physical boundary.
- Represent each digital node frame as independently identified output payloads; reject duplicate output IDs, duplicate GPIO assignments, missing strips, length mismatch, lengths above 100, and incomplete node mappings.
- Specify and implement pure UDP v3 encode/decode with version, flags, node ID, uint32 sequence, media timestamp, optional/reserved `apply_at_us`, output count, per-output identifier/length/payload, and CRC32.
- Ensure one logical frame gives every RS-485 and UDP physical frame the same Engine-owned sequence and media timestamp.
- Send one v3 datagram per ESP32 node without concatenating strips into one logical strip.
- Add JSON v3 Golden Vectors as the single source of truth and generate the C/C++ header used by firmware tests.
- Retain UDP v2 codec/tests as explicit legacy behavior; new cabin production config defaults to v3.

## Out of Scope

- ESP32 runtime changes, final IP addresses, real clock synchronization using `apply_at_us`, Show schema changes, or hardware verification.
- Removing or weakening UDP v2 regression tests.
- Git commit, push, merge, tag, or PR creation.

## Allowed Files

- light_engine/models.py
- light_engine/mapping/**
- light_engine/outputs/udp*.py
- light_engine/outputs/__init__.py
- light_engine/config/**
- config/layout*.yaml
- config/outputs.yaml
- config/profiles/**
- firmware/shared/udp_v3_golden.json
- firmware/shared/udp_v3_golden.h
- firmware/shared/generate_golden_headers.py
- tests/test_physical_mapping.py
- tests/test_udp*.py
- tests/test_config_validation.py
- tests/test_output_safety.py

## Forbidden Files

- firmware/esp32_ws2811_node/src/**
- firmware/esp32_ws2811_node/test/**
- light_engine/show/**
- light_engine/effects/**
- artifacts/**
- .agent/**
- docs/contracts/**

## Binding Quality Constraints

- Protocol codecs MUST be pure and hardware-independent.
- `DigitalStrip` MUST contain no physical topology fields.
- One datagram MUST describe one complete node frame; partial outputs and cross-frame packet interleaving are forbidden.
- `apply_at_us` MUST be optional/reserved in v3 and MUST NOT be required for initial operation.
- Golden JSON is authoritative; generated headers MUST match it exactly.

## Acceptance Criteria

- The approved five-node mapping resolves 13 strips and exactly 260 groups with no duplicate GPIO/output assignment.
- Round-trip, malformed packet, CRC, boundary length, sequence, timestamp, and golden tests pass.
- Three independent strips on one node remain three outputs after encode/decode.
- Production config selects v3 while v2 codec tests continue to pass.

## Required Targeted Tests

```powershell
.\.python\Scripts\python.exe -m pytest tests/test_physical_mapping.py tests/test_udp_v2.py tests/test_udp_v3.py tests/test_config_validation.py tests/test_output_safety.py -q
```

## Required Full Verification

```powershell
.\.python\Scripts\python.exe -m pytest -q --ignore=tests/test_show_e2e_acceptance.py --ignore=tests/test_authoring_modulation_acceptance.py
.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800
git diff --check
git status --short
git diff --stat
```

## Required Report

Report wire format, compatibility boundary, mapping totals, Golden Vector hashes, exact commands/return codes/test count/time/benchmark, traceability, `NOT HARDWARE VERIFIED` limitations, and `git diff --stat`.

## Commit Message

Phase 26: Add multi-output mapping and UDP v3
