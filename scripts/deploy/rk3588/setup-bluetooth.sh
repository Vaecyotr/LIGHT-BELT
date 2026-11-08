#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

require_target_user
require_repo
ensure_sudo

MAIN_CONF="/etc/bluetooth/main.conf"
OBSOLETE_UNIT="$LB_HOME/.config/systemd/user/bluetooth-audio-loopback.service"
OBSOLETE_LINK="$LB_HOME/.config/systemd/user/default.target.wants/bluetooth-audio-loopback.service"
OBSOLETE_HELPER="$LB_HOME/.local/bin/bluetooth-audio-loopback.sh"

log "配置 BlueZ 公共配对策略并清理旧的重复 A2DP loopback"

# The removed user service created a second latency_msec=80 route.  Native
# module-bluetooth-policy is the only owner of the Bluetooth loopback.
systemctl --user disable --now bluetooth-audio-loopback.service >/dev/null 2>&1 || true
rm -f "$OBSOLETE_UNIT" "$OBSOLETE_LINK" "$OBSOLETE_HELPER"
systemctl --user daemon-reload >/dev/null 2>&1 || true
systemctl --user reset-failed >/dev/null 2>&1 || true
pkill -u "$LB_USER" -f "$LB_HOME/.local/bin/bluetooth-audio-loopback.sh" >/dev/null 2>&1 || true

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
    "General": {"DiscoverableTimeout": "0", "PairableTimeout": "0"},
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

# A live PulseAudio session is optional during bootstrap.  If present, unload
# only the confirmed obsolete route; leave policy-owned loopbacks untouched.
if pactl info >/dev/null 2>&1; then
    mapfile -t obsolete_ids < <(
        pactl list short modules 2>/dev/null |
            awk '$2=="module-loopback" && $0 ~ /latency_msec=80/ {print $1}'
    )
    for module_id in "${obsolete_ids[@]:-}"; do
        [[ -n "$module_id" ]] || continue
        log "卸载旧的 latency_msec=80 module-loopback id=$module_id"
        pactl unload-module "$module_id" || true
    done
else
    warn "pi PulseAudio 会话当前不可达；跳过运行时旧 loopback 清理，verify 将在会话可用时重查。"
fi

ok "Bluetooth 配置已收敛；未创建任何手工 A2DP loopback"
