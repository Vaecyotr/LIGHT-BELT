#!/usr/bin/env bash
# Transactional production updater. NOT HARDWARE VERIFIED.
set -uo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../deploy/rk3588/lib/common.sh"
source "$SCRIPT_DIR/../deploy/rk3588/lib/python-env.sh"
source "$SCRIPT_DIR/../deploy/rk3588/lib/session.sh"
REPO="$LB_REPO"
UPDATE_REF="${LIGHT_BELT_UPDATE_BRANCH:-}"
SERVICE=light-belt-host.service
HEALTH_URL="${LIGHT_BELT_HEALTH_URL:-}"
LOG="${LIGHT_BELT_UPDATE_LOG:-$LB_HOME/lb-update.log}"
HEALTH_RETRIES="${LIGHT_BELT_HEALTH_RETRIES:-20}"
HEALTH_INTERVAL="${LIGHT_BELT_HEALTH_INTERVAL:-3}"
SYSTEM_UNITS="${LIGHT_BELT_SYSTEM_UNIT_DIR:-/etc/systemd/system}"
USER_UNITS="${LIGHT_BELT_USER_UNIT_DIR:-$LB_HOME/.config/systemd/user}"
PA_CONFIG="$LB_HOME/.config/pulse/default.pa"
if [[ ! -f "$PA_CONFIG" ]]; then PA_CONFIG="${LIGHT_BELT_SYSTEM_PULSE_CONFIG:-/etc/pulse/default.pa}"; fi
[[ ! -L "$PA_CONFIG" ]] || { printf 'PulseAudio config symlink is unsupported: %s\n' "$PA_CONFIG" >&2; exit 1; }
if [[ -e "$PA_CONFIG" && ! -f "$PA_CONFIG" ]]; then printf 'PulseAudio config is not a regular file: %s\n' "$PA_CONFIG" >&2; exit 1; fi
log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }
fail() { log "ERROR: $*"; exit 1; }
# Capture the parser before a Git transition can replace files on disk.
HEALTH_CHECK_PY="$(cat <<'PY_HEALTH'
import json
import sys

try:
    payload = json.load(sys.stdin)
    data = payload["data"]
    healthy = (
        payload.get("ok") is True
        and data.get("service") == "light-belt-host"
        and data.get("adapter") == "real"
        and data.get("ready") is True
        and data.get("source_clean") is True
        and data.get("commit") == sys.argv[1]
    )
except (ValueError, TypeError, KeyError, AttributeError):
    healthy = False
sys.exit(0 if healthy else 1)
PY_HEALTH
)"
health_ok() {
    local want="$1" i body
    for ((i=1; i<=HEALTH_RETRIES; i++)); do
        body="$(host_status_json "$HEALTH_URL" 2>/dev/null)" || body=""
        if [[ -n "$body" ]] && "$REPO/.venv/bin/python" -c "$HEALTH_CHECK_PY" "$want" <<< "$body"; then
            if ! wayland_session_active || "$REPO/.venv/bin/python" -c "$HEALTH_MPV_PY" "/run/user/$(id -u)/light-belt/mpv.sock" >> "$LOG" 2>&1; then
                return 0
            fi
        fi
        sleep "$HEALTH_INTERVAL"
    done
    return 1
}
sync_template() {
    local source="$1" destination="$2" key="$3"
    [[ -f "$source" && ! -L "$source" && ! -L "$destination" ]] || return 1
    if sudo cmp -s "$source" "$destination"; then return 0; fi
    sudo mkdir -p "$(dirname "$destination")" || return 1
    mkdir -p "$STATE/$(dirname "$key")" || return 1
    if [[ -e "$destination" ]]; then
        sudo cp -a "$destination" "$STATE/$key" || return 1
    fi
    printf '%s\t%s\n' "$key" "$destination" >> "$STATE/units" || return 1
    sudo install -m 0644 "$source" "$destination"
}

