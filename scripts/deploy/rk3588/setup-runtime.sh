#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo

PY="$LB_REPO/.venv/bin/python"
[[ -x "$PY" ]] || die "缺少 .venv；请先执行 scripts/deploy/rk3588/setup-python.sh"
[[ -f "$LB_REPO/scripts/runtime/resolve_nodes.py" ]] || die "缺少 scripts/runtime/resolve_nodes.py"
[[ -f "$LB_REPO/config/profiles/rk3588-host-service.yaml" ]] || die "缺少 rk3588-host-service.yaml"

log "通过 Avahi/mDNS 生成现场 runtime profile"
cd "$LB_REPO"
"$PY" scripts/runtime/resolve_nodes.py

RUNTIME="$LB_REPO/config/runtime/wled-ddp-mdns.yaml"
[[ -f "$RUNTIME" ]] || die "runtime profile 未生成: $RUNTIME"

ok "runtime profile 已生成（未解析节点会被明确 disabled，不固化 IP）"
