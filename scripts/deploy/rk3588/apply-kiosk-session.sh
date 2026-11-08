#!/usr/bin/env bash
set -u

# 该脚本只处理当前 pi 图形会话，不需要 root。
# 可由 setup-kiosk.sh 立即调用，也可由 GNOME Autostart 在每次登录时重放。
UID_NOW="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$UID_NOW}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

if [[ ! -S "$XDG_RUNTIME_DIR/bus" ]]; then
    echo "[kiosk-session] DBus session 尚未就绪，跳过本次；登录后 Autostart 会再次执行。" >&2
    exit 0
fi

failures=0
set_gsetting() {
    local schema="$1" key="$2" value="$3"
    if gsettings writable "$schema" "$key" 2>/dev/null | grep -qx true; then
        if ! gsettings set "$schema" "$key" "$value"; then
            echo "[kiosk-session] Failed to set $schema $key" >&2
            failures=$((failures + 1))
        fi
    else
        echo "[kiosk-session] Setting is unavailable or locked: $schema $key" >&2
        failures=$((failures + 1))
    fi
}

set_gsetting org.gnome.desktop.notifications show-banners false
set_gsetting org.gnome.desktop.notifications show-in-lock-screen false
set_gsetting org.gnome.desktop.screensaver lock-enabled false
set_gsetting org.gnome.desktop.session idle-delay 0
set_gsetting org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type "'nothing'"
set_gsetting org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 0
set_gsetting org.gnome.desktop.background picture-uri "''"
set_gsetting org.gnome.desktop.background picture-uri-dark "''"
set_gsetting org.gnome.desktop.background color-shading-type "'solid'"
set_gsetting org.gnome.desktop.background primary-color "'#000000'"

(( failures == 0 )) || exit 1
echo "[kiosk-session] GNOME kiosk settings applied"
