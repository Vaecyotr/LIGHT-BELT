# Legacy Show Archive

This directory contains 23 selected Show YAMLs retained for compatibility,
current commissioning instructions, maintenance reproduction, and focused
regression fixtures. They do not define current product visuals or authoring
requirements. Do not use them as references for new Shows or effects.

The production Host discovers Shows under `assets/`, including the immutable
original `assets/energy-wakeup/energy-wakeup.yaml`.
`config/shows/energy-wakeup.yaml` is only a test / explicit CLI validation /
compatibility fixture; it does not choose or replace the Host Show.
Historical Show acceptance belongs in `--suite history` (also included in full);
general current behavior tests may use archived input without adopting its design.

| Category | Purpose | Files |
| --- | --- | ---: |
| `cabin-v2/` | Cabin Show v2 compatibility input | 1 |
| `ws2811-ab-experiments/` | Selected WS2811 A/B examples and trace-replay inputs | 4 |
| `ws2811-diagnostics/` | WS2811 node, GPIO, QIO, and static diagnostic fixtures | 7 |
| `ws2811-emergency/` | WS2811 emergency and sentinel runbook inputs | 7 |
| `ws2811-commissioning/` | WS2811 staged commissioning and transport gates | 4 |

The prior archive migration recorded byte identity against the pre-archive HEAD.
Review subsequent file changes with Git; do not turn that migration check into a
permanent SHA gate for ordinary YAML.
Selected fixtures remain because commissioning, maintenance replay, or focused
compatibility tests still consume them. The remaining A/B and diagnostic
fixtures are not production Show choices.
