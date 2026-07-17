# Configuration Layout

| Path | Purpose |
| --- | --- |
| `system.yaml`, `layout.yaml`, `effects.yaml`, `outputs.yaml` | Default runtime configuration loaded by the package |
| `profiles/` | Environment or installation overlays |
| `shows/` | Maintained Show v2 programs |
| `examples/` | Teaching, compatibility, and authoring examples |
| `acceptance/` | Fixed inputs for named software acceptance campaigns |

Hardware endpoints, GPIO mappings, and physical topology remain configurable.
Files under `acceptance/` are test fixtures, not production profiles.
