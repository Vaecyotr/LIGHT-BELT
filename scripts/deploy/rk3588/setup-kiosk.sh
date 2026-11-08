#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo

log "配置舱内显示为 kiosk：黑底、无通知、无锁屏/休眠"

mkdir -p "$LB_HOME/.config/autostart"

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

ok "kiosk 系统配置已写入；Host 用户服务管理全屏窗口"
