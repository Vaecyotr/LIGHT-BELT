# LIGHT-BELT

LIGHT-BELT is the RK3588-hosted lighting controller for the provisional cabin
installation: 13 independent 24V WS2811 RGB strips across five ESP32-S3 nodes
and one RGB+CCT COB zone through STM32 RS-485.

The software topology, protocol codecs, firmware builds, and deterministic
acceptance evidence are verified. Physical wiring, endpoint assignment, power
distribution, cross-node timing, and visible output remain **NOT HARDWARE
VERIFIED**.

## Start here

- [Install and run](INSTALL_AND_RUN.md)
- [Documentation index](docs/README.md)
- [Cabin operator guide](docs/current/cabin-lighting-v3-operator-guide.md)
- [Show v2 authoring](docs/current/show-v2-authoring.md)
- [Effect reference](docs/reference/effect-reference.md)

## Quick validation

Use only the bundled Windows interpreter:

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  validate-show --show config/shows/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  inspect-topology --show config/shows/cabin-show-v2.yaml
```

The production profile intentionally contains placeholder endpoints and fails
explicitly until real installation values are supplied. Memory and fake
transports require explicit configuration.

## Repository map

| Path | Purpose |
| --- | --- |
| `light_engine/` | Runtime, analysis, effects, mapping, protocols, and outputs |
| `firmware/` | STM32 and ESP32-S3 firmware plus shared golden vectors |
| `config/` | Runtime defaults, profiles, shows, examples, and acceptance inputs |
| `tests/` | Unit, integration, golden, and software acceptance tests |
| `docs/current/` | Current operating and authoring instructions |
| `docs/reference/` | Current API and effect reference material |
| `docs/acceptance/` | Human-readable accepted software evidence |
| `docs/history/` | Historical plans and legacy prototype documentation |
| `artifacts/baselines/` | Committed acceptance evidence; normal tests do not write here |
| `artifacts/runs/` | Disposable local acceptance output; ignored by Git |

License: proprietary, internal use.
