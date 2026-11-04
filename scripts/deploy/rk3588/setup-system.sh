#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/deploy/rk3588/lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

log "安装/校验 RK3588 基础系统依赖"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openssh-server \
    avahi-daemon avahi-utils libnss-mdns \
    iw \
    curl git ca-certificates util-linux \
    mpv \
    x11-xserver-utils \
    libglib2.0-bin \
    bluez \
    pulseaudio pulseaudio-utils pulseaudio-module-bluetooth \
    python3-dbus python3-gi dbus-x11

sudo systemctl enable --now ssh
sudo systemctl enable --now avahi-daemon
sudo systemctl enable --now bluetooth || true

# 中国大陆部署的持久兜底配置。部分 RK3588 内核可能把 cfg80211 编进内核，
# 因此这个文件并不能替代厂家/bootloader 的监管域配置；verify 会明确检查并告警。
printf 'options cfg80211 ieee80211_regdom=%s\n' "$LB_REGDOM" | \
    sudo tee /etc/modprobe.d/regdom.conf >/dev/null

if command -v iw >/dev/null 2>&1; then
    sudo iw reg set "$LB_REGDOM" >/dev/null 2>&1 || \
        warn "运行时 iw reg set $LB_REGDOM 失败；将由最终验收检查实际监管域。"
fi

ok "系统基础依赖已安装；SSH/Avahi 已启用"
