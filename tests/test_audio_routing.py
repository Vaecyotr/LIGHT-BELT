from __future__ import annotations

import asyncio
import json

import pytest

from host_services.bluetooth import AudioSystem, BackendUnavailable
from host_services.audio_routing import PulseAudioRouter


class Backend:
    def __init__(self):
        self.devices = [
            {"id": "a", "name": "A", "paired": True, "connected": True},
            {"id": "b", "name": "B", "paired": True, "connected": True},
        ]
        self.speaker_active = {"a": True, "b": False}
        self.calls = []
        self.fail_open = False

    async def start(self, callbacks):
        self.callbacks = callbacks

    async def close(self):
        pass

    async def snapshot(self):
        return {
            "available": True,
            "devices": [
                dict(
                    item,
                    activity="transmitting"
                    if self.speaker_active[item["id"]]
                    else "idle",
                    source_available=True,
                )
                for item in self.devices
            ],
            "challenges": [],
        }

    async def pair(self, device_id, operation_id):
        pass

    async def connect(self, device_id):
        pass

    async def disconnect(self, device_id):
        pass

    async def remove(self, device_id):
        pass

    async def answer_challenge(self, *args):
        pass

    async def set_speaker_route(self, device_id):
        self.calls.append(("open", device_id))
        if self.fail_open:
            raise RuntimeError("open failed")
        return {"device": device_id, "source": f"bluez:{device_id}", "verified": True}

    async def close_speaker_route(self):
        self.calls.append(("close",))


def test_manual_speaker_choice_of_idle_connected_phone_waits_without_route():
    asyncio.run(_manual_speaker_choice_of_idle_connected_phone_waits_without_route())


async def _manual_speaker_choice_of_idle_connected_phone_waits_without_route():
    backend = Backend()
    backend.speaker_active = {"a": False, "b": False}
    system = AudioSystem(backend, gate_mpv=_noop)
    await system.start()

    result = await system.set_speaker("b")

    assert result["status"] == "waiting"
    assert system.snapshot()["speaker"]["device"] == "b"
    assert not any(call[0] == "open" for call in backend.calls)


def test_route_switch_gates_program_then_closes_old_before_opening_new():
    asyncio.run(_route_switch_gates_program_then_closes_old_before_opening_new())


async def _route_switch_gates_program_then_closes_old_before_opening_new():
    backend = Backend()
    backend.speaker_active = {"a": True, "b": True}
    events = []

    async def gate(muted):
        events.append(("gate", muted))

    system = AudioSystem(backend, gate_mpv=gate)
    await system.start()
    await system.set_speaker("a")
    backend.calls.clear()
    events.clear()
    await system.set_speaker("b")

    assert backend.calls == [("close",), ("open", "b")]
    assert events[0] == ("gate", True)
    assert events == [("gate", True)]


def test_failed_route_open_keeps_program_gated_and_never_claims_routed():
    asyncio.run(_failed_route_open_keeps_program_gated_and_never_claims_routed())


def test_one_shot_manual_choice_releases_to_still_streaming_peer_on_pause():
    async def exercise():
        backend = Backend()
        backend.speaker_active = {"a": True, "b": True}
        system = AudioSystem(backend, gate_mpv=_noop, pause_delay=0)
        await system.start()
        try:
            await system.set_speaker("b")
            backend.devices[1]["player_status"] = "paused"
            await backend.callbacks()
            assert system.snapshot()["speaker"]["device"] == "a"
            backend.devices[1]["player_status"] = "playing"
            await backend.callbacks()
            assert system.snapshot()["speaker"]["device"] == "a"
            backend.speaker_active["b"] = False
            await system.set_speaker("b")
            assert system.snapshot()["speaker"]["status"] == "waiting"
            await system.set_speaker(None)
            assert system.snapshot()["speaker"]["device"] == "a"
        finally:
            await system.close()

    asyncio.run(exercise())


async def _failed_route_open_keeps_program_gated_and_never_claims_routed():
    backend = Backend()
    backend.speaker_active = {"a": False, "b": False}
    backend.fail_open = True
    events = []
    system = AudioSystem(backend, gate_mpv=lambda value: _record(events, value))
    await system.start()
    backend.speaker_active["a"] = True

    with pytest.raises(BackendUnavailable, match="open failed"):
        await system.set_speaker("a")

    assert system.snapshot()["speaker"]["status"] == "fault"
    assert events == [True, False, True]


