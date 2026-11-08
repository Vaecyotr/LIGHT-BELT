#!/usr/bin/env bash
# Load once: a Git transition must not replace live transaction helpers.
LB_UV_VERSION=0.9.5
LB_PYTHON_DOWNLOAD_VERSION=3.11.14
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
check_python_contract() {
    [[ "$LB_UV_VERSION" == 0.9.5 && "$LB_PYTHON_VERSION" == "$LB_PYTHON_DOWNLOAD_VERSION" ]]
}
check_python_download() {
    local available
    check_python_contract || return 1
    check_uv || return 1
    available="$("$UV" python list --all-versions --all-platforms --all-arches "$LB_PYTHON_VERSION")" || return 1
    grep -Fq "cpython-$LB_PYTHON_VERSION-linux-aarch64-gnu" <<< "$available"
}
preflight_python_download() {
    check_python_contract || return 1
    HOST_PYTHON="$LB_REPO/.venv/bin/python"
    if [[ -e "$HOST_PYTHON" || -L "$HOST_PYTHON" ]]; then
        [[ -f "$HOST_PYTHON" && -x "$HOST_PYTHON" ]] || return 1
        "$HOST_PYTHON" -c 'import sys; assert sys.version_info[:2] == (3, 11)' || return 1
    fi
    if check_uv; then
        check_python_download || return 1
    fi
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
        if ! check_python_download; then
            warn "uv $LB_UV_VERSION has no verified Linux aarch64 GNU build for Python $LB_PYTHON_VERSION"
            return 1
        fi
        if ! "$UV" python install "$LB_PYTHON_VERSION"; then
            warn "Python $LB_PYTHON_VERSION download/install failed before .venv synchronization"
            return 1
        fi
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
