from fastapi.testclient import TestClient

from host_services.control_terminal import ControlTerminal
from host_services.main import app


def test_managed_render_failure_does_not_undo_or_mask_a_successful_video_pause(
    tmp_path, monkeypatch
):
    from host_services import engine_adapter as host
    from host_services.control_terminal import ControlPreferences
    from types import SimpleNamespace
    from unittest.mock import Mock

    player = Mock()
    renderer = SimpleNamespace(
        _active_show={"show_yaml": "show.yaml", "media_path": "program.mp4"},
        seek_generation=0,
        sender=None,
        status={},
        configure=Mock(side_effect=BrokenPipeError("lost lighting sender")),
    )
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_real_adapter", renderer)
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


def test_screen_enrollment_scope_preferences_and_stale_restore(tmp_path, monkeypatch):
    url = "https://cabin.example"
    monkeypatch.setenv("LIGHT_BELT_CONTROL_ORIGIN", url)
    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr("host_services.engine_adapter.ENGINE_ADAPTER", "mock")
    with TestClient(app, base_url=url) as client:
        assert client.get("/control/state").status_code == 401

        assert client.get("/api/v1/state").status_code == 401
        code = ControlTerminal(tmp_path).issue_code()
        assert client.post("/control/enroll", json={"code": code}).status_code == 403
        client.headers.update({"Origin": url})
        assert client.post("/control/enroll", json={"code": code}).status_code == 200
        snapshot = client.get("/control/state").json()["data"]
        assert snapshot["lighting"]["intent"] == "follow"
        token = snapshot["lighting"]["intent_token"]
        assert (
            client.put("/control/analysis", json={"mode": "device"}).json()["data"][
                "analysis"
            ]["mode"]
            == "auto"
        )
        assert (
            client.put("/control/lighting", json={"intent": "off"}).json()["data"][
                "lighting"
            ]["intent"]
            == "off"
        )
        assert (
            client.put(
                "/control/lighting", json={"intent": "follow", "if_intent": token}
            ).status_code
            == 409
        )
        assert client.post("/control/bluetooth/scan").status_code == 503
        assert client.get("/api/v1/state").status_code == 200
        ControlTerminal(tmp_path).revoke()
        assert client.get("/control/state").status_code == 401


def test_persisted_off_is_reasserted_when_host_starts_without_a_renderer(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from host_services import engine_adapter as host, wled_brightness
    from host_services.control_terminal import ControlPreferences

    ControlPreferences(tmp_path).set_intent("off", None)
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(
        host,
        "_real_adapter",
        SimpleNamespace(
            sender=None,
            _active_show=None,
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


def test_phone_gate_preserves_program_mute_and_volume_when_user_changes_them(
    tmp_path, monkeypatch
):
    from host_services import engine_adapter as host
    from host_services.control_terminal import ControlPreferences

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


def test_separate_cabins_do_not_share_screen_authority_or_lighting_intent(
    tmp_path, monkeypatch
):
    url = "https://local-cabin.example"
    monkeypatch.setenv("LIGHT_BELT_CONTROL_ORIGIN", url)
    monkeypatch.setattr("host_services.engine_adapter.ENGINE_ADAPTER", "mock")
    first_cookie = None
    for cabin in ("first", "second", "first"):
        directory = tmp_path / cabin
        monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(directory))
        with TestClient(app, base_url=url, headers={"Origin": url}) as client:
            if cabin == "first" and (directory / "terminal.sqlite").exists():
                assert first_cookie is not None
                client.cookies.set("__Host-light-belt-control", first_cookie)
                assert (
                    client.get("/control/state").json()["data"]["lighting"]["intent"]
                    == "off"
                )
                continue
            if cabin == "second":
                assert first_cookie is not None
                client.cookies.set("__Host-light-belt-control", first_cookie)
                assert client.get("/control/state").status_code == 401
                client.cookies.clear()
            code = ControlTerminal(directory).issue_code()
            assert (
                client.post("/control/enroll", json={"code": code}).status_code == 200
            )
            snapshot = client.get("/control/state").json()["data"]
            assert (
                snapshot["lighting"]["intent"] == "follow"
                and snapshot["analysis"]["mode"] == "auto"
            )
            if cabin == "first":
                first_cookie = client.cookies.get("__Host-light-belt-control")
                assert (
                    client.put("/control/lighting", json={"intent": "off"}).status_code
                    == 200
                )
