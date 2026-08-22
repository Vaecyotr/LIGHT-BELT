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
  --config config/profiles/rk3588-host-service.yaml `
  validate-show --show config/shows/energy-wakeup.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config/profiles/rk3588-host-service.yaml `
  inspect-topology --show config/shows/energy-wakeup.yaml
```

These commands validate software configuration only. They do not prove
physical output or hardware timing.

## RK3588 live audio input

`config/profiles/rk3588-host-service.yaml` selects
`system.audio.source.kind: wled_audio_sync_v2`. It inherits multicast group
`239.0.0.1`, UDP port `11988`, interface `0.0.0.0`, and a 250 ms stale timeout
from `config/system.yaml`. A loaded audio file has priority over live input;
live input has priority over synthetic features. A stale live source produces
zero audio features rather than silently falling back.

This is configuration and software behavior only. Before installation, verify
the selected network interface, multicast routing/firewall, and the sender's
Audio Sync V2 configuration. No such network or hardware behavior is currently
verified. See [WLED Audio Sync V2 input contract](docs/reference/wled-audio-sync-v2.md).

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
[ESP32 commissioning guide](docs/current/esp32-windows-commissioning.md). The
current 20-effect registry and authored parameters are listed in the
[effect reference](docs/reference/effect-reference.md).
