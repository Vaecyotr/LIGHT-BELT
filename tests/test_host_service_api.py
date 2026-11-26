"""
Smoke tests for host_services API.

All tests use FastAPI TestClient and in-memory state only.
No mpv, no hardware, no filesystem (shows manifest is monkeypatched).
"""

import os

import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from host_services.main import app
from host_services import engine_adapter


@pytest.fixture(autouse=True)
def reset_engine_state(monkeypatch):
    """Reset shared module-level state before each test."""
    monkeypatch.setattr(engine_adapter, "_shows", [
        {
            "show_id": "test-show",
            "name": "Test Show",
            "duration_ms": 60000,
            "description": "Smoke-test fixture show",
            "media_path": "/dev/null",
        }
    ])
    monkeypatch.setattr(engine_adapter, "_scenes", {})
    monkeypatch.setattr(engine_adapter, "_save_scenes", lambda _scenes: None)
    monkeypatch.setitem(engine_adapter._state, "playback_state", "idle")
    monkeypatch.setitem(engine_adapter._state, "show_id", None)
    monkeypatch.setitem(engine_adapter._state, "position_ms", 0)
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 0)
    monkeypatch.setitem(engine_adapter._state, "scene_id", None)
    monkeypatch.setitem(engine_adapter._state, "volume", 0.5)
    monkeypatch.setitem(engine_adapter._state, "muted", False)
    monkeypatch.setitem(engine_adapter._state, "brightness", 1.0)
    monkeypatch.setitem(engine_adapter._state, "brightness_scale", 0.5)


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ── Status ────────────────────────────────────────────────────────────────────

def test_status(client):
    r = client.get("/api/v1/status")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["data"]["service"] == "light-belt-host"
    assert "api_version" in d["data"]


def test_state(client):
    r = client.get("/api/v1/state")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "playback_state" in d
    assert "devices" in d


# ── Shows ─────────────────────────────────────────────────────────────────────

def test_shows_listed(client):
    r = client.get("/api/v1/shows")
    assert r.status_code == 200
    shows = r.json()["data"]["shows"]
    assert len(shows) == 1
    assert shows[0]["show_id"] == "test-show"


def test_shows_no_media_path(client):
    r = client.get("/api/v1/shows")
    shows = r.json()["data"]["shows"]
    for s in shows:
        assert "media_path" not in s


# ── Capabilities ──────────────────────────────────────────────────────────────

def test_capabilities(client):
    r = client.get("/api/v1/capabilities")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "targets" in d
    assert "effects" in d
    assert "websocket" in d
    assert "supports" in d


# ── Playback: play + stop ─────────────────────────────────────────────────────

def test_playback_play_stop(client, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "playing"
    mock_mpv.play_file.assert_called_once_with("/dev/null")
    mock_mpv.resume.assert_called_once_with()

    r = client.post("/api/v1/playback/stop")
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "stopped"


def test_playback_play_unknown_show(client):
    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "no-such-show"},
    )
    assert r.status_code == 404


# ── Lights ────────────────────────────────────────────────────────────────────

def test_lights_set_brightness(client):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.5},
    )
    assert r.status_code == 200
    assert r.json()["data"]["brightness"] == 0.5


def test_lights_set_unknown_target(client):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "nonexistent", "brightness": 0.5},
    )
    assert r.status_code == 404


def test_lights_set_missing_params(client):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all"},
    )
    assert r.status_code == 400


# ── Audio ─────────────────────────────────────────────────────────────────────

def test_audio_get(client):
    r = client.get("/api/v1/audio")
    assert r.status_code == 200
    d = r.json()["data"]
    assert "volume" in d
    assert "muted" in d


def test_audio_set_volume(client):
    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.8},
    )
    assert r.status_code == 200
    assert r.json()["data"]["volume"] == pytest.approx(0.8)


def test_audio_set_muted(client):
    r = client.post(
        "/api/v1/audio/set",
        json={"muted": True},
    )
    assert r.status_code == 200
    assert r.json()["data"]["muted"] is True


# ── Scenes: save + apply + delete ─────────────────────────────────────────────

