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
