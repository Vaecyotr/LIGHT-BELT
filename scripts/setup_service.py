#!/usr/bin/env python3
"""LIGHT-BELT WiFi 配网服务。

用 NetworkManager (nmcli) 管理一切 WiFi 操作，
不装 hostapd / dnsmasq，不碰 /etc/resolv.conf，
和 systemd-resolved 零冲突。

流程：
  启动 → 已连 WiFi？
    是 → mDNS 广播 Host Service 地址，HTTP 状态 API 待命
    否 → 启动 SoftAP 热点 → 手机连热点 → APP 调 API 提交 WiFi 凭据
       → 板子连目标 WiFi → 关热点 → mDNS 广播新地址

2026-07 修订：
  1. /connect 立即返回，切换在后台线程执行（原来先关热点再切换，
     手机当场掉线，响应永远送不出去，操作者看不到成败）。
  2. 热点改为 WPA2 加密（原来是开放热点，手机会因"无互联网"
     自动切回蜂窝数据，配网页面打不开）。
  3. 新增看门狗线程：掉线自动重连、连不上自动重开热点、
     IP 变化自动重新广播 mDNS（原来只在启动时判断一次）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time

from flask import Flask, jsonify, request as flask_request

# ════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════

HOTSPOT_SSID = "LIGHT-BELT_Setup"       # 手机搜到的热点名
HOTSPOT_PASSWORD = "12345678"            # 必须 8~63 字符；留空会退回开放热点
WLAN_IFNAME = "wlan0"                    # 无线网卡名
API_PORT = 8080                          # 配网 HTTP 端口
HOST_SERVICE_PORT = 8443                 # LIGHT-BELT Host Service 端口
MDNS_SERVICE_TYPE = "_light-belt._tcp.local."
MDNS_INSTANCE_NAME = "LIGHT-BELT-RK3588"
CONNECT_TIMEOUT_S = 30                   # 连 WiFi 超时秒数
RETRY_INTERVAL_S = 10                    # 已保存 WiFi 重连间隔

WATCHDOG_INTERVAL_S = 30                 # 看门狗巡检间隔
WATCHDOG_FAIL_THRESHOLD = 3              # 连续几次掉线才动手（约 90 秒）

# ════════════════════════════════════════════════
# 日志
# ════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
_log = logging.getLogger("wifi-setup")

# ════════════════════════════════════════════════
# nmcli 封装
# ════════════════════════════════════════════════

def _run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command and return result; never raises on non-zero exit."""
    _log.debug("$ %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def wifi_is_connected() -> tuple[bool, str | None, str | None]:
    """Return (connected, ssid, ip)."""
    r = _run(["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION",
              "device", "show", WLAN_IFNAME])
    connected = "100 (connected)" in r.stdout or "100 (已连接)" in r.stdout
    ssid = None
    for line in r.stdout.splitlines():
        if "GENERAL.CONNECTION:" in line:
            val = line.split(":", 1)[-1].strip()
            if val and val != "--":
                ssid = val
    ip = _get_wlan_ip()
    return connected, ssid, ip


def _get_wlan_ip() -> str | None:
    """Get the IPv4 address on wlan0."""
    r = _run(["ip", "-4", "-o", "addr", "show", WLAN_IFNAME])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else None


def _is_real_lan_ip(ip: str | None) -> bool:
    """热点自身网关地址 (10.42.x.x) 不算真正上网。"""
    return bool(ip) and not ip.startswith("10.42.")


def wifi_scan() -> list[dict]:
    """Scan and return list of {ssid, signal, security}."""
    # Rescan first (best-effort)
    _run(["nmcli", "device", "wifi", "rescan", "ifname", WLAN_IFNAME])
    time.sleep(2)
    r = _run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list",
              "ifname", WLAN_IFNAME])
    results: list[dict] = []
    seen: set[str] = set()
    for line in r.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        ssid = parts[0].strip()
        if not ssid or ssid in seen or ssid == HOTSPOT_SSID:
            continue
        seen.add(ssid)
        results.append({
            "ssid": ssid,
            "signal": int(parts[1]) if parts[1].isdigit() else 0,
            "security": parts[2] if parts[2] else "OPEN",
        })
    results.sort(key=lambda x: x["signal"], reverse=True)
    return results


