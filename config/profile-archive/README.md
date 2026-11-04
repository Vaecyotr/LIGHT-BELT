# Archived Profiles

These profiles are retained for historical tests, diagnostics, commissioning
records, and custom-firmware reproduction. They are not read by the current
RK3588 WLED/DDP systemd service and must not be selected as the production
`ENGINE_PROFILE_PATH`.

The current tracked production source template is
`../profiles/rk3588-host-service.yaml`. The deployed service resolves its WLED mDNS
names into `../runtime/wled-ddp-mdns.yaml`; operators
must edit the tracked source template, not the generated file.

The only maintained alternate hardware mode is
`../profiles/udp-v3-nine-strip-maintenance.yaml`, for explicitly selected devices using
the project's custom UDP v3 firmware. WLED devices do not use that protocol.

## Historical visual-showcase replay input

`rk3588-wled-200-groups-before-20260917.yaml` preserves the DDP configuration
from the parent of commit `fbaab17` (before the production length update).
Its historical `strip_43` has 20 groups and the nine strips total 200.
The August 2026 visual-showcase regression uses this explicit historical input;
current production independently remains 107 groups, including `strip_43=10`.
Do not select the replay fixture for actual output or change current production
to satisfy historical geometry assertions. Its values come from Git history,
not regenerated expected output.
