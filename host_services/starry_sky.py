"""Local submission and deduplication for the starry sky UDP toggle."""

from __future__ import annotations

import socket
import os
from threading import Lock

HOST = os.environ.get("STARRY_SKY_HOST", "192.168.31.205")
PORT = int(os.environ.get("STARRY_SKY_PORT", "3333"))
_UDP_TIMEOUT = 1.0

_assumed_on: bool = False
_lock = Lock()


def _send_toggle() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(_UDP_TIMEOUT)
        sock.sendto(b"toggle", (HOST, PORT))


def _submit(wanted: bool) -> bool:
    global _assumed_on
    with _lock:
        if wanted == _assumed_on:
            return False
        _send_toggle()
        _assumed_on = wanted
        return True


def ensure_on() -> bool:
    return _submit(True)


def ensure_off() -> bool:
    return _submit(False)


def action_at_position(actions: list[tuple[float, bool]], position_ms: float) -> bool:
    """Resolve the last authored action at the media position."""
    return next((on for at_ms, on in reversed(actions) if at_ms <= position_ms), False)


def get_assumed_state() -> bool:
    """Return the local deduplication flag. Physical state has no feedback."""
    with _lock:
        return _assumed_on


def reset_state() -> None:
    """Clear the process-local submission history without sending a toggle."""
    global _assumed_on
    with _lock:
        _assumed_on = False
