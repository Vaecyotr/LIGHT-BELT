"""Subscribed V1 state events follow real Host snapshots and connection lifetime."""

import asyncio
import json
import threading
from contextlib import asynccontextmanager

from fastapi import WebSocket
import pytest

from host_services import auth_manager, engine_adapter, ws


@asynccontextmanager
async def connected(subscribe, send_failure=None):
    incoming = asyncio.Queue()
    outgoing = asyncio.Queue()
    await incoming.put({"type": "websocket.connect"})
    async def send(message):
        if send_failure is not None:
            send_failure(message)
        await outgoing.put(message)

    socket = WebSocket({"type": "websocket", "path": "/ws"}, incoming.get, send)
    ticket = auth_manager.create_ws_ticket(subscribe)["ws_ticket"]
    task = asyncio.create_task(ws.ws_endpoint(socket, ticket))
    try:
        assert (await asyncio.wait_for(outgoing.get(), 1))["type"] == "websocket.accept"
        initial = json.loads((await asyncio.wait_for(outgoing.get(), 1))["text"])
        assert initial["type"] == "session.connected"
        yield outgoing
    finally:
        await incoming.put({"type": "websocket.disconnect", "code": 1000})
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def receive_event(outgoing, kind, predicate=lambda data: True):
    async def receive():
        while True:
            message = await outgoing.get()
            if message["type"] == "websocket.send":
                payload = json.loads(message["text"])
                if payload["type"] == kind and predicate(payload["data"]):
                    return payload

    return await asyncio.wait_for(receive(), 1)


