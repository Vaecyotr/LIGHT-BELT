# Software Acceptance Test Fixtures

This directory contains fixed, immutable software acceptance inputs and static test fixtures used for deterministic regression testing.
Files in `config/acceptance/` are strictly acceptance test fixtures; they are **NOT** production runtime configurations, live deployment profiles, or active Show libraries.
For live production and deployment configurations, consult [config/profiles/rk3588-host-service.yaml](../profiles/rk3588-host-service.yaml) and [config/README.md](../README.md).
Acceptance campaign fixtures are grouped by campaign name below.

## Fixture Groups

| Path | Type | Status | Purpose | Authority / evidence role | Who should read | Do not use it for |
|---|---|---|---|---|---|---|
| [cabin-lighting-v3/](cabin-lighting-v3/) | `ACCEPTANCE FIXTURE` | `FIXED ACCEPTANCE INPUT` | Static topology-schema fixture (`topology.yaml`) recording a nominal 13-strip / 260-group model, virtual paths, and replay values. | Input for Phase 31 topology validation. The current deployment snapshot is maintained separately in `config/profiles/rk3588-host-service.yaml`. | Engineers validating topology parsing and mapping. | Do not use for deployment or treat its nominal topology as hardware-verified. |
