"""
集中配置，相当于 Spring 的 application.yml。
本地测试时不需要改任何值；部署 RK3588 时按注释调整。
"""

import os

# ── 网络 ──
HOST = "0.0.0.0"
PORT = 8443

# ── 认证 ──
JWT_SECRET = os.environ.get("LIGHT_BELT_JWT_SECRET", "light-belt-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600      # 1 小时
REFRESH_TOKEN_EXPIRE_SECONDS = 86400    # 24 小时
PAIRING_CODE = os.environ.get("LIGHT_BELT_PAIRING_CODE", "123456")

# ── WebSocket ──
WS_TICKET_EXPIRE_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 5
STATE_PUBLISH_INTERVAL_SECONDS = 1

# ── 场景 ──
SCENE_MAX_COUNT = 32
SCENE_FILE_PATH = "data/scenes.json"    # 运行时数据，不进 git

# ── 节目单 ──
# 保留的兼容声明；当前 engine_adapter 调用 loader 默认发现入口，未传此值。
# 实际节目先从 assets/ 发现，再使用 loader 的可选清单覆盖层。
SHOWS_MANIFEST_PATH = "data/shows_manifest.json"  # 运行时数据，不进 git

# ── 引擎 ──
import pathlib as _pl
_REPO_ROOT = _pl.Path(__file__).resolve().parent.parent
WLED_RUNTIME_PROFILE = _REPO_ROOT / "config" / "runtime" / "wled-ddp-mdns.yaml"
WLED_TEMPLATE_PROFILE = _REPO_ROOT / "config" / "profiles" / "rk3588-host-service.yaml"
_DEFAULT_PROFILE = str(WLED_RUNTIME_PROFILE)
ENGINE_PROFILE_PATH: str = os.environ.get("ENGINE_PROFILE_PATH", _DEFAULT_PROFILE)
# "mock" (default, in-memory) or "real" (subprocess light_engine)
ENGINE_ADAPTER: str = os.environ.get("ENGINE_ADAPTER", "mock")


def validate_security_configuration() -> None:
    if ENGINE_ADAPTER != "real":
        return
    if JWT_SECRET == "light-belt-dev-secret-change-in-production" or len(JWT_SECRET.encode("utf-8")) < 32:
        raise RuntimeError("Set LIGHT_BELT_JWT_SECRET to an independent secret of at least 32 bytes")
    if not PAIRING_CODE.strip() or PAIRING_CODE == "123456":
        raise RuntimeError("Set LIGHT_BELT_PAIRING_CODE to an independent pairing code")

# ── TLS（生产部署用，本地默认关闭） ──
ENABLE_TLS = False
TLS_CERTFILE = "/etc/light-belt/cert.pem"
TLS_KEYFILE = "/etc/light-belt/key.pem"

# ── mpv IPC（生产环境用；可用环境变量覆盖，本地调试可设 /tmp/mpv.sock） ──
MPV_SOCKET_PATH = os.environ.get("MPV_SOCKET_PATH", "/run/light-belt/mpv.sock")
# mpv 视频输出的 DISPLAY；仅当进程环境未设置 DISPLAY 时生效
MPV_DISPLAY = os.environ.get("MPV_DISPLAY", ":0")
# X11 兼容默认值；当前 pi 生产服务显式提供 MPV_XAUTHORITY，见 systemd unit。
# 仅当进程环境未设置 XAUTHORITY 时使用适配器选定的认证路径。
MPV_XAUTHORITY = os.environ.get("MPV_XAUTHORITY", "/home/topeet/.Xauthority")
# 保留的历史兼容设置。当前 mpv 启动使用 --fullscreen，不注入 --geometry；
# 修改此值不会改变当前播放器窗口，历史几何策略见 Git 记录。
MPV_GEOMETRY = os.environ.get("MPV_GEOMETRY", "1920x1080+0+0")

# 是否启用 xrandr 视频输出检测（mock 模式默认关闭以免测试环境报错）
VIDEO_DETECT_ENABLED: bool = ENGINE_ADAPTER == "real"

# ── 亮度乘数 ──
BRIGHTNESS_SCALE_DEFAULT: float = 0.5
WLED_HTTP_TIMEOUT_S: float = 1.0

# ── 版本信息 ──
SERVICE_NAME = "light-belt-host"
HOST_ID = "rk3588-main"
API_VERSION = "1.0"
SERVICE_VERSION = "1.0.0"
