#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"
source "$SCRIPT_DIR/lib/python-env.sh"
kiosk=0
require_wayland=0
for argument in "$@"; do
    case "$argument" in
        --kiosk) kiosk=1 ;;
        --require-wayland) require_wayland=1 ;;
        *) die "Usage: $0 [--kiosk] [--require-wayland]" ;;
    esac
done

PASS=0
WARN=0
FAIL=0

pass() { PASS=$((PASS+1)); printf '[PASS] %s\n' "$*"; }
warning() { WARN=$((WARN+1)); printf '[WARN] %s\n' "$*"; }
fail() { FAIL=$((FAIL+1)); printf '[FAIL] %s\n' "$*"; }

check_cmd() {
    command -v "$1" >/dev/null 2>&1 && pass "command: $1" || fail "missing command: $1"
}

printf '%s\n' '===== LIGHT-BELT RK3588 VERIFY ====='

[[ "$(id -un)" == "$LB_USER" ]] && pass "user=$LB_USER" || fail "current user is $(id -un), expected $LB_USER"
[[ -d "$LB_REPO" ]] && pass "repo=$LB_REPO" || fail "repo missing: $LB_REPO"

for cmd in ssh avahi-resolve iw curl mpv git bluetoothctl pactl timeout; do
    check_cmd "$cmd"
done

systemctl is-enabled ssh >/dev/null 2>&1 && pass "ssh enabled" || fail "ssh not enabled"
systemctl is-active ssh >/dev/null 2>&1 && pass "ssh active" || fail "ssh not active"
systemctl is-active avahi-daemon >/dev/null 2>&1 && pass "avahi active" || fail "avahi not active"

bluetooth_ready=0
for ((attempt=0; attempt<10; attempt++)); do
    controller="$(LC_ALL=C timeout 5 bluetoothctl show 2>/dev/null || true)"
    if grep -q 'Powered: yes' <<<"$controller"; then
        bluetooth_ready=1
        break
    fi
    sleep 1
done
if (( bluetooth_ready )); then
    pass "Bluetooth controller powered"
else
    fail "Bluetooth controller is not powered; inspect bluetooth.service"
fi

systemctl is-enabled bluetooth.service >/dev/null 2>&1 && pass "bluetooth enabled" || fail "bluetooth not enabled"
systemctl is-active bluetooth.service >/dev/null 2>&1 && pass "bluetooth active" || fail "bluetooth not active"
for unit in bluetooth-auto-agent.service bluetooth-public-mode.service; do
    if systemctl is-enabled "$unit" >/dev/null 2>&1 || systemctl is-active "$unit" >/dev/null 2>&1; then
        fail "$unit must be disabled; Host owns pairing behavior"
    else
        pass "$unit disabled"
    fi
done
user_systemctl is-enabled light-belt-audio-default-sink.service >/dev/null 2>&1 && pass "RT5616 default-sink service enabled" || fail "RT5616 default-sink service not enabled"
user_systemctl is-active light-belt-audio-default-sink.service >/dev/null 2>&1 && pass "RT5616 default-sink service active" || fail "RT5616 default-sink service not active"

if user_systemctl is-enabled light-belt-bluetooth-priority.service >/dev/null 2>&1 || user_systemctl is-active light-belt-bluetooth-priority.service >/dev/null 2>&1; then
    fail "legacy Bluetooth priority service must be disabled; Host owns audio policy"
else
    pass "legacy Bluetooth priority service disabled"
fi

if user_systemctl is-enabled bluetooth-audio-loopback.service >/dev/null 2>&1 || \
   user_systemctl is-active bluetooth-audio-loopback.service >/dev/null 2>&1; then
    fail "obsolete Bluetooth loopback service must be disabled"
else
    pass "obsolete Bluetooth loopback service disabled"
fi

