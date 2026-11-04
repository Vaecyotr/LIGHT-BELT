#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

log "配置舱内显示为 kiosk：黑底、无通知、无锁屏/休眠"

# 禁止 Ubuntu 发行版升级 GUI 提示，但不卸载 apt、不关闭安全更新能力。
if [[ -f /etc/update-manager/release-upgrades ]]; then
    if grep -q '^Prompt=' /etc/update-manager/release-upgrades; then
        sudo sed -i 's/^Prompt=.*/Prompt=never/' /etc/update-manager/release-upgrades
    else
        printf '\nPrompt=never\n' | sudo tee -a /etc/update-manager/release-upgrades >/dev/null
    fi
fi

# 产品屏幕不允许弹出 crash reporter。保留 journal/systemd 日志用于维护。
if [[ -f /etc/default/apport ]]; then
    if grep -q '^enabled=' /etc/default/apport; then
        sudo sed -i 's/^enabled=.*/enabled=0/' /etc/default/apport
    else
        printf '\nenabled=0\n' | sudo tee -a /etc/default/apport >/dev/null
    fi
fi

mkdir -p "$LB_HOME/.config/autostart"

# 覆盖系统级 GUI 更新提示的 autostart 项。仅对存在的项目创建覆盖。
for name in update-notifier.desktop ubuntu-advantage-notification.desktop; do
    if [[ -f "/etc/xdg/autostart/$name" ]]; then
        cat > "$LB_HOME/.config/autostart/$name" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=Disabled for LIGHT-BELT kiosk
Hidden=true
X-GNOME-Autostart-enabled=false
EOF_DESKTOP
    fi
done

# 每次图形登录重新应用 GNOME session 设置，解决重刷/重置/会话启动顺序问题。
cat > "$LB_HOME/.config/autostart/light-belt-kiosk-settings.desktop" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=LIGHT-BELT Kiosk Session Settings
Exec=/bin/bash $LB_REPO/scripts/deploy/rk3588/apply-kiosk-session.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF_DESKTOP

bash "$LB_REPO/scripts/deploy/rk3588/apply-kiosk-session.sh"

ok "kiosk 系统配置已写入；Host/mpv 负责永久全屏黑幕"
