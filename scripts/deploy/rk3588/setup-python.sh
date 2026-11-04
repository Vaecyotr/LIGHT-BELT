#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/python-env.sh"
require_target_user
require_repo
acquire_host_environment_lock || die "另一个安装/更新正在运行，或无法取得环境锁。"
if systemctl is-active --quiet light-belt-host.service; then
    die "Host 正在运行；请先停止 Host，或使用事务式更新入口。"
fi
ensure_uv || die "无法安装/校验固定 uv $LB_UV_VERSION"
select_host_python || die "现有 .venv Python 不兼容；拒绝自动重建"
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
