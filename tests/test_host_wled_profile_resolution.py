from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest
from host_services import config as host_config
from host_services import engine_adapter
from host_services import wled_brightness


def test_default_host_profile_is_the_wled_runtime_profile() -> None:
    assert Path(host_config._DEFAULT_PROFILE).resolve() == host_config.WLED_RUNTIME_PROFILE.resolve()
    assert host_config.WLED_RUNTIME_PROFILE == Path("config/runtime/wled-ddp-mdns.yaml").resolve()


def test_real_mode_resolves_only_the_default_wled_runtime_profile(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0, stderr=""),
    )

    engine_adapter._run_resolve_nodes()

    assert len(calls) == 1
    assert calls[0][1:] == [
        str(Path("scripts/resolve_nodes.py").resolve()),
        "--template", str(host_config.WLED_TEMPLATE_PROFILE),
        "--out", str(host_config.WLED_RUNTIME_PROFILE),
    ]


def test_real_mode_custom_udp_v3_profile_does_not_run_wled_resolver(monkeypatch) -> None:
    calls: list[list[str]] = []
    maintenance = Path("config/profiles/udp-v3-nine-strip-maintenance.yaml").resolve()
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(maintenance))
    monkeypatch.setattr(engine_adapter.subprocess, "run", lambda *args, **kwargs: calls.append(args[0]))

    engine_adapter._run_resolve_nodes()

    assert calls == []


def test_maintenance_profile_derives_custom_udp_v3_devices(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_adapter,
        "ENGINE_PROFILE_PATH",
        str(Path("config/profiles/udp-v3-nine-strip-maintenance.yaml").resolve()),
    )
    from light_engine.config import Config
    Config.reset()

    _, _, devices = engine_adapter._load_layout_vocab()

    assert len(devices) == 9
    assert {device["device_type"] for device in devices} == {"custom_esp32_udp_v3"}


def test_real_mode_wled_resolver_nonzero_exit_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=7, stderr="resolver diagnostic"),
    )

    with pytest.raises(RuntimeError, match="7: resolver diagnostic"):
        engine_adapter._run_resolve_nodes()


def test_real_mode_wled_resolver_timeout_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "ENGINE_PROFILE_PATH", str(host_config.WLED_RUNTIME_PROFILE))
    monkeypatch.setattr(
        engine_adapter.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("resolve_nodes", 30)),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        engine_adapter._run_resolve_nodes()


def test_disabled_devices_are_never_probed_or_sent_http_output(monkeypatch) -> None:
    disabled = {
        "host": "wled-strip-32.local", "enabled": False, "status": "online",
        "connection_confirmed": True, "error_code": None, "last_output_ms": 17,
        "device_type": "wled_board",
    }
    enabled = {
        "host": "192.168.31.50", "enabled": True, "last_output_ms": 0,
        "device_type": "wled_board",
    }
    monkeypatch.setattr(engine_adapter, "_devices", [disabled, enabled])
    calls: list[object] = []
    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", lambda *args, **kwargs: calls.append(args) or None)
    monkeypatch.setattr(engine_adapter, "_now_ms", lambda: 99)
    monkeypatch.setattr(wled_brightness, "apply_scale", lambda devices, *args: calls.append(("scale", devices)))
    monkeypatch.setattr(wled_brightness, "apply_off", lambda devices, *args: calls.append(("off", devices)))

    engine_adapter._probe_devices()
    engine_adapter._mark_devices_output()
    engine_adapter._push_brightness_scale()
    engine_adapter._push_wled_off()

    assert disabled["status"] == "offline"
    assert disabled["connection_confirmed"] is False
    assert disabled["error_code"] == "MDNS_UNRESOLVED"
    assert disabled["last_output_ms"] == 17
    assert enabled["last_output_ms"] == 99
    assert all("wled-strip-32.local" not in str(call) for call in calls)


def test_enabled_custom_udp_v3_device_skips_wled_http_but_records_output(monkeypatch) -> None:
    custom = {
        "host": "192.0.2.31", "enabled": True, "device_type": "custom_esp32_udp_v3",
        "status": "offline", "connection_confirmed": False, "error_code": None,
        "last_output_ms": 0,
    }
    monkeypatch.setattr(engine_adapter, "_devices", [custom])
    calls: list[object] = []
    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(engine_adapter, "_now_ms", lambda: 123)
    monkeypatch.setattr(wled_brightness, "apply_scale", lambda *args: calls.append(("scale", args)))
    monkeypatch.setattr(wled_brightness, "apply_off", lambda *args: calls.append(("off", args)))

    engine_adapter._probe_devices()
    engine_adapter._push_brightness_scale()
    engine_adapter._push_wled_off()
    engine_adapter._mark_devices_output()

    assert calls == []
    assert custom["status"] == "offline"
    assert custom["last_output_ms"] == 123


