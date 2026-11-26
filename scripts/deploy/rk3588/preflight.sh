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
if ! command -v pactl >/dev/null 2>&1; then
    die "pactl is unavailable; identify the pi audio stack and RT5616 sink before deployment."
fi
native_pulseaudio 2>/dev/null || \
    die "pi audio server is not identifiable as native PulseAudio; deployment made no audio changes."
if ! pactl list short sinks 2>/dev/null | awk '$2 ~ /^alsa_output\.platform-rt5616/ { found=1 } END { exit !found }'; then
    die "RT5616 sink not found in the pi PulseAudio session; deployment made no audio changes."
fi
ok "Ubuntu 22.04 / aarch64 / pi preflight passed"
