"""Host state reads and background work obey the application lifetime."""

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from host_services import engine_adapter
from host_services import main as host


def test_state_read_only_copies_existing_device_snapshot(monkeypatch):
    monkeypatch.setattr(engine_adapter, "_devices", [{
        "device_id": "one", "host": "192.0.2.1", "status": "offline",
    }])

    def reject_probe():
        raise AssertionError("state reads must not perform network I/O")

    monkeypatch.setattr(engine_adapter, "_probe_devices", reject_probe)
    state = engine_adapter.get_state()
    assert state["devices"] == [{"device_id": "one", "status": "offline"}]
    state["devices"][0]["status"] = "changed"
    assert engine_adapter._devices[0]["status"] == "offline"


def test_state_read_does_not_wait_for_profile_resolution_lock():
    locked = threading.Event()
    release = threading.Event()

    def resolve():
        with engine_adapter._profile_refresh_lock:
            locked.set()
            release.wait(timeout=1)

    thread = threading.Thread(target=resolve)
    thread.start()
    try:
        assert locked.wait(1)
        start = time.monotonic()
        engine_adapter.get_state()
        assert time.monotonic() - start < 0.5
    finally:
        release.set()
        thread.join(timeout=2)


def test_probe_publishes_complete_batch_and_closes_responses(monkeypatch):
    devices = [{"device_id": name, "host": host, "device_type": "wled_board",
                "status": "offline", "enabled": True}
               for name, host in [("one", "192.0.2.1"), ("two", "192.0.2.2")]]
    monkeypatch.setattr(engine_adapter, "_devices", devices)
    closed = []

    class Response:
        def close(self):
            closed.append(True)

    def fetch(*_args, **_kwargs):
        assert all(device["status"] == "offline" for device in engine_adapter._devices)
        return Response()

    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", fetch)
    engine_adapter._probe_devices()
    assert all(device["status"] == "online" for device in engine_adapter._devices)
    assert closed == [True, True]


def test_probe_does_not_overwrite_a_replaced_profile(monkeypatch):
    old = {"device_id": "one", "host": "192.0.2.1", "device_type": "wled_board",
           "status": "offline", "enabled": True}
    new = {**old, "host": "192.0.2.2"}
    monkeypatch.setattr(engine_adapter, "_devices", [old])

    class Response:
        def close(self):
            pass

    def replace_profile(*_args, **_kwargs):
        engine_adapter._devices = [new]
        return Response()

    monkeypatch.setattr(engine_adapter.urllib.request, "urlopen", replace_profile)
    engine_adapter._probe_devices()
    assert engine_adapter._devices == [new]
    assert new["status"] == "offline"


def test_shutdown_stops_deferred_resolution_before_it_runs(monkeypatch):
    waiting = threading.Event()

    class StopEvent(threading.Event):
        def wait(self, timeout=None):
            waiting.set()
            return super().wait(timeout)

    stop = StopEvent()
    resolved = []
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_watchdog_stop", stop)
    monkeypatch.setattr(engine_adapter, "_watchdog_thread", None)
    monkeypatch.setattr(engine_adapter, "_real_adapter", None)
    monkeypatch.setattr(engine_adapter, "_mpv_observer", None)
    monkeypatch.setattr(engine_adapter, "_close_mpv_observer", lambda: None)
    monkeypatch.setattr(engine_adapter, "_stop_owned_mpv", lambda: None)
    monkeypatch.setattr(engine_adapter.time, "sleep", lambda _delay: stop.wait(1))
    monkeypatch.setattr(engine_adapter, "_run_resolve_nodes", lambda: resolved.append(True))
    monkeypatch.setattr(engine_adapter, "_load_layout_vocab", lambda: (frozenset({"all"}), [], []))
    monkeypatch.setattr(engine_adapter, "_devices", [])
    thread = threading.Thread(target=engine_adapter._deferred_re_resolve, daemon=True)
    monkeypatch.setattr(engine_adapter, "_deferred_re_resolve_thread", thread)
    thread.start()
    try:
        assert waiting.wait(1)
        engine_adapter.shutdown()
        thread.join(timeout=1)
        assert not thread.is_alive()
        assert resolved == []
    finally:
        stop.set()
        thread.join(timeout=2)


