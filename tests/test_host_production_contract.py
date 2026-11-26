import pytest
from fastapi.testclient import TestClient

from host_services.main import app


@pytest.mark.parametrize("path", ["/api/v1/auth/pair", "/api/v1/auth/refresh", "/control/enroll"])
def test_retired_client_enrollment_has_no_route(path):
    assert TestClient(app).post(path, json={}).status_code == 404


def test_control_works_on_the_anonymous_host(tmp_path, monkeypatch):
    monkeypatch.delenv("LIGHT_BELT_CONTROL_ORIGIN", raising=False)
    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/control/state").status_code == 200
        assert client.get("/api/v1/state", headers={"Authorization": "Bearer stale"}).status_code == 200
        assert client.get("/").status_code == 404


def test_only_recovery_from_off_requires_the_current_intent_version(tmp_path, monkeypatch):
    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    with TestClient(app) as client:
        def set_intent(intent, **extra):
            return client.put("/control/lighting", json={"intent": intent, **extra})

        assert set_intent("music").status_code == 200
        old_off = set_intent("off").json()["data"]["lighting"]["intent_token"]
        current_off = set_intent("off").json()["data"]["lighting"]["intent_token"]
        assert current_off != old_off
        assert set_intent("follow").status_code == 409
        assert set_intent("follow", if_intent=old_off).status_code == 409
        assert set_intent("follow", if_intent=current_off).status_code == 200
        assert set_intent("music", if_intent=current_off).status_code == 409


def test_real_engine_selection_is_independent_of_preferences(monkeypatch):
    from host_services import engine_adapter
    from host_services.managed_adapter import ManagedAdapter

    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_preferences", None)
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    engine_adapter._init_real_adapter()
    assert type(engine_adapter._real_adapter) is ManagedAdapter


def test_production_play_does_not_start_mpv_without_managed_adapter(monkeypatch):
    from unittest.mock import Mock
    from host_services import engine_adapter

    start_player = Mock()
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    monkeypatch.setattr(engine_adapter, "_find_show", lambda show_id: {
        "show_id": show_id, "media_path": "video.mp4", "duration_ms": 1000,
    })
    monkeypatch.setattr(engine_adapter, "_validate_playback_content", lambda show: None)
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", start_player)
    response = TestClient(app).post("/api/v1/playback/play", json={"show_id": "test"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ENGINE_UNAVAILABLE"
    start_player.assert_not_called()


def test_starry_sky_socket_failure_returns_failed_submission(monkeypatch):
    from types import SimpleNamespace
    from host_services import engine_adapter, starry_sky

    def unavailable(*args):
        raise OSError("network unreachable")

    starry_sky.reset_state()
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(starry_sky, "socket", SimpleNamespace(
        socket=unavailable, AF_INET=starry_sky.socket.AF_INET,
        SOCK_DGRAM=starry_sky.socket.SOCK_DGRAM,
    ))
    response = TestClient(app).post("/api/v1/effects/set", json={
        "target_id": "starry_sky", "effect_type": "twinkle",
    })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEVICE_OFFLINE"


def test_manual_broadcast_and_single_target_share_persistent_state(tmp_path, monkeypatch):
    from host_services import engine_adapter
    from host_services.control_preferences import ControlPreferences

    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr(engine_adapter, "_valid_target_ids", frozenset({"all", "strip_11", "strip_12"}))
    with TestClient(app) as client:
        assert client.post("/api/v1/lights/set", json={"target_id": "all", "brightness": 0.5}).status_code == 200
        assert client.post("/api/v1/lights/set", json={"target_id": "strip_11", "brightness": 0.25}).status_code == 200
    restored = ControlPreferences(tmp_path).data
    assert restored["intent"] == "manual"
    assert set(restored["targets"]) == {"strip_11", "strip_12"}
    assert restored["targets"]["strip_11"]["color"] == [0.25] * 3
    assert restored["targets"]["strip_12"]["color"] == [0.5] * 3


@pytest.mark.parametrize("initial, expected", [("playing", "stopped"), ("paused", "paused"), ("idle", "idle")])
def test_v1_scene_stops_only_playing_programs(initial, expected, monkeypatch):
    from host_services import engine_adapter

    monkeypatch.setattr(engine_adapter, "_state", dict(engine_adapter._state, playback_state=initial))
    monkeypatch.setattr(engine_adapter, "_scenes", {"test": {"entries": [{"target_id": "all", "brightness": 0.3}]}})
    with TestClient(app) as client:
        result = client.post("/api/v1/scenes/apply", json={"scene_id": "test"}).json()["data"]
        assert result["partial"] is False
        assert len(result["applied_entries"]) == 1
        assert client.get("/api/v1/playback/state").json()["data"]["playback_state"] == expected


def test_scene_partial_does_not_publish_fully_applied_scene(monkeypatch):
    from host_services import engine_adapter

    def failed_send(effect_type):
        raise OSError("packet submission failed")

    monkeypatch.setattr(engine_adapter, "_submit_starry_sky", failed_send)
    monkeypatch.setattr(engine_adapter, "_state", dict(engine_adapter._state, playback_state="idle"))
    first = {"target_id": "all", "brightness": 0.3}
    failed = {"target_id": "starry_sky", "effect_type": "twinkle"}
    monkeypatch.setattr(engine_adapter, "_scenes", {"test": {"entries": [first, failed]}})
    with TestClient(app) as client:
        result = client.post("/api/v1/scenes/apply", json={"scene_id": "test"}).json()["data"]
        assert result["partial"] is True
        assert result["applied_entries"] == [first]
        assert result["failed_targets"] == ["starry_sky"]
        assert client.get("/api/v1/state").json()["data"]["scene_id"] is None


def test_both_play_entries_preserve_the_explicit_off_interlock(monkeypatch):
    from unittest.mock import Mock
    from host_services import engine_adapter

    media = Mock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: media)
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_find_show", lambda show_id: {
        "show_id": show_id, "media_path": "video.mp4", "duration_ms": 10000,
    })
    with TestClient(app) as client:
        assert client.put("/control/lighting", json={"intent": "off"}).status_code == 200
        assert client.post("/api/v1/brightness/set", json={"brightness_scale": 0.3}).status_code == 200
        for path, expected_scale in [("/control/play", 0.3), ("/api/v1/playback/play", 0.5)]:
            assert client.post(path, json={"show_id": "test"}).status_code == 200
            state = client.get("/control/state").json()["data"]
            assert state["lighting"]["intent"] == "off"
            assert state["lighting"]["brightness"] == expected_scale
            assert state["video"]["state"] == "playing"
        assert client.post("/api/v1/lights/set", json={"target_id": "all", "brightness": 0.4}).status_code == 200
        assert client.get("/control/state").json()["data"]["video"]["state"] == "playing"
        media.stop.assert_not_called()


