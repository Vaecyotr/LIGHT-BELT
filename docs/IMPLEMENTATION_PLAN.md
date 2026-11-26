# Current Implementation Plan

Status: **Phase 40 lighting-language software-contract closure accepted on
2026-08-23; physical acceptance remains NOT HARDWARE VERIFIED**.

Product implementation Phases 0-29 are complete. Their original approved plan
is preserved at
`docs/history/implementation/implementation-plan-phases-0-29.md` and is no
longer an active instruction source. Phases 30-40 are complete software work.
The RK3588-native 1D lighting authoring language is now **CLOSED/FROZEN**:
bug fixes and compatibility-required additions remain allowed, but proactive
primitive/effect migration and casual Show-contract redesign do not. This is a
software authoring-contract boundary, not hardware or product-release
acceptance. Do not begin or prepare Phase 41 without new user approval.

## Approved audio system upgrade

The approved [audio system upgrade](../AUDIO_SYSTEM_UPGRADE_PLAN.md) remains a
historical design and evidence record. Its old A–G work packages and web Kiosk
contracts are superseded by the current architecture and migration scope below;
they are not active implementation instructions.

## Approved workspace maintenance — 2026-11-02

The user-approved WT04 cleanup and structure-governance work preserves product
behavior and is separate from new product Phases. It covers verified duplicate
and cache removal, evidence preservation, documentation placement and current
declarations, plus locked installation/update consistency. Shared live Python
environments and hardware deployments are excluded from mutation. Its actual
results and remaining verification are recorded in
[the maintenance record](acceptance/workspace-governance-20261102.md).
This maintenance approval does not authorize Phase 41 product work.

## Approved deployment remediation — 2026-11-08

The NanoPC-T6 Ubuntu 22.04 aarch64 deployment maintenance covers a fixed,
downloadable Python 3.11/uv pair, read-only preflight, independent APT/proposed
and popup policy, Wayland session-aware Host user services, Host-managed
Bluetooth pairing/audio services, safe service migration, repeatable
installation and behavior regression tests. There is no current web Kiosk;
LIGHT-BELT automatic updates remain disabled. The implementation and physical
acceptance commands are maintained in the [deployment guide](current/rk3588-bootstrap.md)
and the [H1–H6 hardware acceptance guide](current/rk3588-unified-acceptance.md).
This maintenance does not change the frozen lighting authoring contract.

## Current Phase 40 closeout: Lighting Language Pro-Max

The Phase 35-40 campaign completed the approved strict-superset contract while
preserving the released APP playback/control facade, old Shows, old effect
defaults, the Energy Wakeup Show, virtual-path behavior, and branch lifecycle.

Completed closeout scope:

1. Gate 0 froze Host APP API V1 behind an explicit compatibility projection;
   growth of the internal registry no longer changes the advertised APP effect
   vocabulary.
2. Phase 35 added the clean-room RK3588-native `coherent_noise_field`, bringing
   the internal registry to exactly 22 effects.
3. Phase 36 closed product-relevant WLED 1D portability research with zero new
   primitive gaps and added only the approved bounded parameter extensions.
4. Phase 37 made immutable typed `ParameterSpec` metadata the registry's single
   parameter authority and added a live machine-readable exporter.
5. Phase 38 added explicit Show v2 `parameter_modulation` for only approved
   float/runtime-mutable/modulatable effect parameters. Existing common
   `audio_modulation` remains separate and unchanged.
6. Phase 39 added an explicit cue-level `color_source` block with timeline,
   spatial palette, video average/dominant, audio-spectrum palette, and
   author-bounded dominant-frequency palette sources. Existing `ColorSpec`
   modes remain unchanged and frequency has no global color meaning.
7. Phase 40 froze the final internal authoring contract, its navigation index,
   and the delivered teammate manual without exposing internal authoring
   metadata through APP V1.

Current authoring sources are indexed by
`docs/current/show-authoring-source-index.md`. The canonical Show overview is
`docs/current/show-v2-authoring.md`; the live effect contract is exported with
`scripts/dev/export_authoring_contract.py`; effect details, parameter modulation,
and ColorSource are documented under `docs/reference/`.

Closeout boundaries:

- Advanced lighting behavior belongs to Show YAML plus the RK3588 runtime. The
  APP remains a playback/control client and requires no modification.
- No Phase 35-40 work changes ESP32 firmware, physical topology, DDP behavior,
  or the rule that final brightness is applied exactly once in
  `OutputTransform`.
