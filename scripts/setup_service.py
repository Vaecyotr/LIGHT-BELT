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
import ipaddress
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Mapping

from flask import Flask, jsonify, request as flask_request

# ════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════

HOTSPOT_SSID = "LIGHT-BELT_Setup"       # 手机搜到的热点名
HOTSPOT_PASSWORD = "12345678"            # 必须 8~63 字符；留空会退回开放热点
# site_client keeps these historical defaults.  portable_ap validates that its
# radio and security settings were explicitly supplied by deployment config.
NETWORK_MODE = os.environ.get("LIGHT_BELT_NETWORK_MODE", "site_client").strip()
WLAN_IFNAME = os.environ.get("LIGHT_BELT_WLAN_INTERFACE", "wlan0").strip()
API_PORT = 8080                          # 配网 HTTP 端口
HOST_SERVICE_PORT = 8443                 # LIGHT-BELT Host Service 端口
MDNS_SERVICE_TYPE = "_light-belt._tcp.local."
MDNS_INSTANCE_NAME = "LIGHT-BELT-RK3588"
CONNECT_TIMEOUT_S = 30                   # 连 WiFi 超时秒数
RETRY_INTERVAL_S = 10                    # 已保存 WiFi 重连间隔

WATCHDOG_INTERVAL_S = 30                 # 看门狗巡检间隔
WATCHDOG_FAIL_THRESHOLD = 3              # 连续几次掉线才动手（约 90 秒）

SITE_CLIENT_MODE = "site_client"
PORTABLE_AP_MODE = "portable_ap"
DEFAULT_CABIN_AP_CONNECTION = "LIGHT-BELT Cabin AP"


@dataclass(frozen=True)
class NetworkConfig:
    """Deployment-owned network configuration.

    Loading is deliberately separate from module import so an invalid portable
    deployment fails at service startup (with a useful error), not while test
    tooling or a WSGI loader imports this module.
    """

    mode: str
    wlan_interface: str
    cabin_ap_ssid: str | None = None
    cabin_ap_password: str | None = None
    cabin_ap_ipv4_cidr: str | None = None
    cabin_ap_connection: str = DEFAULT_CABIN_AP_CONNECTION


def load_network_config(env: Mapping[str, str] | None = None) -> NetworkConfig:
    """Load and fail-close validate the two supported network modes.

    ``portable_ap`` intentionally requires an explicit interface as well as
    credentials and addressing.  Falling back to wlan0 in that mode could make
    a multi-radio deployment take over the wrong device.
    """
    source = os.environ if env is None else env
    mode = source.get("LIGHT_BELT_NETWORK_MODE", SITE_CLIENT_MODE).strip()
    if mode not in {SITE_CLIENT_MODE, PORTABLE_AP_MODE}:
        raise ValueError("LIGHT_BELT_NETWORK_MODE must be site_client or portable_ap")

    configured_interface = source.get("LIGHT_BELT_WLAN_INTERFACE", "").strip()
    config = NetworkConfig(
        mode=mode,
        wlan_interface=(configured_interface or "wlan0"),
        cabin_ap_ssid=source.get("LIGHT_BELT_CABIN_AP_SSID", "").strip() or None,
        cabin_ap_password=source.get("LIGHT_BELT_CABIN_AP_PASSWORD", "") or None,
        cabin_ap_ipv4_cidr=source.get("LIGHT_BELT_CABIN_AP_IPV4_CIDR", "").strip() or None,
        cabin_ap_connection=(source.get(
            "LIGHT_BELT_CABIN_AP_CONNECTION", DEFAULT_CABIN_AP_CONNECTION
        ).strip() or DEFAULT_CABIN_AP_CONNECTION),
    )
    if mode == PORTABLE_AP_MODE:
        if not configured_interface:
            raise ValueError("portable_ap requires LIGHT_BELT_WLAN_INTERFACE")
        _validate_portable_config(config)
    return config


