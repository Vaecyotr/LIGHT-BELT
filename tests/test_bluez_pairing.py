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


def test_backend_factory_no_longer_requires_hardware_gate_for_real_linux_backend(monkeypatch):
    monkeypatch.setattr("host_services.bluetooth.sys.platform", "linux")
    backend = create_backend(allow_real=True)
    assert backend.__class__.__name__ == "LinuxBluezBackend"
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


def test_pa_route_loss_holds_gate_and_recreates_route_after_pa_recovers():
    async def run():
        route = {"device": "a", "module_id": "42", "verified": True}
        facts = {
            "available": True,
            "devices": [{
                "id": "a", "paired": True, "connected": True,
                "activity": "transmitting", "source_available": True,
            }],
            "speaker_route": dict(route),
            "digital_target": {"kind": "phone_pcm", "source_id": "a"},
            "challenges": [],
        }

        class RestartingAudioBackend(Backend):
            async def snapshot(self):
                return {**facts, "devices": facts["devices"]}

            async def set_speaker_route(self, device_id):
                self.calls.append(("open", device_id))
                fresh = {"device": device_id, "module_id": "99", "verified": True}
                facts["speaker_route"] = fresh
                facts["digital_target"] = {"kind": "phone_pcm", "source_id": device_id}
                return fresh

            async def close_speaker_route(self):
                self.calls.append(("close",))
                facts["speaker_route"] = None

        gates = []
        backend = RestartingAudioBackend()
        system = AudioSystem(backend, gate_mpv=lambda muted: _record(gates, muted))
        await system.start()
        assert system.snapshot()["speaker"]["status"] == "routed"

        facts["route_error"] = "PulseAudio restarted"
        with pytest.raises(BackendUnavailable):
            await system._on_backend_event()
        assert gates[-1] is True

        facts.pop("route_error")
        facts["speaker_route"] = None
        facts["devices"] = [{**facts["devices"][0], "source_available": False}]
        await system._on_backend_event()
        assert system.snapshot()["speaker"]["status"] == "waiting"
        assert gates[-1] is True

        facts["devices"] = [{**facts["devices"][0], "source_available": True}]
        await system._on_backend_event()
        assert system.snapshot()["speaker"]["status"] == "routed"
        assert system.snapshot()["speaker"]["route"]["module_id"] == "99"
        assert gates[-1] is True

        facts["route_error"] = "PulseAudio restarted again"
        with pytest.raises(BackendUnavailable):
            await system._on_backend_event()
        facts.pop("route_error")
        facts["speaker_route"] = {**facts["speaker_route"], "module_id": "100"}
        await system._on_backend_event()
        assert system.snapshot()["speaker"]["route"]["module_id"] == "100"
        assert gates[-1] is True

        facts["speaker_route"] = None
        facts["devices"] = [{
            **facts["devices"][0],
            "source_available": False,
            "player_status": "paused",
        }]
        await system._on_backend_event()
        assert system.snapshot()["speaker"]["status"] == "idle"
        assert gates[-1] is False
        await system.close()

    asyncio.run(run())


def test_first_phone_route_target_preserves_verified_pulse_identity():
    async def run():
        identity = {
            "kind": "phone_pcm",
            "source_id": "phone-a",
            "device": "rt5616.monitor",
            "monitor_stream": 19,
            "pa_generation": 4,
            "flow_generation": 7,
            "pa_sink": "alsa_output.platform-rt5616",
            "pa_sink_index": 2,
            "pa_monitor_source": "rt5616.monitor",
            "pa_source": "bluez_source.phone-a",
            "pa_owner_module": 42,
        }

        class BackendWithIdentity(Backend):
            async def snapshot(self):
                return {
                    "available": True,
                    "devices": [{
                        "id": "phone-a", "paired": True, "connected": True,
                        "activity": "playing", "source_available": True,
                    }],
                    "speaker_route": None,
                    "digital_target": identity,
                    "challenges": [],
                }

            async def set_speaker_route(self, device_id):
                return {
                    "device": device_id,
                    "verified": True,
                    "digital_target": identity,
                }

        backend = BackendWithIdentity()
        system = AudioSystem(backend, gate_mpv=lambda _muted: _record([], False))
        await system.start()
        target = system.snapshot()["digital_target"]
        assert target == identity

    asyncio.run(run())


async def _gate(_muted):
    return None


async def _record(values, value):
    values.append(value)
