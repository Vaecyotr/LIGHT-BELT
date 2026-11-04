#!/usr/bin/env bash
set -Eeuo pipefail

SINK="${LIGHT_BELT_AUDIO_SINK:-alsa_output.platform-rt5616-sound.stereo-fallback}"

for _ in $(seq 1 120); do
    if pactl info >/dev/null 2>&1 && pactl list short sinks | cut -f2 | grep -Fxq "$SINK"; then
        pactl set-default-sink "$SINK"
        while read -r input _; do
            [[ -n "${input:-}" ]] && pactl move-sink-input "$input" "$SINK" >/dev/null 2>&1 || true
        done < <(pactl list short sink-inputs)
        printf '[audio-sink] default sink=%s\n' "$SINK"
        exit 0
    fi
    sleep 1
done

printf '[audio-sink] sink not available after 120s: %s\n' "$SINK" >&2
exit 1