def wifi_connect(ssid: str, password: str) -> tuple[bool, str]:
    """Connect to a WiFi network. Returns (success, message)."""
    # Delete existing connection with same name to avoid conflicts
    _run(["nmcli", "connection", "delete", ssid])
    time.sleep(1)

    cmd = [
        "nmcli", "device", "wifi", "connect", ssid,
        "ifname", WLAN_IFNAME,
    ]
    if password:
        cmd += ["password", password]

    r = _run(cmd, timeout=CONNECT_TIMEOUT_S + 5)

    if r.returncode == 0:
        # Wait for IP
        for _ in range(10):
            time.sleep(1)
            ip = _get_wlan_ip()
            if _is_real_lan_ip(ip):
                return True, ip
        ip = _get_wlan_ip()
        if ip:
            return True, ip
        return False, "已连接但未获取到 IP"
    else:
        msg = (r.stderr or r.stdout or "未知错误").strip()
        return False, msg


def wifi_saved_connections() -> list[str]:
    """Return names of saved wifi connections."""
    r = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    results = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and "wireless" in parts[1]:
            name = parts[0].strip()
            if name and name != HOTSPOT_SSID and name != "Hotspot":
                results.append(name)
    return results


# ════════════════════════════════════════════════
# SoftAP 热点（用 nmcli，不装 hostapd/dnsmasq）
# ════════════════════════════════════════════════

_hotspot_active = False


def hotspot_start() -> str | None:
    """Start SoftAP hotspot via nmcli. Returns hotspot IP or None."""
    global _hotspot_active

    # Kill any existing hotspot
    hotspot_stop()

    cmd = [
        "nmcli", "device", "wifi", "hotspot",
        "ifname", WLAN_IFNAME,
        "ssid", HOTSPOT_SSID,
        "con-name", "Hotspot",
    ]
    if HOTSPOT_PASSWORD:
        cmd += ["password", HOTSPOT_PASSWORD]

    r = _run(cmd)
    if r.returncode != 0:
        _log.error("热点启动失败: %s", (r.stderr or r.stdout).strip())
        # Fallback: build the AP connection manually
        cmd2 = [
            "nmcli", "connection", "add", "type", "wifi",
            "ifname", WLAN_IFNAME, "con-name", "Hotspot",
            "autoconnect", "no", "ssid", HOTSPOT_SSID,
            "802-11-wireless.mode", "ap",
            "802-11-wireless.band", "bg",
            "ipv4.method", "shared",
        ]
        if HOTSPOT_PASSWORD:
            cmd2 += [
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", HOTSPOT_PASSWORD,
            ]
        r2 = _run(cmd2)
        if r2.returncode != 0:
            _log.error("热点备用方案也失败: %s", (r2.stderr or r2.stdout).strip())
            return None
        _run(["nmcli", "connection", "up", "Hotspot"])

    _hotspot_active = True
    # Wait for IP assignment
    for _ in range(10):
        time.sleep(1)
        ip = _get_wlan_ip()
        if ip:
            _log.info("SoftAP 已启动: %s (%s)", HOTSPOT_SSID, ip)
            return ip
    _log.warning("热点已启动但未获取到 IP")
    return _get_wlan_ip() or "10.42.0.1"


def hotspot_stop():
    """Stop the hotspot if running."""
    global _hotspot_active
    _run(["nmcli", "connection", "down", "Hotspot"])
    _run(["nmcli", "connection", "delete", "Hotspot"])
    _hotspot_active = False


# ════════════════════════════════════════════════
# mDNS 广播
# ════════════════════════════════════════════════

_mdns_info = None
_mdns_zc = None
_mdns_ip: str | None = None


def mdns_register(ip: str):
    """Register mDNS service advertising the Host Service."""
    global _mdns_info, _mdns_zc, _mdns_ip
    mdns_unregister()
    try:
        from zeroconf import Zeroconf, ServiceInfo
        _mdns_zc = Zeroconf()
        _mdns_info = ServiceInfo(
            MDNS_SERVICE_TYPE,
            f"{MDNS_INSTANCE_NAME}.{MDNS_SERVICE_TYPE}",
            addresses=[socket.inet_aton(ip)],
            port=HOST_SERVICE_PORT,
            properties={
                "path": "/api/v1/status",
                "setup_port": str(API_PORT),
            },
        )
        _mdns_zc.register_service(_mdns_info)
        _mdns_ip = ip
        _log.info("mDNS 已广播: %s → %s:%d", MDNS_INSTANCE_NAME, ip, HOST_SERVICE_PORT)
    except ImportError:
        _log.warning("zeroconf 未安装，跳过 mDNS 广播")
    except Exception as exc:
        _log.warning("mDNS 注册失败: %s", exc)


