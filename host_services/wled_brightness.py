"""Push a brightness scale to WLED nodes via HTTP (fire-and-forget)."""

from __future__ import annotations

import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger(__name__)


class ManagedStateError(RuntimeError):
    def __init__(self, message: str, *, submitted: bool):
        super().__init__(message)
        self.submitted = submitted


def reports_off(snapshot: dict) -> bool:
    return (
        snapshot["state"]["on"] is False and snapshot["info"]["live"] is False
    )


def _post_bri(host: str, bri: int, timeout: float) -> None:
    try:
        payload = json.dumps({"on": True, "bri": bri, "v": False}).encode()
        req = urllib.request.Request(
            f"http://{host}/json/state",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout)
    except Exception as exc:
        _log.debug("wled_brightness: %s: %s", host, exc)


def apply_scale(devices: list[dict], scale: float, timeout: float = 1.0) -> None:
    """POST brightness to all WLED devices concurrently."""
    bri = max(0, min(255, round(255 * scale)))
    hosts = [d["host"] for d in devices if d.get("host")]
    if not hosts:
        return
    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_post_bri, h, bri, timeout) for h in hosts]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass


def apply_managed(devices: list[dict], scale: float | None, timeout: float) -> None:
    """Set the stored brightness or power off, confirming each enabled node."""
    wanted = {"on": False} if scale is None else {"bri": round(255 * scale)}
    def update(host):
        url = f"http://{host}/json/state"
        request = urllib.request.Request(url, data=json.dumps(wanted).encode(),
                                         headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request, timeout=timeout):
            pass
        try:
            readback = f"http://{host}/json/si" if scale is None else url
            with urllib.request.urlopen(readback, timeout=timeout) as response:
                actual = json.load(response)
            confirmed = reports_off(actual) if scale is None else actual.get("bri") == wanted["bri"]
            if not confirmed:
                raise ValueError("WLED state does not match the requested setting")
        except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
            raise ManagedStateError(str(exc), submitted=True) from exc

    hosts = [device["host"] for device in devices if device.get("host")]
    failures = []
    submitted = bool(hosts)
    with ThreadPoolExecutor(max_workers=max(1,len(hosts))) as executor:
        attempts = [(host,executor.submit(update,host)) for host in hosts]
        for host, future in attempts:
            try:
                future.result()
            except (RuntimeError, ValueError, OSError) as exc:
                submitted = submitted and isinstance(exc, ManagedStateError) and exc.submitted
                failures.append(f"{host}: {exc}")
    if failures or not hosts:
        raise ManagedStateError(
            "; ".join(failures) or "no enabled WLED output", submitted=submitted,
        )


def apply_off(devices: list[dict], timeout: float = 1.0) -> None:
    """把各节点本地状态关掉。

    DDP 停流后 WLED 会在 if.live.timeout（当前 2.5s）后退出 realtime，
    回落到节点自己的本地状态；出厂默认是「开 + 琥珀色 (255,160,0)」，
    表现为节目结束后灯带全黄。停止播放时显式关掉即可。
    """
    hosts = [d["host"] for d in devices if d.get("host")]
    if not hosts:
        return
    payload = json.dumps({"on": False, "v": False}).encode()

    def _off(host: str) -> None:
        try:
            req = urllib.request.Request(
                f"http://{host}/json/state",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=timeout)
        except Exception as exc:
            _log.debug("wled_brightness: off %s: %s", host, exc)

    with ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_off, h) for h in hosts]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass
