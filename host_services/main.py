r"""LIGHT-BELT Host Service application and module entry point.

From the repository root, start the development service with:
``.\.python\Scripts\python.exe -m host_services``.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from .runtime_health import capture_identity

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import HOST, PORT, ENABLE_TLS, TLS_CERTFILE, TLS_KEYFILE, MPV_DISPLAY, MPV_XAUTHORITY
from .config import STATE_PUBLISH_INTERVAL_SECONDS

_log = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(application: FastAPI):
    try:
        await _disable_dpms()
        await _start_runtime()
        yield
    finally:
        await _stop_runtime()


app = FastAPI(title="LIGHT-BELT Host Service", version="1.0", lifespan=_lifespan)
app.state.runtime_identity = capture_identity(Path(__file__).resolve().parent.parent)
app.state.ready = False
app.state.device_probe_task = None
app.state.lighting_update_task = None
app.state.lighting_audio_task = None
app.state.media_health_task = None


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        from .response import error
        return error(request, exc.detail["code"], exc.detail["message"], exc.status_code)
    return await http_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _disable_dpms():
    """禁用 X11 屏保 / DPMS，防止 HDMI 无信号导致黑屏后无法唤醒。"""
    from .config import uses_wayland
    if uses_wayland():
        return
    import subprocess as _sp
    env = os.environ.copy()
    env.setdefault("DISPLAY", MPV_DISPLAY)
    env.setdefault("XAUTHORITY", MPV_XAUTHORITY)
    for cmd in [
        ["xset", "s", "off"],       # 禁用屏保
        ["xset", "-dpms"],          # 禁用 DPMS（防 HDMI 信号关闭）
        ["xset", "s", "noblank"],   # 禁止空白屏保
    ]:
        try:
            _sp.run(cmd, env=env, timeout=5, capture_output=True)
        except Exception:
            pass


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    from .response import error as _error

    def _safe(obj):
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        if isinstance(obj, dict):
            return {k: _safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_safe(x) for x in obj]
        return obj

    details = _safe(exc.errors())
    first = details[0] if details else {}
    field = ".".join(str(loc) for loc in first.get("loc", []))
    msg = first.get("msg", "Validation error")
    return _error(
        request,
        code="INVALID_ARGUMENT",
        message=f"{field}: {msg}" if field else msg,
        status_code=400,
        details={"validation_errors": details},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.exception("Unhandled exception in %s %s", request.method, request.url.path)
    from .response import error as _error
    return _error(
        request,
        code="INTERNAL_ERROR",
        message=f"{type(exc).__name__}: {exc}",
        status_code=500,
    )

# ── 注册路由，相当于 @ComponentScan ──
from .routers import status, state, shows, capabilities
from .routers import playback, lights, effects, audio, scenes, brightness
from . import ws
from .routers import control

app.include_router(control.router)

app.include_router(status.router)
app.include_router(state.router)
app.include_router(shows.router)
app.include_router(capabilities.router)
app.include_router(playback.router)
app.include_router(lights.router)
app.include_router(effects.router)
app.include_router(audio.router)
app.include_router(scenes.router)
app.include_router(brightness.router)
app.include_router(ws.router)


async def _run_in_thread(function):
    task = asyncio.create_task(asyncio.to_thread(function))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


async def _poll_devices():
    from . import engine_adapter
    while True:
        try:
            await _run_in_thread(engine_adapter._probe_devices)
            prefs = engine_adapter._preferences
            if prefs is not None and prefs.data["intent"] == "off":
                await _run_in_thread(engine_adapter._reconcile_lighting)
        except Exception:
            _log.exception("Unable to collect device status")
        await asyncio.sleep(STATE_PUBLISH_INTERVAL_SECONDS)


def _update_readiness() -> None:
    from . import engine_adapter

    if engine_adapter.ENGINE_ADAPTER != "real":
        app.state.ready = True
        return
    system = engine_adapter._audio_system
    facts = system.snapshot() if system else {}
    bluetooth = facts.get("bluetooth", {})
    adapter = engine_adapter._real_adapter
    tasks = (app.state.device_probe_task, app.state.media_health_task,
             app.state.lighting_audio_task, app.state.lighting_update_task,
             ws._state_publisher_task)
    app.state.ready = bool(
        adapter is not None
        and bluetooth.get("available") and bluetooth.get("powered")
        and not bluetooth.get("route_error")
        and facts.get("audio_output_available")
        and facts.get("speaker", {}).get("status") != "fault"
        and getattr(adapter, "status", {}).get("role_phase") != "fault"
        and all(task is not None and not task.done() for task in tasks)
    )


async def _poll_media_health():
    from . import engine_adapter

    while True:
        try:
            await _run_in_thread(engine_adapter.observe_media)
        except Exception:
            _log.exception("Media observation failed")
        _update_readiness()
        await asyncio.sleep(STATE_PUBLISH_INTERVAL_SECONDS)


async def _watch_lighting_updates(update):
    from . import engine_adapter
    while True:
        await update.wait()
        update.clear()
        try:
            await _run_in_thread(engine_adapter._reconcile_lighting)
        except Exception:
            _log.exception("Unable to reconcile lighting after an audio update")


async def _watch_lighting_audio(audio_update, lighting_update):
    from . import engine_adapter
    while True:
        await audio_update.wait()
        audio_update.clear()
        try:
            await _run_in_thread(engine_adapter._refresh_lighting_audio)
        except (OSError, RuntimeError):
            _log.exception("Unable to publish the current lighting audio source")
        lighting_update.set()


async def _start_runtime():
    from . import engine_adapter
    from .bluetooth import AudioSystem, create_backend
    from .control_preferences import ControlPreferences, control_dir

    real = engine_adapter.ENGINE_ADAPTER == "real"
    directory = control_dir() if real or "LIGHT_BELT_CONTROL_DIR" in os.environ else None
    prefs = ControlPreferences(directory)
    engine_adapter._preferences = prefs
    engine_adapter._route_gate = real
    await _run_in_thread(engine_adapter.startup)
    ws.bind_event_loop(asyncio.get_running_loop())
    if real and engine_adapter._real_adapter is None:
        return

    lighting_update = asyncio.Event()
    audio_update = asyncio.Event()

    async def notify_lighting():
        audio_update.set()

    backend = create_backend(allow_real=real, program_pid=engine_adapter.program_mpv_pid)
    system = AudioSystem(
        backend,
        gate_mpv=lambda value: asyncio.to_thread(engine_adapter.gate_program, value),
        notify=notify_lighting,
    )
    engine_adapter._audio_system = system
    await system.start()
    await _run_in_thread(engine_adapter._reconcile_lighting)
    app.state.lighting_audio_task = asyncio.create_task(
        _watch_lighting_audio(audio_update, lighting_update)
    )
    app.state.lighting_update_task = asyncio.create_task(_watch_lighting_updates(lighting_update))
    if real:
        app.state.device_probe_task = asyncio.create_task(_poll_devices())
        app.state.media_health_task = asyncio.create_task(_poll_media_health())
        for task in (app.state.device_probe_task, app.state.media_health_task,
                     app.state.lighting_audio_task, app.state.lighting_update_task,
                     ws._state_publisher_task):
            task.add_done_callback(lambda _task: _update_readiness())
    _update_readiness()


async def _stop_runtime():
    from . import engine_adapter
    app.state.ready = False
    await ws.close_event_loop()
    tasks = [task for task in (app.state.device_probe_task, app.state.lighting_update_task,
                               app.state.lighting_audio_task, app.state.media_health_task)
             if task is not None]
    app.state.device_probe_task = app.state.lighting_update_task = None
    app.state.lighting_audio_task = None
    app.state.media_health_task = None
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    try:
        if engine_adapter._audio_system:
            await engine_adapter._audio_system.close()
    finally:
        try:
            await _run_in_thread(engine_adapter.shutdown)
        finally:
            engine_adapter._preferences = engine_adapter._audio_system = None
            engine_adapter._route_gate = False
            engine_adapter._lighting_error = None
            engine_adapter._power_error = engine_adapter._confirmed_off_hosts = None
            engine_adapter._off_request_submitted = False
            engine_adapter._wled_writes = []
            engine_adapter._brightness_error = None


def run():
    scheme = "https" if ENABLE_TLS else "http"
    print(f"Host Service starting on {scheme}://{HOST}:{PORT}")
    print(f"REST:   {scheme}://localhost:{PORT}/api/v1/status")
    print(f"Swagger: {scheme}://localhost:{PORT}/docs")
    kwargs: dict = {"host": HOST, "port": PORT}
    if ENABLE_TLS:
        kwargs["ssl_certfile"] = TLS_CERTFILE
        kwargs["ssl_keyfile"] = TLS_KEYFILE
    uvicorn.run(app, **kwargs)


if __name__ == "__main__":
    run()