def _validate_portable_config(config: NetworkConfig) -> None:
    """Validate values that can be checked without touching NetworkManager."""
    if config.mode != PORTABLE_AP_MODE:
        raise ValueError("portable AP validation requires portable_ap mode")
    if not config.wlan_interface or any(ch.isspace() for ch in config.wlan_interface):
        raise ValueError("portable_ap requires a valid Wi-Fi interface name")
    ssid = config.cabin_ap_ssid
    if not ssid or "\x00" in ssid or len(ssid.encode("utf-8")) > 32:
        raise ValueError("LIGHT_BELT_CABIN_AP_SSID must be 1..32 UTF-8 bytes")
    password = config.cabin_ap_password
    if not password or "\x00" in password or not 8 <= len(password) <= 63:
        raise ValueError("LIGHT_BELT_CABIN_AP_PASSWORD must be a WPA2 passphrase of 8..63 characters")
    if not config.cabin_ap_connection or config.cabin_ap_connection == "Hotspot":
        raise ValueError("LIGHT_BELT_CABIN_AP_CONNECTION must be a dedicated non-Hotspot name")
    try:
        address = ipaddress.ip_interface(config.cabin_ap_ipv4_cidr or "")
    except ValueError as exc:
        raise ValueError("LIGHT_BELT_CABIN_AP_IPV4_CIDR must be a valid IPv4 CIDR") from exc
    if not isinstance(address, ipaddress.IPv4Interface) or not 1 <= address.network.prefixlen <= 30:
        raise ValueError("LIGHT_BELT_CABIN_AP_IPV4_CIDR must be an IPv4 gateway CIDR (/1../30)")
    if address.ip in {address.network.network_address, address.network.broadcast_address}:
        raise ValueError("LIGHT_BELT_CABIN_AP_IPV4_CIDR must use a usable gateway address")

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
    safe_cmd = _redact_command(cmd)
    _log.debug("$ %s", " ".join(safe_cmd))
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        _log.error("command timed out after %d seconds: %s", timeout, " ".join(safe_cmd))
        return subprocess.CompletedProcess(
            args=safe_cmd,
            returncode=124,
            stdout="",
            stderr=f"command timed out after {timeout} seconds",
        )


def _redact_command(cmd: list[str]) -> list[str]:
    """Return a log-safe command copy; NetworkManager accepts PSKs as argv."""
    redacted: list[str] = []
    redact_next = False
    for value in cmd:
        if redact_next:
            redacted.append("<redacted>")
            redact_next = False
            continue
        key, separator, _secret = value.partition("=")
        if separator and key.lower() in {"password", "psk", "wifi-sec.psk"}:
            redacted.append(f"{key}=<redacted>")
        else:
            redacted.append(value)
            if value.lower() in {"password", "psk", "wifi-sec.psk"}:
                redact_next = True
    return redacted


def _nmcli_error(result: subprocess.CompletedProcess, password: str | None = None) -> str:
    """Return an operator-useful error without ever reflecting a supplied PSK."""
    message = (result.stderr or result.stdout or "nmcli failed").strip()
    if password:
        message = message.replace(password, "<redacted>")
    return message


def _portable_mode_selected() -> bool:
    """Cheap mode check suitable for request/signal paths before validation."""
    return os.environ.get("LIGHT_BELT_NETWORK_MODE", NETWORK_MODE).strip() == PORTABLE_AP_MODE


def _nmcli_value(field: str, interface: str) -> tuple[bool, str]:
    """Read one NetworkManager device property without parsing localized text."""
    result = _run(["nmcli", "-g", field, "device", "show", interface])
    return result.returncode == 0, result.stdout.strip()


def _validate_portable_interface(config: NetworkConfig) -> None:
    """Confirm the explicitly selected NM device is managed and AP capable."""
    ok, device_type = _nmcli_value("GENERAL.TYPE", config.wlan_interface)
    if not ok or device_type.lower() not in {"wifi", "802-11-wireless"}:
        raise RuntimeError(f"portable_ap interface {config.wlan_interface!r} does not exist or is not Wi-Fi")
    ok, managed = _nmcli_value("GENERAL.NM-MANAGED", config.wlan_interface)
    if not ok or managed.lower() not in {"yes", "true"}:
        raise RuntimeError(f"portable_ap interface {config.wlan_interface!r} is not managed by NetworkManager")
    ok, ap_capable = _nmcli_value("WIFI-PROPERTIES.AP", config.wlan_interface)
    if not ok or ap_capable.lower() not in {"yes", "true"}:
        raise RuntimeError(f"portable_ap interface {config.wlan_interface!r} has no AP capability")


def _connection_exists(connection: str) -> bool:
    """Use NM's exact connection lookup so similarly named profiles are safe."""
    result = _run(["nmcli", "connection", "show", connection])
    if result.returncode == 0:
        return True
    if result.returncode == 10:
        return False
    raise RuntimeError(
        f"unable to inspect dedicated Cabin AP profile {connection!r}: "
        + _nmcli_error(result)
    )


