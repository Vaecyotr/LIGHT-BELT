"""
LIGHT-BELT Host Service 入口。
相当于 Spring Boot 的 main() + @SpringBootApplication。

启动方式：
  cd host_service
  python main.py

本地 Postman 测试地址：
  REST:      http://localhost:8443/api/v1/status
  WebSocket: ws://localhost:8443/ws?ticket=<ticket>
"""

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
from .config import validate_security_configuration

validate_security_configuration()

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
    import subprocess as _sp
    env = {"DISPLAY": MPV_DISPLAY, "XAUTHORITY": MPV_XAUTHORITY, "PATH": os.environ.get("PATH", "/usr/bin")}
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
from .routers import status, auth, state, shows, capabilities
from .routers import playback, lights, effects, audio, scenes, brightness
from . import ws

app.include_router(status.router)
app.include_router(auth.router)
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


async def _start_runtime():
    import asyncio
    from . import engine_adapter
    if engine_adapter.ENGINE_ADAPTER == "real":
        from light_engine.config import Config
        Config(Path(engine_adapter.ENGINE_PROFILE_PATH))
    ws.bind_event_loop(asyncio.get_running_loop())
    engine_adapter._start_natural_end_watchdog()
    app.state.ready = engine_adapter.ENGINE_ADAPTER != "real" or engine_adapter._real_adapter is not None


async def _stop_runtime():
    from . import engine_adapter
    app.state.ready = False
    await ws.close_event_loop()
    engine_adapter.shutdown()


from fastapi.staticfiles import StaticFiles

_kiosk_dist = Path(__file__).resolve().parent.parent / "kiosk" / "dist"
if _kiosk_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_kiosk_dist), html=True), name="kiosk")


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
