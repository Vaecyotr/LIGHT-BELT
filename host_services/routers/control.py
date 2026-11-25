"""Device-authorized controls for the cabin's network touch screen."""

import asyncio
import os
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.requests import HTTPConnection
from pydantic import BaseModel, Field
import sqlite3

from .. import engine_adapter
from ..control_terminal import ControlConflict, ControlTerminal, control_dir
from ..response import ok
from ..schemas import PlayRequest
from ..bluetooth import BackendUnavailable

COOKIE = "__Host-light-belt-control"
router = APIRouter(prefix="/control")


def origin():
    value = os.environ.get("LIGHT_BELT_CONTROL_ORIGIN", "")
    parsed = urlsplit(value)
    if value and (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("LIGHT_BELT_CONTROL_ORIGIN requires an exact HTTPS origin")
    return value


def denied(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


def require_origin(request: Request):
    expected = origin()
    if not expected:
        denied(503, "CONTROL_DISABLED", "控制终端尚未启用")
    if request.url.scheme != "https" or f"https://{request.url.netloc}" != expected:
        denied(403, "ORIGIN_DENIED", "请使用本舱的 HTTPS 地址")
    supplied = request.headers.get("origin")
    if (supplied or request.method != "GET") and supplied != expected:
        denied(403, "ORIGIN_DENIED", "请求来源无效")


def authorized(request: Request):
    require_origin(request)
    if not ControlTerminal(control_dir()).authorized(request.cookies.get(COOKIE)):
        denied(401, "UNAUTHORIZED", "请先登记此控制屏")


class Enrollment(BaseModel):
    code: str = Field(min_length=1, max_length=128)


class Mode(BaseModel):
    mode: str


class Intent(BaseModel):
    intent: str
    if_intent: str | None = None


@router.post("/enroll", dependencies=[Depends(require_origin)])
def enroll(body: Enrollment, request: Request):
    try:
        session = ControlTerminal(control_dir()).enroll(body.code)
    except sqlite3.DatabaseError as exc:
        denied(503, "ENROLLMENT_STORAGE_UNAVAILABLE", "控制屏登记数据损坏，需维护后重新登记")
    except ValueError as exc:
        denied(403, "ENROLLMENT_FAILED", str(exc))
    response = ok(request, {"enrolled": True})
    response.set_cookie(
        COOKIE,
        session,
        max_age=365 * 86400,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


controls = APIRouter(prefix="/control", dependencies=[Depends(authorized)])


@controls.get("/state")
def state(request: Request):
    return ok(request, engine_adapter.control_snapshot())


@controls.put("/analysis")
def analysis(body: Mode, request: Request):
    try:
        engine_adapter.control_mode(body.mode)
    except ValueError as exc:
        denied(400, "INVALID_ARGUMENT", str(exc))
    return state(request)


@controls.put("/lighting")
def lighting(body: Intent, request: Request):
    if body.intent not in ("follow", "music", "off"):
        denied(400, "INVALID_ARGUMENT", "未知灯光意图")
    try:
        engine_adapter.control_intent(body.intent, body.if_intent)
    except ControlConflict as exc:
        denied(409, "STALE_INTENT", str(exc))
    return state(request)


@controls.post("/play")
def play(body: PlayRequest, request: Request):
    result, err = engine_adapter.playback_play(
        body.show_id, body.start_position_ms, preserve_controls=True
    )
    if err:
        denied(409, err, f"无法开始节目：{err}")
    return ok(request, result)


class Speaker(BaseModel):
    device: str | None


class Challenge(BaseModel):
    challenge: str
    device: str
    accept: bool
    value: str | None = Field(default=None, max_length=16)


class Attempt(BaseModel):
    operation_id: str


async def bluetooth_command(request, method, *args):
    service = engine_adapter._audio_system
    if service is None:
        denied(503, "ADAPTER_UNAVAILABLE", "蓝牙服务未就绪")
    try:
        result = await getattr(service, method)(*args)
    except BackendUnavailable as exc:
        detail = str(exc)
        if "capacity" in detail:
            denied(409, "CONNECTION_LIMIT", "已连接或正在连接两台手机，请先断开一台")
        if "expired" in detail:
            denied(410, "CHALLENGE_EXPIRED", "配对请求已过期")
        denied(503, "BLUETOOTH_UNAVAILABLE", detail)
    snapshot = await asyncio.to_thread(engine_adapter.control_snapshot)
    response = ok(request, {"result": result, **snapshot})
    response.status_code = 202
    return response


@controls.post("/bluetooth/scan")
async def scan(request: Request):
    return await bluetooth_command(request, "scan")


@controls.post("/bluetooth/add")
async def add(request: Request):
    return await bluetooth_command(request, "add")


@controls.delete("/bluetooth/add")
async def close_window(request: Request):
    return await bluetooth_command(request, "close_add")


@controls.post("/bluetooth/pair/cancel")
async def cancel(body: Attempt, request: Request):
    return await bluetooth_command(request, "cancel_pair", body.operation_id)


@controls.post("/bluetooth/answer")
async def answer(body: Challenge, request: Request):
    return await bluetooth_command(
        request,
        "answer_challenge",
        body.challenge,
        body.device,
        body.accept,
        body.value,
    )


@controls.put("/speaker")
async def speaker(body: Speaker, request: Request):
    return await bluetooth_command(request, "set_speaker", body.device)


@controls.post("/bluetooth/devices/{device}/{action}")
async def device_action(device: str, action: str, request: Request):
    if action not in {"pair", "connect", "disconnect"}:
        denied(404, "NOT_FOUND", "未知操作")
    return await bluetooth_command(request, action, device)


@controls.delete("/bluetooth/devices/{device}")
async def forget(device: str, request: Request):
    return await bluetooth_command(request, "remove", device)


class TerminalBoundary:
    """Apply device trust to the legacy facade on a managed listener."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        expected = origin()
        if expected and (path.startswith("/api/v1/") or path == "/ws"):
            connection = HTTPConnection(scope)
            secure = scope.get("scheme") in ("https", "wss")
            # Optional loopback upstream for the network-isolated legacy APP listener.
            peer = scope.get("client")
            key = os.getenv("LIGHT_BELT_LEGACY_PROXY_TOKEN", "")
            supplied = connection.headers.get("x-light-belt-legacy-proxy", "")
            if (
                secure
                and peer
                and peer[0] in {"127.0.0.1", "::1"}
                and len(key) >= 32
                and secrets.compare_digest(supplied.encode(), key.encode())
            ):
                await self.app(scope, receive, send)
                return
            if (
                secure
                and peer
                and peer[0] in {"127.0.0.1", "::1"}
                and path == "/api/v1/status"
                and scope.get("method") == "GET"
            ):
                await self.app(scope, receive, send)
                return
            valid_origin = connection.headers.get("origin") == expected
            read = scope.get("method") == "GET" and "origin" not in connection.headers
            if not (
                secure
                and "https://" + connection.url.netloc == expected
                and (valid_origin or read)
                and ControlTerminal(control_dir()).authorized(
                    connection.cookies.get(COOKIE)
                )
            ):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4401})
                else:
                    await JSONResponse(
                        {
                            "ok": False,
                            "error": {
                                "code": "UNAUTHORIZED",
                                "message": "请先登记控制屏",
                            },
                        },
                        401,
                    )(scope, receive, send)
                return
        await self.app(scope, receive, send)