def _portable_ap_is_active(config: NetworkConfig) -> bool:
    """AP health is profile activation, never Internet/uplink reachability."""
    ok, connection = _nmcli_value("GENERAL.CONNECTION", config.wlan_interface)
    return ok and connection == config.cabin_ap_connection


def portable_ap_status(config: NetworkConfig | None = None) -> dict[str, object]:
    """Return additive portable state for the status endpoint and tests."""
    config = config or load_network_config()
    ap_ip = _get_wlan_ip(config.wlan_interface) if config.mode == PORTABLE_AP_MODE else None
    return {
        "network_mode": config.mode,
        "ap_interface": config.wlan_interface if config.mode == PORTABLE_AP_MODE else None,
        "ap_ssid": config.cabin_ap_ssid if config.mode == PORTABLE_AP_MODE else None,
        "ap_ip": ap_ip if config.mode == PORTABLE_AP_MODE else None,
        "ap_active": _portable_ap_is_active(config) if config.mode == PORTABLE_AP_MODE else False,
    }


def ensure_portable_ap(config: NetworkConfig | None = None) -> str | None:
    """Reconcile and activate the one persistent Cabin AP profile.

    This deliberately never deletes a profile.  Activation may replace a
    site-client connection on the *explicitly configured* interface, but all
    saved site-client profiles remain intact for a later mode change.
    """
    config = config or load_network_config()
    _validate_portable_config(config)
    _validate_portable_interface(config)

    if not _connection_exists(config.cabin_ap_connection):
        created = _run([
            "nmcli", "connection", "add", "type", "wifi",
            "ifname", config.wlan_interface,
            "con-name", config.cabin_ap_connection,
            "autoconnect", "yes",
            "ssid", config.cabin_ap_ssid or "",
            "802-11-wireless.mode", "ap",
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", config.cabin_ap_password or "",
            "ipv4.method", "shared",
            "ipv4.addresses", config.cabin_ap_ipv4_cidr or "",
            "ipv6.method", "disabled",
        ])
        if created.returncode != 0:
            raise RuntimeError("unable to create dedicated Cabin AP profile: " +
                               _nmcli_error(created, config.cabin_ap_password))

    reconciled = _run([
        "nmcli", "connection", "modify", config.cabin_ap_connection,
        "connection.autoconnect", "yes",
        "connection.interface-name", config.wlan_interface,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.ssid", config.cabin_ap_ssid or "",
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.psk", config.cabin_ap_password or "",
        "ipv4.method", "shared",
        "ipv4.addresses", config.cabin_ap_ipv4_cidr or "",
        "ipv6.method", "disabled",
    ])
    if reconciled.returncode != 0:
        raise RuntimeError("unable to reconcile dedicated Cabin AP profile: " +
                           _nmcli_error(reconciled, config.cabin_ap_password))

    activated = _run([
        "nmcli", "connection", "up", config.cabin_ap_connection,
        "ifname", config.wlan_interface,
    ])
    if activated.returncode != 0:
        raise RuntimeError("unable to activate dedicated Cabin AP profile: " +
                           _nmcli_error(activated, config.cabin_ap_password))
    return _get_wlan_ip(config.wlan_interface)


def portable_ap_watchdog_tick(config: NetworkConfig | None = None) -> bool:
    """Perform one AP-only recovery attempt; convenient for deterministic tests."""
    config = config or load_network_config()
    _validate_portable_config(config)
    if _portable_ap_is_active(config):
        return True
    _log.warning("Cabin AP profile is inactive; requesting NetworkManager recovery")
    try:
        ensure_portable_ap(config)
    except (RuntimeError, ValueError) as exc:
        _log.error("Cabin AP recovery failed: %s", exc)
        return False
    return _portable_ap_is_active(config)


def wifi_is_connected(interface: str | None = None) -> tuple[bool, str | None, str | None]:
    """Return (connected, ssid, ip)."""
    interface = interface or WLAN_IFNAME
    r = _run(["nmcli", "-t", "-f", "GENERAL.STATE,GENERAL.CONNECTION",
              "device", "show", interface])
    connected = "100 (connected)" in r.stdout or "100 (已连接)" in r.stdout
    ssid = None
    for line in r.stdout.splitlines():
        if "GENERAL.CONNECTION:" in line:
            val = line.split(":", 1)[-1].strip()
            if val and val != "--":
                ssid = val
    ip = _get_wlan_ip(interface)
    return connected, ssid, ip


