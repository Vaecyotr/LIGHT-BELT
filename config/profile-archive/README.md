# Archived Profiles

These profiles are retained for historical tests, diagnostics, commissioning
records, and custom-firmware reproduction. They are not read by the current
RK3588 WLED/DDP systemd service and must not be selected as the production
`ENGINE_PROFILE_PATH`.

The current tracked production source template is
`../profiles/rk3588-host-service.yaml`. The deployed service resolves its WLED mDNS
names into a generated runtime profile such as `site-profile.yaml`; operators
must edit the tracked source template, not the generated file.

The only maintained alternate hardware mode is
`../profiles/udp-v3-nine-strip-maintenance.yaml`, for explicitly selected devices using
the project's custom UDP v3 firmware. WLED devices do not use that protocol.
