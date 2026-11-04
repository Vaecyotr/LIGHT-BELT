"""Run the actual updater with external systems replaced by local executables."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import shlex
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = "A:/Git/Git/bin/bash.exe" if os.name == "nt" else shutil.which("bash")
OLD = "a" * 40
NEW = "b" * 40


def posix(path: Path) -> str:
    text = path.resolve().as_posix()
    return "/" + text[0].lower() + text[2:] if len(text) > 1 and text[1] == ":" else text


FAKES = r'''#!/usr/bin/env bash
set -eu
name="$(basename "$0")"
printf '%s %s\n' "$name" "$*" >> "$CASE/events"
head() { cat "$CASE/head"; }
case "$name" in
id) echo pi;;
git)
 case "$1" in
 status) [[ "$MODE" != status-fail ]] || exit 1; [[ "$MODE" != dirty ]] || echo ' M user.txt';;
 rev-parse) if [[ "${*: -1}" == origin/* || "${*: -1}" == FETCH_HEAD ]]; then
   if [[ "$MODE" == no-update ]]; then printf '%040d\n' 0 | tr 0 a; else printf '%040d\n' 0 | tr 0 b; fi
   else head; fi;;
 fetch) [[ "$MODE" != offline ]];;
 merge-base) exit 0;;
 merge) printf '%040d\n' 0 | tr 0 b > "$CASE/head";;
 reset) [[ "$MODE" != rollback-code-fail ]] || exit 1; printf '%040d\n' 0 | tr 0 a > "$CASE/head";;
 *) exit 0;;
 esac;;
uv)
 case "$1" in
 --version) if [[ "$MODE" == wrong-uv ]]; then echo 'uv 0.9.50'; else echo 'uv 0.9.5'; fi;;
 lock) [[ "$MODE" != stale-lock && !( "$(head)" == b* && "$MODE" == stale-new-lock ) ]];;
 sync)
   [[ "$(cat "$CASE/active")" == 0 ]] || { echo UNSAFE_RUNNING_SYNC; exit 99; }
   if [[ "$(head)" == b* && "$MODE" == sync-fail ]]; then exit 1; fi
   if [[ "$(head)" == a* && "$MODE" == rollback-env-fail ]]; then exit 1; fi;;
 esac;;
sudo)
 [[ "${1:-}" != -n ]] || shift
 if [[ "$1" == install && "${*: -1}" == */session.service && "$MODE" == unit-copy-fail ]]; then exit 1; fi
 exec "$@";;
flock) [[ "$MODE" != lock-held ]];;
systemctl)
 scope=system; if [[ "${1:-}" == --user ]]; then scope=user; shift; fi
 case "$1" in
 show-environment) [[ "$MODE" != user-manager-absent ]];;
 daemon-reload) [[ !( "$(head)" == b* && "$MODE" == reload-fail ) ]];;
 is-active) [[ "$2" != *.timer && "$(cat "$CASE/active")" == 1 ]];;
 is-enabled) exit 1;;
 stop) [[ "$MODE" != stop-fail ]] || exit 1; echo 0 > "$CASE/active";;
 start|restart) if [[ "$(head)" == b* && "$MODE" == start-fail ]]; then exit 1; fi; echo 1 > "$CASE/active";;
 esac;;
curl)
 if [[ "$(head)" == b* && "$MODE" == *fail* ]]; then exit 1; fi
 if [[ "$MODE" == legacy-health ]]; then printf '{"commit":"%.12s"}\n' "$(head)"; exit 0; fi
 printf '{"ok":true,"data":{"service":"light-belt-host","adapter":"real","ready":true,"source_clean":true,"commit":"%s"}}\n' "$(head)";;
esac
'''


def run_case(tmp_path: Path, mode: str, entry="scripts/maintenance/update.sh"):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    for directory in ("scripts/maintenance", "scripts/deploy/rk3588/lib", "systemd/user", ".venv/bin"):
        (repo / directory).mkdir(parents=True, exist_ok=True)
    for source in (ROOT / "scripts/deploy/rk3588/lib").glob("*.sh"):
        shutil.copyfile(source, repo / "scripts/deploy/rk3588/lib" / source.name)
    shutil.copyfile(ROOT / "scripts/maintenance/update.sh", repo / "scripts/maintenance/update.sh")
    shutil.copyfile(ROOT / "scripts/deploy/rk3588/setup-python.sh", repo / "scripts/deploy/rk3588/setup-python.sh")
    (repo / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="1"\n')
    (repo / "uv.lock").write_text("fixture lock\n")
    (repo / "systemd/disabled.timer").write_text("new timer\n")
    (repo / "systemd/user/session.service").write_text("new session unit\n")
    (repo / ".venv/bin/python").write_text(
        '#!/usr/bin/env bash\nexec ' + shlex.quote(sys.executable.replace('\\', '/')) + ' "$@"\n',
        encoding='utf-8', newline='\n',
    )
    (tmp_path / "head").write_text(OLD + "\n")
    (tmp_path / "active").write_text("1\n")
    (tmp_path / "units").mkdir()
    (tmp_path / "units/disabled.timer").write_text("previous timer\n")
    (tmp_path / "recovery").mkdir()
    tools = tmp_path / "bin"
    tools.mkdir()
    for name in ("git", "uv", "sudo", "systemctl", "curl", "flock", "id"):
        (tools / name).write_text(FAKES, encoding="utf-8", newline="\n")
    env = os.environ.copy()
    env.update(CASE=posix(tmp_path), MODE=mode, TMPDIR=posix(tmp_path / "recovery"), LIGHT_BELT_REPO=posix(repo),
               LIGHT_BELT_HOME=posix(tmp_path), LIGHT_BELT_UV=posix(tools / "uv"),
               LIGHT_BELT_SYSTEM_UNIT_DIR=posix(tmp_path / "units"),
               LIGHT_BELT_USER_UNIT_DIR=posix(tmp_path / "user-units"),
               LIGHT_BELT_UPDATE_LOG=posix(tmp_path / "update.log"),
               LIGHT_BELT_HEALTH_RETRIES="1", LIGHT_BELT_HEALTH_INTERVAL="0")
    command = f'export PATH="{posix(tools)}:$PATH"; chmod +x "{posix(tools)}"/* "{posix(repo)}/.venv/bin/python"; bash "{posix(repo)}/{entry}"'
    result = subprocess.run([BASH, "-c", command], env=env, capture_output=True, text=True, encoding="utf-8", timeout=25)
    events = (tmp_path / "events").read_text() if (tmp_path / "events").exists() else ""
    log = (tmp_path / "update.log").read_text() if (tmp_path / "update.log").exists() else ""
    return result, events, log


@pytest.mark.parametrize("mode", ["no-update", "offline", "dirty", "status-fail", "lock-held", "stale-lock", "wrong-uv"])
def test_preflight_does_not_mutate_service_or_environment(tmp_path, mode):
    result, events, _ = run_case(tmp_path, mode)
    assert result.returncode == (0 if mode in ("no-update", "offline") else 1), result.stderr
    assert "uv sync " not in events
    assert "systemctl stop " not in events
    assert "git merge " not in events
    assert (tmp_path / "head").read_text().strip() == OLD


def test_lock_only_update_syncs_stopped_host_and_preserves_disabled_units(tmp_path):
    result, events, log = run_case(tmp_path, "lock-only")
    assert result.returncode == 0, (result.stderr, log, events)
    assert events.index("systemctl stop ") < events.index("uv sync ") < events.index("systemctl start ")
    assert "--locked" in events and "--extra host" in events and "--no-dev" in events
    assert "systemctl enable " not in events and "restart disabled.timer" not in events
    assert (tmp_path / "units/disabled.timer").read_text() == "new timer\n"
    assert (tmp_path / "user-units/session.service").read_text() == "new session unit\n"


def test_incompatible_running_health_rejects_update_before_mutation(tmp_path):
    result, events, log = run_case(tmp_path, 'legacy-health')
    assert result.returncode == 1, (result.stderr, log)
    assert 'systemctl stop ' not in events
    assert 'git merge ' not in events
    assert 'uv sync ' not in events
    assert (tmp_path / 'head').read_text().strip() == OLD


@pytest.mark.parametrize("mode", ["sync-fail", "start-fail", "health-fail", "stale-new-lock", "unit-copy-fail", "reload-fail"])
def test_failure_restores_code_and_resynchronizes_old_lock_before_start(tmp_path, mode):
    result, events, log = run_case(tmp_path, mode)
    assert result.returncode == 1, (result.stderr, log, events)
    assert (tmp_path / "head").read_text().strip() == OLD
    rollback = events.index("git reset --hard ")
    assert "uv sync " in events[rollback:]
    assert events.rindex("uv sync ") < events.rindex("systemctl start ")
    assert (tmp_path / "active").read_text().strip() == "1"
    assert (tmp_path / "units/disabled.timer").read_text() == "previous timer\n"
    assert not (tmp_path / "user-units/session.service").exists()


@pytest.mark.parametrize("mode", ["rollback-env-fail", "rollback-code-fail"])
def test_failed_rollback_keeps_host_stopped(tmp_path, mode):
    result, events, log = run_case(tmp_path, mode)
    assert result.returncode == 2, (result.stderr, log, events)
    assert (tmp_path / "active").read_text().strip() == "0"
    assert "ROLLBACK FAILED" in log
    assert "Recovery state retained" in log
    snapshots = list((tmp_path / "recovery").glob("tmp.*"))
    assert len(snapshots) == 1
    assert (snapshots[0] / "system/disabled.timer").read_text() == "previous timer\n"


def test_stop_failure_never_merges_or_syncs(tmp_path):
    result, events, log = run_case(tmp_path, "stop-fail")
    assert result.returncode == 1, (result.stderr, log)
    assert "git merge --ff-only" not in events and "uv sync " not in events
    assert (tmp_path / "head").read_text().strip() == OLD


def test_unavailable_user_manager_defers_reload_without_enabling_units(tmp_path):
    result, events, log = run_case(tmp_path, "user-manager-absent")
    assert result.returncode == 0, (result.stderr, log)
    assert "unit reload deferred" in log
    assert "systemctl enable " not in events


def test_installer_rejects_running_host_before_environment_operations(tmp_path):
    # The required target-user check is retained: choose this fixture's current
    # OS account through the documented configuration boundary.
    result, events, _ = run_case(tmp_path, "install-active", entry="scripts/deploy/rk3588/setup-python.sh")
    assert result.returncode == 1
    assert "Host 正在运行" in result.stderr
    assert "uv sync " not in events and "uv python install " not in events


def test_installer_rejects_updater_lock_before_service_or_environment_checks(tmp_path):
    result, events, _ = run_case(tmp_path, "lock-held", entry="scripts/deploy/rk3588/setup-python.sh")
    assert result.returncode == 1
    assert "uv sync " not in events and "uv python install " not in events
    assert "systemctl is-active " not in events

