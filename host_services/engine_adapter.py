"""
Engine Adapter —— 唯一和「下层」打交道的地方。

Mock 模式（ENGINE_ADAPTER=mock，默认）：所有状态存在内存里，不依赖 mpv /
light_engine / 硬件。

生产模式（ENGINE_ADAPTER=real）：同样的内存状态 + 真实 light_engine 子进程
（通过 _real_adapter）。测试永远跑 mock 模式，不受影响。
"""

import time
import json
import logging
import os
import sys
import uuid
import socket
import subprocess
import threading
from functools import wraps
from typing import Any, Callable
from light_engine.effects import get_effect_registration, list_effect_registrations
from .config import (
    SCENE_MAX_COUNT, SCENE_FILE_PATH, SHOWS_MANIFEST_PATH,
    ENGINE_PROFILE_PATH, ENGINE_ADAPTER, VIDEO_DETECT_ENABLED,
    WLED_RUNTIME_PROFILE, WLED_TEMPLATE_PROFILE,
    BRIGHTNESS_SCALE_DEFAULT, WLED_HTTP_TIMEOUT_S,
)

_log = logging.getLogger(__name__)

WLED_DEVICE_TYPE = "wled_board"
CUSTOM_UDP_V3_DEVICE_TYPE = "custom_esp32_udp_v3"


class MpvUnavailableError(RuntimeError):
    """Raised when mpv cannot be started or an IPC command cannot be confirmed."""


def _device_type_from_outputs(enabled_outputs: list[str]) -> str:
    selected = set(enabled_outputs) & {"ddp", "udp_v3"}
    if selected == {"ddp"}:
        return WLED_DEVICE_TYPE
    if selected == {"udp_v3"}:
        return CUSTOM_UDP_V3_DEVICE_TYPE
    raise ValueError(
        "outputs.enabled must select exactly one of ddp or udp_v3 for Host device typing"
    )


# ══════════════════════════════════════════════
# Layout vocabulary (derived at import time)
# ══════════════════════════════════════════════

def _load_layout_vocab():
    """Return (valid_target_ids, capability_targets, devices) from ENGINE_PROFILE_PATH."""
    try:
        from pathlib import Path as _Path
        from light_engine.config import Config as _Config
        from light_engine.mapping import Layout
        from .layout_vocab import derive_target_ids, derive_capabilities_targets, derive_device_list
        profile_path = _Path(ENGINE_PROFILE_PATH)
        if not profile_path.exists() and profile_path.resolve() == WLED_RUNTIME_PROFILE.resolve():
            profile_path = WLED_TEMPLATE_PROFILE
        config = _Config.get_instance(profile_path)
        layout = Layout.from_config(config)
        device_type = _device_type_from_outputs(config.get("outputs.enabled", []))
        return (
            derive_target_ids(layout),
            derive_capabilities_targets(layout),
            derive_device_list(layout, device_type=device_type),
        )
    except Exception as exc:
        _log.warning(
            "engine_adapter: failed to load layout vocab from %s: %s; using empty vocab",
            ENGINE_PROFILE_PATH, exc,
        )
        return frozenset({"all"}), [{"target_id": "all", "name": "all"}], []


def _run_resolve_nodes() -> None:
    """在进程内跑 resolve_nodes.py，确保 profile 里的 IP 是最新的。"""
    if ENGINE_ADAPTER != "real":
        return
    from pathlib import Path as _P
    if _P(ENGINE_PROFILE_PATH).resolve() != WLED_RUNTIME_PROFILE.resolve():
        return
    script = _P(__file__).resolve().parent.parent / "scripts" / "runtime" / "resolve_nodes.py"
    if not script.exists():
        raise RuntimeError(f"resolve_nodes.py not found at {script}")
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--template", str(WLED_TEMPLATE_PROFILE), "--out", ENGINE_PROFILE_PATH],
            timeout=30,
            capture_output=True,
            text=True,
        )
        for line in (result.stderr or "").splitlines():
            _log.info("[resolve_nodes] %s", line)
        if result.returncode:
            raise RuntimeError(
                f"resolve_nodes.py exited with {result.returncode}: {result.stderr or ''}".strip()
            )
    except Exception as exc:
        raise RuntimeError(f"resolve_nodes.py failed: {exc}") from exc


_valid_target_ids: frozenset[str]
_capability_targets: list[dict]
_devices: list[dict]
_profile_refresh_lock = threading.RLock()
_valid_target_ids, _capability_targets, _devices = _load_layout_vocab()


def _refresh_wled_profile(*, reason: str) -> set[str]:
    """Resolve and reload the WLED runtime profile at a safe process boundary.

    The active light_engine process owns its physical mapping for its lifetime,
    so this helper deliberately updates only the profile used by the *next*
    process. It never claims to hot-update an already running DDP destination.
    """
    global _valid_target_ids, _capability_targets, _devices
    if ENGINE_ADAPTER != "real":
        return set()
    with _profile_refresh_lock:
        old_devices = {d["device_id"]: d for d in _devices}
        old_hosts = {d["device_id"]: d.get("host") for d in _devices}
        _run_resolve_nodes()
        from light_engine.config import Config as _Cfg
        _Cfg.reset()
        new_ids, new_caps, new_devs = _load_layout_vocab()
        new_hosts = {d["device_id"]: d.get("host") for d in new_devs}
        for device in new_devs:
            previous = old_devices.get(device["device_id"], {})
            if (previous.get("host") == device.get("host")
                    and previous.get("enabled", True) == device.get("enabled", True)):
                for key in ("status", "connection_confirmed", "last_seen_ms", "last_output_ms", "error_code"):
                    if key in previous:
                        device[key] = previous[key]
        changed = {
            device_id
            for device_id in old_hosts.keys() | new_hosts.keys()
            if old_hosts.get(device_id) != new_hosts.get(device_id)
        }
        _valid_target_ids = new_ids
        _capability_targets = new_caps
        _devices = new_devs
        if changed:
            _log.info(
                "%s: updated %d device IPs: %s",
                reason,
                len(changed),
                ", ".join(
                    f"{device_id}: {old_hosts.get(device_id)} -> {new_hosts.get(device_id)}"
                    for device_id in sorted(changed)
                ),
            )
        else:
            _log.info("%s: all IPs unchanged", reason)
        return changed


# ══════════════════════════════════════════════
# mpv IPC 客户端
# ══════════════════════════════════════════════

