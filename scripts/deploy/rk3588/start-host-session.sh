#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"
require_target_user
[[ "${XDG_SESSION_TYPE:-}" == wayland && -n "${WAYLAND_DISPLAY:-}" ]] || \
    die "Start this helper from the pi GNOME Wayland session"
user_systemctl import-environment WAYLAND_DISPLAY XDG_SESSION_TYPE
for name in DISPLAY XAUTHORITY; do
    if [[ -n "${!name:-}" ]]; then
        user_systemctl import-environment "$name"
    else
        user_systemctl unset-environment "$name"
    fi
done
user_systemctl restart light-belt-host.service
ok "Host restarted with the current GNOME Wayland environment"
