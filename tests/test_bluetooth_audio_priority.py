from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace


MODULE_PATH = Path("scripts/deploy/rk3588/bluetooth_audio_priority.py")
SPEC = importlib.util.spec_from_file_location("bluetooth_audio_priority", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
priority = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = priority
SPEC.loader.exec_module(priority)


class FakePactl:
    def __init__(self, *, active: bool = False, inputs=()):
        self.active = active
        self.inputs = list(inputs)
        self.mute_calls: list[tuple[int, bool]] = []
        self.ownership_calls: list[tuple[int, bool]] = []

    def bluetooth_active(self) -> bool:
        return self.active

    def sink_inputs(self):
        return list(self.inputs)

    def set_sink_input_mute(self, index: int, muted: bool) -> None:
        self.mute_calls.append((index, muted))
        self.inputs = [
            priority.SinkInput(item.index, item.application_name, muted, item.owned)
            if item.index == index
            else item
            for item in self.inputs
        ]

    def set_sink_input_owned(self, index: int, owned: bool) -> None:
        self.ownership_calls.append((index, owned))
        self.inputs = [
            priority.SinkInput(item.index, item.application_name, item.muted, owned)
            if item.index == index
            else item
            for item in self.inputs
        ]


def local(index: int, muted: bool = False, owned: bool = False):
    return priority.SinkInput(index, priority.MEDIA_NAME, muted, owned)


def other(index: int, muted: bool = False):
    return priority.SinkInput(index, "Other application", muted)


def test_parse_sources_and_any_running_a2dp_source():
    parsed = priority.parse_short_sources(
        "1\talsa_input.foo\tmodule-alsa-card.c\ts16le 2ch 44100Hz\tSUSPENDED\n"
        "2\tbluez_source.AA_BB.a2dp_source\tmodule-bluez5-device.c\ts16le 2ch 44100Hz\tRUNNING\n"
    )
    assert parsed[-1] == ("bluez_source.AA_BB.a2dp_source", "RUNNING")
    assert any(priority.A2DP_SOURCE_RE.fullmatch(name) and state == "RUNNING" for name, state in parsed)


def test_parse_dynamic_local_media_sink_inputs():
    parsed = priority.parse_sink_inputs(
        "Sink Input #18\n\tMute: no\n\tProperties:\n"
        '\t\tapplication.name = "LIGHT-BELT-LocalMedia"\n'
        '\t\tlight_belt.bluetooth_priority_owned = "1"\n'
        "Sink Input #107\n\tMute: yes\n\tProperties:\n"
        '\t\tapplication.name = "Other application"\n'
    )
    assert parsed == [local(18, owned=True), other(107, muted=True)]


def test_case_1_inactive_does_not_suppress_or_unmute_local_media():
    client = FakePactl(inputs=[local(9), local(10, muted=True)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    assert client.mute_calls == []


def test_case_2_active_mutes_local_media_immediately():
    client = FakePactl(inputs=[local(9), other(10)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    client.active = True
    service.reevaluate()
    assert client.mute_calls == [(9, True)]


def test_case_3_active_to_inactive_waits_then_restores():
    delays: list[float] = []
    client = FakePactl(active=True, inputs=[local(9)])
    service = priority.BluetoothAudioPriority(client, sleep=delays.append, log=lambda _message: None)
    service.initial_sync()
    client.active = False
    service.reevaluate()
    assert delays == [priority.RESTORE_DELAY]
    assert client.mute_calls == [(9, True), (9, False)]


def test_case_4_reactivation_inside_debounce_keeps_media_suppressed():
    client = FakePactl(active=True, inputs=[local(9)])

    def resume(_delay: float) -> None:
        client.active = True

    service = priority.BluetoothAudioPriority(client, sleep=resume, log=lambda _message: None)
    service.initial_sync()
    client.active = False
    service.reevaluate()
    assert client.mute_calls == [(9, True)]
    assert service.active is True


def test_case_5_new_local_media_stream_is_suppressed_while_active():
    client = FakePactl(active=True)
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    client.inputs.append(local(25))
    service.handle_event("Event 'new' on sink-input #25")
    assert client.mute_calls == [(25, True)]


def test_case_6_disconnect_releases_owned_suppression():
    client = FakePactl(active=True, inputs=[local(9)])
    service = priority.BluetoothAudioPriority(client, sleep=lambda _delay: None, log=lambda _message: None)
    service.initial_sync()
    client.active = False
    service.handle_event("Event 'remove' on source #4")
    assert client.mute_calls[-1] == (9, False)


def test_case_7_multiple_sources_are_active_when_any_a2dp_source_runs(monkeypatch):
    client = priority.PactlClient()
    monkeypatch.setattr(
        client,
        "_run",
        lambda *_args: (
            "1 bluez_source.AA.a2dp_source module-bluez SUSPENDED\n"
            "2 bluez_source.BB.a2dp_source module-bluez RUNNING\n"
        ),
    )
    assert client.bluetooth_active() is True


def test_case_8_starting_while_active_suppresses_local_media():
    client = FakePactl(active=True, inputs=[local(9)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    assert service.active is True
    assert client.mute_calls == [(9, True)]


def test_case_9_starting_inactive_preserves_external_mute():
    client = FakePactl(active=False, inputs=[local(9, muted=True)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    service.shutdown()
    assert client.mute_calls == []


def test_case_10_shutdown_restores_only_service_owned_mutes():
    client = FakePactl(active=True, inputs=[local(9), local(10, muted=True), other(11)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    service.shutdown()
    assert client.mute_calls == [(9, True), (9, False)]
    assert client.ownership_calls == [(9, True), (9, False)]


def test_case_10_restart_recovers_tagged_mute_without_unmuting_external_state():
    client = FakePactl(active=False, inputs=[local(9, muted=True, owned=True), local(10, muted=True)])
    restarted = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    restarted.initial_sync()
    assert client.mute_calls == [(9, False)]
    assert client.ownership_calls == [(9, False)]
    assert next(item for item in client.inputs if item.index == 10).muted is True


def test_reused_sink_input_index_does_not_transfer_mute_ownership():
    client = FakePactl(active=True, inputs=[local(9)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.initial_sync()
    client.inputs = [local(9, muted=True)]
    service.shutdown()
    assert client.mute_calls == [(9, True)]
    assert client.ownership_calls == [(9, True)]


def test_adapter_uses_supported_pacmd_property_command_and_unsets_with_false(monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(priority.subprocess, "run", run)
    client = priority.PactlClient()
    client.set_sink_input_owned(23, True)
    client.set_sink_input_owned(23, False)

    assert [call[0] for call in calls] == [
        ["pacmd", "update-sink-input-proplist", "23", f"{priority.OWNERSHIP_PROPERTY}=1"],
        ["pacmd", "update-sink-input-proplist", "23", f"{priority.OWNERSHIP_PROPERTY}=0"],
    ]
    assert all(call[1]["env"]["LC_ALL"] == "C" for call in calls)
    assert all(call[1]["env"]["PATH"] == os.environ["PATH"] for call in calls)


def test_adapter_surfaces_pacmd_cli_failure_text_even_with_zero_exit(monkeypatch):
    monkeypatch.setattr(
        priority.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0, stdout="No sink input found with this index.\n", stderr=""
        ),
    )
    try:
        priority.PactlClient().set_sink_input_owned(23, True)
    except priority.PactlError as exc:
        assert "No sink input found" in str(exc)
    else:
        raise AssertionError("pacmd CLI failure was treated as success")


def test_run_and_subscribe_force_c_locale_while_preserving_environment(monkeypatch):
    run_calls = []
    popen_calls = []

    def run(argv, **kwargs):
        run_calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    class FakeProcess:
        stdout = iter(["Event 'change' on server #0\n"])
        stderr = None

        def wait(self):
            return 0

        def poll(self):
            return 0

    def popen(argv, **kwargs):
        popen_calls.append((argv, kwargs))
        return FakeProcess()

    monkeypatch.setattr(priority.subprocess, "run", run)
    monkeypatch.setattr(priority.subprocess, "Popen", popen)
    client = priority.PactlClient()
    assert client._run("info") == "ok"
    assert list(client.subscribe()) == ["Event 'change' on server #0\n"]
    assert run_calls[0][1]["env"]["LC_ALL"] == "C"
    assert run_calls[0][1]["env"]["PATH"] == os.environ["PATH"]
    assert popen_calls[0][1]["env"]["LC_ALL"] == "C"
    assert popen_calls[0][1]["env"]["PATH"] == os.environ["PATH"]


def test_irrelevant_subscription_events_do_not_trigger_policy():
    client = FakePactl(active=True, inputs=[local(9)])
    service = priority.BluetoothAudioPriority(client, log=lambda _message: None)
    service.handle_event("Event 'change' on server #0")
    assert client.mute_calls == []
