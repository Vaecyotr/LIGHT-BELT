"""Native Wayland playback and persistent service configuration contracts."""

import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from host_services import config, engine_adapter, main
from host_services import runtime_health


def test_mpv_uses_native_wayland_and_immediate_black_window(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setattr(config, "wayland_display_available", lambda: True)
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_mpv_proc", None)
    monkeypatch.setattr(engine_adapter.os.path, "exists", lambda _path: False)
    monkeypatch.setattr(engine_adapter.os, "makedirs", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(engine_adapter, "_wait_until", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(engine_adapter, "MpvClient", lambda _path: MagicMock())
    popen = MagicMock(return_value=MagicMock(stderr=iter([])))
    monkeypatch.setattr(engine_adapter.subprocess, "Popen", popen)

    engine_adapter._ensure_mpv()

    args, options = popen.call_args
    assert "--force-window=immediate" in args[0]
    assert "--gpu-context=wayland" in args[0]
    assert "--vo=gpu" in args[0]
    assert options["env"]["WAYLAND_DISPLAY"] == "wayland-1"
    assert "DISPLAY" not in options["env"]
    assert "XAUTHORITY" not in options["env"]


def test_wayland_startup_does_not_run_x11_dpms(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    run = MagicMock()
    monkeypatch.setattr(engine_adapter.subprocess, "run", run)
    asyncio.run(main._disable_dpms())
    run.assert_not_called()


def test_user_host_unit_uses_session_runtime_and_persistent_credentials():
    text = Path("systemd/user/light-belt-host.service").read_text(encoding="utf-8")
    assert "WantedBy=default.target" in text
    assert "RuntimeDirectory=light-belt" in text
    assert "MPV_SOCKET_PATH=%t/light-belt/mpv.sock" in text
    assert "EnvironmentFile=%h/.config/light-belt/host.env" in text
    assert "DISPLAY=:0" not in text
    assert "XAUTHORITY=" not in text


def test_session_activation_imports_actual_wayland_environment():
    text = Path("scripts/deploy/rk3588/start-host-session.sh").read_text(encoding="utf-8")
    assert "import-environment" in text
    assert "WAYLAND_DISPLAY" in text
    assert "restart light-belt-host.service" in text
    assert "gsettings" not in text
    assert "wayland-0" not in text


def test_wayland_backend_waits_for_graphical_login_without_launching_x11(monkeypatch):
    monkeypatch.setenv("MPV_GPU_CONTEXT", "wayland")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(engine_adapter.os.path, "exists", lambda _path: False)
    popen = MagicMock()
    monkeypatch.setattr(engine_adapter.subprocess, "Popen", popen)
    with pytest.raises(engine_adapter.MpvUnavailableError, match="GNOME Wayland"):
        engine_adapter._ensure_mpv()
    popen.assert_not_called()


def test_wayland_display_detection_does_not_require_xrandr(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-2")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1002")
    monkeypatch.setattr(engine_adapter, "VIDEO_DETECT_ENABLED", True)
    monkeypatch.setattr(config, "wayland_display_available", lambda: True)
    run = MagicMock(side_effect=AssertionError("X11 probe in Wayland session"))
    monkeypatch.setattr(engine_adapter.subprocess, "run", run)
    assert engine_adapter._detect_video_available() is True
    run.assert_not_called()


def test_nonexistent_wayland_socket_is_not_a_display(monkeypatch, tmp_path):
    monkeypatch.setenv("WAYLAND_DISPLAY", "missing-wayland-socket")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert config.wayland_display_available() is False


@pytest.mark.parametrize("vo,fullscreen,ready", [(True, True, True), (False, True, False), (True, False, False)])
def test_mpv_health_requires_configured_fullscreen_video(monkeypatch, vo, fullscreen, ready):
    from light_engine.media import mpv_adapter
    client = MagicMock()
    values = {"vo-configured": vo, "fullscreen": fullscreen,
              "idle-active": True, "options/gpu-context": "wayland"}
    client.get_property.side_effect = values.__getitem__
    monkeypatch.setattr(mpv_adapter, "MpvIPCAdapter", lambda _path: client)
    result = runtime_health.check_mpv("audit.sock")
    assert result["mpv_ready"] is ready
    client.close.assert_called_once()
