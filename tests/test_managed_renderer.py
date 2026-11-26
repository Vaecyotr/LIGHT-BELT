import pytest

from light_engine.managed import FrameHandoff


def test_age_expired_candidate_does_not_expire_a_recently_refreshed_active_role():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "music", "active", {}, 0.0)
    assert handoff.commit(handoff.sample(0.0))
    handoff.request(2)
    handoff.publish(2, "show", "expired candidate", {}, 0.1)
    mapped_candidate = handoff.sample(0.5)
    assert not handoff.claim(mapped_candidate, now=0.65)
    handoff.refresh_active(1, "music", "latest active", {}, 0.55, request_number=2)
    assert handoff.sample(0.65)[1] == "latest active"
    assert handoff.disposition(2, "show") == "discarded"
    with pytest.raises(TimeoutError):
        handoff.sample(1.1)


def test_zero_brightness_is_black_on_ddp_without_releasing_the_role(monkeypatch):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Thread

    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.managed import serve
    from light_engine.outputs import NullOutput

    commands, reports = Queue(), Queue()
    frames = []
    output = NullOutput()
    output.send_frame = frames.append

    def init_outputs(engine):
        engine._outputs = {"memory": output}
        output.open()

    monkeypatch.setattr(Engine, "init_outputs", init_outputs)
    profile = Config(Path("config/profiles/rk3588-host-service.yaml").resolve())
    thread = Thread(target=serve, args=(profile, iter(commands.get, None), reports.put))
    thread.start()
    spec = dict(
        role="music", role_on_video_end="none", show=None, targets=[],
        video_generation=1, seek_generation=0, target={"kind": "none"},
        mode="auto", mpv_socket="unused",
    )

    def lit(frame):
        return any(
            any(channel for channel in pixel)
            for node in frame.digital_frames for output in node.outputs for pixel in output.pixels
        )

    try:
        commands.put(json.dumps(dict(spec, n=1, brightness_zero=True)))
        dark = reports.get(timeout=5)
        assert dark["effective_role"] == "music"
        assert not lit(next(frame for frame in frames if frame.sequence == dark["frame_seq"]))
        assert not any(frame.metadata.get("SAFE_STATE") for frame in frames)
        commands.put(json.dumps(dict(spec, n=2)))
        bright = reports.get(timeout=5)
        assert bright["effective_role"] == "music"
        assert lit(next(frame for frame in frames if frame.sequence == bright["frame_seq"]))
    finally:
        commands.put(None)
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert [frame.sequence for frame in frames] == list(range(1, len(frames) + 1))


