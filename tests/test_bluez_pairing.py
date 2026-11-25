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


def test_two_simultaneous_pair_reservations_cannot_overbook_one_free_slot():
    async def run():
        backend = Backend()
        backend.devices = [
            {"id": "a", "paired": True, "connected": True},
            {"id": "b", "paired": False, "connected": False},
            {"id": "c", "paired": False, "connected": False},
        ]
        system = AudioSystem(backend, gate_mpv=_gate)
        await system.start()
        results = await asyncio.gather(
            system.pair("b", operation_id="b-op"),
            system.pair("c", operation_id="c-op"),
            return_exceptions=True,
        )
        assert sum(isinstance(result, str) for result in results) == 1
        assert sum(isinstance(result, BackendUnavailable) for result in results) == 1
        assert len(system._pending) == 1

    asyncio.run(run())


def test_unknown_route_owner_keeps_gate_closed_until_route_is_verified_or_removed():
    async def run():
        class UnknownRouteBackend(Backend):
            async def snapshot(self):
                facts = await super().snapshot()
                facts["route_error"] = "module index was reused by another owner"
                return facts

        gates = []
        system = AudioSystem(
            UnknownRouteBackend(), gate_mpv=lambda muted: _record(gates, muted)
        )
        system._started = True
        system._route = {"device": "a", "module_id": "9", "verified": True}
        await system._gate_program(True)
        with pytest.raises(BackendUnavailable, match="ownership is uncertain"):
            await system._on_backend_event()
        assert system._route["module_id"] == "9"
        assert gates == [True]
        system._started = False
        system._closed = True

    asyncio.run(run())


async def _gate(_muted):
    return None


async def _record(values, value):
    values.append(value)
