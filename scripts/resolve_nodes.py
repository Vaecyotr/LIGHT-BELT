#!/usr/bin/env python3
"""按 MAC 地址发现 WLED 节点的当前 IP，生成站点 profile。（v2）

换 WiFi 环境后节点 IP 会变（DHCP），本脚本按固定不变的 MAC 找回它们。

用法：
    python3 scripts/resolve_nodes.py --check          # 只探测并报告
    python3 scripts/resolve_nodes.py --out <path>     # 生成 profile
    python3 scripts/resolve_nodes.py --check --scan   # 前两级都失败时才加 --scan

v2 相对 v1 的改动（2026-07-27）：
  · 主路径改用 avahi 原生工具，不再用 socket.getaddrinfo()。
    实测板上 avahi-resolve 正常但 getent hosts 失败（libnss-mdns 有问题），
    v1 因此 mDNS 阶段全军覆没。
  · MAC 直接从 mDNS 主机名 wled-<mac后6位> 推出，不再强依赖 HTTP /json/info。
    HTTP 只做尽力而为的二次确认，失败不影响结果 —— v1 在 HTTP 不通时
    整个发现流程会崩掉。
  · 新增 IP 缓存：上次成功的结果存盘，作为第二级兜底（5 次请求）。
  · 全网段扫描降级为可选（--scan），并发 64→8。
    实测 254 地址 × 64 并发会打乱板子的邻居表/驱动状态，副作用严重。
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

# starry_sky 目前不在网上，MAC 未知。查到后填进来。
STARRY_SKY_MAC: str | None = None

HTTP_TIMEOUT = 2.0
AVAHI_TIMEOUT = 6
SCAN_WORKERS = 8          # v1 是 64，太重，会打乱板子网络状态


# ════════════════════════════════════════════════════════════════
# 工具
# ════════════════════════════════════════════════════════════════

def norm_mac(mac: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", mac).lower()


def log(msg: str) -> None:
    print(f"[resolve_nodes] {msg}", file=sys.stderr, flush=True)


def run(cmd: list[str], timeout: int = 15) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout
    except Exception:
        return ""


def http_mac(ip: str, timeout: float = HTTP_TIMEOUT) -> str | None:
    """尽力而为地读 /json/info 的 mac；不通返回 None（不影响主流程）。"""
    try:
        with urllib.request.urlopen(f"http://{ip}/json/info", timeout=timeout) as r:
            info = json.loads(r.read().decode("utf-8", "replace"))
        mac = info.get("mac")
        return norm_mac(mac) if mac else None
    except Exception:
        return None


def local_subnet() -> str | None:
    out = run(["ip", "-4", "-o", "addr", "show", "scope", "global"], 10)
    m = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/", out)
    return m.group(1) if m else None


# ════════════════════════════════════════════════════════════════
# 发现：三级，逐级降级
# ════════════════════════════════════════════════════════════════

def stage1_avahi_resolve(wanted: set[str]) -> dict[str, str]:
    """avahi-resolve -n wled-<mac后6位>.local

    WLED 默认主机名就是 wled-<mac 后 3 字节>，所以主机名本身携带 MAC，
    解析成功即等于身份确认，无需再访问 HTTP。
    """
    names = {f"wled-{m[-6:]}.local": m for m in wanted}
    out = run(["avahi-resolve", "-4", "-n", *names.keys()], AVAHI_TIMEOUT + 4)
    found: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        host, ip = parts[0].strip(), parts[1].strip()
        mac = names.get(host) or names.get(host.rstrip("."))
        if mac and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip):
            found[mac] = ip
            log(f"  mDNS 命中 {host} -> {ip}")
    return found


def stage2_avahi_browse(wanted: set[str]) -> dict[str, str]:
    """avahi-browse -rpt _wled._tcp —— WLED 原生广播的服务类型。"""
    out = run(["avahi-browse", "-rpt", "--no-db-lookup", "_wled._tcp"],
              AVAHI_TIMEOUT + 6)
    found: dict[str, str] = {}
    for line in out.splitlines():
        if not line.startswith("="):
            continue
        f = line.split(";")
        if len(f) < 9:
            continue
        name, addr = f[3], f[7]
        m = re.search(r"wled-([0-9a-fA-F]{6})", name)
        if not m or not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", addr):
            continue
        suffix = m.group(1).lower()
        for mac in wanted:
            if mac.endswith(suffix):
                found[mac] = addr
                log(f"  _wled._tcp 命中 {name} -> {addr}")
    return found


def stage3_cache(wanted: set[str], cache: dict[str, str]) -> dict[str, str]:
    """上次成功的 IP，逐个用 HTTP 确认（最多 5 次请求）。"""
    cands = {m: cache[m] for m in wanted if m in cache}
    if not cands:
        return {}
    log(f"  尝试缓存里的 {len(cands)} 个旧地址...")
    found = {}
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        for mac, got in zip(cands, ex.map(http_mac, cands.values())):
            if got == mac:
                found[mac] = cands[mac]
                log(f"  缓存命中 {mac} -> {cands[mac]}")
    return found


def stage4_scan(wanted: set[str]) -> dict[str, str]:
    """全网段 HTTP 扫描。副作用大，只在显式 --scan 时启用。"""
    sub = local_subnet()
    if not sub:
        log("  未能判断网段，跳过扫描")
        return {}
    log(f"  扫描 {sub}.0/24（并发 {SCAN_WORKERS}，会比较慢）...")

    def probe(i: int):
        ip = f"{sub}.{i}"
        mac = http_mac(ip, timeout=1.5)
        return (mac, ip) if mac and mac in wanted else None

    found = {}
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as ex:
        for res in ex.map(probe, range(1, 255)):
            if res:
                found[res[0]] = res[1]
                log(f"  扫描命中 {res[0]} -> {res[1]}")
    return found


def discover(macs: dict[int, str], cache: dict[str, str],
             allow_scan: bool) -> dict[str, str]:
    found: dict[str, str] = {}
    remaining = set(macs.values())

    for label, fn in (
        ("阶段1 avahi-resolve", lambda w: stage1_avahi_resolve(w)),
        ("阶段2 _wled._tcp",    lambda w: stage2_avahi_browse(w)),
        ("阶段3 IP 缓存",       lambda w: stage3_cache(w, cache)),
    ):
        if not remaining:
            break
        log(f"{label}（缺 {len(remaining)}）...")
        try:
            found.update(fn(remaining))
        except Exception as exc:                        # noqa: BLE001
            log(f"  {label} 异常: {type(exc).__name__}: {exc}")
        remaining = set(macs.values()) - set(found)

    if remaining and allow_scan:
        log(f"阶段4 全网段扫描（缺 {len(remaining)}）...")
        try:
            found.update(stage4_scan(remaining))
        except Exception as exc:                        # noqa: BLE001
            log(f"  扫描异常: {exc}")
    elif remaining:
        log(f"仍缺 {len(remaining)} 个；如需全网段扫描请加 --scan")

    return found


# ════════════════════════════════════════════════════════════════
# 生成 profile
# ════════════════════════════════════════════════════════════════

def rewrite_profile(base: str, out: str, found: dict[str, str]) -> int:
    with open(base, "r", encoding="utf-8") as fh:
        profile = yaml.safe_load(fh)

    nodes = profile.get("layout", {}).get("digital_nodes", [])
    if not nodes:
        log(f"错误：{base} 里没有 layout.digital_nodes")
        return len(NODE_MACS)

    missing = 0
    for node in nodes:
        nid = node.get("node_id")
        mac = NODE_MACS.get(nid)
        if not mac:
            log(f"  node {nid}: 对照表无此 MAC，保留 {node.get('host')}")
            continue
        ip, old = found.get(mac), node.get("host")
        if ip:
            node["host"] = ip
            log(f"  node {nid}: {'不变' if ip == old else f'{old} -> {ip}'}")
        else:
            missing += 1
            log(f"  node {nid}: !! 未找到（{mac}），保留旧值 {old}")

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# 由 scripts/resolve_nodes.py 自动生成，请勿手工编辑。\n")
        fh.write(f"# base: {base}\n")
        yaml.safe_dump(profile, fh, allow_unicode=True, sort_keys=False)
    os.replace(tmp, out)
    log(f"已写出 {out}")
    return missing


def load_cache(path: str) -> dict[str, str]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return {norm_mac(k): v for k, v in json.load(fh).items()}
    except Exception:
        return {}


def save_cache(path: str, found: dict[str, str]) -> None:
    if not found:
        return
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(found, fh, indent=2)
    except Exception as exc:                            # noqa: BLE001
        log(f"缓存写入失败（忽略）: {exc}")


# ════════════════════════════════════════════════════════════════

def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=os.path.join(
        root, "config", "profiles", "rk3588-host-service.yaml"))
    ap.add_argument("--out", default=os.path.join(
        root, "data", "site-profile.yaml"))
    ap.add_argument("--cache", default=os.path.join(
        root, "data", "node-ip-cache.json"))
    ap.add_argument("--check", action="store_true", help="只报告，不写 profile")
    ap.add_argument("--scan", action="store_true",
                    help="允许全网段扫描（副作用大，仅在前三级都失败时用）")
    ap.add_argument("--verify-http", action="store_true",
                    help="额外用 HTTP 二次确认每个结果（不影响成败）")
    args = ap.parse_args()

    cache = load_cache(args.cache)
    found = discover(NODE_MACS, cache, args.scan)

    if args.verify_http:
        for mac, ip in sorted(found.items()):
            got = http_mac(ip)
            state = "OK" if got == mac else ("HTTP不通" if got is None else f"MAC不符({got})")
            log(f"  验证 {ip} -> {state}")

    log(f"共找到 {len(found)}/{len(NODE_MACS)} 个节点")
    save_cache(args.cache, found)

    if STARRY_SKY_MAC:
        sip = found.get(norm_mac(STARRY_SKY_MAC))
        if sip:
            log(f"starry_sky -> {sip}（记得设 STARRY_SKY_HOST）")

    if args.check:
        print()
        for nid, mac in sorted(NODE_MACS.items()):
            print(f"  node_{nid}  {mac}  ->  {found.get(mac, '未找到')}")
        return 0

    rewrite_profile(args.profile, args.out, found)
    return 0        # 永远成功，不阻塞 host service 启动


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                            # noqa: BLE001
        log(f"异常（忽略，不阻塞启动）: {type(exc).__name__}: {exc}")
        sys.exit(0)