def test_scenes_save_apply_delete(client):
    # save
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Smoke Scene",
            "entries": [{"target_id": "all", "brightness": 0.7}],
        },
    )
    assert r.status_code == 200
    scene_id = r.json()["data"]["scene_id"]
    assert scene_id

    # list
    r = client.get("/api/v1/scenes")
    assert r.status_code == 200
    ids = [s["scene_id"] for s in r.json()["data"]["scenes"]]
    assert scene_id in ids

    # apply
    r = client.post(
        "/api/v1/scenes/apply",
        json={"scene_id": scene_id},
    )
    assert r.status_code == 200
    assert r.json()["data"]["accepted"] is True

    # delete
    r = client.post(
        "/api/v1/scenes/delete",
        json={"scene_id": scene_id},
    )
    assert r.status_code == 200
    assert r.json()["data"]["deleted"] is True


def test_scene_apply_not_found(client):
    r = client.post(
        "/api/v1/scenes/apply",
        json={"scene_id": "no-such-scene"},
    )
    assert r.status_code == 404


def test_scene_delete_not_found(client):
    r = client.post(
        "/api/v1/scenes/delete",
        json={"scene_id": "no-such-scene"},
    )
    assert r.status_code == 404


# ── Audio: mpv IPC sync (item 8) ─────────────────────────────────────────────

def test_audio_set_calls_mpv_when_running(client, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.6, "muted": True},
    )
    assert r.status_code == 200
    mock_mpv.set_volume.assert_called_once_with(0.6)
    mock_mpv.set_mute.assert_called_once_with(True)


def test_audio_set_no_mpv_still_succeeds(client, monkeypatch):
    monkeypatch.setattr(engine_adapter, "_mpv", None)

    r = client.post(
        "/api/v1/audio/set",
        json={"volume": 0.3},
    )
    assert r.status_code == 200
    assert r.json()["data"]["volume"] == pytest.approx(0.3)


def test_audio_set_volume_scale_to_mpv(client, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    client.post("/api/v1/audio/set", json={"volume": 1.0})
    mock_mpv.set_volume.assert_called_once_with(1.0)
    # MpvClient.set_volume internally multiplies by 100 — verify via the method
    from host_services.engine_adapter import MpvClient
    sent = []
    mc = MpvClient.__new__(MpvClient)
    mc._send = lambda cmd: sent.append(cmd) or {"error": "success"}
    mc.set_volume(0.75)
    assert sent == [["set_property", "volume", 75.0]]


# ── Playback: start_position_ms > duration_ms → 400 (item 9) ────────────────

def test_playback_play_start_beyond_duration(client, monkeypatch):
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show", "start_position_ms": 999999},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ARGUMENT"


# ── Lights: master state only for target "all" (item 10) ─────────────────────

def test_lights_set_non_all_does_not_change_master_state(client):
    # record the master brightness before
    r = client.get("/api/v1/state")
    before = r.json()["data"]["brightness"]

    # set brightness on a specific (non-all) target
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "strip_11", "brightness": 0.1},
    )
    assert r.status_code == 200

    # master brightness in /state must be unchanged
    r = client.get("/api/v1/state")
    assert r.json()["data"]["brightness"] == before


def test_lights_set_all_updates_master_state(client):
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.42},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/state")
    assert r.json()["data"]["brightness"] == pytest.approx(0.42)


# ── Scene apply: only "all" entries touch master state (item 10) ─────────────

def test_scene_apply_non_all_entry_does_not_change_master_state(client):
    # save scene with a non-"all" entry
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Zone scene",
            "entries": [{"target_id": "strip_11", "brightness": 0.05}],
        },
    )
    scene_id = r.json()["data"]["scene_id"]

    before = client.get("/api/v1/state").json()["data"]["brightness"]

    client.post("/api/v1/scenes/apply", json={"scene_id": scene_id})

    after = client.get("/api/v1/state").json()["data"]["brightness"]
    assert after == before


def test_scene_apply_all_entry_updates_master_state(client):
    r = client.post(
        "/api/v1/scenes/save",
        json={
            "name": "Master scene",
            "entries": [{"target_id": "all", "brightness": 0.33}],
        },
    )
    scene_id = r.json()["data"]["scene_id"]

    client.post("/api/v1/scenes/apply", json={"scene_id": scene_id})

    after = client.get("/api/v1/state").json()["data"]["brightness"]
    assert after == pytest.approx(0.33)


# ── Round-2 fixes ─────────────────────────────────────────────────────────────

def test_lights_set_color_only(client):
    """lights/set with only color (no brightness/CT) must return 200."""
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "color": {"r": 255, "g": 0, "b": 128}},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["color"] == {"r": 255, "g": 0, "b": 128}


