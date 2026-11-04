#!/usr/bin/env bash
# Load once: a Git transition must not replace live transaction helpers.
LB_UV_VERSION=0.9.5
UV="${LIGHT_BELT_UV:-$LB_HOME/.local/bin/uv}"
acquire_host_environment_lock() {
    # Keep this stable inode after exit; waiting processes may already hold fds.
    command -v flock >/dev/null || return 1
    mkdir -p "$LB_HOME/.cache/light-belt" || return 1
    exec 9>"$LB_HOME/.cache/light-belt/update.lock" || return 1
    flock -n 9
}
check_uv() {
    local name version rest
    [[ -x "$UV" ]] || return 1
    read -r name version rest <<< "$("$UV" --version)" || return 1
    [[ "$name" == uv && "$version" == "$LB_UV_VERSION" ]]
}
ensure_uv() {
    if ! check_uv; then
        local installer
        installer="$(mktemp)" || return 1
        if ! curl -LsSf "https://astral.sh/uv/$LB_UV_VERSION/install.sh" -o "$installer"; then
            rm -f "$installer"; return 1
        fi
        if ! UV_UNMANAGED_INSTALL="$(dirname "$UV")" sh "$installer"; then
            rm -f "$installer"; return 1
        fi
        rm -f "$installer"
    fi
    check_uv
}
select_host_python() {
    HOST_PYTHON="$LB_REPO/.venv/bin/python"
    if [[ -e "$HOST_PYTHON" ]]; then
        "$HOST_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 11)' || return 1
    else
        "$UV" python install "$LB_PYTHON_VERSION" || return 1
        HOST_PYTHON="$LB_PYTHON_VERSION"
    fi
}
check_host_lock() {
    [[ -f "$LB_REPO/uv.lock" ]] || return 1
    (cd "$LB_REPO" && "$UV" lock --check --python "$HOST_PYTHON")
}
sync_host_environment() {
    (cd "$LB_REPO" && UV_PROJECT_ENVIRONMENT="$LB_REPO/.venv" \
        "$UV" sync --locked --no-dev --extra host --python "$HOST_PYTHON")
}