class MpvClient:
    def __init__(
        self,
        sock_path: str,
        *,
        socket_factory: Callable[[], Any] | None = None,
    ):
        self._sock_path = sock_path
        self._socket_factory = socket_factory

    _SEND_TIMEOUT_S = 2.0

    def _send(self, cmd: list) -> dict:
        s = None
        try:
            s = (
                self._socket_factory()
                if self._socket_factory is not None
                else socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            )
            s.settimeout(self._SEND_TIMEOUT_S)
            s.connect(self._sock_path)
            # Each request uses a fresh connection, so its ID is unique there.
            request_id = 1
            msg = json.dumps({"command": cmd, "request_id": request_id}) + "\n"
            s.sendall(msg.encode())
            resp = b""
            deadline = time.monotonic() + self._SEND_TIMEOUT_S
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout()
                s.settimeout(remaining)
                chunk = s.recv(4096)
                if not chunk:
                    return {"error": "mpv IPC connection closed before reply"}
                resp += chunk
                while b"\n" in resp:
                    line, resp = resp.split(b"\n", 1)
                    response = json.loads(line)
                    if isinstance(response, dict) and response.get("request_id") == request_id:
                        return response
        except socket.timeout:
            _log.warning("mpv IPC timeout (%.1fs) for command: %s", self._SEND_TIMEOUT_S, cmd)
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)}
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    def _command(self, cmd: list) -> dict:
        response = self._send(cmd)
        if response.get("error") != "success":
            raise MpvUnavailableError(f"mpv command {cmd[0]} failed: {response.get('error')}")
        return response

    def play_file(self, path: str):
        self._command(["loadfile", path, "replace"])

    def pause(self):
        self._command(["set_property", "pause", True])

    def resume(self):
        self._command(["set_property", "pause", False])

    def stop(self):
        self._command(["stop"])

    def seek(self, position_sec: float):
        self._command(["seek", position_sec, "absolute+exact"])

    def get_duration(self) -> float:
        r = self._send(["get_property", "duration"])
        return r.get("data") or 0.0

    def get_position(self) -> float:
        r = self._send(["get_property", "time-pos"])
        return r.get("data") or 0.0

    def set_volume(self, volume_0_1: float):
        self._command(["set_property", "volume", volume_0_1 * 100])

    def set_mute(self, muted: bool):
        self._command(["set_property", "mute", muted])

    def add_audio_track(self, path: str):
        """Add an external audio file as the selected audio track."""
        self._command(["audio-add", path, "select"])

    def get_idle_active(self) -> bool:
        """Return True when mpv is idle (no file loaded / playback finished)."""
        r = self._send(["get_property", "idle-active"])
        return bool(r.get("data", False))


# ══════════════════════════════════════════════
# 内存状态 —— Postman 测试时状态会随操作变化
# ══════════════════════════════════════════════

_state = {
    "system_state": "running",
    "playback_state": "idle",
    "show_id": None,
    "position_ms": 0,
    "duration_ms": 0,
    "brightness": 1.0,
    "color_temperature": 4200,
    "audio_available": True,
    "video_available": True,
    "audio_link_enabled": True,
    "video_link_enabled": True,
    # V1.1
    "volume": 0.5,
    "muted": False,
    "scene_id": None,
    # V1.2
    "brightness_scale": BRIGHTNESS_SCALE_DEFAULT,
}

# Internal fields hidden from the /shows API response.
_SHOW_INTERNAL_FIELDS = {"media_path", "show_yaml", "aux_triggers", "audio_path"}

# Overridable in tests via monkeypatch; None means use shows_loader discovery.
_shows: list[dict] | None = None


def _load_shows() -> list[dict]:
    if _shows is not None:
        return _shows
    from . import shows_loader
    return shows_loader.load_shows()

def _filter_show_fields(show: dict) -> dict:
    return {k: v for k, v in show.items() if k not in _SHOW_INTERNAL_FIELDS}


_scenes: dict[str, dict] = {}  # 启动时由下方 _scenes.update(_load_scenes()) 从 SCENE_FILE_PATH 恢复


def _now_ms() -> int:
    return int(time.time() * 1000)


def _live_position_ms() -> int:
    """Return live mpv position in ms; falls back to stored position if mpv unavailable or idle."""
    if _mpv is None:
        return _state["position_ms"]
    try:
        if _mpv.get_idle_active():
            return _state["position_ms"]
        pos = _mpv.get_position()
        if pos <= 0:
            return _state["position_ms"]
        return int(pos * 1000)
    except Exception:
        return _state["position_ms"]


def _push_brightness_scale() -> None:
    """Send current brightness_scale to all WLED nodes (fire-and-forget)."""
    from . import wled_brightness
    scale = _state["brightness_scale"]
    hosts_devices = [d for d in _devices if d.get("host") and d.get("enabled", True) and d.get("device_type") == WLED_DEVICE_TYPE]
    if hosts_devices:
        wled_brightness.apply_scale(hosts_devices, scale, WLED_HTTP_TIMEOUT_S)


def _push_wled_off() -> None:
    """停止播放时把节点本地状态关掉。

    DDP 停流后 WLED 退出 realtime 会回落到本地状态（出厂默认 = 开 + 琥珀色），
    表现为节目结束后灯带全黄。显式发 {"on": false} 消掉这个回落。
    """
    from . import wled_brightness
    hosts_devices = [d for d in _devices if d.get("host") and d.get("enabled", True) and d.get("device_type") == WLED_DEVICE_TYPE]
    if hosts_devices:
        wled_brightness.apply_off(hosts_devices, WLED_HTTP_TIMEOUT_S)


import urllib.request
from contextlib import closing

def _probe_devices() -> None:
    """Collect one batch, then publish it for unchanged device endpoints."""
    global _devices
    t = _now_ms()
    with _profile_refresh_lock:
        devices = [(device, dict(device)) for device in _devices]
    updates = []
    for original, d in devices:
        if not d.get("enabled", True):
            updates.append((original, d, {"status": "offline", "connection_confirmed": False,
                                          "error_code": "MDNS_UNRESOLVED"}))
            continue
        if d.get("device_type") != WLED_DEVICE_TYPE:
            continue
        host = d.get("host")
        if not host:
            continue
        try:
            with closing(urllib.request.urlopen(f"http://{host}/json/info", timeout=1)):
                pass
            result = {"status": "online", "connection_confirmed": True,
                      "last_seen_ms": t, "error_code": None}
        except Exception:
            result = {"status": "offline", "connection_confirmed": False}
        updates.append((original, d, result))
    with _profile_refresh_lock:
        devices = list(_devices)
        for original, snapshot, result in updates:
            for index, current in enumerate(devices):
                if (current is original and current.get("host") == snapshot.get("host")
                        and current.get("enabled", True) == snapshot.get("enabled", True)):
                    devices[index] = {**current, **result}
                    break
        _devices = devices

def _mark_devices_output() -> None:
    t = _now_ms()
    for d in _devices:
        if d.get("enabled", True):
            d["last_output_ms"] = t


# ══════════════════════════════════════════════
# Real adapter (None in mock mode)
# ══════════════════════════════════════════════

_real_adapter = None  # type: Any  # RealEngineAdapter | None

# Accumulated manual-target state for real-adapter calls.
# key = target_id (strip), value = one complete manual Show effect request.
_manual_targets: dict[str, dict] = {}


def _init_real_adapter():
    global _real_adapter
    if ENGINE_ADAPTER != "real":
        return
    _real_adapter = None
    try:
        from .real_engine_adapter import RealEngineAdapter
        from .config import MPV_SOCKET_PATH
        strip_ids = _valid_target_ids - {"all", "starry_sky"}
        _real_adapter = RealEngineAdapter(
            profile_path=ENGINE_PROFILE_PATH,
            mpv_socket_path=MPV_SOCKET_PATH,
            strip_ids=strip_ids,
        )
        _log.info("engine_adapter: real adapter initialized")
    except Exception as exc:
        _log.error("engine_adapter: failed to init real adapter: %s", exc)



def _detect_video_available() -> bool:
    """Check HDMI connection via xrandr. Returns True if any HDMI output is connected."""
    if not VIDEO_DETECT_ENABLED:
        return True
    from .config import uses_wayland, wayland_display_available
    if uses_wayland():
        return wayland_display_available()
    try:
        result = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True, text=True, timeout=5,
            env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "HDMI" in line and " connected" in line:
                    return True
            return False
    except Exception as exc:
        _log.warning("video detection failed: %s; assuming available", exc)
    return True



