from __future__ import annotations

import asyncio

import pytest

from host_services.bluetooth import (
    AudioSystem,
    BackendUnavailable,
    DisabledBackend,
    create_backend,
)


class Backend:
    def __init__(self):
        self.devices = [
            {"id": "a", "name": "A", "paired": True, "connected": True},
            {"id": "b", "name": "B", "paired": True, "connected": True},
            {"id": "c", "name": "C", "paired": False, "connected": False},
        ]
        self.calls = []
        self.gate = False

    async def start(self, callbacks):
        self.callbacks = callbacks

    async def close(self):
        pass

    async def snapshot(self):
        return {
            "available": True,
            "devices": [
                dict(item, activity="idle", source_available=True)
                for item in self.devices
            ],
            "challenges": [],
        }

    async def pair(self, device_id, request_id):
        self.calls.append(("pair", device_id, request_id))

    async def connect(self, device_id):
        self.calls.append(("connect", device_id))

    async def disconnect(self, device_id):
        self.calls.append(("disconnect", device_id))

    async def remove(self, device_id):
        self.calls.append(("remove", device_id))

    async def answer_challenge(self, challenge_id, device_id, accept, value):
        self.calls.append(("answer", challenge_id, device_id, accept, value))

    async def set_speaker_route(self, device_id):
        self.calls.append(("route", device_id))
        return device_id


def test_pair_reservations_enforce_two_connected_plus_one_pending_limit():
    asyncio.run(_pair_reservations_enforce_two_connected_plus_one_pending_limit())


async def _pair_reservations_enforce_two_connected_plus_one_pending_limit():
    backend = Backend()
    system = AudioSystem(backend, gate_mpv=_gate)
    await system.start()

    with pytest.raises(BackendUnavailable, match="capacity"):
        await system.pair("c")

    assert not any(call[0] == "pair" for call in backend.calls)


def test_same_pair_request_is_idempotent_and_does_not_double_reserve():
    asyncio.run(_same_pair_request_is_idempotent_and_does_not_double_reserve())


async def _same_pair_request_is_idempotent_and_does_not_double_reserve():
    backend = Backend()
    backend.devices = [{"id": "c", "name": "C", "paired": False, "connected": False}]
    system = AudioSystem(backend, gate_mpv=_gate)
    await system.start()

    first = await system.pair("c", operation_id="op-1")
    second = await system.pair("c", operation_id="op-1")

    assert first == second
    assert [call for call in backend.calls if call[0] == "pair"] == [
        ("pair", "c", "op-1")
    ]


def test_real_backend_factory_fails_closed_without_explicit_hardware_gate():
    with pytest.raises(BackendUnavailable, match="H2/H3"):
        create_backend(allow_real=True, h2_h3_verified=False)
    assert isinstance(create_backend(), DisabledBackend)


async def _gate(_muted):
    return None