@pytest.fixture
def state_source(monkeypatch):
    monkeypatch.setattr(ws, "STATE_PUBLISH_INTERVAL_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(engine_adapter, "_probe_devices", lambda: None)
    monkeypatch.setattr(engine_adapter, "_mpv", None)
    monkeypatch.setattr(engine_adapter, "_state", {
        **engine_adapter._state,
        "playback_state": "stopped", "show_id": None,
        "position_ms": 0, "duration_ms": 0, "brightness": 1.0,
    })
    monkeypatch.setattr(engine_adapter, "_devices", [{
        "device_id": "strip_11", "device_type": "wled", "status": "offline",
        "last_output_ms": 0, "connection_confirmed": False, "error_code": None,
        "host": "192.0.2.1",
    }])


def test_runtime_and_device_changes_reach_subscribers(state_source):
    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["runtime.state", "device.status"]) as outgoing:
                await receive_event(outgoing, "runtime.state")
                device = await receive_event(outgoing, "device.status")
                assert "host" not in device["data"]["devices"][0]
                engine_adapter._state["brightness"] = 0.25
                engine_adapter._devices[0]["status"] = "online"
                engine_adapter._devices[0]["connection_confirmed"] = True
                runtime = await receive_event(outgoing, "runtime.state", lambda data: data["brightness"] == 0.25)
                device = await receive_event(outgoing, "device.status", lambda data: data["devices"][0]["status"] == "online")
                assert runtime["data"]["brightness"] == 0.25
                assert device["data"]["devices"][0]["connection_confirmed"] is True
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_progress_uses_live_position_and_initializes_late_subscribers(state_source, monkeypatch):
    class Player:
        position = 1.25

        def get_idle_active(self):
            return False

        def get_position(self):
            return self.position

    player = Player()
    monkeypatch.setattr(engine_adapter, "_mpv", player)
    engine_adapter._state.update(playback_state="playing", show_id="show-one", duration_ms=60000)
    assert engine_adapter.get_playback_progress_snapshot()["position_ms"] == 1250

    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["playback.progress"]) as first:
                progress = await receive_event(first, "playback.progress")
                assert progress["data"] == {
                    "playback_state": "playing", "show_id": "show-one",
                    "position_ms": 1250, "duration_ms": 60000,
                }
                player.position = 2.5
                await receive_event(first, "playback.progress", lambda data: data["position_ms"] == 2500)
                async with connected(["playback.progress"]) as second:
                    progress = await receive_event(second, "playback.progress")
                    assert progress["data"]["position_ms"] == 2500
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_runtime_subscription_filters_other_types_and_deduplicates_snapshots(state_source):
    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["runtime.state"]) as outgoing:
                await receive_event(outgoing, "runtime.state")
                await asyncio.sleep(0.05)
                assert outgoing.empty()
                engine_adapter._state["brightness"] = 0.4
                event = await receive_event(outgoing, "runtime.state")
                assert event["data"]["brightness"] == 0.4
                await asyncio.sleep(0.05)
                assert outgoing.empty()
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_publisher_does_not_read_state_without_state_subscribers(state_source, monkeypatch):
    reads = []

    def record_read():
        reads.append(True)
        return {}

    monkeypatch.setattr(engine_adapter, "get_runtime_state_snapshot", record_read)
    monkeypatch.setattr(engine_adapter, "get_playback_progress_snapshot", record_read)
    monkeypatch.setattr(engine_adapter, "get_state", record_read)

    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["error.event"]):
                await asyncio.sleep(0.05)
                assert reads == []
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_device_probe_timestamp_alone_does_not_emit_state_event(state_source, monkeypatch):
    def probe():
        device = engine_adapter._devices[0]
        device["last_seen_ms"] = device.get("last_seen_ms", 0) + 1

    monkeypatch.setattr(engine_adapter, "_probe_devices", probe)

    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["device.status"]) as outgoing:
                initial = await receive_event(outgoing, "device.status")
                await asyncio.sleep(0.05)
                assert outgoing.empty()
                engine_adapter._devices[0]["last_output_ms"] = 100
                changed = await receive_event(outgoing, "device.status")
                assert changed["data"]["devices"][0]["last_output_ms"] == 100
                assert changed["data"]["devices"][0]["last_seen_ms"] > initial["data"]["devices"][0]["last_seen_ms"]
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_one_client_send_failure_does_not_stop_other_state_subscribers(state_source):
    async def run():
        failed = asyncio.Event()

        def fail_state_send(message):
            if message["type"] == "websocket.send" and json.loads(message["text"])["type"] == "runtime.state":
                failed.set()
                raise RuntimeError("client transport failed")

        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["runtime.state"]) as healthy:
                await receive_event(healthy, "runtime.state")
                async with connected(["runtime.state"], fail_state_send):
                    await asyncio.wait_for(failed.wait(), 1)
                    engine_adapter._state["brightness"] = 0.6
                    event = await receive_event(healthy, "runtime.state", lambda data: data["brightness"] == 0.6)
                    assert event["data"]["brightness"] == 0.6
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_one_client_send_failure_does_not_stop_error_broadcast(state_source):
    def fail_error_send(message):
        if message["type"] == "websocket.send" and json.loads(message["text"])["type"] == "error.event":
            raise RuntimeError("client transport failed")

    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["error.event"], fail_error_send):
                async with connected(["error.event"]) as healthy:
                    await ws.broadcast("error.event", {"code": "MEDIA_ERROR"})
                    event = await receive_event(healthy, "error.event")
                    assert event["data"] == {"code": "MEDIA_ERROR"}
        finally:
            await ws.close_event_loop()

    asyncio.run(run())


def test_repeated_bind_does_not_leave_an_unowned_publisher(state_source):
    async def run():
        loop = asyncio.get_running_loop()
        ws.bind_event_loop(loop)
        first = ws._state_publisher_task
        try:
            ws.bind_event_loop(loop)
            await ws.close_event_loop()
            assert first.done()
        finally:
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)

    asyncio.run(run())


def test_shutdown_waits_for_inflight_snapshot_read(state_source, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    original = engine_adapter.get_runtime_state_snapshot

    def read():
        started.set()
        release.wait(timeout=1)
        finished.set()
        return original()

    monkeypatch.setattr(engine_adapter, "get_runtime_state_snapshot", read)

    async def run():
        ws.bind_event_loop(asyncio.get_running_loop())
        try:
            async with connected(["runtime.state"]):
                assert await asyncio.to_thread(started.wait, 1)

                async def release_read():
                    await asyncio.sleep(0.03)
                    release.set()

                releasing = asyncio.create_task(release_read())
                try:
                    await ws.close_event_loop()
                    assert finished.is_set()
                finally:
                    release.set()
                    await releasing
        finally:
            release.set()
            await ws.close_event_loop()

    asyncio.run(run())
