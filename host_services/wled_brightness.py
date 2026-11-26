"""Managed WLED brightness and power writes with per-node readback."""

from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.request import Request


class ManagedStateError(RuntimeError):
    """A managed write failed; ``attempts`` records each node's evidence."""

    def __init__(self, message: str, *, attempts: list[dict[str, Any]]):
        super().__init__(message)
        self.attempts = attempts
        self.submitted = any(attempt["submitted"] for attempt in attempts)
        self.confirmed = bool(attempts) and all(
            attempt["confirmed"] for attempt in attempts
        )


def reports_off(snapshot: dict) -> bool:
    return (
        snapshot["state"]["on"] is False
        and snapshot["info"]["live"] is False
    )


def _write_one(device: dict, scale: float | None, timeout: float,
               keep_off: bool) -> dict[str, Any]:
    host = device["host"]
    attempt: dict[str, Any] = {
        "device_id": device.get("id", device.get("device_id")),
        "host": host,
        "submitted": False,
        "confirmed": False,
        "post_error": None,
        "readback_error": None,
        "mismatch": None,
    }
    power_off = keep_off or scale is None
    payload: dict[str, Any] = {"v": False}
    if power_off:
        payload["on"] = False
    else:
        payload["on"] = True
    if scale is not None:
        # WLED treats bri=0 as a possible power-off command. Managed zero is
        # represented by black logical frames; retain a valid stored level.
        payload["bri"] = max(1, min(255, round(255 * scale)))

    url = f"http://{host}/json/state"
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
        attempt["submitted"] = True
    except Exception as exc:
        attempt["post_error"] = str(exc)
        return attempt

    try:
        readback_url = f"http://{host}/json/si" if power_off else url
        with urllib.request.urlopen(readback_url, timeout=timeout) as response:
            actual = json.load(response)
        if power_off:
            confirmed = reports_off(actual)
            actual_state = actual.get("state", {})
            if scale is not None:
                confirmed = confirmed and actual_state.get("bri") == payload["bri"]
        else:
            confirmed = actual.get("on") is True
            if scale is not None:
                confirmed = confirmed and actual.get("bri") == payload["bri"]
        if confirmed:
            attempt["confirmed"] = True
        else:
            attempt["mismatch"] = "WLED readback does not match requested state"
    except Exception as exc:
        attempt["readback_error"] = str(exc)
    return attempt


def apply_managed(
    devices: list[dict], scale: float | None, timeout: float,
    *, keep_off: bool = False,
) -> list[dict[str, Any]]:
    """Apply and confirm managed brightness or power state on each WLED node.

    ``scale=None`` explicitly powers nodes off. ``keep_off=True`` stores the
    brightness while keeping nodes off. Returns per-node submission and
    confirmation evidence, or raises :class:`ManagedStateError` on any failure.
    """
    enabled = [device for device in devices if device.get("host")]
    if not enabled:
        raise ManagedStateError("no enabled WLED output", attempts=[])
    with ThreadPoolExecutor(max_workers=len(enabled)) as executor:
        futures = [executor.submit(_write_one, device, scale, timeout, keep_off)
                   for device in enabled]
        attempts = [future.result() for future in futures]
    failures = []
    for attempt in attempts:
        if attempt["post_error"]:
            failures.append(f"{attempt['host']}: POST failed: {attempt['post_error']}")
        elif attempt["readback_error"]:
            failures.append(f"{attempt['host']}: GET failed: {attempt['readback_error']}")
        elif attempt["mismatch"]:
            failures.append(f"{attempt['host']}: {attempt['mismatch']}")
    if failures:
        raise ManagedStateError("; ".join(failures), attempts=attempts)
    return attempts