- `assets/energy-wakeup/energy-wakeup.yaml` remains byte-for-byte immutable.
- Repository-wide pytest is explicitly user-waived for the original Phase 40 closeout. Focused
  and cross-module integration suites are the acceptance evidence; the waiver
  is an omission, never a full-suite pass.
- Hardware, installed wiring, visible output, timing, and RK3588 performance
  remain **NOT HARDWARE VERIFIED**.

## Current deployment

The [production Profile](../config/profiles/rk3588-host-service.yaml) defines
nine WLED/DDP ESP32 nodes from `strip_32` to `strip_21`, 107 digital control
groups in total, and one `output_id: 1` per node. GPIO16 is topology metadata.
The Host uses `config/runtime/wled-ddp-mdns.yaml`, generated by resolving the
template's names via Avahi. Failed resolution disables only the unresolved
node. See the [current deployment guide](current/rk3588-bootstrap.md).

Host business REST is anonymous on the controlled cabin LAN; deployment
network isolation is the access boundary. WebSocket subscriptions retain
one-time tickets. Production lighting has one managed sender and one DDP
writer. WLED brightness and power changes share
`host_services/wled_brightness.py::apply_managed`, which reports per-node POST
submission and readback confirmation separately and propagates partial
failures. Power-off readback requires `state.on=false` and `info.live=false`.
Brightness updates during off do not power nodes on, and zero scale is
represented by managed black frames rather than `bri=0`. REST `accepted`
means the request was accepted; it is not evidence of physical output. BlueZ
pairing must be validated through real Agent callbacks and device state, not
deployment string checks. Hardware behavior remains **NOT HARDWARE VERIFIED**.

| Retained mechanism | Consumer and consequence of removal | Evidence |
| --- | --- | --- |
| Direct business REST | The deployed APP and a cabin workstation call the same show, lighting and Bluetooth controls. Without the Host endpoints they lose those controls. | `test_host_production_contract.py`, `test_host_bluetooth_control.py`, H4 |
| One-use WS ticket | APP runtime subscriptions use the issued address and event selection. Removing issuance or consuming a ticket twice breaks subscription startup or its single-use contract. | `test_host_ws_contracts.py`, `test_host_ws_state.py`, H4 |
| BlueZ Agent and PulseAudio arbitration | Real phones need pairing confirmation and one audible route. Without these the cabin can reject legitimate pairing or mix two competing streams. | `test_bluez_agent_contract.py`, `test_audio_routing.py`, H2–H4 |
| mpv media clock | The active program supplies position and seek/EOF events to lighting. A detached clock loses alignment on pause, seek and file replacement. | `test_managed_adapter.py`, `test_host_playback_contracts.py`, H5–H6 |
| Single managed DDP sender and WLED readback | Lighting endpoints and shows share one output owner. Duplicated senders can race and HTTP submission alone cannot establish that WLED left realtime mode. | `test_managed_renderer.py`, `test_host_wled_brightness.py`, H5 |
| Local Wayland, fullscreen mpv and GNOME session settings | The cabin display needs the real graphical session and black idle window. Without session setup, REST can be available while the panel is unusable. | `test_rk3588_wayland.py`, H1 and H6 |

UDP v3 remains a custom-firmware maintenance path and RS-485 v2 remains
supported for STM32 compatibility. To select the non-production UDP v3
Profile, stop output, set `ENGINE_PROFILE_PATH`, and restart the Host. The APP
has no live Profile switch. Protocol and scheduling rules are maintained in
the [closed-loop specification](CLOSED_LOOP_SPEC.md). Use the [maintenance
operator guide](current/cabin-lighting-v3-operator-guide.md) for the 13-node
site map, nine-node field subset, and coordinated firmware, wiring and Profile
cutover. Any physical result requires the corresponding device observation.

## Pending acceptance

Use the [feature delivery checklist](../feature_gap_08-54.md) for all 47 original
requirements, delivery interfaces, T00–T20 tasks, D01–D10 decisions and field
acceptance. Only requirements 9, 13, 14 and 53 require end-user operation;
other entries use administrator configuration, Shows or system behavior.
The accepted 60-second strip_31 internal-clock showcase does not close
multi-node, media-sync or full-product acceptance. User-approved WT04 Kiosk
synchronization permits anonymous REST control and retains the WS ticket
handshake, superseding the older mandatory Bearer/Kiosk-pairing goal.

Stage-specific design records retain evidence needed by supported behavior or
maintenance. New product work starts from the approved scope recorded here.
