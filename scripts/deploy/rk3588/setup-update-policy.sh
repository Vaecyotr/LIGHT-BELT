#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

mode="${1:-}"
[[ $# -le 1 && ( -z "$mode" || "$mode" == --check ) ]] || die "用法: $0 [--check]"
require_target_user
if [[ "$mode" != --check ]]; then
    ensure_sudo
fi
command -v systemctl >/dev/null || die "缺少 systemctl，无法检查更新定时器"
command -v apt-config >/dev/null || die "缺少 apt-config，无法检查有效 APT 配置"

timers=(apt-daily.timer apt-daily-upgrade.timer)
services=(apt-daily.service apt-daily-upgrade.service)

if [[ "$mode" != --check ]]; then
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            die "$service 正在运行，请等待结束后重试；没有停止该服务"
        fi
    done
    sudo /usr/bin/python3 "$SCRIPT_DIR/update_policy.py" --home "$LB_HOME" --lock --probe-lock
    for timer in "${timers[@]}"; do
        if systemctl list-unit-files "$timer" --no-legend | grep -q "^$timer[[:space:]]"; then
            sudo systemctl disable --now "$timer"
        fi
    done
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            die "$service 已启动，请等待结束后重试；没有停止该服务"
        fi
    done
else
    for timer in "${timers[@]}"; do
        if systemctl is-active --quiet "$timer" || systemctl is-enabled --quiet "$timer" 2>/dev/null; then
            die "$timer 仍处于启用或运行状态"
        fi
    done
fi

if [[ "$mode" == --check ]]; then
    /usr/bin/python3 "$SCRIPT_DIR/update_policy.py" --home "$LB_HOME" --check
else
    sudo /usr/bin/python3 "$SCRIPT_DIR/update_policy.py" --home "$LB_HOME" --lock
fi
apt_config="$(apt-config dump)"
for key in Enable Update-Package-Lists Download-Upgradeable-Packages Unattended-Upgrade; do
    if ! grep -Fxq "APT::Periodic::$key \"0\";" <<<"$apt_config"; then
        die "有效 APT::Periodic::$key 未关闭，请检查其他 APT 配置覆盖"
    fi
done
if [[ "$mode" != --check ]]; then
    if pkill -TERM -u "$LB_USER" -x update-notifier; then
        :
    else
        status=$?
        [[ "$status" == 1 ]] || die "停止 update-notifier 失败 (pkill exit $status)"
        if pgrep -u "$LB_USER" -x update-notifier >/dev/null; then
            die "update-notifier 仍在运行，无法确认已发送终止信号"
        else
            status=$?
            [[ "$status" == 1 ]] || die "检查 update-notifier 失败 (pgrep exit $status)"
        fi
    fi
    warn "若之前安装了 jammy-proposed 包，请维护人员核查；脚本不会降级或删除已安装的包。"
fi
