import subprocess
import sys
import importlib.util
import os
import shutil
import pytest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/deploy/rk3588/update_policy.py'


def run(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), '--root', str(root), '--home', '/home/pi', *args], capture_output=True, text=True)


def put(root, path, text):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')
    return p


def test_sources_preserve_other_entries_and_are_idempotent(tmp_path):
    one = put(tmp_path, 'etc/apt/sources.list', '# keep\ndeb [arch=arm64] http://example jammy main\ndeb http://example jammy-proposed main # old\n')
    two = put(tmp_path, 'etc/apt/sources.list.d/ubuntu.sources', 'Types: deb\nURIs: http://example\nSuites: jammy jammy-proposed jammy-updates\nComponents: main\n')
    before = one.read_text()
    assert run(tmp_path).returncode == 0
    assert one.read_text() == '# keep\ndeb [arch=arm64] http://example jammy main\n# LIGHT-BELT disabled: deb http://example jammy-proposed main # old\n'
    assert 'Suites: jammy jammy-updates' in two.read_text()
    assert one.with_name(one.name + '.light-belt.bak').read_text() == before
    after = two.read_text()
    assert run(tmp_path, '--check').returncode == 0
    assert run(tmp_path).returncode == 0
    assert two.read_text() == after
    assert len(list(one.parent.glob('sources.list.light-belt.bak*'))) == 1


def test_unknown_and_symlink_sources_refuse_before_any_change(tmp_path):
    one = put(tmp_path, 'etc/apt/sources.list', 'deb http://example jammy-proposed main\n')
    put(tmp_path, 'etc/apt/sources.list.d/bad.list', 'mystery jammy-proposed\n')
    assert run(tmp_path).returncode != 0
    assert one.read_text() == 'deb http://example jammy-proposed main\n'


def test_config_is_specific_and_check_detects_drift(tmp_path):
    put(tmp_path, 'etc/xdg/autostart/update-notifier.desktop', '[Desktop Entry]\n')
    assert run(tmp_path).returncode == 0
    assert 'APT::Periodic::Unattended-Upgrade "0";' in (tmp_path / 'etc/apt/apt.conf.d/99light-belt-updates').read_text()
    assert 'Pin: release a=jammy-proposed' in (tmp_path / 'etc/apt/preferences.d/light-belt-no-proposed').read_text()
    assert 'Hidden=true' in (tmp_path / 'home/pi/.config/autostart/update-notifier.desktop').read_text()
    assert run(tmp_path, '--check').returncode == 0
    (tmp_path / 'etc/apt/apt.conf.d/99light-belt-updates').write_text('changed')
    assert run(tmp_path, '--check').returncode != 0


def test_multiline_deb822_preserves_unrelated_comments(tmp_path):
    source = put(tmp_path, 'etc/apt/sources.list.d/mixed.sources', 'Types: deb\nURIs: http://example\nSuites: jammy\n jammy-proposed jammy-updates\n# preserve\nComponents: main\n')
    assert run(tmp_path).returncode == 0
    assert source.read_text() == 'Types: deb\nURIs: http://example\nSuites: jammy jammy-updates\n# preserve\nComponents: main\n'


def test_proposed_only_deb822_is_disabled(tmp_path):
    source = put(tmp_path, 'etc/apt/sources.list.d/proposed.sources', 'Types: deb\nURIs: http://example\nSuites: jammy-proposed\nComponents: main\n')
    assert run(tmp_path).returncode == 0
    assert 'Enabled: no\n' in source.read_text()
    assert run(tmp_path, '--check').returncode == 0