def _get_wlan_ip(interface: str | None = None) -> str | None:
    """Get the IPv4 address on the selected Wi-Fi interface."""
    r = _run(["ip", "-4", "-o", "addr", "show", interface or WLAN_IFNAME])
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else None


def _is_real_lan_ip(ip: str | None) -> bool:
    """热点自身网关地址 (10.42.x.x) 不算真正上网。"""
    return bool(ip) and not ip.startswith("10.42.")


def _is_site_client_connection(
    config: NetworkConfig,
    connected: bool,
    active_connection: str | None,
    ip: str | None,
) -> bool:
    """Reject dedicated Cabin AP activation from site-client health checks."""
    cabin_connections = {config.cabin_ap_connection, DEFAULT_CABIN_AP_CONNECTION}
    return connected and active_connection not in cabin_connections and _is_real_lan_ip(ip)


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
        return False, _nmcli_error(r, password)


def wifi_saved_connections() -> list[str]:
    """Return names of saved wifi connections."""
    cabin_connections = {DEFAULT_CABIN_AP_CONNECTION}
    try:
        cabin_connections.add(load_network_config().cabin_ap_connection)
    except ValueError:
        # Startup validation will report the deployment error. Do not let a
        # malformed configuration expose the dedicated profile as site Wi-Fi.
        pass
    r = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
    results = []
    for line in r.stdout.strip().splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and "wireless" in parts[1]:
            name = parts[0].strip()
            if name and name != HOTSPOT_SSID and name != "Hotspot" and name not in cabin_connections:
                results.append(name)
    return results


# ════════════════════════════════════════════════
# SoftAP 热点（用 nmcli，不装 hostapd/dnsmasq）
# ════════════════════════════════════════════════

_hotspot_active = False


def hotspot_start() -> str | None:
    """Start SoftAP hotspot via nmcli. Returns hotspot IP or None."""
    global _hotspot_active

    # The legacy Hotspot profile is intentionally temporary.  In portable
    # mode, callers must reconcile the dedicated persistent profile instead.
    if _portable_mode_selected():
        return ensure_portable_ap()

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
        _log.error("热点启动失败: %s", _nmcli_error(r, HOTSPOT_PASSWORD))
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
            _log.error("热点备用方案也失败: %s", _nmcli_error(r2, HOTSPOT_PASSWORD))
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
    # Never down/delete the permanent Cabin profile during a service restart,
    # signal, or Flask cleanup.  Its lifecycle belongs to NetworkManager.
    if _portable_mode_selected():
        _hotspot_active = False
        return
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

def _watchdog(config: NetworkConfig | None = None):
    """掉线自动重连；连不上自动重开热点；IP 变化重新广播 mDNS。"""
    config = config or load_network_config()
    if config.mode == PORTABLE_AP_MODE:
        failures = 0
        while True:
            time.sleep(WATCHDOG_INTERVAL_S)
            if portable_ap_watchdog_tick(config):
                failures = 0
                ap_ip = _get_wlan_ip(config.wlan_interface)
                if ap_ip and ap_ip != _mdns_ip:
                    _log.info("Cabin AP 地址变化 %s → %s，重新广播 mDNS", _mdns_ip, ap_ip)
                    mdns_register(ap_ip)
                continue
            failures += 1
            if failures >= WATCHDOG_FAIL_THRESHOLD:
                _log.error("Cabin AP recovery still failing after %d attempts", failures)
                failures = 0
        # Not reached: portable AP must never enter the site-client watchdog.

    fails = 0
    while True:
        time.sleep(WATCHDOG_INTERVAL_S)
        if _switching or _hotspot_active:
            continue
        try:
            connected, active_connection, ip = wifi_is_connected(config.wlan_interface)
            if _is_site_client_connection(config, connected, active_connection, ip):
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
    config = load_network_config()
    connected, ssid, ip = wifi_is_connected(config.wlan_interface)
    portable = portable_ap_status(config)
    return jsonify({
        "code": 0,
        "data": {
            "connected": connected,
            "ssid": ssid,
            "ip": ip,
            "softap_active": _hotspot_active,
            "host_service_port": HOST_SERVICE_PORT,
            "switch": dict(_switch_state),
            # Additive fields: old clients keep their historical response.
            **portable,
        },
    })