def test_refresh_resolves_before_reloading_runtime_devices(monkeypatch) -> None:
    """A safe-boundary refresh must resolve first, then replace Host device data."""
    old_devices = [{"device_id": "strip_11", "host": "192.0.2.11"}]
    new_devices = [{"device_id": "strip_11", "host": "192.0.2.99"}]
    events: list[str] = []
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_devices", old_devices)
    monkeypatch.setattr(engine_adapter, "_valid_target_ids", frozenset({"strip_11"}))
    monkeypatch.setattr(engine_adapter, "_capability_targets", [])
    monkeypatch.setattr(engine_adapter, "_run_resolve_nodes", lambda: events.append("resolve"))
    monkeypatch.setattr(
        engine_adapter,
        "_load_layout_vocab",
        lambda: events.append("load") or (frozenset({"strip_11"}), [{"id": "strip_11"}], new_devices),
    )

    changed = engine_adapter._refresh_wled_profile(reason="test refresh")

    assert events == ["resolve", "load"]
    assert changed == {"strip_11"}
    assert engine_adapter._devices == new_devices
    assert engine_adapter._valid_target_ids == frozenset({"strip_11"})


def test_playback_refreshes_profile_before_starting_real_adapter(monkeypatch) -> None:
    """The playback adapter call (and its engine spawn) follows a profile refresh."""
    events: list[tuple[str, str]] = []
    adapter = SimpleNamespace(
        on_playback_stop=lambda: events.append(("adapter", "stop")),
        on_playback_start=lambda _show, _start: events.append(("adapter", "playback_start")),
    )
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(
        engine_adapter,
        "_refresh_wled_profile",
        lambda *, reason: events.append(("refresh", reason)) or set(),
    )
    monkeypatch.setattr(
        engine_adapter,
        "_find_show",
        lambda _show_id: {"show_id": "demo", "duration_ms": 1_000, "media_path": None},
    )
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_push_brightness_scale", lambda: None)
    monkeypatch.setattr(engine_adapter, "_mark_devices_output", lambda: None)

    data, error = engine_adapter.playback_play("demo", None)

    assert error is None
    assert data is not None
    assert events.index(("refresh", "playback session resolve")) < events.index(("adapter", "playback_start"))


def test_manual_command_refreshes_profile_before_real_adapter_call(monkeypatch) -> None:
    """Manual output must resolve before handing a frame to the real adapter."""
    events: list[tuple[str, str]] = []
    adapter = SimpleNamespace(
        on_manual_command=lambda _targets: events.append(("adapter", "manual_command")),
    )
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(
        engine_adapter,
        "_refresh_wled_profile",
        lambda *, reason: events.append(("refresh", reason)) or set(),
    )
    monkeypatch.setattr(
        engine_adapter,
        "_manual_targets",
        {"strip_11": {"target_id": "strip_11", "effect_type": "static", "color": [1, 0, 0]}},
    )
    monkeypatch.setattr(engine_adapter, "_push_brightness_scale", lambda: None)
    monkeypatch.setattr(engine_adapter, "_mark_devices_output", lambda: None)

    engine_adapter._apply_manual_targets()

    assert events.index(("refresh", "manual session resolve")) < events.index(("adapter", "manual_command"))


def test_playback_reset_refreshes_profile_before_resuming_real_adapter(monkeypatch) -> None:
    """Resuming YAML playback restarts only after the next-session profile refresh."""
    events: list[tuple[str, str]] = []
    adapter = SimpleNamespace(
        on_playback_resume_yaml=lambda: events.append(("adapter", "resume_yaml")) or True,
    )
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(
        engine_adapter,
        "_refresh_wled_profile",
        lambda *, reason: events.append(("refresh", reason)) or set(),
    )
    monkeypatch.setitem(engine_adapter._state, "playback_state", "playing")
    monkeypatch.setattr(engine_adapter, "_push_brightness_scale", lambda: None)

    data, error = engine_adapter.playback_reset()

    assert error is None
    assert data is not None
    assert events.index(("refresh", "playback resume resolve")) < events.index(("adapter", "resume_yaml"))


def test_deferred_refresh_never_restarts_active_adapter(monkeypatch) -> None:
    """Deferred discovery updates only the next profile; it never hot-restarts output."""
    events: list[str] = []
    adapter = SimpleNamespace(
        on_playback_start=lambda *_args: events.append("playback_start"),
        on_playback_resume_yaml=lambda: events.append("resume_yaml"),
        on_manual_command=lambda *_args: events.append("manual_command"),
        on_playback_stop=lambda: events.append("playback_stop"),
    )
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_real_adapter", adapter)
    monkeypatch.setattr(engine_adapter.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        engine_adapter,
        "_refresh_wled_profile",
        lambda *, reason: events.append(reason) or {"strip_11"},
    )

    engine_adapter._deferred_re_resolve()

    assert events == ["deferred re-resolve"]
