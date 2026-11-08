#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"

kiosk=0
for argument in "$@"; do
    case "$argument" in
        --configure-kiosk) kiosk=1 ;;
        *) die "Usage: $0 [--configure-kiosk]" ;;
    esac
done

require_target_user
require_repo
run_repo_script preflight.sh
run_repo_script setup-python.sh --check
ensure_sudo

user_was_active=0
system_was_active=0
system_was_enabled=0
user_was_enabled=0
host_touched=0
if user_systemctl is-enabled --quiet light-belt-host.service; then user_was_enabled=1; fi
if systemctl is-enabled --quiet light-belt-host.service; then system_was_enabled=1; fi
restore_host() {
    local result="$?"
    if (( result != 0 && host_touched )); then
        user_systemctl stop light-belt-host.service || warn "Cannot stop the new user Host"
        if (( user_was_enabled )); then
            user_systemctl enable light-belt-host.service || warn "Cannot restore user Host activation"
        else
            user_systemctl disable light-belt-host.service || warn "Cannot disable the new user Host"
        fi
        if systemctl cat light-belt-host.service >/dev/null 2>&1; then
            if (( system_was_enabled )); then
                sudo systemctl enable light-belt-host.service || warn "Cannot restore system Host activation"
            else
                sudo systemctl disable light-belt-host.service || warn "Cannot restore disabled system Host state"
            fi
        fi
        if (( system_was_active )); then
            sudo systemctl start light-belt-host.service || warn "Cannot restore the previous system Host"
        elif (( user_was_active )); then
            user_systemctl start light-belt-host.service || warn "Cannot restart the previous user Host"
        fi
    fi
    if (( result != 0 )); then warn "Deployment failed with status $result. Inspect the failing step and journalctl logs."; fi
    return "$result"
}
trap restore_host EXIT
if systemctl cat lb-update.timer >/dev/null 2>&1; then
    sudo systemctl disable --now lb-update.timer
fi
if systemctl is-active --quiet lb-update.service; then
    die "LIGHT-BELT updater is running. Wait for it to finish before deployment."
fi

cat <<'BANNER'
============================================================
 LIGHT-BELT RK3588 bootstrap
 Target: NanoPC-T6 / Ubuntu 22.04 / user pi
============================================================
BANNER

log "1/7 独立更新策略（保留手动更新）"
run_repo_script setup-update-policy.sh

log "2/7 系统基础依赖"
run_repo_script setup-system.sh

host_touched=1
if user_systemctl is-active --quiet light-belt-host.service; then
    user_was_active=1
    user_systemctl stop light-belt-host.service
fi
if systemctl is-active --quiet light-belt-host.service; then
    system_was_active=1
    sudo systemctl stop light-belt-host.service
fi
log "3/7 Python/uv/.venv"
run_repo_script setup-python.sh

log "4/7 Bluetooth / A2DP policy / RT5616"
run_repo_script setup-bluetooth.sh

if (( kiosk )); then
    run_repo_script setup-kiosk.sh
fi

log "5/7 mDNS runtime profile"
run_repo_script setup-runtime.sh

log "6/7 systemd / Host / Bluetooth"
run_repo_script install-services.sh

log "7/7 自动验收"
verify_args=()
if (( kiosk )); then verify_args+=(--kiosk); fi
if run_repo_script verify-install.sh "${verify_args[@]}"; then
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
