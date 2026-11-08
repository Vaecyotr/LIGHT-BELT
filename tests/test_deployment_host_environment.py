"""Persistent per-device credentials survive deployment and service migration."""

import importlib.util
from pathlib import Path

import pytest


def load_helper():
    path = Path("scripts/deploy/rk3588/host_environment.py")
    spec = importlib.util.spec_from_file_location("host_environment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_credentials_are_generated_once_and_are_valid(tmp_path):
    helper = load_helper()
    path = tmp_path / "config" / "host.env"
    values = helper.ensure_environment(path)
    original = path.read_bytes()
    assert len(values["LIGHT_BELT_JWT_SECRET"]) >= 32
    assert values["LIGHT_BELT_PAIRING_CODE"] != "123456"
    assert helper.ensure_environment(path) == values
    assert path.read_bytes() == original


def test_existing_legacy_credentials_and_custom_fields_are_preserved(tmp_path):
    helper = load_helper()
    legacy = tmp_path / "legacy.env"
    legacy.write_text('LIGHT_BELT_JWT_SECRET=' + 'a' * 40 + '\n'
                      'LIGHT_BELT_PAIRING_CODE=839201\nCUSTOM_SETTING="keep this"\n', encoding="utf-8")
    path = tmp_path / "user" / "host.env"
    original = legacy.read_bytes()
    values = helper.ensure_environment(path, legacy)
    assert values["LIGHT_BELT_PAIRING_CODE"] == "839201"
    assert values["CUSTOM_SETTING"] == "keep this"
    assert path.read_bytes() == legacy.read_bytes() == original


def test_invalid_existing_credentials_are_reported_without_rotation(tmp_path):
    helper = load_helper()
    path = tmp_path / "host.env"
    path.write_text("LIGHT_BELT_JWT_SECRET=short\nLIGHT_BELT_PAIRING_CODE=123456\n")
    original = path.read_bytes()
    with pytest.raises(ValueError):
        helper.ensure_environment(path)
    assert path.read_bytes() == original


def test_parent_symlink_is_rejected_before_privileged_write(tmp_path, monkeypatch):
    helper = load_helper()
    path = tmp_path / "config" / "host.env"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda candidate: candidate == path.parent or original(candidate))
    with pytest.raises(ValueError, match="symlink"):
        helper.ensure_environment(path)
    assert not path.exists()
