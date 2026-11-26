#!/usr/bin/env bash
# Read-only checks in the same login session as the cabin Host.
set -Eeuo pipefail
export LC_ALL=C
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"
failures=0
check() {
    local label="$1"
    shift
    if "$@"; then
        echo "PASS $label"
    else
        echo "FAIL $label" >&2
        failures=$((failures + 1))
    fi
}
inactive() {
    local result=0
    systemctl "$@" is-active --quiet "$unit" || result=$?
    [[ "$result" == 3 || "$result" == 4 ]]
}
for command in pactl parec bluetoothctl busctl systemctl; do
    check "$command available" command -v "$command"
done
check "user PulseAudio session" pactl info
check "BlueZ adapter" bluetoothctl show
for unit in bluetooth-auto-agent.service bluetooth-public-mode.service; do
    check "$unit inactive" inactive
done
unit=light-belt-bluetooth-priority.service
check "$unit inactive" inactive --user
modules="$(pactl list short modules)"
check "automatic A2DP loopback disabled" bluetooth_policy_disables_autoplay "$modules"
check "Bluetooth playback routes are exclusive" bluetooth_routes_exclusive "$modules"
check "native PulseAudio" native_pulseaudio
selected_output() {
    local selected expected
    selected="$(pactl get-default-sink)" || return 1
    expected="${LIGHT_BELT_AUDIO_SINK:-$selected}"
    printf 'default sink: %s\n' "$selected"
    [[ "$selected" == "$expected" && "$selected" == alsa_output.platform-rt5616* ]]
}
check "RT5616 is the selected default output" selected_output
check "record targets" pactl list short sources
check "speaker streams" pactl list short sink-inputs
echo 'H2/H3/H4 require separate connection, sound isolation and formal API and APP observations.'
(( failures == 0 ))
