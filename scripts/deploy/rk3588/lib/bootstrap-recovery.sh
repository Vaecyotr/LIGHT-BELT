#!/usr/bin/env bash

deployment_ctl() {
    local scope="$1"; shift
    if [[ "$scope" == user ]]; then user_systemctl "$@"; else sudo systemctl "$@"; fi
}

snapshot_deployment() {
    local file key scope unit enabled active
    local system_units="${LIGHT_BELT_SYSTEM_UNIT_DIR:-/etc/systemd/system}"
    local user_units="$LB_HOME/.config/systemd/user"
    local pa_config="$LB_HOME/.config/pulse/default.pa"
    if [[ ! -e "$pa_config" && ! -L "$pa_config" ]]; then
        pa_config="${LIGHT_BELT_SYSTEM_PULSE_CONFIG:-/etc/pulse/default.pa}"
    fi
    local -a files=(
        "$system_units/lb-update.service" "$system_units/lb-update.timer"
        "$user_units/light-belt-host.service" "$user_units/light-belt-audio-default-sink.service"
        "$LB_HOME/.config/autostart/light-belt-host-session.desktop"
        "${LIGHT_BELT_BLUEZ_CONFIG:-/etc/bluetooth/main.conf}" "$pa_config"
        "$LB_REPO/config/runtime/wled-ddp-mdns.yaml"
    )
    : > "$RECOVERY/files"
    for key in "${!files[@]}"; do
        file="${files[$key]}"
        [[ ! -L "$file" && ( ! -e "$file" || -f "$file" ) ]] || die "Unsupported deployment file: $file"
        if [[ -f "$file" ]]; then sudo cp -a -- "$file" "$RECOVERY/$key"; fi
        printf '%s\t%s\n' "$key" "$file" >> "$RECOVERY/files"
    done
    : > "$RECOVERY/services"
    while read -r scope unit; do
        enabled=0; active=0
        if deployment_ctl "$scope" is-enabled --quiet "$unit"; then enabled=1; fi
        if deployment_ctl "$scope" is-active --quiet "$unit"; then active=1; fi
        printf '%s\t%s\t%s\t%s\n' "$scope" "$unit" "$enabled" "$active" >> "$RECOVERY/services"
    done <<'UNITS'
system bluetooth.service
system bluetooth-public-mode.service
system bluetooth-auto-agent.service
system light-belt-audio-default-sink.service
system lb-update.timer
user pulseaudio.socket
user pulseaudio.service
user bluetooth-audio-loopback.service
user light-belt-bluetooth-priority.service
user light-belt-audio-default-sink.service
UNITS
}

restore_service_activation() {
    local scope="$1" unit="$2" enabled="$3" active="$4"
    if (( enabled )) && ! deployment_ctl "$scope" is-enabled --quiet "$unit"; then
        deployment_ctl "$scope" enable "$unit" || return 1
    fi
    if (( active )); then
        case "$unit" in
            bluetooth.service|pulseaudio.service) deployment_ctl "$scope" restart "$unit" || return 1 ;;
            *) deployment_ctl "$scope" start "$unit" || return 1 ;;
        esac
    fi
}

restore_update_timer() {
    local scope unit enabled active
    while IFS=$'\t' read -r scope unit enabled active; do
        if [[ "$unit" == lb-update.timer ]]; then
            restore_service_activation "$scope" "$unit" "$enabled" "$active"
            return
        fi
    done < "$RECOVERY/services"
}

restore_deployment() {
    local key file scope unit enabled active
    while IFS=$'\t' read -r scope unit enabled active; do
        if (( ! enabled )) && deployment_ctl "$scope" is-enabled --quiet "$unit"; then
            deployment_ctl "$scope" disable "$unit" || return 1
        fi
        if (( ! active )) && deployment_ctl "$scope" is-active --quiet "$unit"; then
            deployment_ctl "$scope" stop "$unit" || return 1
        fi
    done < "$RECOVERY/services"
    while IFS=$'\t' read -r key file; do
        [[ ! -L "$file" ]] || return 1
        if [[ -e "$RECOVERY/$key" ]]; then
            sudo cp -a -- "$RECOVERY/$key" "$file" || return 1
        elif [[ -f "$file" ]]; then
            sudo rm -f -- "$file" || return 1
        fi
    done < "$RECOVERY/files"
    deployment_ctl system daemon-reload && deployment_ctl user daemon-reload || return 1
    while IFS=$'\t' read -r scope unit enabled active; do
        [[ "$unit" != lb-update.timer ]] || continue
        restore_service_activation "$scope" "$unit" "$enabled" "$active" || return 1
    done < "$RECOVERY/services"
}