def test_candidate_preparation_discards_video_decoded_for_old_position(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    from light_engine.config import Config
    from light_engine.engine import RenderContext
    from light_engine.managed import Content
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState

    position = [1.0]
    decoded = []
    monkeypatch.setattr(
        MpvIPCAdapter, "read_state", lambda self: MpvState(position[0], False, False),
    )
    monkeypatch.setattr(
        RenderContext, "load_video",
        lambda ctx, path: setattr(ctx, "_video_reader", SimpleNamespace(duration=400, close=lambda: None)),
    )

    def analyze(ctx):
        decoded.append(ctx._timestamp)
        position[0] = 1.4
        return None

    monkeypatch.setattr(RenderContext, "_get_video_features", analyze)
    config = Config(Path("config/profiles/rk3588-host-service.yaml").resolve())
    show = Path("assets/energy-wakeup/energy-wakeup.yaml").resolve()
    spec = {
        "role": "show", "target": {"kind": "none"}, "mpv_socket": "candidate-position",
        "show": {"show_yaml": str(show), "media_path": "input.mp4"},
    }
    content = Content.prepare(config, spec, RenderContext(config)._layout)
    try:
        assert decoded == [1.0, 1.4]
        assert content.prepared_media.position == 1.4
    finally:
        content.close()


def test_handoff_claim_rejects_candidate_when_media_moves_after_render():
    handoff = FrameHandoff()
    handoff.request(4)
    frame = type("Frame", (), {"timestamp": 12.0, "metadata": {
        "managed_media_position": 12.0,
        "managed_media_paused": False,
        "managed_media_observed_at": 3.0,
    }})()
    handoff.publish(4, "show", frame, {}, 3.0)
    item = handoff.sample(3.0)

    assert not handoff.claim(item, now=3.05, period=1 / 30)
    assert handoff.discard(item)
    assert handoff.sample(3.05) is None


def test_handoff_accepts_paused_candidate_after_wall_time_passes():
    handoff = FrameHandoff()
    handoff.request(4)
    frame = type("Frame", (), {"timestamp": 12.0, "metadata": {
        "managed_media_position": 12.0,
        "managed_media_paused": True,
        "managed_media_observed_at": 3.0,
    }})()
    handoff.publish(4, "show", frame, {}, 3.0)
    item = handoff.sample(3.5)
    assert handoff.claim(item, now=3.5, period=1 / 30)


def test_stale_candidate_is_retried_while_committed_role_keeps_sending(monkeypatch):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Event, Thread
    import time

    from light_engine.config import Config
    from light_engine.engine import Engine, RenderContext
    from light_engine.mapping import PhysicalMapping
    from light_engine.managed import serve
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState
    from light_engine.outputs import NullOutput

    commands, reports = Queue(), Queue()
    old_frames, show_frames, errors = [], [], []
    candidate_mapped, allow_candidate = Event(), Event()
    retry_started, release_retry, retry_keeps_rendering = Event(), Event(), Event()
    retry_old_positions = set()
    first_observation = []
    output = NullOutput()

    def send(frame):
        if frame.metadata.get("managed_media_position") is not None:
            show_frames.append(frame)
        else:
            old_frames.append(frame)
            if retry_started.is_set() and not release_retry.is_set():
                retry_old_positions.add(frame.timestamp)
                if len(retry_old_positions) >= 3:
                    retry_keeps_rendering.set()

    output.send_frame = send
    monkeypatch.setattr(
        Engine, "init_outputs",
        lambda engine: (setattr(engine, "_outputs", {"memory": output}), output.open()),
    )
    monkeypatch.setattr(RenderContext, "load_video", lambda self, path: None)
    position = [1.0]
    def read_state(self):
        if position[0] == 1.5 and not retry_started.is_set():
            retry_started.set()
            assert release_retry.wait(3)
        return MpvState(position[0], retry_started.is_set(), False)

    monkeypatch.setattr(MpvIPCAdapter, "read_state", read_state)
    map_physical = PhysicalMapping.map
    def delay_candidate(mapping, frame):
        if (frame.metadata.get("managed_media_position") == 1.0
                and not candidate_mapped.is_set()):
            first_observation.append(frame.metadata["managed_media_observed_at"])
            candidate_mapped.set()
            assert allow_candidate.wait(5)
        return map_physical(mapping, frame)
    monkeypatch.setattr(PhysicalMapping, "map", delay_candidate)

    config = Config(Path("config/profiles/rk3588-host-service.yaml").resolve())
    show = Path("assets/energy-wakeup/energy-wakeup.yaml").resolve()
    base = {
        "role_on_video_end": "none", "video_generation": 1, "seek_generation": 0,
        "mode": "auto", "target": {"kind": "none"}, "mpv_socket": "position-commit",
    }

    def run():
        try:
            serve(config, iter(commands.get, None), reports.put)
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=run, daemon=True)
    thread.start()
    try:
        commands.put(json.dumps(dict(base, n=1, role="music")))
        assert reports.get(timeout=10)["effective_role"] == "music"
        commands.put(json.dumps(dict(
            base, n=2, role="show",
            show={"show_yaml": str(show), "media_path": "show.mp4"},
        )))
        assert candidate_mapped.wait(5)
        position[0] = 1.5
        period = 1 / config.get("system.output_fps")
        allow_candidate.wait(max(0, first_observation[0] + 2 * period - time.monotonic()))
        assert len(old_frames) >= 1
        assert not show_frames
        allow_candidate.set()
        assert retry_started.wait(3)
        assert retry_keeps_rendering.wait(1.5)
        release_retry.set()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            event = reports.get(timeout=max(0.1, deadline-time.monotonic()))
            if event.get("n") == 2 and event.get("effective_role") == "show":
                frame = next(f for f in show_frames if f.sequence == event["frame_seq"])
                assert frame.metadata["managed_media_position"] == 1.5
                break
        else:
            pytest.fail("show candidate did not retry from the current media position")
    finally:
        allow_candidate.set()
        release_retry.set()
        commands.put(None)
        thread.join(12)
    assert not thread.is_alive() and not errors


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
    active = handoff.sample(0.01)
    assert active[1] == "show pixels"
    assert handoff.claim(active) and handoff.commit(active)
    handoff.request(2)
    handoff.request(3)
    handoff.publish(2, "music", "old candidate", {}, 0.05)
    assert handoff.sample(0.1)[1] == "show pixels"
    handoff.publish(3, "manual", "new pixels", {}, 0.11)
    candidate = handoff.sample(0.11)
    assert candidate[1] == "new pixels"
    assert handoff.claim(candidate) and handoff.commit(candidate)
    assert handoff.sample(0.12)[1] == "new pixels"


