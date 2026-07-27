#!/usr/bin/env python3
"""按 MAC 地址发现 WLED 节点的当前 IP，生成站点 profile。

换 WiFi 环境后节点 IP 会变（DHCP），本脚本按固定不变的 MAC 找回它们，
把 IP 写进一份生成的 profile，供 host service 使用。

用法：
    # 只探测并报告，不写文件（验证用）
    python3 scripts/resolve_nodes.py --check

    # 探测并生成 profile（systemd ExecStartPre 用这个）
    python3 scripts/resolve_nodes.py --out data/site-profile.yaml

发现顺序：
    1. mDNS：wled-<mac后6位>.local        （快，1 秒内）
    2. 全网段 HTTP 扫描 /json/info        （慢，约 10 秒，兜底）
    两种方式都用 /json/info 返回的 mac 做最终确认，不会认错设备。

找不到的节点保留 base profile 里的原 IP，并打印警告；
脚本永远以 0 退出，不阻塞 host service 启动。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import yaml

# ════════════════════════════════════════════════════════════════
# 节点 MAC 对照表 —— 换板子时改这里
# 采集于 2026-07-27，来源 /json/info 的 mac 字段
# ════════════════════════════════════════════════════════════════
NODE_MACS: dict[int, str] = {
    1: "e08cfe32f5f0",   # strip_32          左侧舷窗
    2: "2805a50fdc3c",   # strip_41+strip_31 屏幕右/左
    3: "a4f00f8dfe78",   # strip_44+strip_43 右墙波浪
    4: "a4f00f8e1abc",   # strip_12+strip_11 顶棚
    5: "e08cfe32e8b4",   # strip_22+strip_21 地面
}

# starry_sky 目前不在网上，MAC 未知。查到后填进来即可自动解析。
STARRY_SKY_MAC: str | None = None

HTTP_TIMEOUT = 1.5
SCAN_WORKERS = 64


# ════════════════════════════════════════════════════════════════
# 工具
# ════════════════════════════════════════════════════════════════

def norm_mac(mac: str) -> str:
    """统一成小写无分隔符形式。"""
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def log(msg: str) -> None:
    print(f"[resolve_nodes] {msg}", file=sys.stderr, flush=True)


def probe_mac(ip: str, timeout: float = HTTP_TIMEOUT) -> str | None:
    """访问 http://<ip>/json/info，返回该设备的 MAC；失败返回 None。"""
    try:
        with urllib.request.urlopen(f"http://{ip}/json/info", timeout=timeout) as r:
            info = json.loads(r.read().decode("utf-8", "replace"))
        mac = info.get("mac")
        return norm_mac(mac) if mac else None
    except Exception:
        return None


def resolve_mdns(hostname: str) -> str | None:
    """把 xxx.local 解析成 IP（依赖 avahi + libnss-mdns）。"""
    try:
        return socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
    except Exception:
        return None


def local_subnet() -> str | None:
    """返回本机所在 /24 网段前缀，例如 '192.168.31'。"""
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            capture_output=True, text=True, timeout=10,
        ).stdout
    except Exception:
        return None
    m = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/", out)
    return m.group(1) if m else None


# ════════════════════════════════════════════════════════════════
# 发现
# ════════════════════════════════════════════════════════════════

def discover(wanted: dict[int, str]) -> dict[str, str]:
    """返回 {mac: ip}，只包含确认成功的。"""
    found: dict[str, str] = {}

    # ── 阶段 1：mDNS ──
    # WLED 默认主机名是 wled-<mac 后 3 字节>
    log("阶段1 mDNS 解析...")
    def try_mdns(mac: str) -> tuple[str, str | None]:
        ip = resolve_mdns(f"wled-{mac[-6:]}.local")
        if ip and probe_mac(ip) == mac:
            return mac, ip
        return mac, None

    with ThreadPoolExecutor(max_workers=8) as ex:
        for mac, ip in ex.map(try_mdns, wanted.values()):
            if ip:
                found[mac] = ip
                log(f"  mDNS 命中 {mac} -> {ip}")

    missing = {n: m for n, m in wanted.items() if m not in found}
    if not missing:
        return found

    # ── 阶段 2：全网段 HTTP 扫描 ──
    sub = local_subnet()
    if not sub:
        log("未能判断本机网段，跳过扫描")
        return found
    log(f"阶段2 扫描 {sub}.0/24（缺 {len(missing)} 个节点）...")

    targets = set(wanted[n] for n in missing)

    def scan(i: int) -> tuple[str, str] | None:
        ip = f"{sub}.{i}"
        mac = probe_mac(ip, timeout=1.0)
        return (mac, ip) if mac and mac in targets else None

    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        for res in ex.map(scan, range(1, 255)):
            if res:
                mac, ip = res
                found[mac] = ip
                log(f"  扫描命中 {mac} -> {ip}")

    return found


# ════════════════════════════════════════════════════════════════
# 生成 profile
# ════════════════════════════════════════════════════════════════

def rewrite_profile(base_path: str, out_path: str, found: dict[str, str]) -> int:
    """把发现到的 IP 写进 digital_nodes[].host，返回未找到的节点数。"""
    with open(base_path, "r", encoding="utf-8") as fh:
        profile = yaml.safe_load(fh)

    nodes = profile.get("layout", {}).get("digital_nodes", [])
    if not nodes:
        log(f"错误：{base_path} 里没有 layout.digital_nodes")
        return len(NODE_MACS)

    missing = 0
    for node in nodes:
        nid = node.get("node_id")
        mac = NODE_MACS.get(nid)
        if not mac:
            log(f"  node {nid}: 对照表里没有它的 MAC，保留 {node.get('host')}")
            continue
        ip = found.get(mac)
        old = node.get("host")
        if ip:
            node["host"] = ip
            mark = "不变" if ip == old else f"{old} -> {ip}"
            log(f"  node {nid}: {mark}")
        else:
            missing += 1
            log(f"  node {nid}: !! 未找到（mac {mac}），保留旧值 {old}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# 本文件由 scripts/resolve_nodes.py 自动生成，请勿手工编辑。\n")
        fh.write(f"# base: {base_path}\n")
        yaml.safe_dump(profile, fh, allow_unicode=True, sort_keys=False)
    os.replace(tmp, out_path)
    log(f"已写出 {out_path}")
    return missing


# ════════════════════════════════════════════════════════════════

def main() -> int:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--profile",
        default=os.path.join(here, "config", "profiles", "rk3588-host-service.yaml"),
        help="基准 profile（提供布局与像素数）",
    )
    ap.add_argument(
        "--out",
        default=os.path.join(here, "data", "site-profile.yaml"),
        help="生成的站点 profile 路径",
    )
    ap.add_argument("--check", action="store_true",
                    help="只探测并报告，不写文件")
    args = ap.parse_args()

    found = discover(NODE_MACS)

    if STARRY_SKY_MAC:
        sm = norm_mac(STARRY_SKY_MAC)
        sip = found.get(sm)
        if sip:
            log(f"starry_sky -> {sip}（记得设 STARRY_SKY_HOST）")

    log(f"共找到 {len(found)}/{len(NODE_MACS)} 个节点")

    if args.check:
        print()
        for nid, mac in sorted(NODE_MACS.items()):
            ip = found.get(mac, "未找到")
            print(f"  node_{nid}  {mac}  ->  {ip}")
        return 0

    rewrite_profile(args.profile, args.out, found)
    return 0   # 永远成功，不阻塞 host service 启动


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:          # noqa: BLE001
        log(f"异常（忽略，不阻塞启动）：{type(exc).__name__}: {exc}")
        sys.exit(0)