#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"

require_target_user
require_repo
ensure_sudo

uid="$(id -u)"

log "停止已识别的旧配对策略，并安装维护定时器定义"
disable_owned_unit() {
    local scope="$1" unit="$2" expected="$3" actual
    local -a ctl=(sudo systemctl)
    [[ "$scope" != --user ]] || ctl=(systemctl --user)
    if ! "${ctl[@]}" cat "$unit" >/dev/null 2>&1; then return 0; fi
    actual="$("${ctl[@]}" cat "$unit" 2>/dev/null || true)"
    if ! grep -E '^ExecStart=' <<<"$actual" | grep -Fq -- "$expected"; then
        warn "保留来源不匹配的 $unit；请先检查其实际资源所有者。"
        return 0
    fi
    "${ctl[@]}" disable --now "$unit" || die "无法停用已识别的旧服务 $unit"
    "${ctl[@]}" daemon-reload
}
disable_owned_unit system bluetooth-auto-agent.service "$LB_REPO/scripts/deploy/rk3588/bluetooth-auto-agent.py"
disable_owned_unit system bluetooth-public-mode.service "$LB_REPO/scripts/deploy/rk3588/bluetooth-public-mode.sh"
disable_owned_unit --user light-belt-bluetooth-priority.service "$LB_REPO/scripts/deploy/rk3588/bluetooth_audio_priority.py"
disable_owned_unit --user bluetooth-audio-loopback.service "$LB_HOME/.local/bin/bluetooth-audio-loopback.sh"
# Standalone PLC API installed by hand before it moved into the repository.
disable_owned_unit --user plc-status-api.service "plc-status-api/server.py"
for name in lb-update.service lb-update.timer; do
    unit="$LB_REPO/systemd/$name"
    destination="${LIGHT_BELT_SYSTEM_UNIT_DIR:-/etc/systemd/system}/$name"
    [[ -f "$unit" ]] || die "缺少 $unit"
    [[ ! -L "$destination" ]] || die "拒绝覆盖系统服务联接: $destination"
    if ! sudo cmp -s "$unit" "$destination"; then
        if [[ -f "$destination" && ! -e "$destination.light-belt.bak" ]]; then
            sudo cp -a "$destination" "$destination.light-belt.bak"
        fi
        sudo install -m 0644 "$unit" "$destination"
    fi
done
sudo systemctl daemon-reload
sudo systemctl disable --now lb-update.timer
for legacy in light-belt-host.service light-belt-audio-default-sink.service; do
    if systemctl cat "$legacy" >/dev/null 2>&1; then
        sudo systemctl disable --now "$legacy"
    fi
done

sudo loginctl enable-linger "$LB_USER"
sudo systemctl start "user@$uid.service"
user_systemctl show-environment >/dev/null || die "pi 用户服务管理器不可达"
native_pulseaudio 2>/dev/null || die "Audio backend changed after preflight; refusing service changes"
user_systemctl enable --now pulseaudio.socket
user_systemctl start pulseaudio.service

USER_UNIT_DIR="$LB_HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR" "$LB_HOME/.config/autostart"
for name in light-belt-host.service light-belt-audio-default-sink.service light-belt-plc-status.service; do
    install_owned_file "$LB_REPO/systemd/user/$name" "$USER_UNIT_DIR/$name"
done
install_owned_file "$LB_REPO/systemd/light-belt-host-session.desktop" \
    "$LB_HOME/.config/autostart/light-belt-host-session.desktop"
user_systemctl daemon-reload
user_systemctl enable light-belt-host.service light-belt-audio-default-sink.service light-belt-plc-status.service
user_systemctl restart light-belt-audio-default-sink.service
user_systemctl restart light-belt-plc-status.service

if [[ "${XDG_SESSION_TYPE:-}" == wayland && -n "${WAYLAND_DISPLAY:-}" ]]; then
    bash "$SCRIPT_DIR/start-host-session.sh"
else
    user_systemctl restart light-belt-host.service
    if ! wayland_session_active; then
        warn "Host API 已启动；全屏黑幕将在 pi GNOME Wayland 会话建立时自动显示。"
    fi
fi

ok "Host 用户服务、GNOME 会话启动项、BlueZ 与 RT5616 默认音频服务已安装"