def test_keepalive_cannot_mask_stalled_renderer():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "show", "pixels", {}, 1.0)
    active = handoff.sample(1.0)
    assert handoff.claim(active) and handoff.commit(active)
    handoff.request(2)
    assert handoff.sample(1.4)[1] == "pixels"
    handoff.request(3)
    with pytest.raises(TimeoutError):
        handoff.sample(1.6)


def test_active_role_can_refresh_without_acknowledging_pending_manual_role():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "music", "frame 1", {}, 0)
    first = handoff.sample(0)
    assert handoff.claim(first) and handoff.commit(first)
    handoff.request(2)
    handoff.refresh_active(1, "music", "discarded audio projection", {}, 0.3, request_number=1)
    assert handoff.sample(0.3)[1] == "frame 1"
    handoff.refresh_active(1, "music", "frame 2", {}, 0.4, request_number=2)
    assert handoff.sample(0.7)[:4] == ("music", "frame 2", {}, 1)
    handoff.publish(2, "manual", "frame 3", {}, 0.71)
    handoff.refresh_active(1, "music", "late frame", {}, 0.8, request_number=2)
    assert handoff.sample(0.8)[:4] == ("manual", "frame 3", {}, 2)


def test_superseded_uncommitted_candidate_does_not_replace_committed_active_frame():
    handoff = FrameHandoff()
    handoff.request(1)
    assert handoff.publish(1, "show", "show frame", {}, 0.0)
    active = handoff.sample(0.0)
    assert handoff.claim(active)
    assert handoff.commit(active)

    handoff.request(2)
    assert handoff.publish(2, "music", "stale candidate", {}, 0.1)
    stale_candidate = handoff.sample(0.1)
    handoff.request(3)

    assert handoff.sample(0.2) is active
    assert not handoff.claim(stale_candidate)


def test_candidate_superseded_while_in_flight_is_not_acknowledged_applied():
    handoff = FrameHandoff()
    handoff.request(1)
    handoff.publish(1, "show", "show frame", {}, 0.0)
    active = handoff.sample(0.0)
    handoff.claim(active)
    handoff.commit(active)

    handoff.request(2)
    handoff.publish(2, "music", "candidate frame", {}, 0.1)
    candidate = handoff.sample(0.1)
    assert handoff.claim(candidate)
    handoff.request(3)

    assert not handoff.commit(candidate)
    assert handoff.sample(0.2) == active


def test_failed_output_send_never_reports_candidate_as_applied(monkeypatch):
    import json
    from pathlib import Path
    from queue import Empty, Queue
    from threading import Thread
    import time

    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.managed import serve
    from light_engine.outputs import NullOutput

    commands, reports = Queue(), Queue()
    output = NullOutput()
    attempted = []

    def send_all(_outputs, frame):
        attempted.append(frame)
        raise OSError("injected DDP send failure")

    monkeypatch.setattr("light_engine.managed.send_all", send_all)
    monkeypatch.setattr(
        Engine,
        "init_outputs",
        lambda engine: (setattr(engine, "_outputs", {"memory": output}), output.open()),
    )

    def run():
        serve(
            Config(Path("config/profiles/rk3588-host-service.yaml").resolve()),
            iter(commands.get, None),
            reports.put,
        )

    errors = []

    def guarded_run():
        try:
            run()
        except Exception as exc:
            errors.append(exc)

    thread = Thread(target=guarded_run, daemon=True)
    thread.start()
    commands.put(
        json.dumps(
            {
                "n": 1,
                "role": "music",
                "role_on_video_end": "none",
                "video_generation": 1,
                "seek_generation": 0,
                "mode": "auto",
                "target": {"kind": "none"},
                "mpv_socket": "unused-output-failure-test",
            }
        )
    )
    try:
        deadline = time.monotonic() + 10
        events = []
        while time.monotonic() < deadline:
            try:
                event = reports.get(timeout=min(0.1, deadline - time.monotonic()))
            except Empty:
                if not thread.is_alive():
                    break
                continue
            events.append(event)
            if event.get("role_phase") == "fault":
                break
        assert events and events[-1].get("role_phase") == "fault", (events, errors)
        assert not any(event.get("role_phase") == "applied" for event in events)
        assert "injected DDP send failure" in events[-1].get("reason", "")
    finally:
        commands.put(None)
        thread.join(10)
    assert not thread.is_alive()
    assert errors and "injected DDP send failure" in str(errors[0])
    assert attempted


