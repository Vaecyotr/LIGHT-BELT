# Install and Run

This file contains only the current LIGHT-BELT workflow. Historical campaign
commands are archived under `docs/history/campaigns/`.

## Windows setup

Run commands from the repository root. Use only the bundled interpreter:

```powershell
.\.python\Scripts\python.exe -m pip install -e .
.\.python\Scripts\python.exe -m pytest -q
```

## Validate the cabin configuration

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  validate-show --show config/shows/cabin-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/cabin-lighting-v3-production.yaml `
  inspect-topology --show config/shows/cabin-show-v2.yaml
```

These commands validate software configuration only. The production profile
contains documentation endpoints and `REPLACE_WITH_RS485_PORT`; it is expected
to fail if used for physical output before commissioning.

## Develop without hardware

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/windows-development.yaml demo

.\.python\Scripts\python.exe -m light_engine benchmark `
  --effect video_audio_fusion --frames 1800
```

Memory and fake modes are **NOT HARDWARE VERIFIED** and never count as physical
acceptance. For installation work, follow the
[operator guide](docs/current/cabin-lighting-v3-operator-guide.md) and
[ESP32 commissioning guide](docs/current/esp32-windows-commissioning.md).
