from fastapi.testclient import TestClient

from host_services.control_terminal import ControlTerminal
from host_services.main import app


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


def test_phone_gate_preserves_program_mute_and_volume_when_user_changes_them(tmp_path, monkeypatch):
    from host_services import engine_adapter as host
    from host_services.control_terminal import ControlPreferences

    class Player:
        def set_volume(self, value):
            self.volume = value

        def set_mute(self, value):
            self.muted = value

        def _command(self, command):
            assert command == ["get_property", "mute"]
            return {"data":self.muted}

    mpv = Player()
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_mpv", mpv)
    monkeypatch.setattr(host, "_route_gate", False)
    monkeypatch.setattr(host, "_state", dict(host._state, muted=False, playback_state="playing"))
    monkeypatch.setattr(host, "_real_adapter", None)
    host.gate_program(True)
    assert mpv.muted and not host.get_audio()["muted"]
    assert host.audio_set(.35, True, 0)[1] is None
    host.gate_program(False)
    assert mpv.muted and mpv.volume == .35
    host.gate_program(True)
    assert host.audio_set(None, False, 0)[1] is None
    assert mpv.muted
    host.gate_program(False)
    assert not mpv.muted and host._state["playback_state"] == "playing"
    saved = ControlPreferences(tmp_path).data
    assert saved["volume"] == .35 and not saved["muted"]


def test_separate_cabins_do_not_share_screen_authority_or_lighting_intent(tmp_path, monkeypatch):
    url = "https://local-cabin.example"
    monkeypatch.setenv("LIGHT_BELT_CONTROL_ORIGIN", url)
    monkeypatch.setattr("host_services.engine_adapter.ENGINE_ADAPTER", "mock")
    for cabin in ("first", "second", "first"):
        directory = tmp_path / cabin
        monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(directory))
        with TestClient(app, base_url=url, headers={"Origin": url}) as client:
            if cabin == "first" and (directory / "terminal.sqlite").exists():
                client.cookies.set("__Host-light-belt-control", first_cookie)
                assert client.get("/control/state").json()["data"]["lighting"]["intent"] == "off"
                continue
            if cabin == "second":
                client.cookies.set("__Host-light-belt-control", first_cookie)
                assert client.get("/control/state").status_code == 401
                client.cookies.clear()
            code = ControlTerminal(directory).issue_code()
            assert client.post("/control/enroll", json={"code":code}).status_code == 200
            snapshot = client.get("/control/state").json()["data"]
            assert snapshot["lighting"]["intent"] == "follow" and snapshot["analysis"]["mode"] == "auto"
            if cabin == "first":
                first_cookie = client.cookies.get("__Host-light-belt-control")
                assert client.put("/control/lighting", json={"intent":"off"}).status_code == 200