def test_importing_real_adapter_does_not_start_processes_or_threads():
    code = """
import subprocess, threading
def reject(*args, **kwargs):
    raise AssertionError('runtime started during import')
class ForbiddenProcess:
    def __init__(self, *args, **kwargs):
        reject()
subprocess.run = reject
subprocess.Popen = ForbiddenProcess
threading.Thread.start = reject
import host_services.engine_adapter as adapter
assert adapter._real_adapter is None
assert adapter._mpv is None
"""
    env = {**os.environ, "ENGINE_ADAPTER": "real", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-c", code], env=env,
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_lifespan_owns_single_probe_and_waits_for_inflight_work(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    events = []

    def probe():
        events.append("probe-start")
        started.set()
        release.wait(timeout=2)
        events.append("probe-finished")

    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_real_adapter", object())
    monkeypatch.setattr(engine_adapter, "startup", lambda: events.append("startup"))
    monkeypatch.setattr(engine_adapter, "shutdown", lambda: events.append("shutdown"))
    monkeypatch.setattr(engine_adapter, "_probe_devices", probe)
    monkeypatch.setattr(engine_adapter, "_reconcile_lighting", lambda: None)
    from host_services.bluetooth import DisabledBackend
    monkeypatch.setattr("host_services.bluetooth.create_backend", lambda **kwargs: DisabledBackend())
    monkeypatch.setattr(engine_adapter, "observe_media", lambda: None)

    async def run():
        await host._start_runtime()
        task = host.app.state.device_probe_task
        assert await asyncio.to_thread(started.wait, 1)
        try:
            for _ in range(3):
                engine_adapter.get_state()
            assert events.count("probe-start") == 1
            stopping = asyncio.create_task(host._stop_runtime())
            await asyncio.sleep(0)
            assert not stopping.done()
            release.set()
            await asyncio.wait_for(stopping, 2)
            assert task.done()
            assert host.app.state.device_probe_task is None
            assert events == ["startup", "probe-start", "probe-finished", "shutdown"]
        finally:
            release.set()
            await host._stop_runtime()

    asyncio.run(run())


def test_audio_notification_returns_before_lighting_reconciliation(tmp_path, monkeypatch):
    started, release, next_snapshot = threading.Event(), threading.Event(), threading.Event()
    refreshed_while_blocked = threading.Event()
    calls = []
    audio_calls = []

    def refresh_audio():
        audio_calls.append(None)
        if started.is_set() and not release.is_set():
            refreshed_while_blocked.set()

    def reconcile():
        calls.append(len(calls))
        if len(calls) == 2:
            started.set()
            assert release.wait(2)
        elif len(calls) == 3:
            next_snapshot.set()

    class System:
        def __init__(self, _backend, *, notify, **kwargs):
            self.notify = notify

        async def start(self):
            pass

        async def close(self):
            pass

    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "mock")
    monkeypatch.setattr(engine_adapter, "startup", lambda: None)
    monkeypatch.setattr(engine_adapter, "shutdown", lambda: None)
    monkeypatch.setattr(engine_adapter, "_reconcile_lighting", reconcile)
    monkeypatch.setattr(engine_adapter, "_refresh_lighting_audio", refresh_audio)
    monkeypatch.setattr("host_services.bluetooth.AudioSystem", System)

    async def run():
        await host._start_runtime()
        try:
            system = engine_adapter._audio_system
            await asyncio.wait_for(system.notify(), 0.5)
            assert await asyncio.to_thread(started.wait, 1)
            await system.notify()
            await system.notify()
            assert await asyncio.to_thread(refreshed_while_blocked.wait, 1)
            release.set()
            assert await asyncio.to_thread(next_snapshot.wait, 1)
        finally:
            release.set()
            await host._stop_runtime()
        assert len(calls) == 3
        assert len(audio_calls) >= 2

    asyncio.run(run())


def test_runtime_startup_recovers_corrupt_preferences_and_keeps_host_available(
    tmp_path, monkeypatch
):
    (tmp_path / "preferences.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "memory")
    monkeypatch.setattr(engine_adapter, "startup", lambda: None)
    monkeypatch.setattr(engine_adapter, "shutdown", lambda: None)
    monkeypatch.setattr(engine_adapter, "_reconcile_lighting", lambda: None)
    monkeypatch.setattr(host.ws, "bind_event_loop", lambda _loop: None)

    class Backend:
        pass

    class AudioSystem:
        def __init__(self, *_args, **_kwargs):
            pass

        async def start(self):
            pass

        async def close(self):
            pass

        def snapshot(self):
            return {}

    monkeypatch.setattr("host_services.bluetooth.create_backend", lambda **_kwargs: Backend())
    monkeypatch.setattr("host_services.bluetooth.AudioSystem", AudioSystem)

    async def run():
        await host._start_runtime()
        try:
            assert engine_adapter._preferences.data["intent"] == "off"
            assert engine_adapter._preferences.data["muted"] is True
            assert engine_adapter.control_snapshot()["preferences"]["recovery_error"]
        finally:
            await host._stop_runtime()

    asyncio.run(run())


def test_runtime_startup_ignores_retired_enrollment_database(tmp_path, monkeypatch):
    (tmp_path / "terminal.sqlite").write_bytes(b"not a sqlite database")
    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_real_adapter", object())
    monkeypatch.setattr(engine_adapter, "startup", lambda: None)
    monkeypatch.setattr(engine_adapter, "shutdown", lambda: None)
    monkeypatch.setattr(engine_adapter, "_reconcile_lighting", lambda: None)

    class Backend:
        pass

    class AudioSystem:
        def __init__(self, backend, **_kwargs):
            self.backend = backend

        async def start(self):
            assert not hasattr(self.backend, "terminal_generation")

        async def close(self):
            pass

        def snapshot(self):
            return {"bluetooth": {"available": True, "powered": True}, "audio_output_available": True}

    monkeypatch.setattr("host_services.bluetooth.create_backend", lambda **_kwargs: Backend())
    monkeypatch.setattr("host_services.bluetooth.AudioSystem", AudioSystem)

    async def run():
        await host._start_runtime()
        try:
            assert host.app.state.ready is True
            media_task = host.app.state.media_health_task
            media_task.cancel()
            await asyncio.gather(media_task, return_exceptions=True)
            assert host.app.state.ready is False
        finally:
            await host._stop_runtime()

    asyncio.run(run())


def test_rt5616_port_wait_keeps_rest_ready_and_reports_no_output(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient

    observed_port = {
        "available": False, "sink": "alsa_output.platform-rt5616-sound.stereo-fallback",
        "state": "SUSPENDED", "active_port": "headphones", "port_availability": "no",
    }
    facts = {
        "bluetooth": {"available": True, "powered": True}, "speaker": {"status": "waiting"},
        "audio_output_available": False, "audio_output": observed_port,
    }

    class AudioSystem:
        def __init__(self, *_args, **_kwargs):
            pass

        async def start(self):
            pass

        async def close(self):
            pass

        def snapshot(self):
            return facts

    monkeypatch.setenv("LIGHT_BELT_CONTROL_DIR", str(tmp_path))
    monkeypatch.setattr(engine_adapter, "ENGINE_ADAPTER", "real")
    monkeypatch.setattr(engine_adapter, "_real_adapter", SimpleNamespace(status={}))
    for method in ("startup", "shutdown", "_reconcile_lighting", "observe_media", "_probe_devices"):
        monkeypatch.setattr(engine_adapter, method, lambda: None)
    monkeypatch.setattr("host_services.bluetooth.create_backend", lambda **_kwargs: object())
    monkeypatch.setattr("host_services.bluetooth.AudioSystem", AudioSystem)

    with TestClient(host.app) as client:
        def assert_status(ready, output):
            assert client.get("/api/v1/status").json()["data"]["ready"] is ready
            for path in ("/api/v1/audio", "/control/state"):
                assert client.get(path).json()["data"]["audio_output_available"] is output

        assert_status(True, False)

        facts["audio_output"] = {**observed_port, "state": "unknown"}
        client.portal.call(host._update_readiness)
        assert_status(False, False)

        facts["audio_output"] = {"available": False, "reason": "missing sink"}
        client.portal.call(host._update_readiness)
        assert_status(False, False)

        facts["audio_output"] = observed_port
        facts["bluetooth"]["route_error"] = "owner mismatch"
        client.portal.call(host._update_readiness)
        assert_status(False, False)

        del facts["bluetooth"]["route_error"]
        facts["speaker"]["status"] = "fault"
        client.portal.call(host._update_readiness)
        assert_status(False, False)

        facts["speaker"]["status"] = "routed"
        facts["audio_output"] = {**observed_port, "available": True, "port_availability": "yes"}
        facts["audio_output_available"] = True
        client.portal.call(host._update_readiness)
        assert_status(True, True)
