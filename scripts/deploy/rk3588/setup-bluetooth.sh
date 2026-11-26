#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

MAIN_CONF="${LIGHT_BELT_BLUEZ_CONFIG:-/etc/bluetooth/main.conf}"
log "配置 BlueZ A2DP 发现；由 Host 管理真实手机配对及可听路由"

if [[ -f "$MAIN_CONF" ]]; then
    [[ ! -L "$MAIN_CONF" ]] || die "拒绝覆盖 Bluetooth 配置联接: $MAIN_CONF"
    sudo cp -an "$MAIN_CONF" "$MAIN_CONF.light-belt.bak"
fi

sudo /usr/bin/python3 - "$MAIN_CONF" <<'PY'
from pathlib import Path
import sys
import os
import tempfile

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
wanted = {
    "Policy": {"AutoEnable": "true"},
}

for section, values in wanted.items():
    header = f"[{section}]"
    if not any(line.strip() == header for line in lines):
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.append(f"\n{header}\n")
    for key, value in values.items():
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].lstrip().startswith("["):
                end = i
                break
        replacement = f"{key} = {value}\n"
        found = False
        for i in range(start + 1, end):
            candidate = lines[i].strip()
            if candidate.startswith("#"):
                continue
            if "=" in candidate and candidate.split("=", 1)[0].strip() == key:
                lines[i] = replacement
                found = True
        if not found:
            lines.insert(end, replacement)

metadata = path.stat() if path.exists() else None
fd, temporary = tempfile.mkstemp(prefix=".light-belt-bluez-", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("".join(lines))
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, metadata.st_mode & 0o7777 if metadata else 0o644)
    if metadata is not None and os.name == "posix":
        os.chown(temporary, metadata.st_uid, metadata.st_gid)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

sudo systemctl enable bluetooth.service
sudo systemctl restart bluetooth.service

bash "$SCRIPT_DIR/setup-pulseaudio-policy.sh"

ok "BlueZ 已配置；运行时路由仅由 Host 按设备所有权管理"
