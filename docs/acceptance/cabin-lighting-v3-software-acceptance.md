# Cabin lighting V3 software acceptance — Phase 29

Status: **SOFTWARE ACCEPTED — production code was not changed.**

## Software verified

- The fixed acceptance fixture records exactly 13 WS2811 logical strips, 260
  pixel groups, one five-channel RGB+CCT `zone_32`, and five provisional ESP32
  nodes.  Its output table checks every configured GPIO: nodes 1–4 use 4/5/6
  and node 5 uses 4.
- The three Show v2 paths cover all fourteen physical runs and each crosses
  more than one ESP32 node.  The isolated scheduler check proves completion of
  authored `after.target: strip_41` releases exactly `strip_42`, `strip_43`,
  `strip_44`, `strip_45`, and `strip_93` in logical frame sequence 77, not in
  later frames.  Those five targets are explicitly black immediately before
  the threshold.
- Mapping and UDP v3 acceptance proved five one-node datagrams, independent
  output lengths `[3,3,3,3,1]`, and one shared `(sequence, media timestamp)`
  pair `(4294967294, 123456000)`.
- Host codec evidence covers CRC corruption, unknown output IDs, incomplete
  configured sets, stale minimum sequence, packet-size limit, and the 100
  pixel maximum.  The native firmware test additionally passed duplicate,
  stale, out-of-order/wrap sequence, timeout-black, full-output staging, and
  one-refresh behavior: 5/5 cases.
- Deterministic Show replay SHA-256 is
  `fe47009b7e6060b9840b3eb29f486dcde4070a73eb110f07d23485bb2e32052f`.

## Golden evidence

| File | Raw-byte SHA-256 observed in this worktree |
| --- | --- |
| `firmware/shared/udp_v3_golden.json` | `1eecdd68b7aa30cd344f20098dccac1cf584862c322babc2db22dfa581701d42` |
| `firmware/shared/udp_v3_golden.h` | `b82776b4675d8cfdee58a885944a05a01f6e3251ca4aa4994c1a12ccf1c79b83` |
| `firmware/esp32_ws2811_node/test/golden_vectors.h` | `b88e490e52f70b23eba9584d1ae4e533fc00fa6acad50d9f9938824dfc6b2050` |

The JSON raw-byte hash is asserted by the acceptance test.  Header hashes are
raw working-tree bytes, **not LF-normalized values**; Git line-ending settings
can therefore change them without changing the vector semantics.  Headers are
generated artifacts and were only observed here; no Phase 29
production/golden source was modified.

## Commands and results

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_cabin_v3_e2e_acceptance.py -v` | 0 — 5 passed in 1.68s |
| `python -m pytest -q --ignore=tests/test_show_e2e_acceptance.py --ignore=tests/test_authoring_modulation_acceptance.py` | 0 — 544 passed in 56.84s |
| `python -m light_engine benchmark --effect video_audio_fusion --frames 1800` | 0 — 1800 frames in 60.64s; 258.3 FPS, P95 5.10 ms, P99 6.22 ms, 0 drops (current Windows machine only) |
| `pio test -d firmware/esp32_ws2811_node -e native` | 0 — 5 succeeded in 18.253s after one-time A: tool installation |
| `pio run -d firmware/esp32_ws2811_node` | 0 — 20.43s; RAM 8.0%, Flash 11.2%; `firmware.bin` 374432 B and `firmware.elf` 14807560 B |
| `pio run -d firmware/stm32_rgbcct_node` | 0 — 27.94s; RAM 5.9%, Flash 25.8%; `firmware.bin` 17228 B and `firmware.elf` 46592 B |
| `git diff --check` | 0 |

`python` above denotes the repository's required `./.python/Scripts/python.exe`.

## Not hardware verified

No real ESP32-S3, WS2811, COB, STM32, RS-485 bus, switch, power supply,
grounding, transport timing, or physical simultaneous refresh was connected in
this phase.  These are software/codec/firmware-native assertions only.

## Configurable / final installation decisions

- ESP32 IP addresses remain documentation placeholders.
- The RS-485 address for `zone_32` is configurable (current acceptance profile
  uses 17); it is not installation label 32.
- The five-node/13-output allocation and GPIO choices are provisional and can
  change with final cabinet wiring, provided the topology/profile and tests are
  updated together.

## Environment note

The initial ESP32-S3 attempt encountered a Windows long-path C++ include lookup
failure.  The short-path retry subsequently completed successfully; its return
code and resource summary above were captured by the parent workflow, and `L:`
is no longer mapped.  The benchmark measurements describe only the current
Windows host and are not real hardware transport or refresh timing evidence.
