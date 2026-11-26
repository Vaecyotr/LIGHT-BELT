"""Host-to-Engine pipe integration using only in-memory DDP output."""

from pathlib import Path
from shutil import copyfile

import yaml

from host_services.managed_adapter import ManagedAdapter


def test_lighting_audio_rebind_can_revoke_and_replace_source_during_session_lock(monkeypatch):
    import io
    import json
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from host_services import engine_adapter as host

    adapter = ManagedAdapter(profile_path="test", mpv_socket_path="test")
    pipe = io.BytesIO()
    adapter.sender = SimpleNamespace(stdin=pipe, poll=lambda: None)
    route = {"speaker": {"status": "routed"}, "digital_target": {"kind": "phone_pcm", "source_id": "a"}}
    monkeypatch.setattr(host, "_real_adapter", adapter)
    monkeypatch.setattr(host, "_audio_system", SimpleNamespace(snapshot=lambda: route))
    monkeypatch.setattr(host, "_route_gate", True)
    adapter.configure({"role": "show", "mode": "auto", "target": route["digital_target"],
                       "program_target": None, "video_generation": 7, "seek_generation": 3,
                       "await_media": True})
    with ThreadPoolExecutor() as workers, host._session_lock:
        route.update(speaker={"status":"switching"}, digital_target=None)
        workers.submit(host._refresh_lighting_audio).result(timeout=2)
        route.update(speaker={"status":"routed"}, digital_target={"kind":"phone_pcm","source_id":"b"})
        workers.submit(host._refresh_lighting_audio).result(timeout=2)

    commands = [json.loads(line) for line in pipe.getvalue().splitlines()]
    assert [cmd["target"] for cmd in commands] == [
        {"kind":"phone_pcm","source_id":"a"}, {"kind":"none"}, {"kind":"phone_pcm","source_id":"b"}
    ]
    assert [cmd["n"] for cmd in commands] == [1, 2, 3]
    assert all(cmd["video_generation"] == 7 and cmd["seek_generation"] == 3
               and cmd["await_media"] for cmd in commands)


def test_prepare_timeout_remains_visible_through_configuration_until_engine_ack(monkeypatch):
    import io
    from types import SimpleNamespace
    import pytest

    adapter = ManagedAdapter(profile_path="test", mpv_socket_path="test")
    process = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None)
    adapter.sender = process
    monkeypatch.setattr(adapter.changed, "wait_for", lambda *args: False)
    command = {"role":"music", "mode":"auto", "target":{"kind":"none"}}
    with pytest.raises(RuntimeError, match="did not become ready"):
        adapter.configure(command, wait=True)
    adapter.configure(command)
    adapter.configure(dict(command, brightness_zero=True))
    assert adapter.status["role_phase"] == "fault"
    assert "did not become ready" in adapter.status["reason"]
    def reports():
        yield b'{"n":1,"role_phase":"applied"}'
        assert adapter.status["role_phase"] == "fault"
        yield b'{"n":2,"role_phase":"applied","effective_role":"music"}'
        assert adapter.status["effective_role"] == "music"
        assert "reason" not in adapter.status
    process.stdout = reports()
    adapter._read(process)


