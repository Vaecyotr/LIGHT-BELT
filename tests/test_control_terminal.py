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
