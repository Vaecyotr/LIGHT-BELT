#!/usr/bin/env bash
# Transactional production updater. NOT HARDWARE VERIFIED.
set -uo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../deploy/rk3588/lib/common.sh"
source "$SCRIPT_DIR/../deploy/rk3588/lib/python-env.sh"
REPO="$LB_REPO"
BRANCH="${LIGHT_BELT_UPDATE_BRANCH:-validation/energy-wakeup-strip31-20260831}"
SERVICE=light-belt-host.service
HEALTH_URL="${LIGHT_BELT_HEALTH_URL:-http://127.0.0.1:8443/api/v1/status}"
LOG="${LIGHT_BELT_UPDATE_LOG:-$LB_HOME/lb-update.log}"
HEALTH_RETRIES="${LIGHT_BELT_HEALTH_RETRIES:-20}"
HEALTH_INTERVAL="${LIGHT_BELT_HEALTH_INTERVAL:-3}"
SYSTEM_UNITS="${LIGHT_BELT_SYSTEM_UNIT_DIR:-/etc/systemd/system}"
USER_UNITS="${LIGHT_BELT_USER_UNIT_DIR:-$LB_HOME/.config/systemd/user}"
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
        body="$(curl -fsS -m 5 "$HEALTH_URL" 2>/dev/null)" || body=""
        if [[ -n "$body" ]] && "$REPO/.venv/bin/python" -c "$HEALTH_CHECK_PY" "$want" <<< "$body"; then
            return 0
        fi
        sleep "$HEALTH_INTERVAL"
    done
    return 1
}
# Only regular files enter each namespace. Activation symlinks are untouched.
sync_units() {
    local scope source_dir dest_dir file name key
    for scope in system user; do
        source_dir="$REPO/systemd"; dest_dir="$SYSTEM_UNITS"
        [[ "$scope" != user ]] || { source_dir="$REPO/systemd/user"; dest_dir="$USER_UNITS"; }
        [[ -d "$source_dir" ]] || continue
        for file in "$source_dir"/*.service "$source_dir"/*.timer; do
            [[ -f "$file" && ! -L "$file" ]] || continue
            name="$(basename "$file")"; key="$scope/$name"
            if sudo cmp -s "$file" "$dest_dir/$name"; then continue; fi
            [[ ! -L "$dest_dir/$name" ]] || return 1
            sudo mkdir -p "$dest_dir" || return 1
            mkdir -p "$STATE/$scope" || return 1
            if [[ -e "$dest_dir/$name" ]]; then
                sudo cp -a "$dest_dir/$name" "$STATE/$key" || return 1
            fi
            printf '%s\t%s\n' "$key" "$dest_dir/$name" >> "$STATE/units" || return 1
            sudo install -m 0644 "$file" "$dest_dir/$name" || return 1
        done
    done
    sudo systemctl daemon-reload || return 1
    if systemctl --user show-environment >/dev/null 2>&1; then
        systemctl --user daemon-reload || return 1
    else
        log "User manager unavailable; unit reload deferred to next login."
    fi
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
    if systemctl --user show-environment >/dev/null 2>&1; then
        systemctl --user daemon-reload || return 1
    fi
    return 0
}
rollback() {
    log "Rolling back to $OLD_COMMIT"
    if ! sudo systemctl stop "$SERVICE"; then
        log "ROLLBACK FAILED: cannot stop Host"; return 2
    fi
    if ! git reset --hard "$OLD_COMMIT" || ! restore_units || \
       ! check_host_lock || ! sync_host_environment; then
        log "ROLLBACK FAILED: code/units/locked environment restoration failed; Host stopped"
        return 2
    fi
    if ! sudo systemctl start "$SERVICE" || ! health_ok "$OLD_COMMIT"; then
        sudo systemctl stop "$SERVICE" || log "ROLLBACK FAILED: final stop also failed"
        log "ROLLBACK FAILED: recovered Host did not become healthy"; return 2
    fi
    log "Rollback succeeded; original update failed"
    return 1
}
# Parse the complete driver before merge/reset can replace its source file.
main() {
    cd "$REPO" || fail "Cannot enter $REPO"
    for cmd in git curl sudo systemctl mktemp flock; do command -v "$cmd" >/dev/null || fail "Missing $cmd"; done
    acquire_host_environment_lock || fail "Another install/update is running, or environment lock unavailable"
    local status
    status="$(git status --porcelain --untracked-files=normal)" || fail "Cannot inspect worktree"
    [[ -z "$status" ]] || fail "Dirty repository; refusing update"
    check_uv || fail "Install pinned uv $LB_UV_VERSION with setup-python.sh first"
    [[ -x "$REPO/.venv/bin/python" ]] || fail "Missing .venv; run installer first"
    select_host_python || fail "Incompatible existing Python"
    check_host_lock >> "$LOG" 2>&1 || fail "Current lock invalid; recovery not guaranteed"
    OLD_COMMIT="$(git rev-parse HEAD)" || fail "Cannot read HEAD"
    [[ "$OLD_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid HEAD"
    health_ok "$OLD_COMMIT" || fail "Current Host lacks compatible running identity/readiness; install the health contract before automatic updates"
    if ! git fetch origin "$BRANCH" >> "$LOG" 2>&1; then
        log "Fetch unavailable; unchanged"; return 0
    fi
    NEW_COMMIT="$(git rev-parse FETCH_HEAD)" || fail "Cannot read fetched commit"
    [[ "$NEW_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "Invalid fetched commit"
    [[ "$NEW_COMMIT" != "$OLD_COMMIT" ]] || { log "Already current"; return 0; }
    git merge-base --is-ancestor "$OLD_COMMIT" "$NEW_COMMIT" || fail "Update is not fast-forward"
    sudo -n true || fail "Noninteractive sudo unavailable"
    STATE="$(mktemp -d)" || fail "Cannot allocate recovery state"
    trap 'if [[ "${KEEP_RECOVERY:-0}" != 1 ]]; then rm -rf -- "$STATE"; fi' EXIT
    sudo systemctl stop "$SERVICE" || fail "Cannot stop Host"
    if git merge --ff-only "$NEW_COMMIT" >> "$LOG" 2>&1 && \
       check_host_lock >> "$LOG" 2>&1 && sync_host_environment >> "$LOG" 2>&1 && \
       sync_units >> "$LOG" 2>&1 && sudo systemctl start "$SERVICE" >> "$LOG" 2>&1 && \
       health_ok "$NEW_COMMIT"; then
        log "Update succeeded: $NEW_COMMIT"; return 0
    fi
    local result
    if rollback >> "$LOG" 2>&1; then result=0; else result=$?; fi
    if [[ "$result" == 2 ]]; then
        KEEP_RECOVERY=1
        log "Recovery state retained for operator: $STATE"
    fi
    return "$result"
}
main "$@"
