"""mpv JSON IPC adapter used by media clocks."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Optional


class MpvIPCError(RuntimeError):
    """Raised for explicit mpv IPC connection and protocol failures."""


@dataclass(frozen=True)
class MpvState:
    position: float
    paused: bool
    ended: bool


class MpvIPCAdapter:
    """Small synchronous client for mpv's JSON IPC socket."""

    def __init__(self, ipc_path: str, timeout: float = 1.0):
        self._ipc_path = ipc_path
        self._timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._request_id = 0
        self._read_buffer = bytearray()

    def connect(self) -> None:
        if self._socket is not None:
            return
        self._read_buffer.clear()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._timeout)
        try:
            sock.connect(self._ipc_path)
        except OSError as exc:
            sock.close()
            raise MpvIPCError(f"mpv IPC connection failed: {self._ipc_path}") from exc
        self._socket = sock

    def read_state(self) -> MpvState:
        position = self.get_property("playback-time")
        paused = self.get_property("pause")
        idle = self.get_property("idle-active")
        eof = self.get_property("eof-reached")
        return MpvState(
            position=float(position or 0.0),
            paused=bool(paused),
            ended=bool(idle) or bool(eof),
        )

    def get_property(self, name: str) -> Any:
        response = self._request(["get_property", name])
        if response.get("error") != "success":
            raise MpvIPCError(f"mpv get_property failed for {name}: {response.get('error')}")
        return response.get("data")

    def _request(self, command: list[Any]) -> dict[str, Any]:
        deadline = time.monotonic() + self._timeout
        try:
            self.connect()
            assert self._socket is not None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("mpv IPC request deadline expired")
            self._socket.settimeout(remaining)
            self._request_id += 1
            payload = {"command": command, "request_id": self._request_id}
            self._socket.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            while True:
                line = self._readline(deadline)
                response = json.loads(line.decode("utf-8"))
                if not isinstance(response, dict):
                    raise MpvIPCError("mpv IPC response must be a JSON object")
                if response.get("request_id") == self._request_id:
                    return response
        except (OSError, UnicodeError, json.JSONDecodeError, MpvIPCError) as exc:
            self.close()
            if isinstance(exc, MpvIPCError):
                raise
            raise MpvIPCError("mpv IPC request failed") from exc

    def _readline(self, deadline: float) -> bytes:
        assert self._socket is not None
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise socket.timeout("mpv IPC request deadline expired")
            newline = self._read_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._read_buffer[:newline])
                del self._read_buffer[: newline + 1]
                return line
            self._socket.settimeout(remaining)
            chunk = self._socket.recv(4096)
            if not chunk:
                raise MpvIPCError("mpv IPC socket closed")
            self._read_buffer.extend(chunk)

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._read_buffer.clear()
