#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
source "$SCRIPT_DIR/lib/session.sh"

require_target_user
require_repo

native_pulseaudio || die "active pi audio server is not native PulseAudio"
PA_CONFIG="$LB_HOME/.config/pulse/default.pa"
if [[ ! -f "$PA_CONFIG" ]]; then PA_CONFIG="${LIGHT_BELT_SYSTEM_PULSE_CONFIG:-/etc/pulse/default.pa}"; fi
[[ -f "$PA_CONFIG" && ! -L "$PA_CONFIG" ]] || die "regular PulseAudio default.pa required"

if [[ "$PA_CONFIG" == "$LB_HOME"/* ]]; then
    "$LB_REPO/.venv/bin/python" "$SCRIPT_DIR/pulseaudio_policy.py" "$PA_CONFIG"
else
    ensure_sudo
    sudo /usr/bin/python3 "$SCRIPT_DIR/pulseaudio_policy.py" "$PA_CONFIG"
fi

user_systemctl restart pulseaudio.service
for ((attempt=0; attempt<10; attempt++)); do
    if modules="$(pactl list short modules 2>/dev/null)" && bluetooth_policy_disables_autoplay "$modules"; then
        exit 0
    fi
    sleep 0.2
done
die "effective PulseAudio module-bluetooth-policy does not confirm a2dp_source=false"