@app.route("/scan", methods=["GET"])
def api_scan():
    if _portable_mode_selected():
        return jsonify({"code": 3, "message": "portable_ap 模式不允许扫描；扫描可能中断 Cabin AP"}), 409
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
    if _portable_mode_selected():
        return jsonify({"code": 3, "message": "portable_ap 模式不允许切换现场 WiFi"}), 409
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
    if _portable_mode_selected():
        config = load_network_config()
        if name in {config.cabin_ap_connection, DEFAULT_CABIN_AP_CONNECTION}:
            return jsonify({"code": 3, "message": "portable_ap 的 Cabin AP profile 不可通过此接口删除"}), 409
        resolved = _run(["nmcli", "-g", "connection.id", "connection", "show", name])
        if resolved.returncode != 0:
            return jsonify({"code": 3, "message": "portable_ap 无法安全确认待删除的 WiFi profile"}), 409
        resolved_names = {line.strip() for line in resolved.stdout.splitlines() if line.strip()}
        if config.cabin_ap_connection in resolved_names or DEFAULT_CABIN_AP_CONNECTION in resolved_names:
            return jsonify({"code": 3, "message": "portable_ap 的 Cabin AP profile 不可通过此接口删除"}), 409
    _run(["nmcli", "connection", "delete", name])
    return jsonify({"code": 0, "data": {"deleted": name}})


@app.route("/hotspot", methods=["POST"])
def api_hotspot():
    """手动开启配网热点。注意：调用后当前 WiFi 会断开。"""
    global _switching
    if _portable_mode_selected():
        return jsonify({"code": 3, "message": "portable_ap 已管理永久 Cabin AP，不能启动临时热点"}), 409
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


def cleanup_service():
    """Release process-owned state without deleting a persistent Cabin AP."""
    hotspot_stop()
    mdns_unregister()


def main():
    _log.info("LIGHT-BELT 配网服务启动")

    try:
        config = load_network_config()
    except ValueError as exc:
        _log.error("网络配置无效，服务拒绝启动: %s", exc)
        return 2

    if HOTSPOT_PASSWORD and not (8 <= len(HOTSPOT_PASSWORD) <= 63):
        _log.error("HOTSPOT_PASSWORD 必须 8~63 字符，当前 %d 字符，热点将无法启动",
                   len(HOTSPOT_PASSWORD))

    if config.mode == PORTABLE_AP_MODE:
        # No saved-site-WiFi search and no Internet test in this branch.
        try:
            ap_ip = ensure_portable_ap(config)
        except (RuntimeError, ValueError) as exc:
            _log.error("Cabin AP 启动失败，服务拒绝启动: %s", exc)
            return 2
        if ap_ip:
            _log.info("永久 Cabin AP 已启动: %s (%s)", config.cabin_ap_ssid, ap_ip)
            mdns_register(ap_ip)
        else:
            _log.warning("Cabin AP 已激活但暂未读取到 IPv4 地址")
    else:
        # Preserve the legacy saved/site Wi-Fi -> temporary setup hotspot flow.
        connected, active_connection, ip = wifi_is_connected(config.wlan_interface)
        if not _is_site_client_connection(config, connected, active_connection, ip):
            connected, ip = _try_saved_wifi()

        if connected and ip:
            _log.info("WiFi 已连接: %s", ip)
            mdns_register(ip)
        else:
            _log.info("WiFi 未连接，启动配网热点")
            hotspot_ip = hotspot_start()
            if hotspot_ip:
                _log.info("请用手机连接热点 '%s'，网关 IP: %s", HOTSPOT_SSID, hotspot_ip)
            else:
                _log.error("热点启动失败，仍然启动 API 等待重试")

    # 3. Watchdog
    threading.Thread(target=_watchdog, args=(config,), daemon=True).start()
    _log.info("看门狗已启动，每 %d 秒巡检", WATCHDOG_INTERVAL_S)

    # 4. Start HTTP API (blocks)
    _log.info("配网 API 监听: http://0.0.0.0:%d", API_PORT)
    try:
        app.run(host="0.0.0.0", port=API_PORT, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup_service()
        _log.info("配网服务已停止")
    return 0


def _signal_handler(sig, frame):
    cleanup_service()
    sys.exit(0)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

if __name__ == "__main__":
    raise SystemExit(main())