def _accumulate_hw_entry(
    tid: str,
    effect_type: str,
    hw_color: list,
    *,
    speed: float = 1.0,
    intensity: float = 1.0,
    effect_params: dict[str, Any] | None = None,
) -> None:
    """Merge one hw entry into _manual_targets, expanding 'all' to per-strip IDs."""
    strip_ids = _valid_target_ids - {"all", "starry_sky"}
    entry = {
        "target_id": tid,
        "effect_type": effect_type,
        "color": hw_color,
        "speed": speed,
        "intensity": intensity,
        "effect_params": dict(effect_params or {}),
    }
    if tid == "all":
        for sid in strip_ids:
            _manual_targets[sid] = {**entry, "target_id": sid}
    else:
        _manual_targets[tid] = entry


def _apply_manual_targets() -> None:
    """Send the complete accumulated _manual_targets list to the real adapter."""
    if _real_adapter is not None and _manual_targets:
        _refresh_wled_profile(reason="manual session resolve")
        # 节点可能被 playback_stop / 自然结束看门狗关过，先重新点亮再下发。
        _push_brightness_scale()
        _real_adapter.on_manual_command(list(_manual_targets.values()))
    if _manual_targets:
        _mark_devices_output()


# ══════════════════════════════════════════════
# Status
# ══════════════════════════════════════════════

def get_status() -> dict:
    from .config import SERVICE_NAME, HOST_ID, API_VERSION, SERVICE_VERSION
    return {
        "service": SERVICE_NAME,
        "host_id": HOST_ID,
        "api_version": API_VERSION,
        "version": SERVICE_VERSION,
        "time_ms": _now_ms(),
    }


# ══════════════════════════════════════════════
# State
# ══════════════════════════════════════════════

def get_state() -> dict:
    devices = _devices
    safe_devices = [
        {k: v for k, v in d.items() if k != "host"}
        for d in devices
    ]
    return {**_state, "devices": safe_devices}


# ══════════════════════════════════════════════
# Brightness scale (V1.2)
# ══════════════════════════════════════════════

def get_brightness_scale() -> dict:
    return {"brightness_scale": _state["brightness_scale"]}


def brightness_scale_set(brightness_scale: float, transition_ms: float) -> tuple[dict, None]:
    _state["brightness_scale"] = brightness_scale
    _push_brightness_scale()
    return {
        "brightness_scale": _state["brightness_scale"],
        "transition_ms": transition_ms,
        "accepted": True,
    }, None


# ══════════════════════════════════════════════
# Shows
# ══════════════════════════════════════════════

def get_shows() -> list[dict]:
    return [_filter_show_fields(s) for s in _load_shows()]

# ══════════════════════════════════════════════
# Capabilities
# ══════════════════════════════════════════════

def get_capabilities() -> dict:
    # Targets remain the existing layout-derived V1 discovery surface. Effects
    # and event vocabulary are an APP compatibility projection and must not
    # reveal the engine's effect-registration metadata.
    from .app_v1 import capabilities

    return capabilities(_capability_targets)


# ══════════════════════════════════════════════
# Playback
# ══════════════════════════════════════════════

_mpv: MpvClient | None = None
_mpv_proc: subprocess.Popen | None = None
_audio_pending = True
_session_lock = threading.RLock()
_session_generation = 0
_mpv_observer = None
_media_loading_generation = None


