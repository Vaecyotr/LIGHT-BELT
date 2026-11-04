"""The updater consumes the actual public status envelope."""
import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient

from host_services.main import app

ROOT = Path(__file__).resolve().parents[1]


def test_status_exposes_frozen_running_identity(monkeypatch):
    with TestClient(app) as client:
        before = client.get('/api/v1/status').json()['data']
        assert len(before['commit']) == 40
        assert isinstance(before['ready'], bool)
        assert isinstance(before['source_clean'], bool)
        monkeypatch.setattr(subprocess, 'check_output', lambda *args, **kwargs: b'b' * 40)
        after = client.get('/api/v1/status').json()['data']
        assert after['commit'] == before['commit']


def test_real_adapter_initialization_failure_blocks_readiness(monkeypatch):
    from host_services import engine_adapter
    monkeypatch.setattr(engine_adapter, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(engine_adapter, '_real_adapter', None)
    with TestClient(app) as client:
        data = client.get('/api/v1/status').json()['data']
        assert data['ready'] is False


def test_status_identity_is_captured_from_a_clean_checkout(tmp_path):
    from host_services.runtime_health import capture_identity
    subprocess.run(['git', 'init', str(tmp_path)], check=True, capture_output=True)
    (tmp_path / 'source.txt').write_text('before', encoding='utf-8')
    subprocess.run(['git', '-C', str(tmp_path), 'add', 'source.txt'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                    'commit', '-m', 'fixture'], check=True, capture_output=True)
    identity = capture_identity(tmp_path)
    assert identity['source_clean'] is True
    (tmp_path / 'source.txt').write_text('after', encoding='utf-8')
    assert identity['source_clean'] is True
    assert capture_identity(tmp_path)['source_clean'] is False


def test_updater_parser_accepts_real_status_shape_and_rejects_unready_or_wrong_instance():
    source = (ROOT / 'scripts/maintenance/update.sh').read_text(encoding='utf-8')
    parser = source.split("<<'PY_HEALTH'\n", 1)[1].split('\nPY_HEALTH', 1)[0]
    with TestClient(app) as client:
        payload = client.get('/api/v1/status').json()
    expected = payload['data']['commit']
    payload['data'].update(adapter='real', ready=True, source_clean=True)

    def check(value, want=expected):
        return subprocess.run([sys.executable, '-c', parser, want], input=json.dumps(value),
                              text=True, capture_output=True).returncode

    assert check(payload) == 0
    assert check(payload, 'b' * 40 if expected != 'b' * 40 else 'a' * 40) != 0
    for field, value in [('ready', False), ('source_clean', False), ('adapter', 'mock')]:
        broken = json.loads(json.dumps(payload))
        broken['data'][field] = value
        assert check(broken) != 0
    assert check({'commit': expected}) != 0
    assert check({'ok': False, 'data': payload['data']}) != 0
