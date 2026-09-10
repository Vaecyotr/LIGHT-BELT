# Legacy Show Archive

This directory contains the 32 retired Show YAMLs. They are frozen historical
replay and regression fixtures, not current product behavior, visual
requirements, topology, timing, or authoring guidance. Do not use them as
references for new Shows or effects.

The production Host discovers Shows under `assets/`, including the immutable
original `assets/energy-wakeup/energy-wakeup.yaml`.
`config/shows/energy-wakeup.yaml` is only a test / explicit CLI validation /
compatibility fixture; it does not choose or replace the Host Show.
Historical Show acceptance belongs in `--suite history` (also included in full);
general current behavior tests may use archived input without adopting its design.

| Category | Purpose | Files |
| --- | --- | ---: |
| `cabin-v2/` | Cabin Show v2 commissioning and acceptance fixtures | 2 |
| `wled-legacy-demos/` | Legacy WLED multi-board and two-output demos | 2 |
| `ws2811-ab-experiments/` | WS2811 A/B color, breath, isolation, and effect experiments | 9 |
| `ws2811-diagnostics/` | WS2811 node, GPIO, QIO, and static diagnostic fixtures | 8 |
| `ws2811-emergency/` | WS2811 emergency and sentinel fixtures | 7 |
| `ws2811-commissioning/` | WS2811 staged commissioning and transport gates | 4 |

The prior archive migration recorded byte identity against the pre-archive HEAD.
Review subsequent file changes with Git; do not turn that migration check into a
permanent SHA gate for ordinary YAML.
The archive is not a source of current Show design decisions.