def test_program_audio_does_not_wait_for_managed_lighting_ready(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from unittest.mock import Mock

    from host_services import engine_adapter as host
    from host_services.control_terminal import ControlPreferences

    adapter = ManagedAdapter(profile_path="test", mpv_socket_path="test")
    adapter._active_show = {"show_yaml": "show.yaml"}
    waiting, release = Event(), Event()

    def configure(spec, *, wait=False):
        if wait:
            waiting.set()
            assert release.wait(5)

    adapter.configure = configure
    mpv = Mock()
    mpv._command.return_value = {"data": True}
    monkeypatch.setattr(host, "_mpv", mpv)
    monkeypatch.setattr(host, "_active_mpv", lambda: mpv)
    monkeypatch.setattr(host, "_real_adapter", adapter)
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_audio_system", None)
    monkeypatch.setattr(host, "_power_error", None)
    monkeypatch.setattr(host, "_lighting_error", None)
    monkeypatch.setattr(host, "_route_gate", False)
    monkeypatch.setattr(host, "_audio_pending", False)
    monkeypatch.setattr(host, "_state", dict(host._state, playback_state="paused", muted=False))
    with ThreadPoolExecutor() as pool:
        resume = pool.submit(host.playback_resume)
        try:
            assert waiting.wait(2)
            pool.submit(host.gate_program, True).result(timeout=1)
            assert pool.submit(host.audio_set, 0.35, None, 0).result(timeout=1)[1] is None
            mpv.resume.assert_not_called()
            mpv.set_mute.assert_called_once_with(True)
            mpv.set_volume.assert_called_once_with(0.35)
        finally:
            release.set()
        assert resume.result(timeout=2)[1] is None


def test_managed_seek_holds_old_frame_and_commits_new_position_before_resume(
    tmp_path, monkeypatch,
):
    from unittest.mock import Mock
    from host_services import engine_adapter as host
    from host_services.control_terminal import ControlPreferences

    adapter = ManagedAdapter(profile_path="test", mpv_socket_path="test")
    adapter._active_show = {"show_yaml": "show.yaml"}
    adapter.command = {"role": "show", "seek_generation": 0}
    calls = []
    def configure(spec, *, wait=False):
        if spec != adapter.command or wait:
            calls.append(
                ("configure", spec.get("await_media", False), spec["seek_generation"], wait)
            )
        adapter.command = spec

    adapter.configure = configure
    mpv = Mock()
    mpv.pause.side_effect = lambda: calls.append("pause")
    mpv.seek.side_effect = lambda _: calls.append("seek")
    mpv.resume.side_effect = lambda: calls.append("resume")
    seeking = iter((True, False))

    def read(command):
        if command[-1] == "seeking":
            active = next(seeking)
            calls.append(("seeking", active))
            return {"error": "success", "data": active}
        return {"error": "success", "data": 1.234}

    mpv._send.side_effect = read
    monkeypatch.setattr(host, "_active_mpv", lambda: mpv)
    monkeypatch.setattr(host, "_real_adapter", adapter)
    monkeypatch.setattr(host, "_preferences", ControlPreferences(tmp_path))
    monkeypatch.setattr(host, "_audio_system", None)
    monkeypatch.setattr(host, "_power_error", None)
    monkeypatch.setattr(host, "_lighting_error", None)
    monkeypatch.setattr(host, "_state", dict(host._state, playback_state="playing"))

    data, error = host.playback_seek(1234)
    assert error is None and data["position_ms"] == 1234
    assert calls == [
        "pause", ("configure", True, 1, True), "seek",
        ("seeking", True), ("seeking", False),
        ("configure", False, 1, True), "resume",
    ]


def test_same_child_confirms_role_switches_then_shuts_down(tmp_path):
    template = Path("config/profiles/rk3588-host-service.yaml")
    config = yaml.safe_load(template.read_text(encoding="utf-8"))
    config["outputs"]["mode"] = "memory"
    profile = tmp_path / "profiles" / "memory.yaml"
    profile.parent.mkdir()
    for name in ("system.yaml", "layout.yaml", "effects.yaml", "outputs.yaml"):
        copyfile(template.parent.parent / name, tmp_path / name)
    profile.write_text(yaml.safe_dump(config), encoding="utf-8")
    adapter = ManagedAdapter(profile_path=str(profile), mpv_socket_path="unused")
    spec = {
        "role": "music",
        "role_on_video_end": "none",
        "show": None,
        "mode": "auto",
        "target": {"kind": "none"},
        "video_generation": 1,
        "seek_generation": 0,
        "targets": [],
    }
    try:
        adapter.configure(spec, wait=True)
        first = adapter.sender
        assert adapter.status["effective_role"] == "music"
        sequence = adapter.status["frame_seq"]
        adapter.configure(
            dict(
                spec,
                role="manual",
                targets=[
                    {"target_id": "strip_12", "color": [0.4, 0.2, 0.1]},
                ],
            ),
            wait=True,
        )
        assert adapter.sender is first
        assert adapter.status["role_phase"] == "applied"
        assert adapter.status["effective_role"] == "manual"
        assert adapter.status["frame_seq"] > sequence
        adapter.configure(dict(spec, role="none"))
        assert first.poll() == 0
        assert adapter.sender is None
        assert adapter.status["role_phase"] == "idle"
    finally:
        with adapter.changed:
            adapter._close_sender()
