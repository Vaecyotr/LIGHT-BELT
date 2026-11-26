from fastapi.testclient import TestClient
import pytest

from host_services.main import app


def test_production_idle_confirms_black_before_any_sender(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from host_services import engine_adapter as host
    from host_services.control_preferences import ControlPreferences

    adapter = SimpleNamespace(sender=None, seek_generation=0, configure=Mock())
    write = Mock()
    for name, value in {
        "ENGINE_ADAPTER": "real", "_preferences": ControlPreferences(tmp_path),
        "_real_adapter": adapter, "_session_show": None, "_audio_system": None,
        "_devices": [{"host": "192.0.2.2", "device_type": host.WLED_DEVICE_TYPE}],
        "_confirmed_off_hosts": None, "_power_error": None, "_off_request_submitted": False,
        "_write_wled": write,
    }.items():
        monkeypatch.setattr(host, name, value)
    host._reconcile_lighting()
    host._reconcile_lighting()
    write.assert_called_once_with(None)
    assert all(call.args[0]["role"] == "none" for call in adapter.configure.call_args_list)


def test_managed_render_failure_does_not_undo_or_mask_a_successful_video_pause(
    tmp_path, monkeypatch
):
    from host_services import engine_adapter as host
    from host_services.control_preferences import ControlPreferences
    from types import SimpleNamespace
    from unittest.mock import Mock

    player = Mock()
    renderer = SimpleNamespace(
        seek_generation=0,
        sender=None,
        status={},
        configure=Mock(side_effect=BrokenPipeError("lost lighting sender")),
    )
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_real_adapter", renderer)
    monkeypatch.setattr(host, "_session_show", {"show_yaml": "show.yaml", "media_path": "program.mp4"})
    monkeypatch.setattr(host, "_active_mpv", lambda: player)
    monkeypatch.setattr(host, "_state", dict(host._state, playback_state="playing"))
    monkeypatch.setattr(host, "_power_error", None)
    monkeypatch.setattr(host, "_lighting_error", None)
    result, error = host.playback_pause()
    assert error is None and result["playback_state"] == "paused"
    player.pause.assert_called_once()
    player.stop.assert_not_called()
    assert host.control_snapshot()["lighting"]["phase"] == "fault"
    assert "lost lighting sender" in host.control_snapshot()["lighting"]["reason"]
    renderer.configure.side_effect = None
    host._reconcile_lighting()
    assert host.control_snapshot()["lighting"]["phase"] != "fault"


def test_persisted_off_is_reasserted_when_host_starts_without_a_renderer(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from host_services import engine_adapter as host, wled_brightness
    from host_services.control_preferences import ControlPreferences

    ControlPreferences(tmp_path).set_intent("off", None)
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(
        host,
        "_real_adapter",
        SimpleNamespace(
            sender=None,
            seek_generation=0,
            configure=Mock(),
        ),
    )
    monkeypatch.setattr(
        host, "_devices", [{"host": "192.0.2.2", "device_type": host.WLED_DEVICE_TYPE}]
    )
    monkeypatch.setattr(host, "_power_error", None)
    monkeypatch.setattr(host, "_lighting_error", None)
    write = Mock(side_effect=[RuntimeError("unreachable light"), None])
    monkeypatch.setattr(host, "_confirmed_off_hosts", None)
    monkeypatch.setattr(wled_brightness, "apply_managed", write)
    host._reconcile_lighting()
    assert write.call_count == 1 and host._power_error == "unreachable light"
    host._reconcile_lighting()
    assert write.call_count == 2 and host._power_error is None
    host._reconcile_lighting()
    assert write.call_count == 2


def test_same_wled_address_is_rechecked_after_reboot(tmp_path, monkeypatch):
    import io
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    from host_services import engine_adapter as host
    from host_services.control_preferences import ControlPreferences

    prefs = ControlPreferences(tmp_path)
    prefs.set_intent("off", None)
    adapter = SimpleNamespace(
        seek_generation=0, sender=None, configure=Mock(),
        status={"role_phase": "idle", "effective_role": "none"},
    )
    device = {"host": "192.0.2.1", "device_type": host.WLED_DEVICE_TYPE}
    for name, value in {
        "_preferences": prefs, "_real_adapter": adapter, "_audio_system": None,
        "_devices": [device], "_confirmed_off_hosts": None,
        "_off_request_submitted": False,
        "_power_error": None, "_lighting_error": None,
    }.items():
        monkeypatch.setattr(host, name, value)
    state = {"on": True, "uptime": 200, "live": True}
    writes = []

    def fetch(request, **kwargs):
        if not isinstance(request, str):
            payload = json.loads(request.data)
            writes.append(payload)
            state.update(payload)
            return io.BytesIO(b'{"success":true}')
        return io.BytesIO(json.dumps({
            "on": state["on"], "state": {"on": state["on"]},
            "info": {"uptime": state["uptime"], "live": state["live"]},
        }).encode())

    monkeypatch.setattr(host.urllib.request, "urlopen", fetch)
    host._reconcile_lighting()
    lighting = host.control_snapshot()["lighting"]
    assert lighting["off_submitted"] is True
    assert lighting["off_status"] == "unknown"
    state["live"] = False
    host._probe_devices()
    host._reconcile_lighting()
    assert host.control_snapshot()["lighting"]["off_status"] == "confirmed"
    assert writes == [{"on": False, "v": False}]
    state.update(on=True, uptime=1)
    host._probe_devices()
    host._reconcile_lighting()
    assert state["on"] is False
    assert writes == [{"on": False, "v": False}, {"on": False, "v": False}]


@pytest.mark.parametrize(("scale", "playing"), [(0.25, True), (0.25, False), (0.0, True)])
def test_restore_reapplies_brightness_saved_while_off_before_starting_ddp(
    tmp_path, monkeypatch, scale, playing
):
    import io
    import json
    from types import SimpleNamespace
    from unittest.mock import Mock
    from host_services import engine_adapter as host
    from host_services.control_preferences import ControlPreferences

    prefs = ControlPreferences(tmp_path)
    prefs.set_intent("off", None)
    device = {"host": "192.0.2.1", "device_type": host.WLED_DEVICE_TYPE}
    player = Mock()
    calls = []
    renderer = SimpleNamespace(
        seek_generation=0, sender=None,
        configure=lambda spec, **kwargs: calls.append(
            ("configure", spec["role"], spec.get("brightness_zero", False))
        ),
    )
    for name, value in {
        "_preferences": prefs, "_real_adapter": renderer, "_audio_system": None,
        "_session_show": {"show_yaml": "show.yaml", "media_path": "program.mp4"},
        "_devices": [device], "_confirmed_off_hosts": frozenset({device["host"]}),
        "_power_error": None, "_mpv": player, "_route_gate": False,
        "_state": dict(host._state, playback_state="playing" if playing else "stopped",
                       position_ms=3200, volume=0.2),
    }.items():
        monkeypatch.setattr(host, name, value)
    state = {"on": False, "bri": 127}

    def fetch(request, **kwargs):
        if not isinstance(request, str):
            payload = json.loads(request.data)
            state.update(payload)
            calls.append(("post", payload))
        return io.BytesIO(json.dumps({
            **state, "state": state, "info": {"live": False}
        }).encode())

    monkeypatch.setattr(host.urllib.request, "urlopen", fetch)
    monkeypatch.setattr(host, "ENGINE_ADAPTER", "real")
    assert host.brightness_scale_set(scale, 0)[1] is None
    assert calls == [("configure", "none", scale == 0)]
    calls.clear()
    host.control_intent("follow", prefs.token)
    if not playing:
        assert calls == [("configure", "none", False)]
        calls.clear()
        host._state["playback_state"] = "playing"
        host._reconcile_lighting()
    expected = [("post", {"on": False, "bri": 64, "v": False})] if scale else []
    assert calls == expected + [("configure", "show", scale == 0)]
    assert prefs.data["brightness"] == scale
    assert host._state["position_ms"] == 3200 and host._state["volume"] == 0.2
    assert prefs.data["mode"] == "auto"
    assert not player.mock_calls


def test_phone_gate_preserves_program_mute_and_volume_when_user_changes_them(
    tmp_path, monkeypatch
):
    from host_services import engine_adapter as host
    from host_services.control_preferences import ControlPreferences

    class Player:
        def set_volume(self, value):
            self.volume = value

        def set_mute(self, value):
            self.muted = value

        def _command(self, command):
            assert command == ["get_property", "mute"]
            return {"data": self.muted}

    mpv = Player()
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_mpv", mpv)
    monkeypatch.setattr(host, "_route_gate", False)
    monkeypatch.setattr(
        host, "_state", dict(host._state, muted=False, playback_state="playing")
    )
    monkeypatch.setattr(host, "_real_adapter", None)
    host.gate_program(True)
    assert mpv.muted and not host.get_audio()["muted"]
    assert host.audio_set(0.35, True, 0)[1] is None
    host.gate_program(False)
    assert mpv.muted and mpv.volume == 0.35
    host.gate_program(True)
    assert host.audio_set(None, False, 0)[1] is None
    assert mpv.muted
    host.gate_program(False)
    assert not mpv.muted and host._state["playback_state"] == "playing"
    saved = ControlPreferences(tmp_path).data
    assert saved["volume"] == 0.35 and not saved["muted"]