def test_audio_output_observation_updates_during_route_ownership_failure(monkeypatch):
    import asyncio
    from host_services import engine_adapter
    from host_services.bluetooth import AudioSystem, BackendUnavailable

    class Backend:
        async def snapshot(self):
            return {"audio_output_available": False, "audio_output": {
                "available": False, "reason": "sink absent",
            }, "route_error": "unverified route"}

    async def gate(_muted):
        return None

    system = AudioSystem(Backend(), gate_mpv=gate)
    system._snapshot["audio_output_available"] = True
    monkeypatch.setattr(engine_adapter, "_audio_system", system)
    with pytest.raises(BackendUnavailable, match="ownership is uncertain"):
        asyncio.run(system._refresh())
    assert engine_adapter.get_audio()["audio_output_available"] is False
    assert system.snapshot()["audio_output"]["reason"] == "sink absent"


def test_playback_stop_reports_auxiliary_failure_and_stops_media(monkeypatch):
    from unittest.mock import Mock
    from host_services import engine_adapter, starry_sky
    from host_services.managed_adapter import ManagedAdapter

    adapter = ManagedAdapter(profile_path="test", mpv_socket_path="test")
    adapter._aux_poll_thread = object()
    monkeypatch.setattr(adapter, "_stop_aux_poll", lambda: None)
    monkeypatch.setattr(starry_sky, "ensure_off", Mock(side_effect=OSError("link closed")))
    media = Mock()
    monkeypatch.setattr(engine_adapter, "_mpv", media)
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(engine_adapter, "_state", dict(engine_adapter._state, playback_state="playing"))

    response = TestClient(app).post("/api/v1/playback/stop")

    assert response.status_code == 200
    assert response.json()["data"]["playback_state"] == "stopped"
    assert response.json()["data"]["auxiliary_error"] == {
        "code": "STARRY_SKY_SUBMISSION_FAILED", "message": "link closed",
    }
    media.stop.assert_called_once()
