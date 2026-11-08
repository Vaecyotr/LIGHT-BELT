#!/usr/bin/env bash
set -Eeuo pipefail

LB_USER="${LIGHT_BELT_USER:-pi}"
LB_HOME="${LIGHT_BELT_HOME:-/home/$LB_USER}"
LB_REPO="${LIGHT_BELT_REPO:-$LB_HOME/LIGHT-BELT}"
LB_PYTHON_VERSION="${LIGHT_BELT_PYTHON_VERSION:-3.11.14}"
LB_REGDOM="${LIGHT_BELT_REGDOM:-CN}"

_ts() { date '+%Y-%m-%d %H:%M:%S'; }
log()  { printf '[%s] %s\n' "$(_ts)" "$*"; }
ok()   { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" >&2; }
die()  { printf '[FAIL] %s\n' "$*" >&2; exit 1; }

require_target_user() {
    if [[ "$(id -un)" != "$LB_USER" ]]; then
        die "请以 $LB_USER 用户运行，不要用 sudo 启动整个脚本。需要 root 的步骤会自动调用 sudo。"
    fi
    if [[ "$HOME" != "$LB_HOME" ]]; then
        warn "HOME=$HOME，与预期 $LB_HOME 不同。"
    fi
}

require_repo() {
    [[ -d "$LB_REPO/.git" || -f "$LB_REPO/.git" ]] || die "找不到 Git 仓库: $LB_REPO"
    [[ -f "$LB_REPO/pyproject.toml" ]] || die "缺少 $LB_REPO/pyproject.toml"
}

ensure_sudo() {
    sudo -v || die "无法获得 sudo 权限"
}

run_repo_script() {
    local script="$1"
    shift || true
    bash "$LB_REPO/scripts/deploy/rk3588/$script" "$@"
}
