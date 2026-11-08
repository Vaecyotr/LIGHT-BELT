#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"
require_target_user
require_repo
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || die "Required target is Ubuntu 22.04"
[[ "$(uname -m)" == aarch64 ]] || die "Required target architecture is aarch64"
[[ "$LB_USER" == pi ]] || die "This deployment targets the pi account"
[[ "$LB_HOME" == "$HOME" && "$LB_REPO" == "$LB_HOME/LIGHT-BELT" ]] || \
    die "User services require the pi home directory and its LIGHT-BELT checkout"
[[ -x /usr/bin/python3 ]] || die "Missing Ubuntu system Python 3"
for command in sudo systemctl loginctl dpkg-query apt-get apt-config; do
    command -v "$command" >/dev/null || die "Missing deployment prerequisite: $command"
done
if user_systemctl is-active --quiet pipewire-pulse.service 2>/dev/null; then
    die "pipewire-pulse is active. Preserve the existing audio stack and confirm native PulseAudio before deployment."
fi
ok "Ubuntu 22.04 / aarch64 / pi preflight passed"
