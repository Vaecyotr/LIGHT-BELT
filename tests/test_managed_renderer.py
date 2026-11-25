import pytest

from light_engine.managed import FrameHandoff


@pytest.mark.parametrize("failed", [1, 2, 3])
def test_partial_send_stops_normal_frame_and_attempts_every_safe_node(failed):
    from light_engine.mapping.physical import DigitalNodeFrame, PhysicalFrame
    from light_engine.outputs.ddp_output import DdpOutput
    from light_engine.outputs import OutputMode

    class Socket:
        def sendto(self, packet, address):
            if address[0] == f"node-{failed}":
                raise OSError("unreachable")
            return len(packet)

    output = DdpOutput(mode=OutputMode.PRODUCTION, socket=Socket())
    output.open()
    nodes = [
        DigitalNodeFrame(i, f"node-{i}", 4048, pixels=[(1.0, 0.0, 0.0)])
        for i in (1, 2, 3)
    ]
    try:
        with pytest.raises(OSError, match="unreachable"):
            output.send_frame(PhysicalFrame(10, 1.0, digital_frames=nodes))
        assert set(output.last_node_submission) == set(range(1, failed + 1))
        black = [
            DigitalNodeFrame(i, f"node-{i}", 4048, pixels=[(0.0, 0.0, 0.0)])
            for i in (1, 2, 3)
        ]
        output.send_frame(
            PhysicalFrame(11, 1.0, digital_frames=black, metadata={"SAFE_STATE": True})
        )
        assert {
            i: r["submitted"] for i, r in output.last_node_safe_submission.items()
        } == {i: i != failed for i in (1, 2, 3)}
    finally:
        output.close()


def test_superseded_candidate_cannot_replace_or_black_live_frame():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "show", "show pixels", {}, 0.0)
    assert handoff.sample(0.01)[1] == "show pixels"
    handoff.request(2)
    handoff.request(3)
    handoff.publish(2, "music", "old candidate", {}, 0.05)
    assert handoff.sample(0.1)[1] == "show pixels"
    handoff.publish(3, "manual", "new pixels", {}, 0.11)
    assert handoff.sample(0.11)[1] == "new pixels"


def test_keepalive_cannot_mask_stalled_renderer():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "show", "pixels", {}, 1.0)
    handoff.request(2)
    assert handoff.sample(1.4)[1] == "pixels"
    handoff.request(3)
    with pytest.raises(TimeoutError):
        handoff.sample(1.6)


def test_active_role_can_refresh_without_acknowledging_pending_manual_role():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "music", "frame 1", {}, 0)
    handoff.request(2)
    handoff.refresh_active(1, "music", "frame 2", {}, 0.4)
    assert handoff.sample(0.7)[:4] == ("music", "frame 2", {}, 1)
    handoff.publish(2, "manual", "frame 3", {}, 0.71)
    handoff.refresh_active(1, "music", "late frame", {}, 0.8)
    assert handoff.sample(0.8)[:4] == ("manual", "frame 3", {}, 2)


def test_managed_sender_switches_real_effects_without_intermediate_safety_frame(
    monkeypatch,
    tmp_path,
):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Thread
    import time
    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.outputs import NullOutput
    from light_engine.managed import serve
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState

    commands, reports = Queue(), Queue()
    frames, errors = [], []
    output = NullOutput()
    output.send_frame = frames.append

    def open_memory(engine):
        engine._outputs = {"memory": output}
        output.open()

    monkeypatch.setattr(Engine, "init_outputs", open_memory)
    position = [0.2]
    monkeypatch.setattr(
        MpvIPCAdapter,
        "read_state",
        lambda self: MpvState(position[0], False, position[0] >= 1.1),
    )
    show = tmp_path / "short.yaml"
    show.write_text(
        """schema_version: 2
show:
  id: short
  duration: 1.0
  cues:
    - id: red
      start: 0.0
      end: 1.0
      target: {type: digital_strip, id: strip_12}
      effect: {mode: fixed, id: static}
      color: {mode: solid, color: [1, 0, 0]}
""",
        encoding="utf-8",
    )
    profile = Config(Path("config/profiles/rk3588-host-service.yaml").resolve())

    def run():
        try:
            serve(profile, iter(commands.get, None), reports.put)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    base = {
        "mode": "auto",
        "target": {"kind": "none"},
        "mpv_socket": "unused",
        "video_generation": 1,
        "seek_generation": 0,
        "role_on_video_end": "none",
    }
    try:
        for i, role in enumerate(("music", "manual", "music"), start=1):
            commands.put(
                json.dumps(
                    dict(
                        base,
                        n=i,
                        role=role,
                        targets=[{"target_id": "strip_12", "color": [0.4, 0.5, 0.2]}],
                    )
                )
            )
            report = reports.get(timeout=10)
            assert report["effective_role"] == role and report["n"] == i, report
            assert not any(f.metadata.get("SAFE_STATE") for f in frames)
        config = dict(
            base,
            n=4,
            role="show",
            role_on_video_end="music",
            show={"show_yaml": str(show), "media_path": "soundtrack.flac"},
        )
        commands.put(json.dumps(config))
        event = reports.get(timeout=10)
        assert event.get("effective_role") == "show", event
        position[0] = 1.05
        deadline = time.monotonic() + 10
        while True:
            event = reports.get(timeout=max(0.1, deadline - time.monotonic()))
            if event.get("effective_role") == "music":
                break
            assert time.monotonic() < deadline, event
        assert (event["n"], event["effective_role"]) == (4, "music")
        position[0] = 0.25
        commands.put(json.dumps(dict(config, n=5, seek_generation=1)))
        event = reports.get(timeout=10)
        assert (event["n"], event["effective_role"]) == (5, "show")
        assert not any(f.metadata.get("SAFE_STATE") for f in frames)
    finally:
        commands.put(None)
        thread.join(12)
    assert not thread.is_alive() and not errors
    assert frames[-1].metadata["SAFE_STATE"]
    assert [f.sequence for f in frames] == list(range(1, len(frames) + 1))


