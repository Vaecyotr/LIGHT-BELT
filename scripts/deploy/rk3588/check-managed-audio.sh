#!/usr/bin/env bash
# Read-only checks in the same login session as the cabin Host.
set -Eeuo pipefail
export LC_ALL=C
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
if ! awk '$2 == "module-bluetooth-policy" {
              n++; if ($0 ~ /(^|[[:space:]])a2dp_source=(false|no|0)([[:space:]]|$)/) disabled++
          } END { exit !(n == 1 && disabled == 1) }' <<<"$modules"; then
    echo 'FAIL expected exactly one Bluetooth policy with automatic A2DP loopback disabled' >&2
    failures=$((failures + 1))
fi
if ! awk '$2 == "module-loopback" && $0 ~ /bluez_source\./ {
              if ($0 !~ /sink_input_properties=["\047]?light_belt\.route_owner=/) foreign++
              else owned++
          } END { exit !(foreign == 0 && owned <= 1) }' <<<"$modules"; then
    echo 'FAIL found a competing Bluetooth loopback; inspect route ownership' >&2
    failures=$((failures + 1))
fi
native_server() {
    local info
    info="$(pactl info)" || return 1
    [[ "$info" != *PipeWire* ]] && grep -qi '^Server Name: pulseaudio' <<<"$info"
}
check "native PulseAudio" native_server
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
echo 'H2/H3/H4 require separate connection, sound isolation and touch-screen observations.'
(( failures == 0 ))