def _serialized_session(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _session_lock:
            return fn(*args, **kwargs)
    return wrapped


_apply_manual_targets = _serialized_session(_apply_manual_targets)


def _close_mpv_observer() -> None:
    global _mpv_observer
    observer, _mpv_observer = _mpv_observer, None
    if observer is not None:
        observer["stop"].set()
        observer["socket"].close()


def _set_playback_error(code: str, message: str) -> None:
    global _session_generation
    _session_generation += 1
    _close_mpv_observer()
    _state["playback_state"] = "error"
    from . import ws
    ws.publish_error({"code": code, "message": message})


@_serialized_session
def _handle_mpv_event(event: dict, generation: int, observer: dict) -> None:
    global _media_loading_generation
    if generation != _session_generation:
        return
    kind = event.get("event")
    if kind == "start-file":
        observer["entry_id"] = event.get("playlist_entry_id")
    elif kind == "file-loaded" and observer.get("entry_id") is not None:
        _media_loading_generation = None
    elif kind == "end-file" and observer.get("entry_id") is not None:
        if event.get("playlist_entry_id") != observer["entry_id"]:
            return
        reason = event.get("reason")
        if reason not in ("error", "eof"):
            return
        _media_loading_generation = None
        if reason == "error":
            _finalize_playback_error(generation, "MEDIA_ERROR", str(event.get("file_error", "media playback failed")))
        else:
            _finalize_natural_end(generation)


def _start_mpv_observer(sock_path: str, generation: int) -> dict:
    global _mpv_observer, _media_loading_generation
    _close_mpv_observer()
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(1.0)
        sock.connect(sock_path)
    except OSError as exc:
        sock.close()
        raise MpvUnavailableError(f"cannot observe mpv events: {exc}") from exc
    observer = {"socket": sock, "stop": threading.Event(), "entry_id": None,
                "loaded": threading.Event(), "load_error": None}
    _mpv_observer = observer
    _media_loading_generation = generation

    def consume():
        pending = b""
        disconnected = False
        while not observer["stop"].is_set():
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    disconnected = True
                    break
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    event = json.loads(line)
                    if isinstance(event, dict):
                        kind = event.get("event")
                        if kind == "start-file":
                            observer["entry_id"] = event.get("playlist_entry_id")
                            continue
                        if kind == "file-loaded" and observer["entry_id"] is not None:
                            observer["loaded"].set()
                        elif (kind == "end-file" and event.get("playlist_entry_id") == observer["entry_id"]
                              and event.get("reason") == "error"):
                            observer["load_error"] = event.get("file_error", "media playback failed")
                            observer["loaded"].set()
                        _handle_mpv_event(event, generation, observer)
            except socket.timeout:
                continue
            except (OSError, ValueError) as exc:
                if not observer["stop"].is_set():
                    _log.error("mpv event observer stopped: %s", exc)
                    disconnected = True
                break
        if disconnected and not observer["stop"].is_set():
            observer["load_error"] = "mpv event connection closed"
            observer["loaded"].set()
            with _session_lock:
                if generation == _session_generation and _state["playback_state"] in ("playing", "paused"):
                    _finalize_playback_error(generation, "MPV_EVENTS_LOST", observer["load_error"])

    observer["thread"] = threading.Thread(target=consume, name="mpv-events", daemon=True)
    observer["thread"].start()
    return observer


def _find_show(show_id: str) -> dict | None:
    for s in _load_shows():
        if s["show_id"] == show_id:
            return s
    return None


def _validate_playback_content(show: dict) -> str | None:
    from pathlib import Path
    from .shows_loader import _probe_duration_ms
    media = show.get("media_path")
    show_yaml = show.get("show_yaml")
    if not media and not show_yaml:
        return "no media or show YAML"
    if not media:
        return "YAML-only playback mode is not configured"
    for path in (media, show.get("audio_path")):
        if path and (not Path(path).is_file() or _probe_duration_ms(path) <= 0):
            return f"missing or undecodable media: {path}"
    if show_yaml:
        try:
            from light_engine.config import Config
            from light_engine.cli import _load_show_for_config
            definition, _ = _load_show_for_config(show_yaml, Config.get_instance(Path(ENGINE_PROFILE_PATH)))
            show["_engine_duration_ms"] = int(definition.duration * 1000)
        except Exception as exc:
            return f"invalid show or target configuration: {exc}"
    return None


def _playback_data() -> dict:
    return {
        "playback_state": _state["playback_state"],
        "show_id": _state["show_id"],
        "position_ms": _state["position_ms"],
        "duration_ms": _state["duration_ms"],
    }


def _wait_until(cond, timeout_s: float = 3.0, interval_s: float = 0.05) -> bool:
    """轮询直到 cond() 为真或超时。返回是否成功。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(interval_s)
    return cond()


def _mpv_position_matches(mpv: MpvClient, position_ms: float) -> bool:
    reply = mpv._send(["get_property", "time-pos"])
    value = reply.get("data")
    return (reply.get("error") == "success" and isinstance(value, (int, float))
            and abs(value * 1000 - position_ms) <= 250)


def _drain_stderr(proc: subprocess.Popen, name: str) -> None:
    import threading
    def _reader():
        for raw in proc.stderr:
            _log.warning("[%s] %s", name, raw.decode(errors="replace").rstrip())
    threading.Thread(target=_reader, daemon=True).start()


def _stop_owned_mpv() -> None:
    if _mpv_proc is None or _mpv_proc.poll() is not None:
        return
    try:
        _mpv_proc.terminate()
        try:
            _mpv_proc.wait(3)
        except subprocess.TimeoutExpired:
            _mpv_proc.kill()
            _mpv_proc.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MpvUnavailableError(f"cannot stop stale mpv: {exc}") from exc


def _ensure_mpv() -> MpvClient:
    global _mpv, _mpv_proc, _audio_pending
    from .config import MPV_SOCKET_PATH, MPV_DISPLAY, MPV_XAUTHORITY, uses_wayland, wayland_display_available
    sock = MPV_SOCKET_PATH

    if os.path.exists(sock):
        # Probe whether mpv is actually alive behind the socket.
        try:
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(1.0)
            probe.connect(sock)
            probe.close()
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            _log.warning("mpv socket %s is stale; removing and restarting mpv", sock)
            _stop_owned_mpv()
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass
            _mpv_proc = None
            _mpv = None
        # Probe succeeded — mpv is alive; skip restart.

    if not os.path.exists(sock):
        wayland = uses_wayland()
        if wayland and not wayland_display_available():
            raise MpvUnavailableError("Waiting for the pi GNOME Wayland session environment")
        _stop_owned_mpv()
        _mpv_proc = None
        _mpv = None
        try:
            os.makedirs(os.path.dirname(sock), exist_ok=True)
        except Exception as exc:
            _log.error(
                "mpv: cannot create socket directory %s: %s — "
                "ensure /run/light-belt exists or set RuntimeDirectory=light-belt in the systemd unit",
                os.path.dirname(sock), exc,
            )
            raise MpvUnavailableError(f"Cannot create mpv socket directory: {exc}") from exc
        env = os.environ.copy()
        if not wayland:
            env.setdefault("DISPLAY", MPV_DISPLAY)
            env.setdefault("XAUTHORITY", MPV_XAUTHORITY)
        video_options = ["--vo=gpu", "--gpu-context=wayland"] if wayland else []
        from pathlib import Path as _Path
        _input_conf = str(
            _Path(__file__).resolve().parent.parent / "config" / "mpv-kiosk-input.conf"
        )
        try:
            _mpv_proc = subprocess.Popen(
                ["mpv", f"--input-ipc-server={sock}", "--idle=yes",
                 "--keep-open=no", "--no-terminal",
                 "--no-config",
                 "--audio-client-name=LIGHT-BELT-LocalMedia",
                 "--fullscreen",
                 "--ontop",
                 "--cursor-autohide=always",
                 "--input-default-bindings=no",
                 "--no-border", "--force-window=immediate", "--no-osc",
                 f"--input-conf={_input_conf}", *video_options],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                env=env,
            )
        except Exception as exc:
            _log.error(
                "mpv: failed to start mpv subprocess: %s — "
                "check that mpv is installed and the socket path %s is writable",
                exc, sock,
            )
            raise MpvUnavailableError(f"Cannot start mpv: {exc}") from exc
        _drain_stderr(_mpv_proc, "mpv")
        if not _wait_until(lambda: os.path.exists(sock)):
            _log.warning("mpv IPC socket %s not ready after timeout", sock)

    if _mpv is None:
        _mpv = MpvClient(sock)
        _audio_pending = True
        _mpv.set_volume(_state["volume"])
        _mpv.set_mute(_state["muted"])
        _audio_pending = False
    elif _audio_pending:
        _mpv.set_volume(_state["volume"])
        _mpv.set_mute(_state["muted"])
        _audio_pending = False
    return _mpv


def _active_mpv() -> MpvClient:
    if ENGINE_ADAPTER != "real":
        return _ensure_mpv()
    if _mpv is None or (_mpv_proc is not None and _mpv_proc.poll() is not None):
        _finalize_playback_error(_session_generation, "MPV_UNAVAILABLE", "active playback has lost its mpv process")
        raise MpvUnavailableError("active playback has lost its mpv process")
    return _mpv


@_serialized_session
def playback_play(show_id: str, start_ms: float | None) -> tuple[dict | None, str | None]:
    global _session_generation
    show = _find_show(show_id)
    if show is None:
        return None, "NOT_FOUND"
    if ENGINE_ADAPTER == "real":
        content_error = _validate_playback_content(show)
        if content_error:
            _log.error("playback content not ready: %s", content_error)
            return None, "CONTENT_NOT_READY"
    if start_ms is not None and start_ms > show["duration_ms"]:
        return None, "INVALID_ARGUMENT"
    if _real_adapter is not None:
        _refresh_wled_profile(reason="playback session resolve")
    # Tear down current lighting playback before starting the new show.
    # When the new show has media, loadfile(..., "replace") replaces the
    # current media directly; stopping mpv first is unnecessary.
    if _mpv and not show.get("media_path"):
        try:
            _mpv.stop()
        except MpvUnavailableError:
            return None, "MPV_UNAVAILABLE"
    if _real_adapter is not None:
        try:
            _real_adapter.on_playback_stop()
        except RuntimeError as exc:
            _log.error("cannot stop previous engine: %s", exc)
            return None, "ENGINE_UNAVAILABLE"
    _manual_targets.clear()
    _session_generation += 1
    _close_mpv_observer()
    _state.update(playback_state="stopped", show_id=None, position_ms=0, duration_ms=0)
    if show.get("media_path"):
        mpv = _mpv
        try:
            mpv = _ensure_mpv()
            if ENGINE_ADAPTER == "real":
                _start_mpv_observer(mpv._sock_path, _session_generation)
                mpv.pause()
            mpv.play_file(show["media_path"])
            if ENGINE_ADAPTER == "real":
                observer = _mpv_observer
                if not observer["loaded"].wait(5.0) or observer["load_error"]:
                    _log.error("media failed to load: %s", observer["load_error"] or "timeout")
                    _session_generation += 1
                    _close_mpv_observer()
                    try:
                        mpv.stop()
                    except MpvUnavailableError:
                        _log.exception("cannot stop media after loading failure")
                        _set_playback_error("MPV_UNAVAILABLE", "media cleanup failed after loading timeout")
                    return None, "MEDIA_NOT_READY"
            if show.get("audio_path"):
                if not _wait_until(lambda: mpv.get_duration() > 0, timeout_s=2.0):
                    _log.warning("mpv did not report duration in time; adding audio track anyway")
                mpv.add_audio_track(show["audio_path"])
            if start_ms and start_ms > 0:
                if not _wait_until(lambda: mpv.get_duration() > 0, timeout_s=2.0):
                    _log.warning("mpv did not report duration in time; seeking anyway")
                mpv.seek(start_ms / 1000)
                if ENGINE_ADAPTER == "real" and not _wait_until(
                    lambda: _mpv_position_matches(mpv, start_ms), timeout_s=3.0
                ):
                    raise MpvUnavailableError("initial seek position not confirmed")
            if ENGINE_ADAPTER != "real":
                mpv.resume()
        except MpvUnavailableError as exc:
            _session_generation += 1
            _close_mpv_observer()
            cleanup_mpv = _mpv if _mpv is not None else mpv
            if cleanup_mpv is not None:
                try:
                    cleanup_mpv.stop()
                except MpvUnavailableError:
                    _log.exception("cannot stop media after start failure")
                    _set_playback_error("MPV_UNAVAILABLE", "media cleanup failed after playback start")
            _log.error("playback start failed: %s", exc)
            return None, "MPV_UNAVAILABLE"
    if _real_adapter is not None:
        try:
            _real_adapter.on_playback_start(show, start_ms)
            if show.get("media_path") and ENGINE_ADAPTER == "real":
                mpv.resume()
        except (RuntimeError, OSError) as exc:
            error_code = "MPV_UNAVAILABLE" if isinstance(exc, MpvUnavailableError) else "ENGINE_UNAVAILABLE"
            _session_generation += 1
            _close_mpv_observer()
            _log.error("cannot start playback engine: %s", exc)
            if show.get("media_path"):
                try:
                    _real_adapter.on_playback_stop()
                except RuntimeError:
                    _log.exception("cannot stop engine after playback start failure")
                    _set_playback_error("ENGINE_UNAVAILABLE", "engine cleanup failed after playback start")
                try:
                    mpv.stop()
                except MpvUnavailableError:
                    _log.exception("cannot stop media after engine start failure")
                    _set_playback_error("MPV_UNAVAILABLE", "media cleanup failed after engine start")
            return None, error_code
    _state["playback_state"] = "playing"
    _state["show_id"] = show_id
    _state["position_ms"] = start_ms or 0
    _state["duration_ms"] = show["duration_ms"]
    _state["scene_id"] = None
    _state["brightness_scale"] = BRIGHTNESS_SCALE_DEFAULT
    _manual_targets.clear()
    if _real_adapter is not None:
        _mark_devices_output()
    _push_brightness_scale()
    return _playback_data(), None


@_serialized_session
def playback_pause() -> tuple[dict | None, str | None]:
    if _state["playback_state"] != "playing":
        return None, "PLAYBACK_NOT_READY"
    try:
        _active_mpv().pause()
    except MpvUnavailableError:
        return None, "MPV_UNAVAILABLE"
    _state["playback_state"] = "paused"
    return _playback_data(), None


@_serialized_session
def playback_resume() -> tuple[dict | None, str | None]:
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "PLAYBACK_NOT_READY"
    try:
        _active_mpv().resume()
    except MpvUnavailableError:
        return None, "MPV_UNAVAILABLE"
    _state["playback_state"] = "playing"
    return _playback_data(), None


@_serialized_session
def playback_stop() -> tuple[dict | None, str | None]:
    global _session_generation
    if _real_adapter is not None:
        try:
            _real_adapter.on_playback_stop()
        except RuntimeError as exc:
            _log.error("cannot stop engine: %s", exc)
            _set_playback_error("ENGINE_UNAVAILABLE", str(exc))
            return None, "ENGINE_UNAVAILABLE"
    if _mpv:
        try:
            _mpv.stop()
        except MpvUnavailableError:
            _set_playback_error("MPV_UNAVAILABLE", "mpv did not confirm stop")
            return None, "MPV_UNAVAILABLE"
    _session_generation += 1
    _close_mpv_observer()
    _state["playback_state"] = "stopped"
    _state["show_id"] = None
    _state["position_ms"] = 0
    _state["duration_ms"] = 0
    _manual_targets.clear()
    if _real_adapter is not None:
        _push_wled_off()
    return _playback_data(), None


@_serialized_session
def playback_seek(position_ms: float) -> tuple[dict | None, str | None]:
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "SHOW_NOT_LOADED"
    was_playing = _state["playback_state"] == "playing"
    engine_stopped = False
    try:
        mpv = _active_mpv()
        if _real_adapter is not None:
            if was_playing:
                mpv.pause()
                _state["playback_state"] = "paused"
            _real_adapter.on_playback_seek_prepare()
            engine_stopped = True
        mpv.seek(position_ms / 1000)
        if _real_adapter is not None and not _wait_until(
            lambda: _mpv_position_matches(mpv, position_ms),
            timeout_s=3.0,
        ):
            _log.error("mpv did not confirm seek position %s ms", position_ms)
            _set_playback_error("SEEK_NOT_READY", "mpv did not confirm the requested position")
            return None, "SEEK_NOT_READY"
        _state["position_ms"] = position_ms
        if _real_adapter is not None:
            if not _real_adapter.on_playback_resume_yaml():
                _set_playback_error("NO_ACTIVE_SHOW", "could not restart the active show after seek")
                return None, "NO_ACTIVE_SHOW"
            if was_playing:
                mpv.resume()
                _state["playback_state"] = "playing"
    except MpvUnavailableError as exc:
        _log.error("seek failed: %s", exc)
        if engine_stopped:
            try:
                _real_adapter.on_playback_resume_yaml()
            except (OSError, RuntimeError):
                _log.exception("could not restore engine after failed seek")
                _set_playback_error("ENGINE_UNAVAILABLE", "engine restore failed after seek")
        return None, "MPV_UNAVAILABLE"
    except (OSError, RuntimeError) as exc:
        _log.error("seek engine restart failed: %s", exc)
        _set_playback_error("ENGINE_UNAVAILABLE", str(exc))
        return None, "ENGINE_UNAVAILABLE"
    _state["position_ms"] = position_ms
    return _playback_data(), None


@_serialized_session
def playback_reset() -> tuple[dict | None, str | None]:
    """Resume the show's YAML lighting after a manual override.

    Clears accumulated manual targets and restarts the show's light_engine
    subprocess.  mpv is NOT restarted; the engine re-syncs via --clock mpv.
    In mock mode (_real_adapter is None) only clears manual targets.
    """
    if _state["playback_state"] not in ("playing", "paused"):
        return None, "PLAYBACK_NOT_READY"
    _manual_targets.clear()
    if _real_adapter is not None:
        _refresh_wled_profile(reason="playback resume resolve")
        try:
            ok = _real_adapter.on_playback_resume_yaml()
        except (RuntimeError, OSError) as exc:
            _set_playback_error("ENGINE_UNAVAILABLE", str(exc))
            return None, "ENGINE_UNAVAILABLE"
        if not ok:
            return None, "NO_ACTIVE_SHOW"
    if _state["playback_state"] == "paused":
        if _mpv is not None:
            try:
                _mpv.resume()
            except MpvUnavailableError:
                return None, "MPV_UNAVAILABLE"
        _state["playback_state"] = "playing"
    _push_brightness_scale()
    return _playback_data(), None


# ══════════════════════════════════════════════
# Lights
# ══════════════════════════════════════════════

def lights_set(target_id: str, brightness: float | None,
               color_temperature: int | None,
               transition_ms: float,
               color=None) -> tuple[dict | None, str | None]:
    if target_id not in _valid_target_ids:
        return None, "NOT_FOUND"
    if brightness is None and color_temperature is None and color is None:
        return None, "INVALID_ARGUMENT"
    if target_id == "all":
        if brightness is not None:
            _state["brightness"] = brightness
        if color_temperature is not None:
            _state["color_temperature"] = color_temperature
    _state["scene_id"] = None
    data: dict[str, Any] = {
        "target_id": target_id,
        "transition_ms": transition_ms,
        "accepted": True,
    }
    if brightness is not None:
        data["brightness"] = brightness
    if color_temperature is not None:
        data["color_temperature"] = color_temperature
    if color is not None:
        data["color"] = {"r": color.r, "g": color.g, "b": color.b}
    if _real_adapter is not None:
        if color is not None:
            hw_color = [color.r / 255, color.g / 255, color.b / 255]
        else:
            hw_color = [brightness if brightness is not None else 1.0] * 3
        _accumulate_hw_entry(target_id, "static", hw_color)
        _apply_manual_targets()
    else:
        _mark_devices_output()
    return data, None


# ══════════════════════════════════════════════
# Effects
# ══════════════════════════════════════════════

def _validate_effect_request(
    target_id: str,
    effect_type: str,
    effect_params: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Validate one Host effect request against the runtime Registry."""
    from .layout_vocab import STARRY_SKY_TARGET_ID

    if target_id == STARRY_SKY_TARGET_ID and effect_type == "off":
        return {}, None
    try:
        registration = get_effect_registration(effect_type)
    except KeyError:
        return {}, {"field": "effect_type", "reason": "unknown registered effect"}
    if target_id == STARRY_SKY_TARGET_ID and effect_type != "twinkle":
        return {}, {
            "field": "effect_type",
            "reason": "starry_sky supports only twinkle or off",
        }
    try:
        return dict(registration.validator(effect_params or {})), None
    except (TypeError, ValueError) as exc:
        return {}, {"field": "effect_params", "reason": str(exc)}


def effects_set(target_id: str, effect_type: str,
                transition_ms: float,
                params=None, effect_params=None) -> tuple[dict | None, str | None]:
    from .layout_vocab import STARRY_SKY_TARGET_ID
    if target_id not in _valid_target_ids:
        return None, "NOT_FOUND"
    validated_effect_params, validation_error = _validate_effect_request(
        target_id,
        effect_type,
        effect_params,
    )
    if validation_error is not None:
        return {"error_detail": validation_error}, "INVALID_ARGUMENT"
    # twinkle is the only registered effect for starry_sky; "off" is an action.
    if target_id == STARRY_SKY_TARGET_ID:
        from . import starry_sky as _ss
        if effect_type == "twinkle":
            _ss.ensure_on()
        else:
            _ss.ensure_off()
        _state["scene_id"] = None
        return {
            "target_id": target_id,
            "effect_type": effect_type,
            "transition_ms": transition_ms,
            "accepted": True,
        }, None
    _state["scene_id"] = None
    data: dict[str, Any] = {
        "target_id": target_id,
        "effect_type": effect_type,
        "transition_ms": transition_ms,
        "accepted": True,
    }
    if params is not None:
        data["params"] = params.model_dump(exclude_none=True)
    if effect_params is not None:
        data["effect_params"] = validated_effect_params
    if _real_adapter is not None:
        if params is not None and params.color is not None:
            hw_color = [params.color.r / 255, params.color.g / 255, params.color.b / 255]
        else:
            hw_color = [1.0, 1.0, 1.0]
        common = params.model_dump(exclude_none=True) if params is not None else {}
        _accumulate_hw_entry(
            target_id,
            effect_type,
            hw_color,
            speed=common.get("speed", 1.0),
            intensity=common.get("intensity", 1.0),
            effect_params=validated_effect_params,
        )
        _apply_manual_targets()
    return data, None


# ══════════════════════════════════════════════
# Audio (V1.1)
# ══════════════════════════════════════════════

def get_audio() -> dict:
    return {
        "volume": _state["volume"],
        "muted": _state["muted"],
        "audio_output_available": True,
    }


@_serialized_session
def audio_set(volume: float | None, muted: bool | None,
              transition_ms: float) -> tuple[dict | None, str | None]:
    global _audio_pending
    if volume is None and muted is None:
        return None, "INVALID_ARGUMENT"
    if volume is not None:
        _state["volume"] = volume
    if muted is not None:
        _state["muted"] = muted
    _state["scene_id"] = None
    was_pending = _audio_pending
    _audio_pending = True
    if _mpv is not None:
        try:
            if volume is not None:
                _mpv.set_volume(volume)
            if muted is not None:
                _mpv.set_mute(muted)
            _audio_pending = was_pending
        except Exception as exc:
            _log.warning("audio_set: mpv IPC failed: %s", exc)
            return None, "MPV_UNAVAILABLE"
    else:
        _log.warning("audio_set: mpv not running, state updated in memory only")
    return {
        "volume": _state["volume"],
        "muted": _state["muted"],
        "transition_ms": transition_ms,
        "accepted": True,
    }, None


# ══════════════════════════════════════════════
# Scenes (V1.1)
# ══════════════════════════════════════════════

def _load_scenes() -> dict[str, dict]:
    try:
        with open(SCENE_FILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        _log.warning("scene file %s has unexpected format; ignoring", SCENE_FILE_PATH)
    except FileNotFoundError:
        pass
    except Exception as exc:
        _log.warning("failed to load scenes from %s: %s", SCENE_FILE_PATH, exc)
    return {}


def _save_scenes(scenes: dict[str, dict]) -> None:
    d = os.path.dirname(SCENE_FILE_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = SCENE_FILE_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(scenes, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SCENE_FILE_PATH)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _validate_scene_entries(
    entries: list[dict] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate persisted or incoming scene effects through the Registry."""
    for i, entry in enumerate(entries or []):
        if entry.get("target_id") not in _valid_target_ids:
            return {"entry_index": i, "field": "target_id"}, "INVALID_ARGUMENT"
        if not entry.get("effect_type"):
            continue
        validated_params, validation_error = _validate_effect_request(
            entry["target_id"],
            entry["effect_type"],
            entry.get("effect_params"),
        )
        if validation_error is not None:
            return {"entry_index": i, **validation_error}, "INVALID_ARGUMENT"
        if "effect_params" in entry:
            entry["effect_params"] = validated_params
    return None, None


# 服务启动时从磁盘恢复场景（文件不存在则保持空）
_scenes.update(_load_scenes())


def get_scenes() -> list[dict]:
    return [
        {"scene_id": sid, "name": s["name"],
         "created_ms": s["created_ms"], "updated_ms": s["updated_ms"]}
        for sid, s in _scenes.items()
    ]


def scene_save(scene_id: str | None, name: str,
               audio: dict | None,
               entries: list[dict] | None) -> tuple[dict | None, str | None]:
    global _scenes
    if audio is None and entries is None:
        return None, "INVALID_ARGUMENT"
    validation_error, error = _validate_scene_entries(entries)
    if error is not None:
        return {"error_detail": validation_error}, error
    if scene_id is None:
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
    if scene_id not in _scenes and len(_scenes) >= SCENE_MAX_COUNT:
        return None, "SCENE_LIMIT_EXCEEDED"
    now = _now_ms()
    scenes = dict(_scenes)
    scenes[scene_id] = {
        "name": name, "audio": audio, "entries": entries,
        "created_ms": _scenes.get(scene_id, {}).get("created_ms", now),
        "updated_ms": now,
    }
    try:
        _save_scenes(scenes)
    except (OSError, TypeError, ValueError):
        _log.exception("Unable to persist scene %s", scene_id)
        return None, "INTERNAL_ERROR"
    _scenes = scenes
    return {"scene_id": scene_id, "saved": True}, None


@_serialized_session
def scene_apply(scene_id: str,
                transition_ms: float | None) -> tuple[dict | None, str | None]:
    if scene_id not in _scenes:
        return None, "NOT_FOUND"
    scene = _scenes[scene_id]
    validation_error, error = _validate_scene_entries(scene.get("entries"))
    if error is not None:
        return {"error_detail": validation_error}, error
    if _state["playback_state"] == "playing":
        _, stop_error = playback_stop()
        if stop_error:
            return None, stop_error
    if scene.get("audio"):
        a = scene["audio"]
        if a.get("volume") is not None or a.get("muted") is not None:
            _, audio_error = audio_set(a.get("volume"), a.get("muted"), transition_ms or 0)
            if audio_error:
                return None, audio_error
    if scene.get("entries"):
        _manual_targets.clear()
        for e in scene["entries"]:
            tid = e.get("target_id")
            if not tid:
                continue
            if tid == "all":
                if e.get("brightness") is not None:
                    _state["brightness"] = e["brightness"]
                if e.get("color_temperature") is not None:
                    _state["color_temperature"] = e["color_temperature"]
            color_raw = (e.get("params") or {}).get("color")
            if color_raw is not None:
                hw_color = [color_raw["r"] / 255, color_raw["g"] / 255, color_raw["b"] / 255]
            else:
                brightness = e.get("brightness")
                hw_color = [brightness if brightness is not None else 1.0] * 3
            effect_type = e.get("effect_type", "static")
            common = e.get("params") or {}
            _accumulate_hw_entry(
                tid,
                effect_type,
                hw_color,
                speed=common.get("speed", 1.0),
                intensity=common.get("intensity", 1.0),
                effect_params=e.get("effect_params"),
            )
        _apply_manual_targets()
    _state["scene_id"] = scene_id
    return {
        "scene_id": scene_id,
        "accepted": True,
        "partial": False,
        "failed_targets": [],
        "applied_entries": scene.get("entries", []),
    }, None


def scene_delete(scene_id: str) -> tuple[dict | None, str | None]:
    global _scenes
    if scene_id not in _scenes:
        return None, "NOT_FOUND"
    scenes = dict(_scenes)
    del scenes[scene_id]
    try:
        _save_scenes(scenes)
    except (OSError, TypeError, ValueError):
        _log.exception("Unable to persist deletion of scene %s", scene_id)
        return None, "INTERNAL_ERROR"
    _scenes = scenes
    if _state["scene_id"] == scene_id:
        _state["scene_id"] = None
    return {"scene_id": scene_id, "deleted": True}, None


# ══════════════════════════════════════════════
# WebSocket 状态快照（供 ws.py 推送）
# ══════════════════════════════════════════════

def get_playback_state() -> dict:
    """Live /playback/state response: live position, current show fields, brightness_scale, audio."""
    show_id = _state["show_id"]
    show = None
    if show_id:
        s = _find_show(show_id)
        if s:
            show = _filter_show_fields(s)
    return {
        "playback_state": _state["playback_state"],
        "show": show,
        "position_ms": _live_position_ms(),
        "duration_ms": _state["duration_ms"],
        "brightness_scale": _state["brightness_scale"],
        "audio": {
            "volume": _state["volume"],
            "muted": _state["muted"],
        },
    }


def get_runtime_state_snapshot() -> dict:
    return {
        "system_state": _state["system_state"],
        "playback_state": _state["playback_state"],
        "show_id": _state["show_id"],
        "brightness": _state["brightness"],
        "color_temperature": _state["color_temperature"],
        "audio_available": _state["audio_available"],
        "video_available": _state["video_available"],
        "audio_link_enabled": _state["audio_link_enabled"],
        "video_link_enabled": _state["video_link_enabled"],
        "volume": _state["volume"],
        "muted": _state["muted"],
        "scene_id": _state["scene_id"],
        "brightness_scale": _state["brightness_scale"],
    }


def get_playback_progress_snapshot() -> dict:
    return {**_playback_data(), "position_ms": _live_position_ms()}


# ══════════════════════════════════════════════
# 自然结束看门狗
# ══════════════════════════════════════════════
#
# 节目自己播到结尾时没有人调 /playback/stop：mpv 变 idle、light_engine 停止
# 推 DDP，节点在 if.live.timeout 之后回落到本地状态（默认琥珀色）→ 灯全黄。
# 这个线程负责补上那次收尾。仅在 real 模式启动，mock 模式（测试）不受影响。

_WATCHDOG_INTERVAL_S = 1.0
_WATCHDOG_IDLE_STREAK = 3      # 连续 3 次读到 idle 才认定结束，躲开加载中的空窗
_WATCHDOG_CRASH_STREAK = 5     # 连续 5 次进程已死/IPC 不可达才判定 mpv 崩溃
_watchdog_thread: threading.Thread | None = None
_watchdog_stop = threading.Event()


@_serialized_session
def _finalize_natural_end(expected_generation: int | None = None) -> None:
    """等价于一次 playback_stop。如果 mpv 进程已死，顺带清理引用以便下次重建。"""
    global _mpv, _mpv_proc
    if expected_generation is not None and expected_generation != _session_generation:
        return
    if _real_adapter is not None:
        try:
            _real_adapter.on_playback_stop()
            _push_wled_off()
        except RuntimeError as exc:
            _set_playback_error("ENGINE_UNAVAILABLE", str(exc))
            return
    _state["playback_state"] = "stopped"
    _state["show_id"] = None
    _state["position_ms"] = 0
    _state["duration_ms"] = 0
    _manual_targets.clear()
    if _mpv_proc is not None and _mpv_proc.poll() is not None:
        _log.warning(
            "_finalize_natural_end: mpv process already dead (exit %s); clearing references",
            _mpv_proc.returncode,
        )
        sock = _mpv._sock_path if _mpv is not None else None
        if sock:
            try:
                os.unlink(sock)
            except FileNotFoundError:
                pass
            except Exception:
                pass
        _mpv = None
        _mpv_proc = None


@_serialized_session
def _finalize_playback_error(generation: int, code: str, message: str) -> None:
    if generation != _session_generation:
        return
    if _mpv is not None:
        try:
            _mpv.stop()
        except MpvUnavailableError:
            _log.exception("could not stop mpv after playback failure")
    if _real_adapter is not None:
        try:
            _real_adapter.on_playback_stop()
            _push_wled_off()
        except RuntimeError:
            _log.exception("could not stop engine after playback failure")
    _set_playback_error(code, message)

def _natural_end_watchdog() -> None:
    streak = 0
    dead_streak = 0
    ipc_streak = 0
    last_generation = None
    while not _watchdog_stop.wait(_WATCHDOG_INTERVAL_S):
        try:
            with _session_lock:
                generation = _session_generation
                mpv = _mpv
                proc = _mpv_proc
                adapter = _real_adapter
                active = (_state["playback_state"] == "playing" and bool(_state["duration_ms"])
                          and _media_loading_generation != generation)
                engine_failure = None
                engine_proc = adapter._playback_proc if adapter is not None else None
            position_ms = None
            if engine_proc is not None and engine_proc.poll() is not None and mpv is not None:
                response = mpv._send(["get_property", "time-pos"])
                if response.get("error") == "success" and isinstance(response.get("data"), (float, int)):
                    position_ms = response["data"] * 1000
            with _session_lock:
                if generation == _session_generation and adapter is _real_adapter and adapter is not None:
                    engine_failure = adapter.process_failure(position_ms=position_ms)
            if engine_failure:
                _finalize_playback_error(generation, "ENGINE_EXITED", engine_failure)
                continue
            if generation != last_generation:
                streak = dead_streak = ipc_streak = 0
                last_generation = generation
            # 只管「我们以为在播、且确实有媒体」的情况。
            # duration_ms == 0 的占位节目本来就没有 mpv 参与，跳过。
            if not active:
                streak = 0
                dead_streak = 0
                ipc_streak = 0
                continue

            # mpv 子进程已经退出（被 kill / 崩溃）——不用等 IPC 超时，直接判定。
            if proc is not None and proc.poll() is not None:
                dead_streak += 1
                if dead_streak >= _WATCHDOG_CRASH_STREAK:
                    _log.error(
                        "watchdog: mpv process dead (exit %s) while state='playing'; "
                        "finalizing as crash",
                        proc.returncode,
                    )
                    dead_streak = 0
                    ipc_streak = 0
                    _finalize_playback_error(generation, "MPV_EXITED", f"mpv exited with code {proc.returncode}")
                continue
            dead_streak = 0

            if mpv is None:
                streak = 0
                continue

            # 直接调用 _send 而不是 get_idle_active()，因为后者把 IPC 失败
            # 和「IPC 成功但 idle=False」都折叠成同一个 False，无法区分
            # 「mpv 半死不活/超时」和「mpv 正常在播」。
            r = mpv._send(["get_property", "idle-active"])
            if r.get("error") != "success":
                ipc_streak += 1
                if ipc_streak >= _WATCHDOG_CRASH_STREAK:
                    _log.error(
                        "watchdog: mpv IPC unreachable %d times (%s); finalizing as crash",
                        ipc_streak, r.get("error"),
                    )
                    ipc_streak = 0
                    _finalize_playback_error(generation, "MPV_UNAVAILABLE", "mpv IPC is unreachable")
                streak = 0
                continue
            ipc_streak = 0

            if not bool(r.get("data", False)):
                streak = 0
                continue
            streak += 1
            if streak < _WATCHDOG_IDLE_STREAK:
                continue
            streak = 0
            _log.info("watchdog: mpv idle while playing; finalizing natural show end")
            _finalize_natural_end(generation)
        except Exception as exc:                        # noqa: BLE001
            _log.debug("watchdog: %s: %s", type(exc).__name__, exc)
            streak = 0
            dead_streak = 0
            ipc_streak = 0

def _start_natural_end_watchdog() -> None:
    global _watchdog_thread
    if _real_adapter is None:
        return
    if _watchdog_thread is not None and _watchdog_thread.is_alive():
        return
    _watchdog_stop.clear()
    _watchdog_thread = threading.Thread(
        target=_natural_end_watchdog, name="natural-end-watchdog", daemon=True)
    _watchdog_thread.start()
    _log.info("engine_adapter: natural-end watchdog started")


def shutdown() -> None:
    """Stop background observation and owned processes during Host shutdown."""
    global _mpv, _mpv_proc, _session_generation
    _watchdog_stop.set()
    if (_deferred_re_resolve_thread is not None
            and _deferred_re_resolve_thread is not threading.current_thread()):
        _deferred_re_resolve_thread.join()
    observer = _mpv_observer
    _close_mpv_observer()
    if observer is not None and observer.get("thread") is not threading.current_thread():
        observer["thread"].join(timeout=2)
    if _watchdog_thread is not None and _watchdog_thread is not threading.current_thread():
        _watchdog_thread.join(timeout=_WATCHDOG_INTERVAL_S + MpvClient._SEND_TIMEOUT_S + 1)
    with _session_lock:
        _session_generation += 1
        errors = []
        if _real_adapter is not None:
            try:
                _real_adapter.on_playback_stop()
            except (RuntimeError, OSError) as exc:
                errors.append(str(exc))
        try:
            _stop_owned_mpv()
        except MpvUnavailableError as exc:
            errors.append(str(exc))
        else:
            _mpv = None
            _mpv_proc = None
        if errors:
            raise RuntimeError("shutdown cleanup failed: " + "; ".join(errors))


def _ensure_mpv_at_startup() -> None:
    """在 real 模式下，服务启动时立即拉起 mpv 全屏黑窗口（遮住桌面）。"""
    if _real_adapter is None:
        return
    try:
        _ensure_mpv()
        _log.info("engine_adapter: mpv started at startup (fullscreen idle)")
    except MpvUnavailableError as exc:
        _log.warning("engine_adapter: mpv not available at startup: %s (will retry on first play)", exc)


# ══════════════════════════════════════════════
# 延迟重新 resolve —— 补开机时节点还没 ready 的时序缝隙
# ══════════════════════════════════════════════

def _deferred_re_resolve() -> None:
    """开机后退避重试 resolve，直到当前配置的节点全部解析出真实 IP 或耗尽重试。

    覆盖冷启动时节点还没连 WiFi / avahi 还没 ready 的时序缝隙。
    单次 30s 对慢冷启动不够，改为退避重试；任一次全部解析成功即停止。
    """
    if ENGINE_ADAPTER != "real":
        return

    for attempt, delay in enumerate(
        (15, 15, 30, 30, 60, 60, 120),
        start=1,
    ):
        if _watchdog_stop.wait(delay):
            return

        try:
            _refresh_wled_profile(reason=f"deferred resolve #{attempt}")
            with _profile_refresh_lock:
                unresolved = [
                    d["device_id"] for d in _devices
                    if not d.get("host") or str(d["host"]).endswith(".local")
                ]

            if not unresolved:
                _log.info(
                    "deferred re-resolve #%d: all configured nodes resolved",
                    attempt,
                )
                return

            _log.info(
                "deferred re-resolve #%d: unresolved nodes remain: %s",
                attempt,
                unresolved,
            )

        except Exception as exc:
            _log.warning(
                "deferred re-resolve #%d failed: %s",
                attempt,
                exc,
            )

    _log.warning(
        "deferred re-resolve: retry schedule exhausted; "
        "some nodes are still unresolved"
    )


_deferred_re_resolve_thread: threading.Thread | None = None


def _start_deferred_re_resolve() -> None:
    """Start exactly one deferred node-resolution worker."""
    global _deferred_re_resolve_thread

    if ENGINE_ADAPTER != "real":
        return

    if (
        _deferred_re_resolve_thread is not None
        and _deferred_re_resolve_thread.is_alive()
    ):
        return

    _deferred_re_resolve_thread = threading.Thread(
        target=_deferred_re_resolve,
        name="deferred-re-resolve",
        daemon=True,
    )
    _deferred_re_resolve_thread.start()

    _log.info(
        "engine_adapter: deferred re-resolve thread started"
    )


def startup() -> None:
    """Acquire production runtime resources for one application lifetime."""
    if ENGINE_ADAPTER != "real":
        return
    _watchdog_stop.clear()
    _refresh_wled_profile(reason="Host startup resolve")
    from light_engine.config import Config
    Config(ENGINE_PROFILE_PATH)
    _init_real_adapter()
    if _real_adapter is None:
        return
    _state["video_available"] = _detect_video_available()
    _ensure_mpv_at_startup()
    _start_natural_end_watchdog()
    _start_deferred_re_resolve()