@pytest.mark.parametrize("malformed", [False, True])
def test_old_content_lives_until_candidate_output_commits(monkeypatch, malformed):
    from dataclasses import replace
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Event, Thread

    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.managed import Content, FrameHandoff, serve
    from light_engine.outputs import NullOutput

    commands, reports = Queue(), Queue()
    offered, sending, release, closed = Event(), Event(), Event(), Event()
    producer_advanced = Event()
    output = NullOutput()
    original_publish = FrameHandoff.publish
    original_render = Content.render
    original_close = Content.close

    def publish(self, number, role, frame, audio, now, **kwargs):
        result = original_publish(self, number, role, frame, audio, now, **kwargs)
        if number == 2 and result:
            offered.set()
        return result

    def render(self, audio, command):
        if offered.is_set():
            producer_advanced.set()
        frame = original_render(self, audio, command)
        if malformed and self.role == "manual":
            return replace(frame, strips=[])
        return frame

    def close(self):
        if self.role == "music":
            closed.set()
        original_close(self)

    def send(frame):
        if offered.is_set() and not release.is_set():
            sending.set()
            assert release.wait(5)

    output.send_frame = send
    monkeypatch.setattr(FrameHandoff, "publish", publish)
    monkeypatch.setattr(Content, "render", render)
    monkeypatch.setattr(Content, "close", close)
    monkeypatch.setattr(
        Engine,
        "init_outputs",
        lambda e: (setattr(e, "_outputs", {"memory": output}), output.open()),
    )
    profile = Config(Path("config/profiles/rk3588-host-service.yaml").resolve())
    thread = Thread(target=serve, args=(profile, iter(commands.get, None), reports.put))
    thread.start()
    spec = {
        "role": "music",
        "role_on_video_end": "none",
        "video_generation": 1,
        "seek_generation": 0,
        "mode": "device",
        "target": {"kind": "none"},
        "mpv_socket": "unused-commit-test",
    }
    try:
        commands.put(json.dumps(dict(spec, n=1)))
        assert reports.get(timeout=5)["effective_role"] == "music"
        commands.put(json.dumps(dict(spec, n=2, role="manual", targets=[])))
        if malformed:
            event = reports.get(timeout=5)
            assert event["n"] == 2 and event["role_phase"] == "fault"
            assert not offered.is_set() and not closed.is_set()
            return
        assert sending.wait(5)
        assert producer_advanced.wait(5)
        assert not closed.is_set()
        release.set()
        assert reports.get(timeout=5)["effective_role"] == "manual"
        assert closed.wait(5)
    finally:
        release.set()
        commands.put(None)
        thread.join(10)
    assert not thread.is_alive()


