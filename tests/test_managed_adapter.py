"""Host-to-Engine pipe integration using only in-memory DDP output."""

from pathlib import Path
from shutil import copyfile

import yaml

from host_services.managed_adapter import ManagedAdapter


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
