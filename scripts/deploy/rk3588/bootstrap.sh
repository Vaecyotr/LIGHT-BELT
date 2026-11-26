#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"
source "$SCRIPT_DIR/lib/bootstrap-recovery.sh"

kiosk=0
for argument in "$@"; do
    case "$argument" in
        --configure-kiosk) kiosk=1 ;;
        *) die "Usage: $0 [--configure-kiosk]" ;;
    esac
done

require_target_user
require_repo
previous_commit="${LIGHT_BELT_PREVIOUS_COMMIT:-}"
previous_branch="${LIGHT_BELT_PREVIOUS_BRANCH:-}"
if [[ -n "$previous_commit" ]]; then
    [[ "$previous_commit" =~ ^[0-9a-f]{40}$ ]] && git -C "$LB_REPO" cat-file -e "$previous_commit^{commit}" || \
        die "Previous release commit is not available in the checkout"
    checkout_status="$(git -C "$LB_REPO" status --porcelain)" || die "Cannot check release checkout"
    [[ -z "$checkout_status" ]] || die "A clean release checkout is required for first migration"
fi
user_was_active=0
system_was_active=0
system_was_enabled=0
user_was_enabled=0
host_touched=0
runtime_changed=0
python_touched=0
timer_touched=0
RECOVERY=""
restore_host() {
    local result="$?"
    trap '' INT TERM HUP
    if (( result != 0 && host_touched )); then
        if user_systemctl is-active --quiet light-belt-host.service && ! user_systemctl stop light-belt-host.service; then
            warn "Cannot stop the new user Host. Recovery files: $RECOVERY"
            trap - EXIT
            exit 2
        fi
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
        if [[ -n "$previous_commit" ]] && ! restore_previous_release; then
            warn "Previous release or locked Python environment could not be restored. Host remains stopped. Recovery files: $RECOVERY"
            trap - EXIT
            exit 2
        fi
        if (( runtime_changed )) && ! restore_deployment; then
            warn "Rollback incomplete. Host remains stopped. Recovery files: $RECOVERY"
            trap - EXIT
            exit 2
        fi
        if (( system_was_active )); then
            sudo systemctl start light-belt-host.service || warn "Cannot restore the previous system Host"
        elif (( user_was_active )); then
            user_systemctl start light-belt-host.service || warn "Cannot restart the previous user Host"
        fi
    elif (( result != 0 )) && [[ -n "$previous_commit" ]] && ! restore_previous_release; then
        warn "Previous release could not be restored"
        trap - EXIT
        exit 2
    fi
    if (( result != 0 && timer_touched )) && ! restore_update_timer; then
        warn "Previous update timer state could not be restored. Recovery files: $RECOVERY"
        trap - EXIT
        exit 2
    fi
    if [[ -n "$RECOVERY" ]]; then rm -rf -- "$RECOVERY"; fi
    if (( result != 0 )); then warn "Deployment failed with status $result. Inspect the failing step and journalctl logs."; fi
    return "$result"
}
restore_previous_release() {
    local branch_commit
    branch_commit="$(git -C "$LB_REPO" rev-parse --verify "refs/heads/$previous_branch" 2>/dev/null || true)"
    if [[ -n "$previous_branch" && "$branch_commit" == "$previous_commit" ]]; then
        git -C "$LB_REPO" switch -- "$previous_branch" || return 1
    else
        git -C "$LB_REPO" switch --detach "$previous_commit" || return 1
    fi
    if (( python_touched )); then run_repo_script setup-python.sh; fi
}
trap restore_host EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
run_repo_script preflight.sh
run_repo_script setup-python.sh --check
ensure_sudo
if user_systemctl is-enabled --quiet light-belt-host.service; then user_was_enabled=1; fi
if systemctl is-enabled --quiet light-belt-host.service; then system_was_enabled=1; fi
if systemctl is-active --quiet lb-update.service; then
    die "LIGHT-BELT updater is running. Wait for it to finish before deployment."
fi
RECOVERY="$(mktemp -d)"
snapshot_deployment
if systemctl cat lb-update.timer >/dev/null 2>&1; then
    timer_touched=1
    sudo systemctl disable --now lb-update.timer
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
python_touched=1
run_repo_script setup-python.sh

log "4/7 Bluetooth / A2DP policy / RT5616"
runtime_changed=1
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
- PulseAudio 保留 A2DP 发现，自动 A2DP loopback 为关闭状态。
- Host 配置获选手机的可听路由，并按当前用户静音恢复节目原声。
- 蓝牙、可听输出、全屏黑幕和无 SSH 启动须在目标机验收。
- lb-update.timer / lb-backup-data.timer / hdmi-setup.service 默认不启用。
NOTE
