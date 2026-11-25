import json

import pytest

from host_services.control_terminal import (
    ControlTerminal,
    ControlPreferences,
    ControlConflict,
)


def test_authorization_survives_restart_and_replacement_revokes_old_screen(tmp_path):
    terminal = ControlTerminal(tmp_path)
    code = terminal.issue_code()
    session = terminal.enroll(code)
    assert ControlTerminal(tmp_path).authorized(session)
    with pytest.raises(ValueError):
        terminal.enroll(code)
    replacement = terminal.enroll(terminal.issue_code())
    assert not terminal.authorized(session)
    assert terminal.authorized(replacement)


def test_corrupt_enrollment_database_rejects_sessions_and_clears_generation(tmp_path):
    terminal = ControlTerminal(tmp_path)
    (tmp_path / "terminal.sqlite").write_bytes(b"not a sqlite database")

    assert terminal.authorized("stale-session") is False
    assert terminal.generation() is None
    assert terminal.storage_error


def test_preferences_normalize_device_and_reject_stale_restore(tmp_path):
    prefs = ControlPreferences(tmp_path)
    old = prefs.token
    prefs.set_mode("device")
    assert prefs.data["mode"] == "auto"
    prefs.set_mode("mic")
    prefs.set_intent("off", old)
    with pytest.raises(ControlConflict):
        prefs.set_intent("follow", old)
    restored = ControlPreferences(tmp_path)
    assert restored.data["intent"] == "off"
    assert restored.data["mode"] == "mic"
    assert restored.token != prefs.token


def test_corrupt_preferences_recover_safe_state_without_blocking_host(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text('{"volume":0.7,"intent":', encoding="utf-8")

    prefs = ControlPreferences(tmp_path)

    assert prefs.recovery_error
    assert prefs.data["intent"] == "off"
    assert prefs.data["muted"] is True
    assert prefs.data["volume"] == 0.5
    prefs.save()
    assert ControlPreferences(tmp_path).data["intent"] == "off"


def test_invalid_unrelated_field_preserves_known_intent_and_mute(tmp_path):
    (tmp_path / "preferences.json").write_text(
        '{"volume":0.8,"brightness":1.3,"intent":"follow","muted":false}',
        encoding="utf-8",
    )

    prefs = ControlPreferences(tmp_path)

    assert prefs.recovery_error
    assert prefs.data["volume"] == 0.8
    assert prefs.data["brightness"] == 0.5
    assert prefs.data["intent"] == "follow"
    assert prefs.data["muted"] is False


def test_failed_save_keeps_applied_and_persisted_state_distinct(tmp_path, monkeypatch):
    prefs = ControlPreferences(tmp_path)
    import host_services.control_terminal as terminal_module

    def fail_replace(*args):
        raise OSError("read-only storage")

    monkeypatch.setattr(terminal_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="read-only storage"):
        prefs.save(volume=0.8)

    assert prefs.data["volume"] == 0.5
    assert prefs._unsaved is True
    assert prefs.persistence_error == "read-only storage"


def test_save_rejects_invalid_nested_manual_targets(tmp_path, monkeypatch):
    prefs = ControlPreferences(tmp_path)
    from host_services import engine_adapter

    monkeypatch.setattr(engine_adapter, "_valid_target_ids", frozenset({"strip-1"}))
    with pytest.raises(ValueError, match="Invalid stored target"):
        prefs.save(targets={"strip-1": ["not", "a", "target"]})
    assert prefs.data["targets"] == {}


@pytest.mark.parametrize("invalid", [{"effect_params": {"unknown": True}}, {"speed": 10**400}])
def test_restore_rejects_bad_effect_payload_for_matching_target_id(tmp_path, monkeypatch, invalid):
    from host_services import engine_adapter

    monkeypatch.setattr(engine_adapter, "_valid_target_ids", frozenset({"strip-1"}))
    target = {
        "target_id": "strip-1", "effect_type": "static", "color": [1, 1, 1],
        "speed": 1, "intensity": 1, "effect_params": {},
    }
    target.update(invalid)
    (tmp_path / "preferences.json").write_text(
        json.dumps({"intent": "manual", "targets": {"strip-1": target}}),
        encoding="utf-8",
    )
    prefs = ControlPreferences(tmp_path)
    assert prefs.data["intent"] == "off"
    assert prefs.recovery_error


def test_valid_manual_target_survives_restart(tmp_path, monkeypatch):
    from host_services import engine_adapter

    monkeypatch.setattr(engine_adapter, "_valid_target_ids", frozenset({"strip-1"}))
    target = {
        "target_id": "strip-1", "effect_type": "static", "color": [1, 1, 1],
        "speed": 1, "intensity": 1, "effect_params": {},
    }
    ControlPreferences(tmp_path).save(intent="manual", targets={"strip-1": target})
    restored = ControlPreferences(tmp_path)
    assert restored.data["intent"] == "manual"
    assert restored.data["targets"] == {"strip-1": target}


def test_restore_corrupt_manual_target_does_not_attempt_manual_output(tmp_path):
    (tmp_path / "preferences.json").write_text(
        '{"intent":"manual","muted":true,"targets":{"strip-1":{"effect_type":"static"}}}',
        encoding="utf-8",
    )
    prefs = ControlPreferences(tmp_path)
    assert prefs.data["intent"] == "off"
    assert prefs.data["muted"] is True
    assert prefs.recovery_error
    assert not prefs.saved
