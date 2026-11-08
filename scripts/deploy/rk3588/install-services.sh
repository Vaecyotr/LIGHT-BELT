#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"

require_target_user
require_repo
ensure_sudo

uid="$(id -u)"
gid="$(id -g)"
sudo /usr/bin/python3 "$SCRIPT_DIR/host_environment.py" --home "$LB_HOME" --uid "$uid" --gid "$gid"

log "安装公共 Bluetooth 系统服务和维护定时器定义"
for name in bluetooth-auto-agent.service bluetooth-public-mode.service lb-update.service lb-update.timer; do
    unit="$LB_REPO/systemd/$name"
    destination="/etc/systemd/system/$name"
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
sudo systemctl enable --now bluetooth-auto-agent.service
sudo systemctl enable --now bluetooth-public-mode.service

sudo loginctl enable-linger "$LB_USER"
sudo systemctl start "user@$uid.service"
user_systemctl show-environment >/dev/null || die "pi 用户服务管理器不可达"
if user_systemctl is-active --quiet pipewire-pulse.service; then
    die "检测到 pipewire-pulse；现有音频配置已保留，请先确认原生 PulseAudio 部署方案"
fi
user_systemctl enable --now pulseaudio.socket
user_systemctl start pulseaudio.service

USER_UNIT_DIR="$LB_HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR" "$LB_HOME/.config/autostart"
for name in light-belt-host.service light-belt-audio-default-sink.service light-belt-bluetooth-priority.service; do
    install_owned_file "$LB_REPO/systemd/user/$name" "$USER_UNIT_DIR/$name"
done
install_owned_file "$LB_REPO/systemd/light-belt-host-session.desktop" \
    "$LB_HOME/.config/autostart/light-belt-host-session.desktop"
user_systemctl daemon-reload
user_systemctl enable light-belt-host.service light-belt-audio-default-sink.service light-belt-bluetooth-priority.service
user_systemctl restart light-belt-audio-default-sink.service
user_systemctl restart light-belt-bluetooth-priority.service

if [[ "${XDG_SESSION_TYPE:-}" == wayland && -n "${WAYLAND_DISPLAY:-}" ]]; then
    bash "$SCRIPT_DIR/start-host-session.sh"
else
    user_systemctl restart light-belt-host.service
    if ! wayland_session_active; then
        warn "Host API 已启动；全屏黑幕将在 pi GNOME Wayland 会话建立时自动显示。"
    fi
fi

ok "Host 用户服务、GNOME 会话启动项、Bluetooth 与音频服务已安装"