def mdns_unregister():
    """Remove mDNS registration."""
    global _mdns_info, _mdns_zc, _mdns_ip
    if _mdns_zc and _mdns_info:
        try:
            _mdns_zc.unregister_service(_mdns_info)
            _mdns_zc.close()
        except Exception:
            pass
    _mdns_info = None
    _mdns_zc = None
    _mdns_ip = None


# ════════════════════════════════════════════════
# 后台切换（修订 1）
# ════════════════════════════════════════════════

_switching = False
_switch_state: dict = {
    "status": "idle",      # idle | switching | success | failed
    "ssid": None,
    "ip": None,
    "message": None,
}


def _do_switch(ssid: str, password: str):
    """在后台线程里完成 关热点 → 连目标WiFi → 成功广播/失败重开热点。"""
    global _switching
    try:
        hotspot_stop()
        time.sleep(2)
        ok, result = wifi_connect(ssid, password)
        if ok:
            _log.info("连接成功: %s (%s)", ssid, result)
            _switch_state.update(status="success", ssid=ssid, ip=result, message=None)
            mdns_register(result)
        else:
            _log.warning("连接失败: %s — %s", ssid, result)
            _switch_state.update(status="failed", ssid=ssid, ip=None, message=result)
            hotspot_start()
    except Exception as exc:                      # noqa: BLE001
        _log.error("切换过程异常: %s", exc)
        _switch_state.update(status="failed", ssid=ssid, ip=None, message=str(exc))
        hotspot_start()
    finally:
        _switching = False


# ════════════════════════════════════════════════
# 看门狗（修订 3）
# ════════════════════════════════════════════════

def _watchdog():
    """掉线自动重连；连不上自动重开热点；IP 变化重新广播 mDNS。"""
    fails = 0
    while True:
        time.sleep(WATCHDOG_INTERVAL_S)
        if _switching or _hotspot_active:
            continue
        try:
            connected, _ssid, ip = wifi_is_connected()
            if connected and _is_real_lan_ip(ip):
                fails = 0
                if ip != _mdns_ip:
                    _log.info("IP 变化 %s → %s，重新广播 mDNS", _mdns_ip, ip)
                    mdns_register(ip)
                continue

            fails += 1
            _log.warning("WiFi 异常 (%d/%d)", fails, WATCHDOG_FAIL_THRESHOLD)
            if fails < WATCHDOG_FAIL_THRESHOLD:
                continue

            fails = 0
            ok, new_ip = _try_saved_wifi()
            if ok and new_ip:
                _log.info("看门狗已恢复连接: %s", new_ip)
                mdns_register(new_ip)
            else:
                _log.warning("已保存的 WiFi 全部连不上，重开配网热点")
                hotspot_start()
        except Exception as exc:                  # noqa: BLE001
            _log.error("看门狗异常: %s", exc)


# ════════════════════════════════════════════════
# Flask HTTP API
# ════════════════════════════════════════════════

app = Flask(__name__)
# Suppress Flask's default request logs in production
flog = logging.getLogger("werkzeug")
flog.setLevel(logging.WARNING)


@app.route("/status", methods=["GET"])
def api_status():
    connected, ssid, ip = wifi_is_connected()
    return jsonify({
        "code": 0,
        "data": {
            "connected": connected,
            "ssid": ssid,
            "ip": ip,
            "softap_active": _hotspot_active,
            "host_service_port": HOST_SERVICE_PORT,
            "switch": dict(_switch_state),
        },
    })


@app.route("/scan", methods=["GET"])
def api_scan():
    networks = wifi_scan()
    return jsonify({"code": 0, "data": {"networks": networks}})