# Regular templates change together. Activation symlinks stay in place.
sync_units() {
    local scope source_dir dest_dir file name
    for scope in system user; do
        source_dir="$REPO/systemd"; dest_dir="$SYSTEM_UNITS"
        [[ "$scope" != user ]] || { source_dir="$REPO/systemd/user"; dest_dir="$USER_UNITS"; }
        [[ -d "$source_dir" ]] || continue
        for file in "$source_dir"/*.service "$source_dir"/*.timer; do
            [[ -f "$file" && ! -L "$file" ]] || continue
            name="$(basename "$file")"
            sync_template "$file" "$dest_dir/$name" "$scope/$name" || return 1
        done
    done
    sync_template "$REPO/systemd/light-belt-host-session.desktop" \
        "$LB_HOME/.config/autostart/light-belt-host-session.desktop" \
        "autostart/light-belt-host-session.desktop" || return 1
    sudo systemctl daemon-reload || return 1
    user_systemctl daemon-reload || return 1
}
restore_units() {
    local key dest
    [[ -f "$STATE/units" ]] || return 0
    while IFS=$'\t' read -r key dest; do
        if [[ -e "$STATE/$key" ]]; then
            sudo cp -a "$STATE/$key" "$dest" || return 1
        else
            sudo rm -f -- "$dest" || return 1
        fi
    done < "$STATE/units"
    sudo systemctl daemon-reload || return 1
    user_systemctl daemon-reload || return 1
    return 0
}
restore_audio_policy() {
    [[ "$policy_attempted" == 1 ]] || return 0
    [[ ! -L "$PA_CONFIG" ]] || return 1
    sudo cp -a "$STATE/pulseaudio.pa" "$PA_CONFIG" || return 1
    user_systemctl restart pulseaudio.service || return 1
}
apply_audio_policy() {
    policy_attempted=1
    bash "$REPO/scripts/deploy/rk3588/setup-pulseaudio-policy.sh"
}
start_runtime_services() {
    user_systemctl restart light-belt-audio-default-sink.service && user_systemctl start "$SERVICE" && restart_plc_api
}
restart_plc_api() {
    user_systemctl is-enabled --quiet light-belt-plc-status.service || return 0
    user_systemctl restart light-belt-plc-status.service
}
rollback() {
    log "Rolling back to $OLD_COMMIT"
    if ! user_systemctl stop "$SERVICE"; then
        log "ROLLBACK FAILED: cannot stop Host"; return 2
    fi
    if ! git reset --hard "$OLD_COMMIT" || ! restore_units || ! restore_audio_policy || \
       ! check_host_lock || ! sync_host_environment; then
        log "ROLLBACK FAILED: code/units/locked environment restoration failed; Host stopped"
        return 2
    fi
    if ! start_runtime_services || ! health_ok "$OLD_COMMIT"; then
        user_systemctl stop "$SERVICE" || log "ROLLBACK FAILED: final stop also failed"
        log "ROLLBACK FAILED: recovered Host did not become healthy"; return 2
    fi
    log "Rollback succeeded; original update failed"
    return 1
}

recover_update() {
    local result
    rollback_pending=0
    if rollback >> "$LOG" 2>&1; then result=0; else result=$?; fi
    if [[ "$result" == 2 ]]; then
        KEEP_RECOVERY=1
        log "Recovery state retained for operator: $STATE"
    fi
    return "$result"
}

interrupt_update() {
    local signal_exit="$1" result
    trap '' INT TERM HUP
    if (( rollback_pending )); then
        log "Update interrupted (status $signal_exit)"
        if recover_update; then result=0; else result=$?; fi
        if [[ "$result" == 2 ]]; then exit 2; fi
    fi
    exit "$signal_exit"
}
# Parse the complete driver before merge/reset can replace its source file.
main() {
    cd "$REPO" || fail "Cannot enter $REPO"
    for cmd in git curl sudo systemctl mktemp flock; do command -v "$cmd" >/dev/null || fail "Missing $cmd"; done
    acquire_host_environment_lock || fail "Another install/update is running, or environment lock unavailable"
    user_systemctl show-environment >/dev/null 2>&1 || fail "Host user manager unavailable"
    local status
    status="$(git status --porcelain --untracked-files=normal)" || fail "Cannot inspect worktree"
    [[ -z "$status" ]] || fail "Dirty repository; refusing update"
    check_uv || fail "Install pinned uv $LB_UV_VERSION with setup-python.sh first"
    [[ -x "$REPO/.venv/bin/python" ]] || fail "Missing .venv; run installer first"
    select_host_python || fail "Incompatible existing Python"
    check_host_lock >> "$LOG" 2>&1 || fail "Current lock invalid; recovery not guaranteed"
    OLD_COMMIT="$(git rev-parse HEAD)" || fail "Cannot read HEAD"
    [[ "$OLD_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid HEAD"
    HEALTH_MPV_PY="$("$REPO/.venv/bin/python" - <<'PY_MPV'
import inspect
from host_services.runtime_health import check_mpv
print(inspect.getsource(check_mpv))
print("import sys")
print("sys.exit(0 if check_mpv(sys.argv[1])['mpv_ready'] else 1)")
PY_MPV
)" || fail "Cannot capture the player readiness contract"
    health_ok "$OLD_COMMIT" || fail "Current Host lacks compatible running identity/readiness; install the health contract before automatic updates"
    local remote ref current_branch
    if [[ -n "$UPDATE_REF" ]]; then
        remote="${UPDATE_REF%%/*}"
        ref="${UPDATE_REF#*/}"
        [[ "$remote" != "$UPDATE_REF" && -n "$remote" && -n "$ref" ]] || fail "LIGHT_BELT_UPDATE_BRANCH must be remote/branch"
    else
        current_branch="$(git branch --show-current)" || fail "Cannot read current branch"
        [[ -n "$current_branch" ]] || fail "Detached checkout requires LIGHT_BELT_UPDATE_BRANCH=remote/branch"
        remote="$(git config --get "branch.$current_branch.remote")" || fail "Current branch has no configured upstream remote"
        ref="$(git config --get "branch.$current_branch.merge")" || fail "Current branch has no configured upstream branch"
        ref="${ref#refs/heads/}"
        [[ -n "$remote" && -n "$ref" ]] || fail "Current branch upstream is incomplete"
    fi
    [[ "$remote" != . && "$remote" != -* && "$ref" != -* ]] || fail "Invalid update source"
    git remote get-url -- "$remote" >/dev/null 2>&1 || fail "Unknown update remote"
    git check-ref-format "refs/heads/$ref" || fail "Invalid update branch"
    log "Update source: $remote/$ref"
    if ! git fetch -- "$remote" "refs/heads/$ref" >> "$LOG" 2>&1; then
        log "Fetch unavailable; unchanged"; return 0
    fi
    NEW_COMMIT="$(git rev-parse FETCH_HEAD)" || fail "Cannot read fetched commit"
    [[ "$NEW_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid fetched commit"
    [[ "$NEW_COMMIT" != "$OLD_COMMIT" ]] || { log "Already current"; return 0; }
    git merge-base --is-ancestor "$OLD_COMMIT" "$NEW_COMMIT" || fail "Update is not fast-forward"
    [[ -f "$PA_CONFIG" && ! -L "$PA_CONFIG" ]] || fail "regular PulseAudio default.pa required"
    native_pulseaudio || fail "Native PulseAudio is required"
    sudo -n true || fail "Noninteractive sudo unavailable"
    STATE="$(mktemp -d)" || fail "Cannot allocate recovery state"
    trap 'if [[ "${KEEP_RECOVERY:-0}" != 1 ]]; then rm -rf -- "$STATE"; fi' EXIT
    cp -a "$PA_CONFIG" "$STATE/pulseaudio.pa" || fail "Cannot snapshot PulseAudio policy configuration"
    policy_attempted=0
    rollback_pending=1
    trap 'interrupt_update 130' INT
    trap 'interrupt_update 143' TERM
    trap 'interrupt_update 129' HUP
    if ! user_systemctl stop "$SERVICE"; then
        rollback_pending=0
        fail "Cannot stop Host"
    fi
    if git merge --ff-only "$NEW_COMMIT" >> "$LOG" 2>&1 && \
       check_host_lock >> "$LOG" 2>&1 && sync_host_environment >> "$LOG" 2>&1 && \
       apply_audio_policy >> "$LOG" 2>&1 && \
       sync_units >> "$LOG" 2>&1 && start_runtime_services >> "$LOG" 2>&1 && \
       health_ok "$NEW_COMMIT"; then
        rollback_pending=0
        log "Update succeeded: $NEW_COMMIT"; return 0
    fi
    trap '' INT TERM HUP
    recover_update
}
main "$@"