def test_playback_play_clears_scene_id(client, monkeypatch):
    """Starting playback must clear scene_id in state."""
    monkeypatch.setitem(engine_adapter._state, "scene_id", "some-scene")
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post("/api/v1/playback/play", json={"show_id": "test-show"})
    assert r.status_code == 200
    assert engine_adapter._state["scene_id"] is None


def test_ensure_mpv_stale_socket(monkeypatch):
    """_ensure_mpv must detect a stale socket, remove it, and restart mpv."""
    exists_calls = []

    def mock_exists(p):
        # First call: socket appears to exist (stale).
        # Subsequent calls: socket is gone (after unlink) → triggers mpv start.
        exists_calls.append(p)
        return len(exists_calls) == 1

    unlinked = []
    mock_probe = MagicMock()
    mock_probe.connect.side_effect = ConnectionRefusedError("stale")

    mock_proc = MagicMock()
    mock_proc.stderr = iter([])
    mock_popen = MagicMock(return_value=mock_proc)

    monkeypatch.setattr(engine_adapter.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_mpv_proc", None)
    monkeypatch.setattr(engine_adapter.os.path, "exists", mock_exists)
    monkeypatch.setattr(engine_adapter.os, "makedirs", MagicMock())
    monkeypatch.setattr(engine_adapter.os, "unlink", lambda p: unlinked.append(p))
    monkeypatch.setattr(engine_adapter.socket, "socket", MagicMock(return_value=mock_probe))
    monkeypatch.setattr(engine_adapter.subprocess, "Popen", mock_popen)
    monkeypatch.setattr(engine_adapter, "_wait_until", lambda *a, **kw: True)
    client = MagicMock()
    monkeypatch.setattr(engine_adapter, "MpvClient", lambda _path: client)

    result = engine_adapter._ensure_mpv()

    assert result is not None
    client.set_volume.assert_called_once()
    client.set_mute.assert_called_once()
    assert len(unlinked) == 1           # stale socket was removed
    assert mock_popen.called            # mpv was relaunched
    command = mock_popen.call_args.args[0]
    assert "--no-config" in command
    assert "--fullscreen" in command
    assert "--ontop" in command
    assert "--cursor-autohide=always" in command
    assert not any(arg.startswith("--vo=") for arg in command)
    assert not any(arg == "--geometry" or arg.startswith("--geometry=") for arg in command)
    assert "--input-default-bindings=no" in command


def test_ensure_mpv_exposes_local_media_audio_identity(monkeypatch):
    """The production mpv process must be discoverable by PulseAudio identity."""
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_mpv_proc", None)
    monkeypatch.setattr(engine_adapter.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(engine_adapter.os, "makedirs", MagicMock())
    monkeypatch.setattr(engine_adapter.subprocess, "Popen", MagicMock(
        return_value=MagicMock(stderr=iter([]), poll=MagicMock(return_value=None)))
    )
    monkeypatch.setattr(engine_adapter, "_wait_until", lambda *args, **kwargs: True)
    monkeypatch.setattr(engine_adapter, "MpvClient", lambda _path: MagicMock())

    engine_adapter._ensure_mpv()

    command = engine_adapter.subprocess.Popen.call_args.args[0]
    assert "--audio-client-name=LIGHT-BELT-LocalMedia" in command


# ── New: color params passed through (problems 1 & 2) ────────────────────────

def test_effects_set_with_color(client):
    r = client.post(
        "/api/v1/effects/set",
        json={
            "target_id": "all",
            "effect_type": "static",
            "params": {"color": {"r": 255, "g": 128, "b": 0}},
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["effect_type"] == "static"
    assert data["params"]["color"] == {"r": 255, "g": 128, "b": 0}


def test_lights_set_with_color(client):
    r = client.post(
        "/api/v1/lights/set",
        json={
            "target_id": "all",
            "brightness": 0.8,
            "color": {"r": 100, "g": 200, "b": 50},
        },
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["brightness"] == pytest.approx(0.8)
    assert data["color"] == {"r": 100, "g": 200, "b": 50}


def test_playback_play_no_media(client, monkeypatch):
    monkeypatch.setattr(engine_adapter, "_shows", [{
        "show_id": "no-media-show",
        "name": "No Media Show",
        "duration_ms": 30000,
        "description": None,
        "media_path": None,
    }])
    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "no-media-show"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "playing"


# ── Round-3 fixes ─────────────────────────────────────────────────────────────

def test_global_exception_handler_returns_structured_error(monkeypatch):
    """Problem 2: unhandled exceptions must return ok=false JSON (not bare 500)."""
    def _boom(*_a, **_kw):
        raise RuntimeError("simulated crash")
    monkeypatch.setattr(engine_adapter, "get_state", _boom)

    # raise_server_exceptions=False lets the FastAPI exception handler respond
    # instead of propagating the exception to the test process.
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/state")

    assert r.status_code == 500
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "RuntimeError" in body["error"]["message"]
    assert "request_id" in body


def test_playback_play_mpv_unavailable_returns_503(client, monkeypatch):
    """Problem 3: MpvUnavailableError must surface as 503 MPV_UNAVAILABLE."""
    from host_services.engine_adapter import MpvUnavailableError

    def _raise(*_a, **_kw):
        raise MpvUnavailableError("mpv not found")
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", _raise)

    r = client.post(
        "/api/v1/playback/play",
        json={"show_id": "test-show"},
    )

    assert r.status_code == 503
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "MPV_UNAVAILABLE"


# ── Fix 1: Pydantic 422 → project envelope 400 ───────────────────────────────

def test_validation_error_missing_field_returns_envelope(client):
    """Missing required field must return ok=false INVALID_ARGUMENT at 400, not 422."""
    r = client.post("/api/v1/playback/play", json={})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"
    assert "validation_errors" in body["error"].get("details", {})


def test_validation_error_wrong_type_returns_envelope(client):
    """Wrong field type (brightness='abc') must return INVALID_ARGUMENT envelope at 400."""
    r = client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": "abc"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"


def test_validation_error_no_content_type_returns_envelope(client):
    """POST with body but no Content-Type must return INVALID_ARGUMENT envelope at 400."""
    r = client.post(
        "/api/v1/lights/set",
        content=b'{"target_id": "all", "brightness": 0.5}',
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENT"


# ── Fix 3: ws_url uses request Host header ────────────────────────────────────

def test_ws_ticket_url_uses_request_host(client):
    """ws_url must use the Host header from the request, not hardcoded 0.0.0.0."""
    r = client.post(
        "/api/v1/session/ws-ticket",
        json={"subscribe": ["heartbeat"]},
        headers={"host": "cabin.local:8443"},
    )
    assert r.status_code == 200
    ws_url = r.json()["data"]["ws_url"]
    assert "cabin.local" in ws_url
    assert "0.0.0.0" not in ws_url


# ── Fix 4: devices last_output_ms is 0 on start, updated after lights/set ────

def test_devices_last_output_ms_zero_on_start(client, monkeypatch):
    """Before any command, last_output_ms and last_seen_ms must be 0."""
    fake_device = {
        "device_id": "node_1", "device_type": "wled_board",
        "status": "online",
        "last_output_ms": 0, "last_seen_ms": 0,
        "connection_confirmed": True, "error_code": None,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [fake_device])

    r = client.get("/api/v1/state")
    assert r.status_code == 200
    devices = r.json()["data"]["devices"]
    assert len(devices) == 1
    assert devices[0]["last_output_ms"] == 0
    assert devices[0]["last_seen_ms"] == 0


def test_devices_last_output_ms_requires_node_submission(client, monkeypatch):
    """A saved light command does not prove local DDP submission."""
    fake_device = {
        "device_id": "node_1", "device_type": "wled_board",
        "status": "online",
        "last_output_ms": 0, "last_seen_ms": 0,
        "connection_confirmed": True, "error_code": None,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [fake_device])

    client.post(
        "/api/v1/lights/set",
        json={"target_id": "all", "brightness": 0.5},
    )

    r = client.get("/api/v1/state")
    assert r.json()["data"]["devices"][0]["last_output_ms"] == 0

    fake_device["host"] = "192.0.2.1"
    engine_adapter._record_ddp_submissions({
        "submitted_ms": 99,
        "node_submissions": {"1": {"host": fake_device["host"], "submitted": True}},
    })
    r = client.get("/api/v1/state")
    assert r.json()["data"]["devices"][0]["last_output_ms"] == 99


# ── Fix 5: CORS middleware ────────────────────────────────────────────────────

def test_cors_header_present(client):
    """Requests with Origin header must get Access-Control-Allow-Origin in response."""
    r = client.get("/api/v1/status", headers={"Origin": "http://cabin.local"})
    assert r.status_code == 200
    assert "access-control-allow-origin" in {k.lower() for k in r.headers}


# ── Fix 9: device initial status is offline / connection_confirmed False ──────

def test_state_devices_initial_status_offline(client, monkeypatch):
    """derive_device_list() must initialise status='offline' and connection_confirmed=False."""
    from host_services.layout_vocab import derive_device_list
    from types import SimpleNamespace
    layout = SimpleNamespace(digital_nodes=[SimpleNamespace(node_id=1, host=None)])
    devices = derive_device_list(layout)
    assert devices[0]["status"] == "offline"
    assert devices[0]["connection_confirmed"] is False


# ── Fix 10: video_available True in mock mode ─────────────────────────────────

def test_video_available_true_in_mock_mode(client):
    """In mock mode (VIDEO_DETECT_ENABLED=False), video_available must be True."""
    r = client.get("/api/v1/state")
    assert r.status_code == 200
    assert r.json()["data"]["video_available"] is True


def test_detect_video_available_xrandr_connected(monkeypatch):
    """_detect_video_available returns True when xrandr reports an HDMI output connected."""
    import subprocess as _sp
    from host_services import engine_adapter as ea
    fake_result = _sp.CompletedProcess(
        args=[], returncode=0,
        stdout="HDMI-1 connected 1920x1080+0+0\n",
        stderr="",
    )
    monkeypatch.setattr(ea, "VIDEO_DETECT_ENABLED", True)
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "host_services.engine_adapter.subprocess.run", return_value=fake_result
    ):
        assert ea._detect_video_available() is True


def test_detect_video_available_xrandr_disconnected(monkeypatch):
    """_detect_video_available returns False when xrandr reports no HDMI connected."""
    import subprocess as _sp
    from host_services import engine_adapter as ea
    fake_result = _sp.CompletedProcess(
        args=[], returncode=0,
        stdout="HDMI-1 disconnected\nDP-1 disconnected\n",
        stderr="",
    )
    monkeypatch.setattr(ea, "VIDEO_DETECT_ENABLED", True)
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "host_services.engine_adapter.subprocess.run", return_value=fake_result
    ):
        assert ea._detect_video_available() is False


def test_detect_video_available_xrandr_exception_returns_false(monkeypatch):
    """A failed display probe does not confirm an available display."""
    from host_services import engine_adapter as ea
    monkeypatch.setattr(ea, "VIDEO_DETECT_ENABLED", True)
    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "host_services.engine_adapter.subprocess.run", side_effect=FileNotFoundError("xrandr not found")
    ):
        assert ea._detect_video_available() is False


# ── Fix 11: playback_resume allowed from 'playing' state ─────────────────────

def test_playback_resume_from_playing_succeeds(client, monkeypatch):
    """When playback_state is 'playing', resume must succeed (not return PLAYBACK_NOT_READY)."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "show_id", "test-show")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)
    r = client.post("/api/v1/playback/resume")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["playback_state"] == "playing"


def test_playback_resume_from_idle_returns_not_ready(client, monkeypatch):
    """When playback_state is 'idle', resume must still return PLAYBACK_NOT_READY."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "idle")
    r = client.post("/api/v1/playback/resume")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PLAYBACK_NOT_READY"


# ── /playback/reset ───────────────────────────────────────────────────────────

def test_playback_reset_returns_playback_data(client, monkeypatch):
    """Calling reset while playing must return 200 with playback data."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "show_id", "test-show")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)

    r = client.post("/api/v1/playback/reset")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["playback_state"] == "playing"
    assert data["show_id"] == "test-show"


def test_playback_reset_when_idle_returns_409(client):
    """Calling reset while idle must return 409 PLAYBACK_NOT_READY."""
    r = client.post("/api/v1/playback/reset")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PLAYBACK_NOT_READY"


def test_playback_reset_when_stopped_returns_409(client, monkeypatch):
    """Calling reset while stopped must return 409 PLAYBACK_NOT_READY."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "stopped")

    r = client.post("/api/v1/playback/reset")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PLAYBACK_NOT_READY"


def test_playback_reset_from_paused_resumes_playback(client, monkeypatch):
    """reset while paused must transition playback_state to 'playing'."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "paused")
    monkeypatch.setitem(engine_adapter._state, "show_id", "test-show")
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    r = client.post("/api/v1/playback/reset")
    assert r.status_code == 200
    assert r.json()["data"]["playback_state"] == "playing"
    mock_mpv.resume.assert_called_once()


def test_playback_reset_from_playing_does_not_call_resume(client, monkeypatch):
    """reset while already playing must NOT call mpv.resume."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    r = client.post("/api/v1/playback/reset")
    assert r.status_code == 200
    mock_mpv.resume.assert_not_called()


def test_playback_reset_clears_manual_state(client, monkeypatch):
    assert client.post("/api/v1/lights/set", json={"target_id": "strip_11", "brightness": 0.6}).status_code == 200
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")

    assert client.post("/api/v1/playback/reset").status_code == 200
    assert engine_adapter._preferences.data["targets"] == {}


def test_brightness_get_default(client):
    """GET /brightness returns brightness_scale=0.5 (the default)."""
    r = client.get("/api/v1/brightness")
    assert r.status_code == 200
    assert r.json()["data"]["brightness_scale"] == pytest.approx(0.5)


def test_brightness_set(client):
    """POST /brightness/set persists brightness_scale."""
    r = client.post(
        "/api/v1/brightness/set",
        json={"brightness_scale": 0.8},
    )
    assert r.status_code == 200
    assert r.json()["data"]["brightness_scale"] == pytest.approx(0.8)
    assert r.json()["data"]["accepted"] is True

    # Verify the value is stored
    r2 = client.get("/api/v1/brightness")
    assert r2.json()["data"]["brightness_scale"] == pytest.approx(0.8)


def test_brightness_set_out_of_range(client):
    """POST /brightness/set with scale > 1.0 returns 400 INVALID_ARGUMENT."""
    r = client.post(
        "/api/v1/brightness/set",
        json={"brightness_scale": 1.5},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ARGUMENT"


def test_brightness_scale_in_state(client):
    """GET /state must include brightness_scale."""
    r = client.get("/api/v1/state")
    assert r.status_code == 200
    assert "brightness_scale" in r.json()["data"]


def test_playback_state_idle(client):
    """GET /playback/state returns well-formed dict when idle."""
    r = client.get("/api/v1/playback/state")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["playback_state"] == "idle"
    assert d["show"] is None
    assert "position_ms" in d
    assert "duration_ms" in d
    assert "brightness_scale" in d
    assert "audio" in d
    assert "volume" in d["audio"]
    assert "muted" in d["audio"]


def test_playback_state_when_playing(client, monkeypatch):
    """GET /playback/state includes filtered show info when a show is playing."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "show_id", "test-show")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)

    r = client.get("/api/v1/playback/state")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["playback_state"] == "playing"
    assert d["show"] is not None
    assert d["show"]["show_id"] == "test-show"
    assert "media_path" not in d["show"]
    assert d["duration_ms"] == 60000
    assert "brightness_scale" in d


def test_playback_play_resets_brightness_scale(client, monkeypatch):
    """Starting playback must reset brightness_scale to the default (0.5)."""
    engine_adapter._preferences.save(brightness=0.1)
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_ensure_mpv", lambda: mock_mpv)

    r = client.post("/api/v1/playback/play", json={"show_id": "test-show"})
    assert r.status_code == 200
    assert engine_adapter.get_brightness_scale()["brightness_scale"] == pytest.approx(0.5)


@pytest.mark.parametrize("enabled", [True, False])
def test_brightness_set_sends_http_only_to_enabled_wled(client, monkeypatch, enabled):
    import io
    import json
    from types import SimpleNamespace
    from host_services import wled_brightness

    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    adapter = SimpleNamespace(sender=object())
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(engine_adapter, "_reconcile_lighting", lambda **kwargs: None)
    monkeypatch.setattr(adapter, "shutdown", lambda: None, raising=False)
    monkeypatch.setattr(engine_adapter, "_devices", [{
        "device_id": "node_1", "host": "192.0.2.1", "enabled": enabled, "device_type": "wled_board",
    }])
    posts = []

    def fetch(request, **kwargs):
        if not isinstance(request, str):
            posts.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(b'{"on":true,"bri":153}')

    monkeypatch.setattr(wled_brightness.urllib.request, "urlopen", fetch)
    response = client.post("/api/v1/brightness/set", json={"brightness_scale": 0.6})
    assert response.status_code == 200
    assert response.json()["data"]["brightness_scale"] == pytest.approx(0.6)
    assert posts == (
        [("http://192.0.2.1/json/state", {"on": True, "bri": 153, "v": False})]
        if enabled else []
    )
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)


def test_brightness_scale_in_runtime_snapshot(monkeypatch):
    """get_runtime_state_snapshot must include brightness_scale."""
    monkeypatch.setitem(engine_adapter._state, "brightness_scale", 0.7)
    snap = engine_adapter.get_runtime_state_snapshot()
    assert snap["brightness_scale"] == pytest.approx(0.7)


# ── mpv hang/deadlock hardening ───────────────────────────────────────────────

def test_mpv_client_send_timeout_returns_error_and_closes_socket():
    """A recv() that blocks past the IPC timeout must not hang the caller; it must
    return an error dict and always close the socket, even on failure."""
    closed = []

    class FakeSocket:
        def settimeout(self, _t):
            pass

        def connect(self, _path):
            pass

        def sendall(self, _data):
            pass

        def recv(self, _n):
            raise engine_adapter.socket.timeout()

        def close(self):
            closed.append(True)

    mpv = engine_adapter.MpvClient("/tmp/fake.sock", socket_factory=FakeSocket)
    result = mpv._send(["get_property", "time-pos"])

    assert result == {"error": "timeout"}
    assert closed == [True]


def test_mpv_client_send_generic_exception_still_closes_socket():
    """Any other _send failure (e.g. connection refused) must still close the socket."""
    closed = []

    class FakeSocket:
        def settimeout(self, _t):
            pass

        def connect(self, _path):
            raise ConnectionRefusedError("boom")

        def sendall(self, _data):
            pass

        def recv(self, _n):
            return b""

        def close(self):
            closed.append(True)

    mpv = engine_adapter.MpvClient("/tmp/fake.sock", socket_factory=FakeSocket)
    result = mpv._send(["stop"])

    assert result == {"error": "boom"}
    assert closed == [True]


def test_mpv_client_default_factory_preserves_unix_stream_socket(monkeypatch):
    """Production IPC still constructs a Linux AF_UNIX stream socket."""
    calls = []
    closed = []

    class FakeSocket:
        def settimeout(self, _t):
            pass

        def connect(self, _path):
            pass

        def sendall(self, _data):
            pass

        def recv(self, _n):
            return b'{"request_id":1,"error":"success","data":true}\n'

        def close(self):
            closed.append(True)

    def socket_factory(*args):
        calls.append(args)
        return FakeSocket()

    monkeypatch.setattr(engine_adapter.socket, "AF_UNIX", 123, raising=False)
    monkeypatch.setattr(engine_adapter.socket, "socket", socket_factory)

    result = engine_adapter.MpvClient("/tmp/fake.sock")._send(["get_property", "pause"])

    assert result == {"request_id": 1, "error": "success", "data": True}
    assert calls == [(123, engine_adapter.socket.SOCK_STREAM)]
    assert closed == [True]


def test_live_position_ms_falls_back_on_non_positive_position(monkeypatch):
    """A timed-out get_position() reads back as 0.0; this must not be reported as
    the live position (which would look like 'just started'), it must fall back
    to the last known stored position."""
    monkeypatch.setitem(engine_adapter._state, "position_ms", 12345)
    mock_mpv = MagicMock()
    mock_mpv.get_idle_active.return_value = False
    mock_mpv.get_position.return_value = 0.0
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    assert engine_adapter._live_position_ms() == 12345


def test_live_position_ms_returns_live_value_when_positive(monkeypatch):
    monkeypatch.setitem(engine_adapter._state, "position_ms", 0)
    mock_mpv = MagicMock()
    mock_mpv.get_idle_active.return_value = False
    mock_mpv.get_position.return_value = 5.5
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    assert engine_adapter._live_position_ms() == 5500


def test_finalize_natural_end_clears_dead_mpv_refs(monkeypatch, tmp_path):
    """If mpv's process already exited, finalize must clear _mpv/_mpv_proc (and the
    stale socket file) so the next play request rebuilds them via _ensure_mpv."""
    sock_path = str(tmp_path / "mpv.sock")
    open(sock_path, "w").close()

    dead_proc = MagicMock()
    dead_proc.poll.return_value = 1
    dead_proc.returncode = 1
    monkeypatch.setattr(engine_adapter, "_mpv_proc", dead_proc)
    monkeypatch.setattr(engine_adapter, "_mpv", engine_adapter.MpvClient(sock_path))
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "show_id", "test-show")

    engine_adapter._finalize_natural_end()

    assert engine_adapter._mpv is None
    assert engine_adapter._mpv_proc is None
    assert not os.path.exists(sock_path)
    assert engine_adapter._state["playback_state"] == "stopped"


def test_finalize_natural_end_keeps_mpv_refs_when_process_alive(monkeypatch):
    """Normal natural-end finalize (mpv idle but alive) must not tear down _mpv/_mpv_proc."""
    alive_proc = MagicMock()
    alive_proc.poll.return_value = None
    mock_mpv = MagicMock()
    monkeypatch.setattr(engine_adapter, "_mpv_proc", alive_proc)
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")

    engine_adapter._finalize_natural_end()

    assert engine_adapter._mpv is mock_mpv
    assert engine_adapter._mpv_proc is alive_proc
    assert engine_adapter._state["playback_state"] == "stopped"


class _StopWatchdogLoop(Exception):
    """Sentinel used to break out of the watchdog's `while True` after N ticks."""


def _run_watchdog_ticks(monkeypatch, ticks):
    """Run `_natural_end_watchdog` for exactly `ticks` iterations by making
    the stop event's wait raise after the desired number of ticks."""
    calls = {"n": 0}

    def fake_wait(_s):
        calls["n"] += 1
        if calls["n"] > ticks:
            raise _StopWatchdogLoop()

    monkeypatch.setattr(engine_adapter, "_watchdog_stop", MagicMock(wait=fake_wait))
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    monkeypatch.setattr(engine_adapter, "_media_loading_generation", None)
    with pytest.raises(_StopWatchdogLoop):
        engine_adapter._natural_end_watchdog()


def test_natural_end_watchdog_finalizes_on_dead_process(monkeypatch):
    """A dead mpv process must be detected without waiting on IPC at all, and
    finalize only after _WATCHDOG_CRASH_STREAK consecutive dead ticks."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)

    dead_proc = MagicMock()
    dead_proc.poll.return_value = 1
    dead_proc.returncode = 1
    monkeypatch.setattr(engine_adapter, "_mpv_proc", dead_proc)
    monkeypatch.setattr(engine_adapter, "_mpv", MagicMock())

    finalize_calls = []
    monkeypatch.setattr(engine_adapter, "_finalize_playback_error", lambda _gen, code, _msg: finalize_calls.append(code))

    _run_watchdog_ticks(monkeypatch, engine_adapter._WATCHDOG_CRASH_STREAK)

    assert finalize_calls == ["MPV_EXITED"]


def test_natural_end_watchdog_finalizes_on_ipc_unreachable(monkeypatch):
    """A live process whose IPC never succeeds (timeout/refused) must also be
    treated as a crash after _WATCHDOG_CRASH_STREAK consecutive failures."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)

    alive_proc = MagicMock()
    alive_proc.poll.return_value = None
    monkeypatch.setattr(engine_adapter, "_mpv_proc", alive_proc)

    mock_mpv = MagicMock()
    mock_mpv._send.return_value = {"error": "timeout"}
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    finalize_calls = []
    monkeypatch.setattr(engine_adapter, "_finalize_playback_error", lambda _gen, code, _msg: finalize_calls.append(code))

    _run_watchdog_ticks(monkeypatch, engine_adapter._WATCHDOG_CRASH_STREAK)

    assert finalize_calls == ["MPV_UNAVAILABLE"]
    mock_mpv._send.assert_called_with(["get_property", "idle-active"])


def test_natural_end_watchdog_still_finalizes_on_idle_streak(monkeypatch):
    """Regression guard: normal natural-end detection (mpv alive, IPC healthy,
    idle-active=True for _WATCHDOG_IDLE_STREAK ticks) must keep working."""
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setitem(engine_adapter._state, "duration_ms", 60000)

    alive_proc = MagicMock()
    alive_proc.poll.return_value = None
    monkeypatch.setattr(engine_adapter, "_mpv_proc", alive_proc)

    mock_mpv = MagicMock()
    mock_mpv._send.return_value = {"data": True, "error": "success"}
    monkeypatch.setattr(engine_adapter, "_mpv", mock_mpv)

    finalize_calls = []
    monkeypatch.setattr(engine_adapter, "_finalize_natural_end", lambda _gen: finalize_calls.append(1))

    _run_watchdog_ticks(monkeypatch, engine_adapter._WATCHDOG_IDLE_STREAK)

    assert len(finalize_calls) == 1


def test_scene_apply_reports_audio_failure(client, monkeypatch):
    monkeypatch.setattr(engine_adapter, 'scene_apply', lambda *_: (None, 'MPV_UNAVAILABLE'))
    response = client.post('/api/v1/scenes/apply', json={'scene_id': 'demo'})
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'MPV_UNAVAILABLE'