if native_pulseaudio 2>/dev/null; then
    pass "PulseAudio reachable for $LB_USER"
    MODULES="$(pactl list short modules 2>/dev/null || true)"
    bluetooth_policy_disables_autoplay "$MODULES" && pass "automatic A2DP loopback disabled" || fail "automatic A2DP loopback is not confirmed disabled"
    [[ "$MODULES" == *'module-bluetooth-discover'* ]] && pass "module-bluetooth-discover present" || fail "module-bluetooth-discover missing"
    bluetooth_routes_exclusive "$MODULES" && pass "Bluetooth playback routes are exclusive" || fail "foreign or competing Bluetooth playback routes"
    if bash "$SCRIPT_DIR/set-default-audio-sink.sh" --check; then
        pass "RT5616 sink check passed; see /api/v1/audio for current output availability"
    else
        fail "RT5616 output or Bluetooth route not ready; inspect the default-sink user service journal"
    fi
else
    fail "pi PulseAudio session unavailable; inspect the pulseaudio user service"
fi

if check_uv; then
    pass "uv $LB_UV_VERSION installed"
else
    fail "uv missing"
fi

if [[ -x "$LB_REPO/.venv/bin/python" ]]; then
    PYVER="$($LB_REPO/.venv/bin/python -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
    [[ "$PYVER" == 3.11.* ]] && pass "Python $PYVER" || fail "unexpected Python version: ${PYVER:-unknown}"
else
    fail ".venv missing"
fi

RUNTIME="$LB_REPO/config/runtime/wled-ddp-mdns.yaml"
[[ -f "$RUNTIME" ]] && pass "runtime profile exists" || fail "runtime profile missing"

user_systemctl is-enabled light-belt-host.service >/dev/null 2>&1 && pass "Host user service enabled" || fail "Host user service not enabled"
user_systemctl is-active light-belt-host.service >/dev/null 2>&1 && pass "Host user service active" || fail "Host user service not active"
if systemctl is-active --quiet light-belt-host.service || systemctl is-enabled --quiet light-belt-host.service; then
    fail "Legacy system Host is still active or enabled"
fi
HOST_ENV="$LB_HOME/.config/light-belt/host.env"
if [[ ! -e "$HOST_ENV" ]]; then
    pass "optional Host environment file absent"
elif [[ -f "$HOST_ENV" && ! -L "$HOST_ENV" && "$(stat -c '%a:%u' "$HOST_ENV")" == "600:$(id -u)" ]]; then
    pass "Host environment file preserved with owner-only permissions"
else
    fail "Host environment file is not a regular owner-only file: $HOST_ENV"
fi
if cmp -s "$LB_REPO/systemd/light-belt-host-session.desktop" "$LB_HOME/.config/autostart/light-belt-host-session.desktop"; then
    pass "GNOME Host login entry installed"
else
    fail "GNOME Host login entry missing or different"
fi
[[ "$(loginctl show-user "$LB_USER" -p Linger --value)" == yes ]] && pass "Host starts at boot through user linger" || fail "user linger is not enabled"
if systemctl is-enabled --quiet lb-update.timer 2>/dev/null || systemctl is-active --quiet lb-update.timer; then
    fail "LIGHT-BELT automatic update timer must remain disabled"
else
    pass "LIGHT-BELT automatic update disabled"
fi

ready=0
for ((attempt=0; attempt<30; attempt++)); do
    STATUS="$(host_status_json 2>/dev/null || true)"
    if "$LB_REPO/.venv/bin/python" -c 'import json,sys; p=json.load(sys.stdin); d=p["data"]; sys.exit(0 if p.get("ok") is True and d.get("service")=="light-belt-host" and d.get("adapter")=="real" and d.get("ready") is True else 1)' <<<"$STATUS" 2>/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
if (( ready )); then
    pass "GET /api/v1/status reports the real Host ready"
else
    fail "Host did not become ready; inspect systemctl --user status light-belt-host and journalctl --user -u light-belt-host"
fi

MPV_SOCKET="/run/user/$(id -u)/light-belt/mpv.sock"
if ! wayland_session_active; then
    if (( require_wayland )); then
        fail "No active pi GNOME Wayland session for graphical acceptance"
    else
        warning "GNOME Wayland login pending; fullscreen black is NOT HARDWARE VERIFIED until the pi graphical session starts"
    fi
elif [[ -S "$MPV_SOCKET" ]]; then
    pass "mpv IPC socket exists"
    if "$LB_REPO/.venv/bin/python" -m host_services.runtime_health --mpv-socket "$MPV_SOCKET"; then
        pass "mpv IPC confirms configured fullscreen Wayland video output"
    else
        fail "mpv IPC video readiness failed"
    fi
