"""Formal HTTP regression for anonymous Host Bluetooth controls."""

from fastapi.testclient import TestClient

from host_services import engine_adapter
from host_services.bluetooth import AudioSystem, BackendUnavailable
from host_services.control_preferences import ControlPreferences
from host_services.main import app


class FakeBluetoothBackend:
    def __init__(self):
        self.devices = [
            {"id": "AA:BB:CC:DD:EE:01", "name": "Phone One", "paired": False,
             "connected": False, "activity": "idle"},
            {"id": "AA:BB:CC:DD:EE:02", "name": "Phone Two", "paired": True,
             "connected": False, "activity": "idle"},
            {"id": "AA:BB:CC:DD:EE:03", "name": "Phone Three", "paired": True,
             "connected": False, "activity": "idle"},
        ]
        self.challenges = []
        self.operations = {}
        self.pair_window = False
        self.discovering = False
        self.route = None
        self.callbacks = None

    async def start(self, callbacks):
        self.callbacks = callbacks

    async def close(self):
        pass

    async def snapshot(self):
        return {
            "available": True, "powered": True,
            "devices": [dict(device) for device in self.devices],
            "challenges": [dict(challenge) for challenge in self.challenges],
            "operations": {key: dict(value) for key, value in self.operations.items()},
            "speaker_route": dict(self.route) if self.route else None,
            "digital_target": None, "audio_output_available": True,
            "audio_output": {"available": True, "sink": "fixture-rt5616",
                             "state": "SUSPENDED", "port_availability": "unknown"},
        }

    async def scan(self, enabled):
        self.discovering = enabled

    async def set_pairing_window(self, enabled):
        self.pair_window = enabled
        if not enabled:
            self.challenges = [c for c in self.challenges if c.get("operation_id")]

    async def pair(self, device_id, operation_id):
        self.operations[operation_id] = {"state": "pending", "device_id": device_id}
        self.challenges.append({"id": "challenge-fixture-1", "device_id": device_id,
                                "kind": "confirm", "value": "004281",
                                "operation_id": operation_id,
                                "expires_at": 9999999999, "display_only": False})
        if self.callbacks:
            loop = __import__("asyncio").get_running_loop()
            loop.call_soon(lambda: loop.create_task(self.callbacks()))

    async def cancel_pair(self, operation_id):
        if operation_id not in self.operations:
            raise BackendUnavailable("pairing operation is not pending")
        self.operations[operation_id]["state"] = "cancelled"
        self.challenges = [c for c in self.challenges if c["operation_id"] != operation_id]

    async def answer_challenge(self, challenge_id, device_id, accept, value):
        item = next((c for c in self.challenges if c["id"] == challenge_id), None)
        if item is None or item["device_id"] != device_id:
            raise BackendUnavailable("pairing challenge expired or unavailable")
        self.challenges.remove(item)
        operation = item.get("operation_id")
        if accept and operation:
            self.operations[operation]["state"] = "succeeded"
            self.operations[operation]["value"] = value
            next(d for d in self.devices if d["id"] == device_id)["paired"] = True
        if self.callbacks:
            loop = __import__("asyncio").get_running_loop()
            loop.call_soon(lambda: loop.create_task(self.callbacks()))

    async def connect(self, device_id):
        next(d for d in self.devices if d["id"] == device_id).update(
            connected=True, activity="playing", player_status="playing"
        )

    async def disconnect(self, device_id):
        next(d for d in self.devices if d["id"] == device_id).update(
            connected=False, activity="idle", player_status="stopped"
        )
        if self.route and self.route["device"] == device_id:
            self.route = None

    async def remove(self, device_id):
        self.devices = [d for d in self.devices if d["id"] != device_id]

    async def set_speaker_route(self, device_id):
        self.route = {"device": device_id, "module_id": "fixture-route-1",
                      "verified": True, "digital_target": None}
        return dict(self.route)

    async def close_speaker_route(self):
        self.route = None