def test_managed_sender_switches_real_effects_without_intermediate_safety_frame(
    monkeypatch,
    tmp_path,
):
    import json
    from pathlib import Path
    from queue import Queue
    from threading import Event, Thread
    import time
    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.outputs import NullOutput
    from light_engine.managed import serve
    from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvState
    from light_engine.show.compositor import ShowRuntime

    commands, reports = Queue(), Queue()
    frames, errors = [], []
    output = NullOutput()
    media_requested, release_media, active_keeps_rendering = Event(), Event(), Event()
    active_timestamps = set()

    def send(frame):
        frames.append(frame)
        if media_requested.is_set() and not release_media.is_set():
            active_timestamps.add(frame.timestamp)
            if len(active_timestamps) >= 5:
                active_keeps_rendering.set()

    output.send_frame = send
    engines = []
    init_engine = Engine.__init__

    def track_engine(engine, *args, **kwargs):
        engines.append(engine)
        init_engine(engine, *args, **kwargs)

    monkeypatch.setattr(Engine, "__init__", track_engine)

    def open_memory(engine):
        engine._outputs = {"memory": output}
        output.open()

    monkeypatch.setattr(Engine, "init_outputs", open_memory)
    position = [0.2]
    paused = [True]
    position_clock = [time.monotonic()]
    show_renders = []
    render_show = ShowRuntime.render

    def render(runtime, context, base):
        frame = render_show(runtime, context, base)
        if runtime.show.id == "short":
            show_renders.append(frame.timestamp)
            # A fresh context can generate different phase-dependent pixels
            # at the same timestamp.
            frame.strips[0].pixels[0] = (1.0 / len(show_renders), 0.0, 0.0)
        return frame

    monkeypatch.setattr(ShowRuntime, "render", render)

    def read_media(self):
        if not media_requested.is_set():
            media_requested.set()
            assert release_media.wait(3)
        current = position[0]
        if not paused[0]:
            current += time.monotonic() - position_clock[0]
        return MpvState(current, paused[0], current >= 1.1)

    monkeypatch.setattr(MpvIPCAdapter, "read_state", read_media)
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
        assert media_requested.wait(3)
        assert active_keeps_rendering.wait(1.5)
        release_media.set()
        event = reports.get(timeout=10)
        assert event.get("effective_role") == "show", event
        still = next(f for f in frames if f.sequence == event["frame_seq"])

        def await_role(number, role):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                status = reports.get(timeout=max(0.001, deadline - time.monotonic()))
                if status["n"] == number and status.get("effective_role") == role:
                    return status
            pytest.fail(f"role {role} did not become active for request {number}")

        commands.put(json.dumps(dict(config, n=5, role="music")))
        await_role(5, "music")
        commands.put(json.dumps(dict(config, n=6)))
        event = await_role(6, "show")
        restored = next(f for f in frames if f.sequence == event["frame_seq"])
        assert restored.digital_frames == still.digital_frames
        assert restored.timestamp == still.timestamp
        commands.put(json.dumps(dict(config, n=7, seek_generation=1, await_media=True)))
        while (event := reports.get(timeout=5))["n"] != 7:
            pass
        assert event["role_phase"] == "held", event
        position[0], paused[0] = 0.25, True
        position_clock[0] = time.monotonic()
        commands.put(json.dumps(dict(config, n=8, seek_generation=1)))
        event = await_role(8, "show")
        new_frame = next(f for f in frames if f.sequence == event["frame_seq"])
        assert new_frame.timestamp == 0.25
        position[0], paused[0] = 1.05, False
        position_clock[0] = time.monotonic()
        deadline = time.monotonic() + 10
        while True:
            event = reports.get(timeout=max(0.1, deadline - time.monotonic()))
            if event.get("effective_role") == "music":
                break
            assert time.monotonic() < deadline, event
        assert (event["n"], event["effective_role"]) == (8, "music")
        position[0], paused[0] = 0.3, True
        position_clock[0] = time.monotonic()
        commands.put(json.dumps(dict(config, n=9, seek_generation=2)))
        event = reports.get(timeout=10)
        assert (event["n"], event["effective_role"]) == (9, "show")
        assert not any(f.metadata.get("SAFE_STATE") for f in frames)
    finally:
        release_media.set()
        commands.put(None)
        thread.join(12)
    assert not thread.is_alive() and not errors
    assert frames[-1].metadata["SAFE_STATE"]
    assert [f.sequence for f in frames] == list(range(1, len(frames) + 1))
    assert len(engines) == 1


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
    from light_engine.engine import Engine, RenderContext
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
    monkeypatch.setattr(RenderContext, "load_video", lambda self, path: None)
    media_position = [position]
    monkeypatch.setattr(
        MpvIPCAdapter,
        "read_state",
        lambda self: MpvState(
            media_position[0], True, media_position[0] >= 305.620998
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
    from light_engine.engine import Engine, RenderContext
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
    monkeypatch.setattr(RenderContext, "load_video", lambda self, path: None)
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
