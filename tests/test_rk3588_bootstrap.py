"""Run deployment orchestration with isolated system commands and modules."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_update_transaction import BASH, posix


STAGES = ["preflight.sh", "setup-python.sh", "setup-update-policy.sh", "setup-system.sh",
          "setup-bluetooth.sh", "setup-kiosk.sh", "setup-runtime.sh", "install-services.sh",
          "verify-install.sh"]


def run_bootstrap(tmp_path, *arguments, fail="", active=False, legacy=False):
    if BASH is None:
        pytest.fail("Deployment tests require runnable Git Bash")
    root = tmp_path / "LIGHT-BELT"
    deploy = root / "scripts/deploy/rk3588"
    (deploy / "lib").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").touch()
    source = Path("scripts/deploy/rk3588")
    shutil.copy2(source / "bootstrap.sh", deploy / "bootstrap.sh")
    for path in (source / "lib").glob("*.sh"):
        shutil.copy2(path, deploy / "lib" / path.name)
    for name in STAGES:
        (deploy / name).write_text('''#!/usr/bin/env bash
name="$(basename "$0")"
printf 'stage %s %s\\n' "$name" "$*" >> "$CASE/events"
[[ "$name" != "$FAIL_STAGE" || "${1:-}" == --check ]] || exit 9
if [[ "$name" == install-services.sh ]]; then
    systemctl --user enable light-belt-host.service
    systemctl --user start light-belt-host.service
    systemctl disable light-belt-host.service
fi
''', encoding="utf-8", newline="\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    fake = '''#!/usr/bin/env bash
name="$(basename "$0")"
printf 'tool %s %s\\n' "$name" "$*" >> "$CASE/events"
case "$name" in
id) case "$1" in -un) echo pi;; *) echo 1000;; esac;;
sudo) [[ "$1" != -v ]] || exit 0; exec "$@";;
systemctl)
 scope=system
 if [[ "${1:-}" == --user ]]; then scope=user; shift; fi
 case "$1" in
 is-active) [[ "${*: -1}" == light-belt-host.service && "$(cat "$CASE/active-$scope")" == 1 ]];;
 is-enabled) [[ "${*: -1}" == light-belt-host.service && "$(cat "$CASE/enabled-$scope")" == 1 ]];;
 cat) [[ "$scope" == system && "$LEGACY" == 1 ]];;
 start|restart) echo 1 > "$CASE/active-$scope";;
 stop) echo 0 > "$CASE/active-$scope";;
 enable) if [[ "${*: -1}" == light-belt-host.service ]]; then echo 1 > "$CASE/enabled-$scope"; fi;;
 disable) if [[ "${*: -1}" == light-belt-host.service ]]; then echo 0 > "$CASE/enabled-$scope"; fi;;
 esac;;
esac
'''
    for name in ["id", "sudo", "systemctl"]:
        path = tools / name
        path.write_text(fake, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    for scope, value in [("user", active), ("system", legacy)]:
        (tmp_path / f"active-{scope}").write_text("1" if value else "0")
        (tmp_path / f"enabled-{scope}").write_text("1" if value else "0")
    env = {**os.environ, "CASE": posix(tmp_path), "FAIL_STAGE": fail,
           "LIGHT_BELT_HOME": posix(tmp_path), "LIGHT_BELT_REPO": posix(root),
           "LEGACY": "1" if legacy else "0"}
    command = f'export PATH="{posix(tools)}:$PATH"; bash "{posix(deploy / "bootstrap.sh")}" ' + " ".join(arguments)
    result = subprocess.run([BASH, "-c", command], env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=15)
    events = (tmp_path / "events").read_text(encoding="utf-8")
    return result, events, (tmp_path / "active-user").read_text().strip()


def test_default_deployment_runs_policy_before_packages_and_skips_kiosk(tmp_path):
    result, events, _ = run_bootstrap(tmp_path)
    assert result.returncode == 0, result.stderr
    stages = [line for line in events.splitlines() if line.startswith("stage ")]
    assert stages[:4] == ["stage preflight.sh ", "stage setup-python.sh --check",
                          "stage setup-update-policy.sh ", "stage setup-system.sh "]
    assert not any("setup-kiosk.sh" in line for line in stages)
    assert stages.index("stage setup-bluetooth.sh ") < stages.index("stage install-services.sh ")
    assert stages[-1] == "stage verify-install.sh "


def test_explicit_kiosk_is_independent_of_mandatory_update_policy(tmp_path):
    result, events, _ = run_bootstrap(tmp_path, "--configure-kiosk")
    assert result.returncode == 0, result.stderr
    assert events.count("stage setup-update-policy.sh ") == 1
    assert events.count("stage setup-kiosk.sh ") == 1


def test_failure_stops_deployment_and_restores_previously_running_host(tmp_path):
    result, events, active = run_bootstrap(tmp_path, fail="setup-python.sh", active=True)
    assert result.returncode != 0
    assert "stage setup-bluetooth.sh " not in events
    assert "tool systemctl --user stop light-belt-host.service" in events
    assert "tool systemctl --user start light-belt-host.service" in events
    assert active == "1"


def test_policy_failure_prevents_package_and_environment_changes(tmp_path):
    result, events, _ = run_bootstrap(tmp_path, fail="setup-update-policy.sh")
    assert result.returncode != 0
    assert "stage setup-system.sh " not in events
    assert "stage setup-python.sh \n" not in events


def test_failed_migration_restores_only_the_previous_boot_service(tmp_path):
    result, events, active = run_bootstrap(tmp_path, fail="verify-install.sh", legacy=True)
    assert result.returncode != 0
    assert active == "0"
    assert (tmp_path / "enabled-user").read_text().strip() == "0"
    assert (tmp_path / "active-system").read_text().strip() == "1"
    assert (tmp_path / "enabled-system").read_text().strip() == "1"
    assert events.rindex("tool systemctl --user disable light-belt-host.service") < events.rindex("tool systemctl start light-belt-host.service")


@pytest.mark.parametrize("missing", ["", "mpv"])
def test_packages_install_only_missing_dependencies_without_system_upgrade(tmp_path, missing):
    if BASH is None:
        pytest.fail("Deployment tests require runnable Git Bash")
    source = Path("scripts/deploy/rk3588")
    deploy = tmp_path / "deploy"
    (deploy / "lib").mkdir(parents=True)
    shutil.copy2(source / "lib/common.sh", deploy / "lib/common.sh")
    (tmp_path / "repo/.git").mkdir(parents=True)
    (tmp_path / "repo/pyproject.toml").touch()
    conf = tmp_path / "modprobe.d"
    conf.mkdir()
    (conf / "regdom.conf").write_text("original regulatory settings\n")
    script = (source / "setup-system.sh").read_text(encoding="utf-8")
    (deploy / "setup-system.sh").write_text(script.replace("/etc/modprobe.d", posix(conf)),
                                           encoding="utf-8", newline="\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    commands = {
        "id": "echo pi",
        "sudo": '[[ "$1" != -v ]] || exit 0; while [[ "$1" == *=* ]]; do export "$1"; shift; done; exec "$@"',
        "systemctl": "exit 0",
        "iw": "exit 0",
        "dpkg-query": '[[ "${*: -1}" != "$MISSING" ]] || exit 1; printf "install ok installed"',
        "apt-get": 'printf "%s\\n" "$*" >> "$CASE/apt-events"',
    }
    for name, content in commands.items():
        path = tools / name
        path.write_text("#!/usr/bin/env bash\n" + content + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)
    env = {**os.environ, "CASE": posix(tmp_path), "MISSING": missing,
           "LIGHT_BELT_HOME": posix(tmp_path), "LIGHT_BELT_REPO": posix(tmp_path / "repo")}
    command = f'export PATH="{posix(tools)}:$PATH"; bash "{posix(deploy / "setup-system.sh")}"'
    result = subprocess.run([BASH, "-c", command], env=env, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    if missing:
        assert (tmp_path / "apt-events").read_text().splitlines() == [
            "update", "install --no-upgrade -y mpv"]
    else:
        assert not (tmp_path / "apt-events").exists()
    assert (conf / "regdom.conf.light-belt.bak").read_text() == "original regulatory settings\n"


@pytest.mark.parametrize("legacy", [False, True])
def test_service_installation_is_repeatable_and_keeps_manual_updates(tmp_path, legacy):
    if BASH is None:
        pytest.fail("Deployment tests require runnable Git Bash")
    source = Path("scripts/deploy/rk3588")
    root = tmp_path / "LIGHT-BELT"
    deploy = root / "scripts/deploy/rk3588"
    (deploy / "lib").mkdir(parents=True)
    (root / ".git").mkdir()
    (root / "pyproject.toml").touch()
    shutil.copytree("systemd", root / "systemd")
    for path in (source / "lib").glob("*.sh"):
        shutil.copy2(path, deploy / "lib" / path.name)
    system_units = tmp_path / "system-units"
    system_units.mkdir()
    (system_units / "bluetooth-auto-agent.service").write_text("original agent settings\n")
    if legacy:
        (system_units / "light-belt-host.service").write_text("original system Host\n")
    script = (source / "install-services.sh").read_text(encoding="utf-8")
    script = script.replace("/etc/systemd/system", posix(system_units))
    script = script.replace("/usr/bin/python3", "fake-python")
    (deploy / "install-services.sh").write_text(script, encoding="utf-8", newline="\n")
    tools = tmp_path / "bin"
    tools.mkdir()
    commands = {
        "id": 'if [[ "$1" == -un ]]; then echo pi; else echo 1000; fi',
        "sudo": '[[ "$1" != -v ]] || exit 0; exec "$@"',
        "loginctl": 'exit 0',
        "fake-python": 'exit 0',
        "systemctl": '''printf '%s\\n' "$*" >> "$CASE/events"
if [[ "$1" == --user ]]; then shift; fi
case "$1" in is-active) exit 1;; cat) [[ "$LEGACY" == 1 ]];; *) exit 0;; esac''',
    }
    for name, content in commands.items():
        path = tools / name
        path.write_text("#!/usr/bin/env bash\n" + content + "\n", encoding="utf-8", newline="\n")
        path.chmod(0o755)
    env = {**os.environ, "CASE": posix(tmp_path), "LIGHT_BELT_HOME": posix(tmp_path),
           "LIGHT_BELT_REPO": posix(root), "XDG_SESSION_TYPE": "", "WAYLAND_DISPLAY": "",
           "LEGACY": "1" if legacy else "0"}
    command = f'export PATH="{posix(tools)}:$PATH"; bash "{posix(deploy / "install-services.sh")}"'
    def install():
        return subprocess.run([BASH, "-c", command], env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=20)
    first = install()
    assert first.returncode == 0, first.stdout + first.stderr
    user_units = tmp_path / ".config/systemd/user"
    before = {p.name: p.read_bytes() for p in user_units.iterdir()}
    second = install()
    assert second.returncode == 0, second.stdout + second.stderr
    assert before == {p.name: p.read_bytes() for p in user_units.iterdir()}
    assert not list(user_units.glob("*.bak"))
    events = (tmp_path / "events").read_text()
    assert "disable --now lb-update.timer" in events
    assert "enable --now lb-update.timer" not in events
    assert "--user enable --now pulseaudio.socket" in events
    assert "--user enable light-belt-host.service" in events
    assert "--user restart light-belt-host.service" in events
    assert (tmp_path / ".config/autostart/light-belt-host-session.desktop").is_file()
    assert not (tmp_path / ".config/autostart/light-belt-kiosk-settings.desktop").exists()
    assert (system_units / "bluetooth-auto-agent.service.light-belt.bak").read_text() == "original agent settings\n"
    if legacy:
        assert "disable --now light-belt-host.service" in events
        assert (system_units / "light-belt-host.service").read_text() == "original system Host\n"
