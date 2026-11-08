#!/usr/bin/env bash
set -u
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"
source "$SCRIPT_DIR/lib/python-env.sh"
kiosk=0
if [[ "${1:-}" == --kiosk ]]; then kiosk=1; shift; fi
[[ $# == 0 ]] || die "Usage: $0 [--kiosk]"

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

for cmd in ssh avahi-resolve iw curl mpv git bluetoothctl pactl pacmd timeout; do
    check_cmd "$cmd"
done

systemctl is-enabled ssh >/dev/null 2>&1 && pass "ssh enabled" || fail "ssh not enabled"
systemctl is-active ssh >/dev/null 2>&1 && pass "ssh active" || fail "ssh not active"
systemctl is-active avahi-daemon >/dev/null 2>&1 && pass "avahi active" || fail "avahi not active"

bluetooth_ready=0
for ((attempt=0; attempt<10; attempt++)); do
    controller="$(LC_ALL=C timeout 5 bluetoothctl show 2>/dev/null || true)"
    if grep -q 'Powered: yes' <<<"$controller" && grep -q 'Pairable: yes' <<<"$controller" && grep -q 'Discoverable: yes' <<<"$controller"; then
        bluetooth_ready=1
        break
    fi
    sleep 1
done
if (( bluetooth_ready )); then
    pass "Bluetooth controller powered, pairable and discoverable"
else
    fail "Bluetooth public pairing not ready; inspect bluetooth and bluetooth-public-mode journals"
fi

systemctl is-enabled bluetooth.service >/dev/null 2>&1 && pass "bluetooth enabled" || fail "bluetooth not enabled"
systemctl is-active bluetooth.service >/dev/null 2>&1 && pass "bluetooth active" || fail "bluetooth not active"
for unit in bluetooth-auto-agent.service bluetooth-public-mode.service; do
    systemctl is-enabled "$unit" >/dev/null 2>&1 && pass "$unit enabled" || fail "$unit not enabled"
    systemctl is-active "$unit" >/dev/null 2>&1 && pass "$unit active" || fail "$unit not active"
done
user_systemctl is-enabled light-belt-audio-default-sink.service >/dev/null 2>&1 && pass "RT5616 default-sink service enabled" || fail "RT5616 default-sink service not enabled"
user_systemctl is-active light-belt-audio-default-sink.service >/dev/null 2>&1 && pass "RT5616 default-sink service active" || fail "RT5616 default-sink service not active"

PRIORITY_UNIT="$LB_HOME/.config/systemd/user/light-belt-bluetooth-priority.service"
PRIORITY_LINK="$LB_HOME/.config/systemd/user/default.target.wants/light-belt-bluetooth-priority.service"
if user_systemctl is-enabled light-belt-bluetooth-priority.service >/dev/null 2>&1; then
    pass "Bluetooth priority user service enabled"
elif [[ -f "$PRIORITY_UNIT" && -L "$PRIORITY_LINK" ]]; then
    warning "Bluetooth priority user unit is statically enabled; user manager unavailable, reboot/no-SSH lifecycle is NOT HARDWARE VERIFIED"
else
    fail "Bluetooth priority user service not enabled"
fi
if user_systemctl is-active light-belt-bluetooth-priority.service >/dev/null 2>&1; then
    pass "Bluetooth priority user service active"
else
    warning "Bluetooth priority user service not active; reboot/no-SSH lifecycle is NOT HARDWARE VERIFIED"
fi

if [[ -e "$LB_HOME/.local/bin/bluetooth-audio-loopback.sh" || \
      -e "$LB_HOME/.config/systemd/user/bluetooth-audio-loopback.service" || \
      -e "$LB_HOME/.config/systemd/user/default.target.wants/bluetooth-audio-loopback.service" ]]; then
    fail "obsolete Bluetooth loopback helper/service still exists"
else
    pass "obsolete Bluetooth loopback helper/service absent"
fi

SINK="alsa_output.platform-rt5616-sound.stereo-fallback"
if pactl info >/dev/null 2>&1; then
    pass "PulseAudio reachable for $LB_USER"
    MODULES="$(pactl list short modules 2>/dev/null || true)"
    [[ "$MODULES" == *'module-bluetooth-policy'* ]] && pass "module-bluetooth-policy present" || fail "module-bluetooth-policy missing"
    [[ "$MODULES" == *'module-bluetooth-discover'* ]] && pass "module-bluetooth-discover present" || fail "module-bluetooth-discover missing"
    BAD_LOOPBACKS="$(printf '%s\n' "$MODULES" | awk '$2=="module-loopback" && $0 ~ /latency_msec=80/ {n++} END {print n+0}')"
    ALL_LOOPBACKS="$(printf '%s\n' "$MODULES" | awk '$2=="module-loopback" {n++} END {print n+0}')"
    (( BAD_LOOPBACKS == 0 )) && pass "no latency_msec=80 loopback" || fail "$BAD_LOOPBACKS obsolete latency_msec=80 loopback(s)"
    (( ALL_LOOPBACKS <= 1 )) && pass "module-loopback count valid ($ALL_LOOPBACKS; idle zero is allowed)" || fail "multiple module-loopback instances ($ALL_LOOPBACKS)"
    DEFAULT_SINK="$(pactl get-default-sink 2>/dev/null || true)"
    [[ "$DEFAULT_SINK" == "$SINK" ]] && pass "default sink=$SINK" || fail "default sink=${DEFAULT_SINK:-unknown}, expected $SINK"
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
[[ "$(loginctl show-user "$LB_USER" -p Linger --value)" == yes ]] && pass "Host starts at boot through user linger" || fail "user linger is not enabled"
if systemctl is-enabled --quiet lb-update.timer 2>/dev/null || systemctl is-active --quiet lb-update.timer; then
    fail "LIGHT-BELT automatic update timer must remain disabled"
else
    pass "LIGHT-BELT automatic update disabled"
fi

ready=0
for ((attempt=0; attempt<30; attempt++)); do
    STATUS="$(curl -fsS --max-time 1 http://127.0.0.1:8443/api/v1/status 2>/dev/null || true)"
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
    warning "GNOME Wayland login pending; fullscreen black is NOT HARDWARE VERIFIED until the pi graphical session starts"
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

MPV_ARGS="$(pgrep -a -u "$LB_USER" mpv 2>/dev/null | grep -F -- "--input-ipc-server=$MPV_SOCKET" | head -1)"
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
