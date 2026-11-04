#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

HOST_UNIT="$LB_REPO/systemd/light-belt-host.service"
PRIORITY_UNIT="$LB_REPO/systemd/user/light-belt-bluetooth-priority.service"
[[ -f "$HOST_UNIT" ]] || die "缺少 $HOST_UNIT。请先把仓库 systemd/ 部署文件同步到当前分支。"
[[ -f "$PRIORITY_UNIT" ]] || die "缺少 $PRIORITY_UNIT"

# 当前正式 unit 固定使用 pi + /home/pi/LIGHT-BELT；拒绝把旧 topeet unit 装回系统。
if grep -qE 'topeet|/home/topeet' "$HOST_UNIT"; then
    die "light-belt-host.service 仍含旧 topeet 路径，拒绝安装"
fi
if ! grep -q '^User=pi$' "$HOST_UNIT"; then
    die "light-belt-host.service 不是 User=pi，拒绝安装"
fi
if [[ "$(id -u "$LB_USER")" != "1000" ]]; then
    die "当前 pi UID 不是 1000；现有 unit 的 XDG_RUNTIME_DIR=/run/user/1000 需要先参数化"
fi

log "安装 LIGHT-BELT systemd units"
# System-wide units retain the current repository deployment model.
for unit in "$LB_REPO"/systemd/*.service "$LB_REPO"/systemd/*.timer; do
    [[ -f "$unit" ]] || continue
    sudo install -m 0644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done

sudo systemctl daemon-reload

sudo systemctl enable --now bluetooth-auto-agent.service
sudo systemctl enable --now bluetooth-public-mode.service
sudo systemctl enable light-belt-audio-default-sink.service
if ! sudo systemctl restart light-belt-audio-default-sink.service; then
    warn "RT5616/PulseAudio 尚未就绪；default-sink service 将按 Restart=on-failure 重试。"
fi

# The priority daemon naturally belongs to pi's PulseAudio session.  Install
# and enable it as a user unit without manufacturing session environment.
USER_UNIT_DIR="$LB_HOME/.config/systemd/user"
mkdir -p "$USER_UNIT_DIR/default.target.wants"
install -m 0644 "$PRIORITY_UNIT" "$USER_UNIT_DIR/light-belt-bluetooth-priority.service"
ln -sfn ../light-belt-bluetooth-priority.service \
    "$USER_UNIT_DIR/default.target.wants/light-belt-bluetooth-priority.service"
if systemctl --user daemon-reload >/dev/null 2>&1; then
    if ! systemctl --user restart light-belt-bluetooth-priority.service; then
        warn "priority user service 已 enable，但当前 user manager/PulseAudio 尚未就绪。"
    fi
else
    warn "当前 systemd --user manager 不可达；unit 已 enable，将在 pi user manager 启动时加载。"
fi

sudo systemctl enable light-belt-host.service
sudo systemctl restart light-belt-host.service

ok "Host、Bluetooth、RT5616 与 priority units 已安装"
warn "不自动 enable lb-update.timer / lb-backup-data.timer / hdmi-setup.service，避免未验收的后台行为改变运行状态。"
