#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[bluetooth-public] %s\n' "$*"; }

# Keep retrying so a late adapter does not make bootstrap fail and an adapter
# reset does not leave the appliance permanently undiscoverable.
while true; do
    if bluetoothctl show >/dev/null 2>&1; then
        if printf 'power on\npairable on\ndiscoverable on\nquit\n' | bluetoothctl >/dev/null; then
            log "adapter powered, pairable and discoverable"
            sleep 60
            continue
        fi
    fi
    log "Bluetooth controller not ready; retrying"
    sleep 5
done