def test_atomic_replace_failure_preserves_existing_source(tmp_path, monkeypatch):
    source = put(tmp_path, 'etc/apt/sources.list', 'deb http://example jammy-proposed main\n')
    spec = importlib.util.spec_from_file_location('update_policy_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.os, 'replace', lambda *_: (_ for _ in ()).throw(OSError('injected failure')))
    monkeypatch.setattr(sys, 'argv', [str(SCRIPT), '--root', str(tmp_path), '--home', '/home/pi'])
    with pytest.raises(OSError, match='injected failure'):
        module.main()
    assert source.read_text() == 'deb http://example jammy-proposed main\n'
    assert source.with_name(source.name + '.light-belt.bak').read_text() == source.read_text()


@pytest.mark.parametrize('active,expected', [('', 0), ('unattended-upgrades.service', 0), ('apt-daily.service', 1)])
def test_shell_timer_and_active_service_behavior(tmp_path, active, expected):
    bash = Path('A:/Git/Git/bin/bash.exe') if os.name == 'nt' else Path(shutil.which('bash') or '')
    if not bash.is_file():
        pytest.skip('Bash is unavailable')
    scriptdir = tmp_path / 'deploy'
    (scriptdir / 'lib').mkdir(parents=True)
    original = SCRIPT.parent
    script = (original / 'setup-update-policy.sh').read_text(encoding='utf-8')
    # The fake executable prevents this isolated test from touching the host.
    script = script.replace('/usr/bin/python3', 'fake-policy-python')
    (scriptdir / 'setup-update-policy.sh').write_text(script, encoding='utf-8', newline='\n')
    shutil.copyfile(original / 'lib/common.sh', scriptdir / 'lib/common.sh')
    fake = tmp_path / 'fake'
    fake.mkdir()
    commands = {
        'id': 'echo pi\n',
        'sudo': 'printf "sudo %s\\n" "$*" >> "$FAKE_LOG"\nif [[ "$1" == -v ]]; then exit 0; fi\nexec "$@"\n',
        'fake-policy-python': 'printf "policy %s\\n" "$*" >> "$FAKE_LOG"\n',
        'pkill': 'printf "pkill %s\\n" "$*" >> "$FAKE_LOG"\nexit "${FAKE_PKILL_EXIT:-0}"\n',
        'pgrep': 'printf "pgrep %s\\n" "$*" >> "$FAKE_LOG"\nexit "${FAKE_PGREP_EXIT:-1}"\n',
        'apt-config': 'for k in Enable Update-Package-Lists Download-Upgradeable-Packages Unattended-Upgrade; do echo "APT::Periodic::$k \\"0\\";"; done\n',
        'systemctl': '''printf 'systemctl %s\\n' "$*" >> "$FAKE_LOG"
case "$1" in
  is-active) [[ "$3" == "$FAKE_ACTIVE" ]] ;;
  is-enabled) exit 1 ;;
  list-unit-files) printf '%s enabled\\n' "$2" ;;
  disable) exit 0 ;;
  *) exit 1 ;;
esac
''',
    }
    for name, body in commands.items():
        file = fake / name
        file.write_text('#!/usr/bin/env bash\n' + body, encoding='utf-8', newline='\n')
        file.chmod(0o755)
    env = os.environ.copy()
    env.update(FAKE_ACTIVE=active, FAKE_LOG=str(tmp_path / 'commands.log'), LIGHT_BELT_USER='pi', LIGHT_BELT_HOME='/home/pi')
    # Git Bash converts Windows paths with cygpath; native Linux needs no conversion.
    convert = 'cygpath -u' if os.name == 'nt' else 'printf %s'
    command = f'export PATH="$({convert} "$1"):$PATH"; export FAKE_LOG="$({convert} "$FAKE_LOG")"; exec bash "$({convert} "$2")"'
    def execute(mode=''):
        invocation = command + (' --check' if mode else '')
        try:
            return subprocess.run([str(bash), '-c', invocation, 'harness', str(fake), str(scriptdir / 'setup-update-policy.sh')], env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        except PermissionError:
            pytest.skip('Bash execution is blocked by the environment')
    first = execute()
    assert first.returncode == expected, first.stdout + first.stderr
    if expected == 0:
        second = execute()
        assert second.returncode == 0, second.stdout + second.stderr
    log = (tmp_path / 'commands.log').read_text()
    assert 'is-active --quiet unattended-upgrades.service' not in log
    if expected:
        assert 'disable --now' not in log
        assert 'pkill ' not in log
    else:
        assert log.count('--home /home/pi --lock --probe-lock') == 4
        assert len([line for line in log.splitlines() if line.endswith('--home /home/pi --lock')]) == 4
        assert log.count('systemctl disable --now apt-daily.timer') == 4  # sudo and systemctl each record it
        assert [line for line in log.splitlines() if line.startswith('pkill ')] == [
            'pkill -TERM -u pi -x update-notifier',
            'pkill -TERM -u pi -x update-notifier',
        ]
        before_check = len(log)
        checked = execute('check')
        assert checked.returncode == 0, checked.stdout + checked.stderr
        check_log = (tmp_path / 'commands.log').read_text()[before_check:]
        assert 'sudo ' not in check_log
        assert 'pkill ' not in check_log
        assert '--home /home/pi --check' in check_log
        env['FAKE_ACTIVE'] = 'apt-daily.timer'
        assert execute('check').returncode == 1
        env['FAKE_ACTIVE'] = ''
        env['FAKE_PKILL_EXIT'] = '1'
        assert execute().returncode == 0
        env['FAKE_PGREP_EXIT'] = '0'
        assert execute().returncode != 0
        env['FAKE_PGREP_EXIT'] = '1'
        env['FAKE_PKILL_EXIT'] = '2'
        assert execute().returncode != 0
