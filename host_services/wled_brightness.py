"""Push a brightness scale to WLED nodes via HTTP (fire-and-forget)."""

from __future__ import annotations

import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger(__name__)


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
