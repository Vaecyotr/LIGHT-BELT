# Software Acceptance Test Fixtures

This directory contains fixed, immutable software acceptance inputs and static test fixtures used for deterministic regression testing.
Files in `config/acceptance/` are strictly acceptance test fixtures; they are **NOT** production runtime configurations, live deployment profiles, or active Show libraries.
For live production and deployment configurations, consult [config/profiles/rk3588-host-service.yaml](../profiles/rk3588-host-service.yaml) and [config/README.md](../README.md).
Acceptance campaign fixtures are grouped by campaign name below.

## Fixture Groups

| Path | Type | Status | Purpose | Authority / evidence role | Who should read | Do not use it for |
|---|---|---|---|---|---|---|
| [authoring-modulation-v1/](authoring-modulation-v1/) | `ACCEPTANCE FIXTURE` | `FIXED ACCEPTANCE INPUT` | Fixed static test fixtures (`layout.yaml`, `show.yaml`) defining a 2-digital-strip (4px `front`, 4px `wall_right`), 6-analog-zone layout and a 9.0s show for deterministic software acceptance of color timelines, cue modulation, and transition overlaps. | Input fixture for Phase 22 software acceptance runner; fixed software test baseline. | Test authors, engine developers reproducing Phase 22 software acceptance. | Do not use as production layout or target names (contains test stub targets like `front`, `wall_right`). |
| [show-orchestration-v1/](show-orchestration-v1/) | `ACCEPTANCE FIXTURE` | `FIXED ACCEPTANCE INPUT` | Fixed static test fixtures (`layout.yaml`, `show.yaml`) defining a 6-digital-strip (220 total pixels across ceiling/wall/front/rear) and 6-analog-node layout with a 300.0s 30 FPS show for deterministic software acceptance of seam chase, analog breathing, and fallback. | Input fixture for Phase 17 show orchestration software acceptance; fixed software test baseline. | Test authors, engine developers reproducing Phase 17 software acceptance. | Do not use as production cabin lighting profile (uses legacy single UDP node 7 and superseded zone IDs). |
| [cabin-lighting-v3/](cabin-lighting-v3/) | `ACCEPTANCE FIXTURE` | `FIXED ACCEPTANCE INPUT` | Static topology schema fixture (`topology.yaml`) recording the nominal 13 digital strips / 260 pixel groups model, virtual paths (`screen_to_top`, etc.), and golden replay hashes (`json_sha256`, `deterministic_replay_sha256`). | Fixed schema validation fixture for Phase 31 software acceptance; current production snapshot is in `config/profiles/rk3588-host-service.yaml` (9 ESP32 / 200 groups). | System architects and test engineers validating 13-node topology schema. | Do not use as live production runtime deployment (use `config/profiles/rk3588-host-service.yaml`), or treat 13/260 as hardware-verified facts. |