def test_formal_bluetooth_http_workflow_and_response_contract(tmp_path, monkeypatch):
    backend = FakeBluetoothBackend()
    async def noop_gate(_muted):
        return None

    async def noop_notify():
        return None

    service = AudioSystem(backend, gate_mpv=noop_gate, notify=noop_notify)
    backend.callbacks = service._on_backend_event
    service._started = True
    service._snapshot["bluetooth"] = {
        "available": True, "powered": True, "devices": [dict(d) for d in backend.devices],
        "challenges": [], "operations": {},
    }
    service._snapshot["audio_output_available"] = True
    service._snapshot["audio_output"] = {
        "available": True, "sink": "fixture-rt5616", "state": "SUSPENDED",
        "port_availability": "unknown",
    }
    monkeypatch.setattr(engine_adapter, "_audio_system", service)
    monkeypatch.setattr(engine_adapter, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)

    client = TestClient(app)

    def accepted(response):
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["ok"] is True
        assert "request_id" in payload
        return payload["data"]

    state_response = client.get("/control/state")
    assert state_response.status_code == 200
    state = state_response.json()["data"]
    assert state["bluetooth"]["available"] is True
    assert state["audio_output_available"] is True
    assert state["audio_output"]["sink"] == "fixture-rt5616"
    assert state["speaker"]["status"] == "idle"

    accepted(client.post("/control/bluetooth/scan"))
    assert backend.discovering is True
    accepted(client.post("/control/bluetooth/add"))
    assert backend.pair_window is True

    # Active pairing is independent from the inbound add window.
    data = accepted(client.post("/control/bluetooth/devices/AA:BB:CC:DD:EE:01/pair"))
    operation_id = data["result"]
    challenge = client.get("/control/state").json()["data"]["bluetooth"]["challenges"][0]
    assert challenge["value"] == "004281"
    answered = accepted(client.post("/control/bluetooth/answer", json={
        "challenge": challenge["id"], "device": challenge["device_id"],
        "accept": True, "value": None,
    }))
    state_after_pairing = client.get("/control/state").json()["data"]
    assert state_after_pairing["bluetooth"]["operations"][operation_id]["state"] == "succeeded"
    accepted(client.delete("/control/bluetooth/add"))
    assert backend.pair_window is False

    # Challenge IDs invalidated by cancellation return the documented 410.
    backend.challenges.append({"id": "stale-fixture", "device_id": "AA:BB:CC:DD:EE:03",
                               "kind": "confirm", "value": "000042",
                               "operation_id": "cancel-me", "expires_at": 9999999999})
    backend.operations["cancel-me"] = {"state": "pending", "device_id": "AA:BB:CC:DD:EE:03"}
    service._pending["cancel-me"] = "AA:BB:CC:DD:EE:03"
    accepted(client.post("/control/bluetooth/pair/cancel", json={"operation_id": "cancel-me"}))
    stale = client.post("/control/bluetooth/answer", json={
        "challenge": "stale-fixture", "device": "AA:BB:CC:DD:EE:03",
        "accept": True, "value": None,
    })
    assert stale.status_code == 410
    assert stale.json()["error"]["code"] == "CHALLENGE_EXPIRED"

    for device in ("AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"):
        accepted(client.post(f"/control/bluetooth/devices/{device}/connect"))
    routed = accepted(client.put("/control/speaker", json={"device": "AA:BB:CC:DD:EE:02"}))
    assert routed["speaker"]["status"] == "routed"
    assert routed["speaker"]["device"] == "AA:BB:CC:DD:EE:02"

    limited = client.post("/control/bluetooth/devices/AA:BB:CC:DD:EE:03/connect")
    assert limited.status_code == 409
    assert limited.json()["error"]["code"] == "CONNECTION_LIMIT"

    accepted(client.post("/control/bluetooth/devices/AA:BB:CC:DD:EE:01/disconnect"))
    forgotten = accepted(client.delete("/control/bluetooth/devices/AA:BB:CC:DD:EE:01"))
    assert all(d["id"] != "AA:BB:CC:DD:EE:01" for d in forgotten["bluetooth"]["devices"])

    reconnect = accepted(client.post("/control/bluetooth/devices/AA:BB:CC:DD:EE:02/connect"))
    assert any(d["id"] == "AA:BB:CC:DD:EE:02" and d["connected"]
               for d in reconnect["bluetooth"]["devices"])