else
    fail "mpv IPC socket missing"
fi

MPV_ARGS="$(pgrep -a -u "$LB_USER" mpv 2>/dev/null | grep -m1 -F -- "--input-ipc-server=$MPV_SOCKET" || true)"
if [[ -n "$MPV_ARGS" ]]; then
    [[ "$MPV_ARGS" == *'--fullscreen'* ]] && pass "mpv fullscreen kiosk" || fail "mpv missing --fullscreen"
    [[ "$MPV_ARGS" == *'--force-window=immediate'* ]] && pass "mpv creates its startup window immediately" || fail "mpv startup window is not immediate"
    [[ "$MPV_ARGS" == *'--gpu-context=wayland'* ]] && pass "mpv native Wayland context" || fail "mpv is not using native Wayland"
    [[ "$MPV_ARGS" != *'--vo=xv'* ]] && pass "mpv does not force legacy xv" || fail "mpv still forces --vo=xv"
    [[ "$MPV_ARGS" == *'--audio-client-name=LIGHT-BELT-LocalMedia'* ]] && pass "mpv PulseAudio identity present" || fail "mpv missing LIGHT-BELT-LocalMedia identity"
else
    if wayland_session_active; then
        fail "mpv process not running in the pi Wayland session"
    fi
fi

if grep -q -- '--audio-client-name=LIGHT-BELT-LocalMedia' "$LB_REPO/host_services/engine_adapter.py"; then
    pass "mpv source exposes LIGHT-BELT-LocalMedia"
else
    fail "mpv source missing LIGHT-BELT-LocalMedia"
fi

FORBIDDEN_LOOPBACK_CREATE="pactl load-module"" module-loopback"
if grep -R -n -F -- "$FORBIDDEN_LOOPBACK_CREATE" \
    "$LB_REPO/scripts/deploy/rk3588" "$LB_REPO/systemd" >/dev/null 2>&1; then
    fail "permanent deployment contains manual Bluetooth loopback creation"
else
    pass "deployment contains no manual Bluetooth loopback creation"
fi

# 监管域是厂家/BSP 与现场部署的交界。脚本写入持久兜底并尝试 iw reg set，
# 但不盲改 bootloader；如果内核仍为 00，这里明确警告而不是伪造 PASS。
REGDOM="$(cat /sys/module/cfg80211/parameters/ieee80211_regdom 2>/dev/null || true)"
if [[ "$REGDOM" == "$LB_REGDOM" ]]; then
    pass "Wi-Fi regulatory domain=$LB_REGDOM"
else
    warning "Wi-Fi regulatory domain=${REGDOM:-unknown}, expected $LB_REGDOM；请由厂家镜像/bootloader 固化后重启验收"
fi

if bash "$SCRIPT_DIR/setup-update-policy.sh" --check; then
    pass "Independent system update, proposed and popup policy verified"
else
    fail "Independent update policy is not effective"
fi

UID_NOW="$(id -u)"
if (( kiosk )) && [[ -S "/run/user/$UID_NOW/bus" ]]; then
    export XDG_RUNTIME_DIR="/run/user/$UID_NOW"
    export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
    BANNERS="$(gsettings get org.gnome.desktop.notifications show-banners 2>/dev/null || true)"
    [[ "$BANNERS" == "false" ]] && pass "GNOME notification banners disabled" || warning "GNOME banner setting=${BANNERS:-unknown}"
elif (( kiosk )); then
    warning "GNOME DBus session unavailable；kiosk settings will be replayed by autostart at login"
fi

printf '\nRESULT: PASS=%d WARN=%d FAIL=%d\n' "$PASS" "$WARN" "$FAIL"
if (( FAIL > 0 )); then
    printf 'LIGHT-BELT RK3588 DEPLOYMENT: FAIL\n'
    exit 1
fi
printf 'LIGHT-BELT RK3588 DEPLOYMENT: PASS\n'
if (( WARN > 0 )); then
    printf 'Deployment passed with %d warning(s).\n' "$WARN"
fi
