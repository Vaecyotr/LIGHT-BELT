#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

cat <<'BANNER'
============================================================
 LIGHT-BELT RK3588 bootstrap
 Target: NanoPC-T6 / Ubuntu 22.04 / user pi
============================================================
BANNER

log "1/7 系统基础依赖"
run_repo_script setup-system.sh

log "2/7 Python/uv/.venv"
run_repo_script setup-python.sh

log "3/7 Bluetooth / A2DP policy / RT5616"
run_repo_script setup-bluetooth.sh

log "4/7 kiosk / 黑屏 / 禁弹窗"
run_repo_script setup-kiosk.sh

log "5/7 mDNS runtime profile"
run_repo_script setup-runtime.sh

log "6/7 systemd / Host / Bluetooth"
run_repo_script install-services.sh

log "7/7 自动验收"
if run_repo_script verify-install.sh; then
    printf '\nLIGHT-BELT RK3588 BOOTSTRAP: PASS\n'
else
    printf '\nLIGHT-BELT RK3588 BOOTSTRAP: FAIL\n' >&2
    exit 1
fi

cat <<'NOTE'

NOTE:
- PulseAudio module-bluetooth-policy 独占 A2DP loopback；部署不会创建手工 loopback。
- Bluetooth RUNNING 时仅抑制 LIGHT-BELT-LocalMedia 音频流，视频继续运行。
- 0.20 秒恢复延迟和 systemd --user 重启/无 SSH 生命周期仍需当前 NanoPC-T6 实机验证。
- lb-update.timer / lb-backup-data.timer / hdmi-setup.service 默认不启用。
NOTE