def test_pulse_router_requires_exact_module_readback_before_reporting_success():
    asyncio.run(_pulse_router_requires_exact_module_readback_before_reporting_success())


async def _pulse_router_requires_exact_module_readback_before_reporting_success():
    calls = []

    async def pactl(*args):
        calls.append(args)
        if args[:1] == ("load-module",):
            return "42\n"
        if args[:3] == ("list", "short", "modules"):
            return "3\tmodule-bluetooth-policy\ta2dp_source=false\n42\tmodule-loopback\tsource=bt_A sink=rt5616 source_dont_move=true sink_dont_move=true sink_input_properties=light_belt.route_owner=A\n"
        raise AssertionError(args)

    router = PulseAudioRouter(runner=pactl)
    route = await router.open("bt_A", "rt5616", device_id="A")
    assert route["verified"] is True
    assert ("load-module", "module-loopback") in [call[:2] for call in calls]


def test_pulse_router_rejects_wrong_readback_and_unloads_partial_module():
    asyncio.run(_pulse_router_rejects_wrong_readback_and_unloads_partial_module())


def test_pulse_subscribe_events_trigger_reconciliation_and_monitor_closes_cleanly():
    asyncio.run(_pulse_subscribe_events_trigger_reconciliation_and_monitor_closes_cleanly())


async def _pulse_subscribe_events_trigger_reconciliation_and_monitor_closes_cleanly():
    events = asyncio.Queue()
    seen = asyncio.Event()

    async def subscription():
        while True:
            yield await events.get()

    def changed():
        seen.set()

    router = PulseAudioRouter(subscriber=subscription)
    await router.start_monitor(changed)
    await events.put("sink-input changed")
    await asyncio.wait_for(seen.wait(), 0.5)
    await router.stop_monitor()
    assert router._watch_task is None


async def _pulse_router_rejects_wrong_readback_and_unloads_partial_module():
    calls = []

    async def pactl(*args):
        calls.append(args)
        if args[:1] == ("load-module",):
            return "42\n"
        if args[:3] == ("list", "short", "modules"):
            policy = "3\tmodule-bluetooth-policy\ta2dp_source=false\n"
            return (
                policy
                if calls.count(args) == 1
                else policy + "42\tmodule-loopback\tsource=wrong sink=rt5616\n"
            )
        if args[:1] == ("unload-module",):
            return ""
        raise AssertionError(args)

    router = PulseAudioRouter(runner=pactl)
    with pytest.raises(BackendUnavailable, match="readback"):
        await router.open("bt_A", "rt5616", device_id="A")
    # A reused PA index must not unload another application's module.
    assert ("unload-module", "42") not in calls


def test_selected_monitor_index_is_integer_and_actual_sink_is_verified():
    async def run():
        stream_sink = [2]

        async def pactl(*args):
            if args[0] == "load-module":
                return "42"
            if args == ("list", "short", "modules"):
                return (
                    "3\tmodule-bluetooth-policy\ta2dp_source=false\n"
                    "42\tmodule-loopback\tsource=bt_A sink=rt5616 source_dont_move=true "
                    "sink_dont_move=true sink_input_properties=light_belt.route_owner=A\n"
                )
            if args == ("--format=json", "list", "sinks"):
                return '[{"name":"rt5616","index":2,"monitor_source":"rt5616.monitor"}]'
            if args == ("--format=json", "list", "sink-inputs"):
                return json.dumps(
                    [{"owner_module": 42, "index": 7, "sink": stream_sink[0]}]
                )
            raise AssertionError(args)

        router = PulseAudioRouter(runner=pactl)
        await router.open("bt_A", "rt5616", device_id="A")
        assert (await router.route_details("42"))["sink_input_index"] == 7
        stream_sink[0] = 9
        with pytest.raises(BackendUnavailable, match="selected sink"):
            await router.route_details("42")

    asyncio.run(run())


async def _record(events, value):
    events.append(value)


async def _noop(_value):
    return None
