#!/usr/bin/env bash

user_systemctl() {
    local runtime="/run/user/$(id -u)"
    XDG_RUNTIME_DIR="$runtime" DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        systemctl --user "$@"
}

wayland_session_active() {
    local display runtime
    runtime="/run/user/$(id -u)"
    display="$(user_systemctl show-environment | sed -n 's/^WAYLAND_DISPLAY=//p')" || return 1
    [[ -n "$display" ]] || return 1
    if [[ "$display" != /* ]]; then display="$runtime/$display"; fi
    [[ -S "$display" ]]
}

install_owned_file() {
    local source="$1" destination="$2" mode="${3:-0644}"
    [[ ! -L "$destination" ]] || die "Refusing to replace symlink: $destination"
    if [[ -f "$destination" ]] && cmp -s "$source" "$destination"; then return; fi
    if [[ -e "$destination" && ! -e "$destination.light-belt.bak" ]]; then
        cp -p -- "$destination" "$destination.light-belt.bak"
    fi
    install -m "$mode" "$source" "$destination"
}
