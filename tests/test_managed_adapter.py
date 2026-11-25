"""Host-to-Engine pipe integration using only in-memory DDP output."""

from pathlib import Path
from shutil import copyfile

import yaml

from host_services.managed_adapter import ManagedAdapter


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
