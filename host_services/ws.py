"""
WebSocket 端点：ticket 验证、session.connected、心跳推送。
相当于 Java 的 @ServerEndpoint + 连接管理。
"""

import asyncio
import json
import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .auth_manager import consume_ws_ticket
from .config import HEARTBEAT_INTERVAL_SECONDS, STATE_PUBLISH_INTERVAL_SECONDS, WS_SEND_TIMEOUT_SECONDS
from . import engine_adapter

router = APIRouter()
_log = logging.getLogger(__name__)

# Connections and all send operations belong to the bound ASGI loop.
_connections: list[dict] = []
_sequence = 0
_event_loop: asyncio.AbstractEventLoop | None = None
_broadcast_tasks: set[asyncio.Task] = set()
_connection_tasks: set[asyncio.Task] = set()
_state_publisher_task: asyncio.Task | None = None


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop, _state_publisher_task
    if _state_publisher_task is not None and not _state_publisher_task.done():
        if _event_loop is loop:
            return
        raise RuntimeError("Close the previous WebSocket event loop before rebinding")
    _event_loop = loop
    _state_publisher_task = loop.create_task(_publish_state())


def publish_error(data: dict) -> None:
    loop = _event_loop
    if loop is None or loop.is_closed():
        return

    def dispatch():
        if _event_loop is not loop:
            return
        task = loop.create_task(broadcast("error.event", data))
        _broadcast_tasks.add(task)
        task.add_done_callback(_broadcast_tasks.discard)

    try:
        loop.call_soon_threadsafe(dispatch)
    except RuntimeError:
        # The ASGI loop can close between the snapshot and scheduling.
        return


async def close_event_loop() -> None:
    global _event_loop, _state_publisher_task
    _event_loop = None
    tasks = list(_broadcast_tasks)
    if _state_publisher_task is not None:
        tasks.append(_state_publisher_task)
        _state_publisher_task = None
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _broadcast_tasks.clear()
    connection_tasks = list(_connection_tasks)
    for task in connection_tasks:
        task.cancel()
    if connection_tasks:
        await asyncio.gather(*connection_tasks, return_exceptions=True)
    _connection_tasks.clear()


def _next_seq() -> int:
    global _sequence
    _sequence += 1
    return _sequence


def _ws_msg(msg_type: str, data: dict) -> str:
    return json.dumps({
        "type": msg_type,
        "timestamp": int(time.time() * 1000),
        "sequence": _next_seq(),
        "data": data,
    })


async def _send_text(conn: dict, message: str) -> None:
    async with asyncio.timeout(WS_SEND_TIMEOUT_SECONDS):
        async with conn["send_lock"]:
            await conn["ws"].send_text(message)


async def _send_to_subscriber(conn: dict, message: str) -> bool:
    try:
        await _send_text(conn, message)
    except Exception as exc:
        if not isinstance(exc, WebSocketDisconnect):
            _log.exception("WebSocket send failed for session %s", conn["session_id"])
        if conn in _connections:
            _connections.remove(conn)
        conn["task"].cancel()
        return False
    return True


async def _send_state(conn: dict, snapshots: dict, identities: dict) -> None:
    previous = conn.setdefault("last_state", {})
    for kind, data in snapshots.items():
        if kind in conn["subscribe"] and previous.get(kind) != identities[kind]:
            if not await _send_to_subscriber(conn, _ws_msg(kind, data)):
                return
            previous[kind] = identities[kind]


def _read_state_snapshots(subscribed: set[str]) -> dict[str, dict]:
    snapshots = {}
    if "runtime.state" in subscribed:
        snapshots["runtime.state"] = engine_adapter.get_runtime_state_snapshot()
    if "playback.progress" in subscribed:
        snapshots["playback.progress"] = engine_adapter.get_playback_progress_snapshot()
    if "device.status" in subscribed:
        snapshots["device.status"] = {"devices": engine_adapter.get_state()["devices"]}
    return snapshots


async def _publish_state() -> None:
    state_types = {"runtime.state", "playback.progress", "device.status"}
    while True:
        subscribed = {kind for conn in _connections for kind in conn["subscribe"]} & state_types
        if subscribed:
            reading = asyncio.create_task(asyncio.to_thread(_read_state_snapshots, subscribed))
            try:
                snapshots = await asyncio.shield(reading)
            except asyncio.CancelledError:
                await asyncio.gather(reading, return_exceptions=True)
                raise
            except Exception:
                _log.exception("Unable to read Host WebSocket state")
            else:
                identities = dict(snapshots)
                if "device.status" in snapshots:
                    identities["device.status"] = {"devices": [
                        {key: value for key, value in device.items() if key != "last_seen_ms"}
                        for device in snapshots["device.status"]["devices"]
                    ]}
                await asyncio.gather(*(
                    _send_state(conn, snapshots, identities) for conn in list(_connections)
                ))
        await asyncio.sleep(STATE_PUBLISH_INTERVAL_SECONDS)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket, ticket: str = ""):
    # ── ticket 验证 ──
    info = consume_ws_ticket(ticket)
    if info is None:
        await ws.close(code=4401, reason="Invalid or expired ticket")
        return

    await ws.accept()

    session_id = info["session_id"]
    subscribe = info["subscribe"]
    conn = {
        "ws": ws, "session_id": session_id, "subscribe": subscribe,
        "send_lock": asyncio.Lock(),
    }
    _connections.append(conn)
    task = asyncio.current_task()
    conn["task"] = task
    if task is not None:
        _connection_tasks.add(task)

    receive_task = None
    try:
        # 发送 session.connected
        await _send_text(conn, _ws_msg("session.connected", {
            "session_id": session_id,
            "subscribe": subscribe,
        }))

        # Keep exactly one reader so disconnect is observed even without heartbeat.
        receive_task = asyncio.create_task(ws.receive())
        while True:
            done, _ = await asyncio.wait(
                {receive_task}, timeout=HEARTBEAT_INTERVAL_SECONDS,
            )
            if done:
                message = receive_task.result()
                if message["type"] == "websocket.disconnect":
                    break
                receive_task = asyncio.create_task(ws.receive())
                continue
            if "heartbeat" in subscribe:
                await _send_text(conn, _ws_msg("heartbeat", {
                    "session_id": session_id,
                }))
    except WebSocketDisconnect:
        pass
    except Exception:
        _log.exception("WebSocket connection failed for session %s", session_id)
        raise
    finally:
        if receive_task is not None and not receive_task.done():
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        if conn in _connections:
            _connections.remove(conn)
        if task is not None:
            _connection_tasks.discard(task)


async def broadcast(msg_type: str, data: dict):
    """供 router 在状态变更后调用，向所有订阅该类型的连接推送"""
    msg = _ws_msg(msg_type, data)
    await asyncio.gather(*(
        _send_to_subscriber(conn, msg) for conn in list(_connections)
        if msg_type in conn["subscribe"]
    ))
