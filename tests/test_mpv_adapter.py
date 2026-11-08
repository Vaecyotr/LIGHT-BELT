from __future__ import annotations

import json
import socket
import time

import pytest

import light_engine.media.mpv_adapter as mpv_adapter
from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvIPCError


class ScriptedSocket:
    def __init__(self, replies):
        self.replies = replies
        self.buffer = bytearray()
        self.closed = False
        self.timeout = None
        self.request_count = 0

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, _path):
        pass

    def sendall(self, payload):
        request = json.loads(payload)
        self.request_count += 1
        self.buffer.extend(self.replies(request["request_id"]))

    def recv(self, size):
        if self.closed:
            raise OSError("socket is closed")
        if not self.buffer:
            return b""
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def close(self):
        self.closed = True


def test_ipc_correlates_multiline_events_and_preserves_persistent_connection(monkeypatch):
    def replies(request_id):
        if request_id == 1:
            lines = [
                {"event": "pause"},
                {"request_id": 99, "error": "success", "data": "stale"},
                {"request_id": 1, "error": "success", "data": 17},
            ]
        else:
            lines = [{"request_id": 2, "error": "success", "data": True}]
        return b"".join(json.dumps(line).encode() + b"\n" for line in lines)

    transport = ScriptedSocket(replies)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_args: transport)
    client = MpvIPCAdapter("ipc", timeout=0.2)

    assert client.get_property("volume") == 17
    assert client.get_property("pause") is True
    assert transport.request_count == 2
    assert not transport.closed
    client.close()


class SlowByteSocket(ScriptedSocket):
    def __init__(self, reply, byte_delay):
        super().__init__(lambda _request_id: reply)
        self.byte_delay = byte_delay

    def recv(self, size):
        if self.timeout is not None and self.timeout < self.byte_delay:
            time.sleep(self.timeout)
            raise socket.timeout("read timed out")
        time.sleep(self.byte_delay)
        return super().recv(min(size, 1))


def test_ipc_request_has_one_total_deadline_across_partial_reads(monkeypatch):
    reply = json.dumps({"request_id": 1, "error": "success", "data": 17}).encode() + b"\n"
    transport = SlowByteSocket(reply, byte_delay=0.01)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_args: transport)
    client = MpvIPCAdapter("ipc", timeout=0.06)
    started = time.monotonic()

    with pytest.raises(MpvIPCError, match="request failed"):
        client.get_property("volume")

    assert time.monotonic() - started < 0.25
    assert transport.closed


def test_ipc_deadline_applies_while_consuming_buffered_unrelated_events(monkeypatch):
    def replies(request_id):
        lines = [
            {"event": "pause"},
            {"request_id": 99, "error": "success", "data": "stale"},
            {"request_id": request_id, "error": "success", "data": 17},
        ]
        return b"".join(json.dumps(line).encode() + b"\n" for line in lines)

    transport = ScriptedSocket(replies)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_args: transport)
    times = iter((0.0, 0.2, 0.8, 1.1))
    monkeypatch.setattr(mpv_adapter.time, "monotonic", lambda: next(times))
    client = MpvIPCAdapter("ipc", timeout=1.0)

    with pytest.raises(MpvIPCError, match="request failed"):
        client.get_property("volume")

    assert transport.closed


@pytest.mark.parametrize("reply", [b"", b"not-json\n", b"[]\n", b"null\n", b"\xff\n"])
def test_ipc_eof_or_malformed_response_closes_connection(monkeypatch, reply):
    transport = ScriptedSocket(lambda _request_id: reply)
    monkeypatch.setattr(socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(socket, "socket", lambda *_args: transport)
    client = MpvIPCAdapter("ipc")

    with pytest.raises(MpvIPCError):
        client.get_property("volume")

    assert transport.closed