@pytest.mark.parametrize("position", [304.9, 305.0, 305.3, 305.620998])
def test_energy_wakeup_tail_ready_and_eof_transfer_to_music(
    monkeypatch, position
):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Thread
    import time

    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState
    from light_engine.outputs import NullOutput
    from light_engine.managed import serve

    commands, reports = Queue(), Queue()
    frames, errors = [], []
    output = NullOutput()
    output.send_frame = frames.append

    def open_memory(engine):
        engine._outputs = {"memory": output}
        output.open()

    monkeypatch.setattr(Engine, "init_outputs", open_memory)
    monkeypatch.setattr(Engine, "load_video", lambda self, path: None)
    media_position = [position]
    monkeypatch.setattr(
        MpvIPCAdapter,
        "read_state",
        lambda self: MpvState(
            media_position[0], False, media_position[0] >= 305.620998
        ),
    )
    project = Path(__file__).resolve().parents[1]
    profile = Config((project / "config/profiles/rk3588-host-service.yaml").resolve())
    show = project / "assets/energy-wakeup/energy-wakeup.yaml"

    def run():
        try:
            serve(profile, iter(commands.get, None), reports.put)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    commands.put(
        json.dumps(
            {
                "n": 1,
                "role": "show",
                "role_on_video_end": "music",
                "video_generation": 7,
                "seek_generation": 0,
                "mode": "auto",
                "target": {"kind": "none"},
                "mpv_socket": "offline-test",
                "show": {
                    "show_yaml": str(show),
                    "media_path": "energy-wakeup.mp4",
                },
            }
        )
    )
    try:
        deadline = time.monotonic() + 20
        events = []
        while time.monotonic() < deadline:
            event = reports.get(timeout=max(0.1, deadline - time.monotonic()))
            events.append(event)
            if event.get("effective_role") == "show":
                media_position[0] = 305.0
            if event.get("effective_role") == "music":
                break
        assert events[-1].get("effective_role") == "music", events
        if position < 305.0:
            assert any(event.get("effective_role") == "show" for event in events)
        assert not any(frame.metadata.get("SAFE_STATE") for frame in frames[:-1])
        assert frames[-1].metadata.get("SAFE_STATE") is not True
    finally:
        commands.put(
            json.dumps(
                {
                    "n": 2,
                    "role": "none",
                    "role_on_video_end": "none",
                    "video_generation": 7,
                    "seek_generation": 0,
                    "mode": "auto",
                    "target": {"kind": "none"},
                }
            )
        )
        commands.put(None)
        thread.join(20)
    assert not thread.is_alive()
    assert not errors
    assert frames[-1].metadata["SAFE_STATE"]
    assert [frame.sequence for frame in frames] == list(range(1, len(frames) + 1))


def test_energy_wakeup_after_show_end_without_handoff_sends_safe_black(
    monkeypatch,
):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Thread

    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState
    from light_engine.outputs import NullOutput
    from light_engine.managed import serve

    commands, reports = Queue(), Queue()
    frames, errors = [], []
    output = NullOutput()
    output.send_frame = frames.append

    def open_memory(engine):
        engine._outputs = {"memory": output}
        output.open()

    monkeypatch.setattr(Engine, "init_outputs", open_memory)
    monkeypatch.setattr(Engine, "load_video", lambda self, path: None)
    monkeypatch.setattr(
        MpvIPCAdapter, "read_state", lambda self: MpvState(305.3, False, False)
    )
    project = Path(__file__).resolve().parents[1]
    profile = Config((project / "config/profiles/rk3588-host-service.yaml").resolve())
    show = project / "assets/energy-wakeup/energy-wakeup.yaml"

    def run():
        try:
            serve(profile, iter(commands.get, None), reports.put)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    commands.put(
        json.dumps(
            {
                "n": 1,
                "role": "show",
                "role_on_video_end": "none",
                "video_generation": 8,
                "seek_generation": 0,
                "mode": "auto",
                "target": {"kind": "none"},
                "mpv_socket": "offline-test",
                "show": {"show_yaml": str(show), "media_path": "energy-wakeup.mp4"},
            }
        )
    )
    try:
        event = reports.get(timeout=20)
        assert (event.get("role_phase"), event.get("effective_role")) == (
            "idle",
            "none",
        ), event
    finally:
        commands.put(None)
        thread.join(20)
    assert not thread.is_alive()
    assert not errors
    assert frames
    assert frames[-1].metadata["SAFE_STATE"]
    assert [frame.sequence for frame in frames] == list(range(1, len(frames) + 1))
