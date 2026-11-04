"""
WebSocket 端点：ticket 验证、session.connected、心跳推送。
相当于 Java 的 @ServerEndpoint + 连接管理。
"""

import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from .auth_manager import consume_ws_ticket
from .config import HEARTBEAT_INTERVAL_SECONDS
from . import engine_adapter

router = APIRouter()

# 活跃连接列表，供将来主动推送用
_connections: list[dict] = []
_sequence = 0
_event_loop: asyncio.AbstractEventLoop | None = None
_broadcast_tasks: set[asyncio.Task] = set()


def bind_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _event_loop
    _event_loop = loop


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
    global _event_loop
    _event_loop = None
    tasks = list(_broadcast_tasks)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _broadcast_tasks.clear()


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
    conn = {"ws": ws, "session_id": session_id, "subscribe": subscribe}
    _connections.append(conn)

    try:
        # 发送 session.connected
        await ws.send_text(_ws_msg("session.connected", {
            "session_id": session_id,
            "subscribe": subscribe,
        }))

        # 心跳循环
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            if "heartbeat" in subscribe:
                await ws.send_text(_ws_msg("heartbeat", {
                    "session_id": session_id,
                }))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if conn in _connections:
            _connections.remove(conn)


async def broadcast(msg_type: str, data: dict):
    """供 router 在状态变更后调用，向所有订阅该类型的连接推送"""
    msg = _ws_msg(msg_type, data)
    dead = []
    for conn in list(_connections):
        if msg_type in conn["subscribe"]:
            try:
                await conn["ws"].send_text(msg)
            except Exception:
                dead.append(conn)
    for c in dead:
        if c in _connections:
            _connections.remove(c)