@app.route("/connect", methods=["POST"])
def api_connect():
    """立即返回，切换在后台进行。

    手机在热点关闭的瞬间就会掉线，所以这里不能等切换结果再响应。
    判断方法：等约 60 秒——
      热点消失不再出现 → 成功，改连目标 WiFi 后访问 /status 看新 IP
      热点重新出现     → 失败，重连热点后访问 /status 看 switch.message
    """
    global _switching
    body = flask_request.get_json(silent=True) or {}
    ssid = (body.get("ssid") or "").strip()
    password = body.get("password") or ""
    if not ssid:
        return jsonify({"code": 1, "message": "缺少 ssid"}), 400
    if _switching:
        return jsonify({"code": 3, "message": "正在切换中，请稍候"}), 409

    _log.info("收到配网请求: SSID=%s", ssid)
    _switching = True
    _switch_state.update(status="switching", ssid=ssid, ip=None, message=None)
    threading.Thread(target=_do_switch, args=(ssid, password), daemon=True).start()

    return jsonify({
        "code": 0,
        "data": {
            "status": "switching",
            "ssid": ssid,
            "hint": "热点即将关闭。约 60 秒后：热点未再出现=成功；热点重新出现=失败，重连后查 /status",
        },
    })


@app.route("/saved", methods=["GET"])
def api_saved():
    """List saved WiFi connections."""
    return jsonify({"code": 0, "data": {"connections": wifi_saved_connections()}})


@app.route("/forget", methods=["POST"])
def api_forget():
    """Delete a saved WiFi connection."""
    body = flask_request.get_json(silent=True) or {}
    name = (body.get("ssid") or "").strip()
    if not name:
        return jsonify({"code": 1, "message": "缺少 ssid"}), 400
    _run(["nmcli", "connection", "delete", name])
    return jsonify({"code": 0, "data": {"deleted": name}})


@app.route("/hotspot", methods=["POST"])
def api_hotspot():
    """手动开启配网热点。注意：调用后当前 WiFi 会断开。"""
    global _switching
    if _switching:
        return jsonify({"code": 3, "message": "正在切换中"}), 409
    threading.Thread(target=hotspot_start, daemon=True).start()
    return jsonify({"code": 0, "data": {"ssid": HOTSPOT_SSID, "status": "starting"}})


# ════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════

def _try_saved_wifi() -> tuple[bool, str | None]:
    """Try connecting with saved WiFi profiles. Returns (success, ip)."""
    saved = wifi_saved_connections()
    if not saved:
        _log.info("无已保存的 WiFi 配置")
        return False, None

    _log.info("尝试已保存的 WiFi: %s", ", ".join(saved))
    for name in saved:
        _run(["nmcli", "connection", "up", name])
        for _ in range(15):
            time.sleep(1)
            connected, ssid, ip = wifi_is_connected()
            if connected and _is_real_lan_ip(ip):
                return True, ip
        _log.warning("连接 %s 失败，尝试下一个", name)
    return False, None


def main():
    _log.info("LIGHT-BELT 配网服务启动")

    if HOTSPOT_PASSWORD and not (8 <= len(HOTSPOT_PASSWORD) <= 63):
        _log.error("HOTSPOT_PASSWORD 必须 8~63 字符，当前 %d 字符，热点将无法启动",
                   len(HOTSPOT_PASSWORD))

    # 1. Try saved WiFi first
    connected, _, ip = wifi_is_connected()
    if not connected or not _is_real_lan_ip(ip):
        connected, ip = _try_saved_wifi()

    if connected and ip:
        _log.info("WiFi 已连接: %s", ip)
        mdns_register(ip)
    else:
        # 2. No WiFi → start SoftAP
        _log.info("WiFi 未连接，启动配网热点")
        hotspot_ip = hotspot_start()
        if hotspot_ip:
            _log.info("请用手机连接热点 '%s'，网关 IP: %s", HOTSPOT_SSID, hotspot_ip)
        else:
            _log.error("热点启动失败，仍然启动 API 等待重试")

    # 3. Watchdog
    threading.Thread(target=_watchdog, daemon=True).start()
    _log.info("看门狗已启动，每 %d 秒巡检", WATCHDOG_INTERVAL_S)

    # 4. Start HTTP API (blocks)
    _log.info("配网 API 监听: http://0.0.0.0:%d", API_PORT)
    try:
        app.run(host="0.0.0.0", port=API_PORT, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        hotspot_stop()
        mdns_unregister()
        _log.info("配网服务已停止")


def _signal_handler(sig, frame):
    hotspot_stop()
    mdns_unregister()
    sys.exit(0)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

if __name__ == "__main__":
    main()