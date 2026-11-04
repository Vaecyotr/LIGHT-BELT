# Configuration Layout

| Path | Purpose |
| --- | --- |
| `system.yaml`, `layout.yaml`, `effects.yaml`, `outputs.yaml` | Default runtime configuration loaded by the package |
| `profiles/` | Current production, maintenance, and development overlays |
| `profile-archive/` | Retained legacy, diagnostic, emergency, and A/B profiles |
| `shows/` | Admission rules and newly approved current Shows |
| `shows/archive/` | Retired Show fixtures by stable category; never a current design reference |
| `examples/` | Teaching, compatibility, and authoring examples |
| [`acceptance/`](acceptance/README.md) | Fixed static inputs and test fixtures for named software acceptance campaigns |

Hardware endpoints, GPIO mappings, and physical topology remain configurable.
Files under `acceptance/` are test fixtures, not production profiles; see [acceptance/README.md](acceptance/README.md).

The immutable original production Show is
`assets/energy-wakeup/energy-wakeup.yaml`; the Host discovers Shows under
`assets/`, where associated media is also found. An optional manifest can
overlay discovery metadata; it is not the sole source of truth. The
`config/shows/energy-wakeup.yaml` file is used for tests, explicit CLI
validation, and the current Show compatibility baseline. The 32 legacy Shows are retained byte-identically under
`shows/archive/` in stable categories. They are legacy replay/regression
material, not design references. New Shows must follow `shows/README.md`.

`profile-archive/wled-five-board-phase-17.yaml` is the historical five-board WLED
Profile retained for compatibility. The current nine-board Host
template is `profiles/rk3588-host-service.yaml`; `scripts/runtime/resolve_nodes.py`
copies it to ignored `config/runtime/wled-ddp-mdns.yaml` after Avahi mDNS
resolution. Do not edit or deploy the tracked template as a resolved profile.
Its nine nodes and 107 pixel groups are a current Profile snapshot, not runtime
capacity limits. Unresolved nodes are disabled, not redirected to an old
address. This is **NOT HARDWARE VERIFIED**.

The separate UDP v3 maintenance Profile retains nine custom-firmware strips
with 200 groups. That is a maintenance configuration snapshot, not the current
WLED/DDP production total or a system capacity limit.

The same RK3588 template enables `system.audio.source.kind:
wled_audio_sync_v2`. Missing source fields inherit the tracked defaults in
`system.yaml`: multicast `239.0.0.1`, port `11988`, interface `0.0.0.0`, and
`stale_after_ms: 250`. This live audio receive path is independent of DDP
lighting output and does not imply that any ESP32 node is configured as an
Audio Sync sender. See
[`docs/reference/wled-audio-sync-v2.md`](../docs/reference/wled-audio-sync-v2.md).
All network and hardware behavior remains **NOT HARDWARE VERIFIED**.

For custom firmware only, `profiles/udp-v3-nine-strip-maintenance.yaml` uses
the same nine logical strips with UDP v3 and no RGB+CCT nodes. It is not valid
for WLED. Stop the show, set `ENGINE_PROFILE_PATH`, and restart the Host to
change mode; there is no APP hot-switch. **NOT HARDWARE VERIFIED.**

The only other top-level Profile is `profiles/windows-development.yaml` for
explicit non-hardware development. Files under `profile-archive/` are never
production defaults; see `profile-archive/README.md`.
