"""Cabin business controls on the Host listener."""

import asyncio
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import engine_adapter
from ..control_preferences import ControlConflict
from ..response import ok
from ..schemas import PlayRequest
from ..bluetooth import BackendUnavailable

router = APIRouter(prefix="/control", tags=["Control"])


def denied(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


class Mode(BaseModel):
    mode: str


class Intent(BaseModel):
    intent: str
    if_intent: str | None = None


@router.get("/state")
def state(request: Request):
    return ok(request, engine_adapter.control_snapshot())


@router.put("/analysis")
def analysis(body: Mode, request: Request):
    try:
        engine_adapter.control_mode(body.mode)
    except ValueError as exc:
        denied(400, "INVALID_ARGUMENT", str(exc))
    return state(request)


@router.put("/lighting")
def lighting(body: Intent, request: Request):
    if body.intent not in ("follow", "music", "off"):
        denied(400, "INVALID_ARGUMENT", "未知灯光意图")
    try:
        engine_adapter.control_intent(body.intent, body.if_intent)
    except ControlConflict as exc:
        denied(409, "STALE_INTENT", str(exc))
    return state(request)


@router.post("/play")
def play(body: PlayRequest, request: Request):
    result, err = engine_adapter.playback_play(
        body.show_id, body.start_position_ms, preserve_controls=True
    )
    if err:
        denied(503 if err in {"ENGINE_UNAVAILABLE", "MPV_UNAVAILABLE"} else 409,
               err, f"无法开始节目：{err}")
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


@router.post("/bluetooth/scan")
async def scan(request: Request):
    return await bluetooth_command(request, "scan")


@router.post("/bluetooth/add")
async def add(request: Request):
    return await bluetooth_command(request, "add")


@router.delete("/bluetooth/add")
async def close_window(request: Request):
    return await bluetooth_command(request, "close_add")


@router.post("/bluetooth/pair/cancel")
async def cancel(body: Attempt, request: Request):
    return await bluetooth_command(request, "cancel_pair", body.operation_id)


@router.post("/bluetooth/answer")
async def answer(body: Challenge, request: Request):
    return await bluetooth_command(
        request,
        "answer_challenge",
        body.challenge,
        body.device,
        body.accept,
        body.value,
    )


@router.put("/speaker")
async def speaker(body: Speaker, request: Request):
    return await bluetooth_command(request, "set_speaker", body.device)


@router.post("/bluetooth/devices/{device}/{action}")
async def device_action(device: str, action: str, request: Request):
    if action not in {"pair", "connect", "disconnect"}:
        denied(404, "NOT_FOUND", "未知操作")
    return await bluetooth_command(request, action, device)


@router.delete("/bluetooth/devices/{device}")
async def forget(device: str, request: Request):
    return await bluetooth_command(request, "remove", device)
