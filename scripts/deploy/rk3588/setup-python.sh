#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/python-env.sh"
source "$SCRIPT_DIR/lib/session.sh"
require_target_user
require_repo
[[ $# == 0 || ( $# == 1 && "$1" == --check ) ]] || die "Usage: $0 [--check]"
if [[ "${1:-}" == --check ]]; then
    [[ "$#" == 1 ]] || die "--check 不接受其他参数"
    preflight_python_download || die "uv $LB_UV_VERSION 不支持目标 Python 构建 $LB_PYTHON_VERSION (Linux aarch64 GNU)，拒绝继续"
    ok "固定 uv/Python 下载组合可用"
    exit 0
fi
acquire_host_environment_lock || die "另一个安装/更新正在运行，或无法取得环境锁。"
if systemctl is-active --quiet light-belt-host.service; then
    die "Host 正在运行；请先停止 Host，或使用事务式更新入口。"
fi
if user_systemctl show-environment >/dev/null 2>&1; then
    if user_systemctl is-active --quiet light-belt-host.service; then
        die "Host 正在运行；请先停止 Host，或使用事务式更新入口。"
    fi
elif systemctl is-active --quiet "user@$(id -u).service"; then
    die "Host 用户管理器正在运行但无法访问，拒绝修改依赖。"
fi
ensure_uv || die "无法安装/校验固定 uv $LB_UV_VERSION"
select_host_python || die "Python 3.11 选择或下载失败；检查上方错误，已有环境不会被自动重建"
check_host_lock || die "声明与 uv.lock 不一致；生产端禁止改锁"
sync_host_environment || die "锁定 Host 环境同步失败"
"$LB_REPO/.venv/bin/python" - <<'PY'
import sys
import fastapi, uvicorn, websockets, jwt
import numpy, scipy, cv2, soundfile, serial, yaml
assert sys.version_info[:2] == (3, 11), sys.version
print("PYTHON_ENV_OK", sys.version.split()[0])
PY
ok "Python/.venv/Host 锁定依赖已就绪"
