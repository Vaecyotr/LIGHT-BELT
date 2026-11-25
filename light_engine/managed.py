"""One Host-owned frame sender with replaceable, output-free content contexts."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
from threading import Event, Lock, Thread
import time

from light_engine.cli import _configure_engine_show
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvIPCError
from light_engine.models import EffectContext
from light_engine.outputs import send_all
from light_engine.show.compositor import ShowRuntime, black_base_frame
from light_engine.show.loader import TargetCatalog, validate_show_data


class FrameHandoff:
    def __init__(self):
        self.lock = Lock()
        self.requested = 0
        self.latest = None
        self.committed = None

    def request(self, number):
        with self.lock:
            self.requested = number
            if self.latest is not None and self.latest[3] != number:
                self.latest = None

    def publish(self, number, role, frame, audio, now):
        with self.lock:
            if number == self.requested:
                self.latest = (role, frame, audio, number, now)
                return True
            return False

    def claim(self, item):
        """Claim a current candidate or the committed active role for one send."""
        with self.lock:
            return item is self.latest and item[3] == self.requested or (
                item is self.committed
            )

    def commit(self, item):
        """Commit only frames still current after the complete output send."""
        with self.lock:
            if item is self.latest and item[3] == self.requested:
                self.committed = item
                self.latest = None
                return True
            if item is self.committed:
                return True
            return False

    def refresh_active(self, number, role, frame, audio, now):
        with self.lock:
            if self.committed is not None and self.committed[3] == number:
                self.committed = (role, frame, audio, number, now)

    def sample(self, now):
        with self.lock:
            item = self.latest if self.latest is not None else self.committed
            if item is not None and now - item[-1] > 0.5:
                raise TimeoutError("lighting content exceeded the frame hold deadline")
            return item


def effect_show(targets, layout):
    cues = []
    for i, entry in enumerate(targets):
        cues.append(
            {
                "id": f"manual_{i}",
                "start": 0,
                "end": 86400,
                "target": {"type": "digital_strip", "id": entry["target_id"]},
                "effect": {
                    "mode": "fixed",
                    "id": entry.get("effect_type", "static"),
                    "intensity": entry.get("intensity", 1),
                    "speed": entry.get("speed", 1),
                    "params": entry.get("effect_params", {}),
                },
                "color": {"mode": "solid", "color": entry.get("color", [1, 1, 1])},
            }
        )
    doc = {
        "schema_version": 2,
        "show": {
            "id": "manual",
            "duration": 86400,
            "defaults": {"fade_in": 0, "fade_out": 0, "blend": "replace"},
            "cues": cues,
        },
    }
    return ShowRuntime.from_layout(
        validate_show_data(doc, TargetCatalog.from_layout(layout)), layout
    )


class Content:
    def __init__(self, config, command):
        self.engine = Engine(config)
        self.role = command["role"]
        self.start = time.monotonic()
        self.last_time = None
        self.frame = None
        self.duration = None
        self.mpv = MpvIPCAdapter(command["mpv_socket"])
        self.last_video = None
        self.frozen = False
        e = self.engine
        try:
            if self.role == "show":
                show = command["show"]
                self.duration = _configure_engine_show(e, show["show_yaml"])
                if Path(show["media_path"]).suffix.lower() in (".mp4", ".mkv", ".mov"):
                    e.load_video(show["media_path"])
            elif self.role == "manual":
                e.set_show_runtime(effect_show(command["targets"], e._layout))
            elif self.role == "music":
                e.set_effect("audio_pulse")
            else:
                raise ValueError("unknown content role")
        except BaseException:
            self.close()
            raise

    def close(self):
        self.mpv.close()
        if self.engine._video_reader:
            self.engine._video_reader.close()

    def render(self, audio, command):
        media = None
        if self.role == "show" or command["target"].get("kind") == "file":
            try:
                media = self.mpv.read_state()
            except MpvIPCError:
                if self.role == "show" and self.mpv.get_property("idle-active"):
                    return None
                raise
        if self.role == "show":
            if media.ended or media.position >= self.duration:
                return None
            t = media.position
        else:
            t = time.monotonic() - self.start
        features, music = audio.poll(media.position if media else t)
        self.frozen = False
        if (
            self.role == "show"
            and self.frame is not None
            and self.last_time == t
        ):
            self.frozen = True
            return self.frame
        if features is not None:
            features = copy(features)
            features.timestamp = t
        if music is not None:
            music = replace(music, timestamp=t)
        e = self.engine
        dt = 1 / e._output_fps if self.last_time is None else max(0, t - self.last_time)
        if self.last_time is not None and t < self.last_time:
            e._handle_timeline_reset()
            self.last_video = None
            dt = 1/e._output_fps
        self.last_time = t
        e._timestamp = t
        if e._video_reader and (
            self.last_video is None or t - self.last_video >= 1 / e._video_fps
        ):
            e._latest_video = (
                e._get_video_features() if t < e._video_reader.duration else None
            )
            self.last_video = t
        ctx = EffectContext(
            timestamp=t,
            delta_time=min(0.25, dt),
            sequence=0,
            video_features=e._latest_video,
            audio_features=features,
            music_control_state=music,
            mode_parameters={"strip_defs": e._strip_defs, "zone_defs": e._zone_defs},
        )
        if e._show_runtime:
            if self.role == "manual":
                ctx = replace(ctx, timestamp=t % 86400)
                if self.frame and ctx.timestamp < self.frame.timestamp:
                    e._show_runtime.reset()
            base = black_base_frame(
                timestamp=ctx.timestamp,
                sequence=0,
                analog_zones=e._layout.zones,
                digital_strips=e._layout.strips,
            )
            self.frame = e._show_runtime.render(ctx, base)
        else:
            self.frame = e._effect.process(ctx)
            for strip in self.frame.strips:
                strip.pixels = [
                    (max(r, 0.035), max(g, 0.018), max(b, 0.009))
                    for r, g, b in strip.pixels
                ]
        return self.frame


def serve(config, commands, report):
    from light_engine.analysis.managed_audio_input import ManagedAudioInput

    writer = Engine(config)
    handoff = FrameHandoff()
    stop = Event()
    lock = Lock()
    command = {}
    failures = []
    terminal_status = {}
    period = 1 / writer._output_fps

    def receive():
        nonlocal command
        try:
            for raw in commands:
                if len(raw) > 262144:
                    raise ValueError("managed command exceeds limit")
                value = json.loads(raw)
                with lock:
                    if value["n"] > command.get("n", 0):
                        handoff.request(value["n"])
                        command = value
        except Exception as exc:
            failures.append(str(exc))
        finally:
            stop.set()

    def produce():
        active = pending = ready = None
        active_key = pending_key = None
        abandoned = False
        failed_key = None
        audio = ManagedAudioInput(config)
        loader = ThreadPoolExecutor(max_workers=1)
        ended = None
        audio_key = None
        applied_number = None
        try:
            while not stop.is_set():
                with lock:
                    cfg = command
                if not cfg:
                    stop.wait(period)
                    continue
                timeline = (cfg["video_generation"], cfg["seek_generation"])
                if timeline == ended and cfg["role"] == "show":
                    cfg = dict(cfg, role=cfg["role_on_video_end"])
                if cfg["role"] == "none":
                    terminal_status.update(
                        n=cfg["n"],
                        role_phase="idle",
                        effective_role="none",
                        reason="content finished",
                    )
                    stop.set()
                    break
                role = cfg["role"]
                key = (
                    role,
                    cfg["video_generation"] if role == "show" else None,
                    cfg.get("seek_generation") if role == "show" else None,
                    cfg.get("targets") if role == "manual" else None,
                )
                if pending and pending.done():
                    try:
                        ready = pending.result()
                        if key != pending_key or abandoned:
                            ready.close()
                            ready = None
                    except Exception as exc:
                        failed_key = (pending_key, cfg["n"])
                        report(
                            {"n": cfg["n"], "role_phase": "fault", "reason": str(exc)}
                        )
                    pending = None
                if (
                    not pending
                    and not ready
                    and key != active_key
                    and (key, cfg["n"]) != failed_key
                ):
                    pending_key = key
                    pending = loader.submit(Content, config, cfg)
                    abandoned = False
                    prepare_start = time.monotonic()
                if pending and not abandoned and time.monotonic() - prepare_start > 10:
                    if active is None:
                        raise TimeoutError("content preparation timed out")
                    abandoned = True
                    failed_key = (pending_key, cfg["n"])
                    report(
                        {
                            "n": cfg["n"],
                            "role_phase": "fault",
                            "reason": "content preparation timed out",
                        }
                    )
                current = ready or active
                old_timeline_valid = active_key is not None and (
                    active_key[0] != "show"
                    or active_key[1:3] == timeline
                    and ended != timeline
                )
                if current and (ready or active_key == key or old_timeline_valid):
                    target = cfg["target"]
                    if cfg["mode"] == "mic":
                        target = {"kind": "wled", "source_id": cfg.get("mic_sender")}
                    elif target.get("kind") == "file":
                        target = dict(target, timeline=timeline)
                    source_key = (
                        cfg["mode"],
                        target,
                        cfg["seek_generation"]
                        if target.get("kind") == "file"
                        else None,
                    )
                    if source_key != audio_key:
                        audio.configure(cfg["mode"], target)
                        audio_key = source_key
                    try:
                        frame = current.render(audio, cfg)
                    except Exception as exc:
                        if ready is None:
                            raise
                        ready.close()
                        ready = None
                        failed_key = (key, cfg["n"])
                        report(
                            {"n": cfg["n"], "role_phase": "fault", "reason": str(exc)}
                        )
                    else:
                        if frame is None:
                            ended = timeline
                            if ready:
                                ready.close()
                                ready = None
                        else:
                            now = time.monotonic()
                            status = audio.status()
                            if current.frozen:
                                status = dict(
                                    status,
                                    phase="preparing",
                                    effective=None,
                                    reason="节目暂停，灯光定格",
                                )
                            if current is active and active_key != key:
                                handoff.refresh_active(
                                    applied_number, current.role, frame, status, now
                                )
                            elif handoff.publish(
                                cfg["n"], current.role, frame, status, now
                            ):
                                applied_number = cfg["n"]
                                if ready:
                                    if active:
                                        active.close()
                                    active, active_key, ready = ready, key, None
                            elif ready:
                                ready.close()
                                ready = None
                stop.wait(period)
        except Exception as exc:
            failures.append(str(exc))
            stop.set()
        finally:
            audio.close()
            if active:
                active.close()
            if ready:
                ready.close()
            if pending and not pending.cancel():
                pending.add_done_callback(
                    lambda job: job.result().close() if not job.exception() else None
                )
            loader.shutdown(wait=False, cancel_futures=True)

    Thread(target=receive, daemon=True).start()
    worker = Thread(target=produce, daemon=True)
    worker.start()
    last_report = None
    try:
        writer.init_outputs()
        while not stop.is_set():
            now = time.monotonic()
            item = handoff.sample(now)
            if item and handoff.claim(item):
                role, frame, source, n, _ = item
                frame = replace(frame, sequence=writer._advance_sequence())
                writer._timestamp = frame.timestamp
                physical = writer._physical_mapping.map(
                    writer._output_transform.apply_to_frame(frame)
                )
                if not any(node.enabled for node in physical.digital_frames):
                    raise RuntimeError("no enabled DDP node")
                send_all(writer._outputs, physical)
                applied_current = handoff.commit(item)
                identity = (
                    n,
                    role,
                    source.get("phase"),
                    source.get("quality"),
                    source.get("effective"),
                    source.get("silent"),
                    source.get("reason"),
                )
                if applied_current and identity != last_report:
                    report(
                        {
                            "n": n,
                            "role_phase": "applied",
                            "effective_role": role,
                            "audio": source,
                            "frame_seq": frame.sequence,
                        }
                    )
                    last_report = identity
            stop.wait(max(0, period - (time.monotonic() - now)))
    except Exception as exc:
        failures.append(str(exc))
    finally:
        stop.set()
        writer._shutdown()
        worker.join(timeout=2)
    if failures:
        ddp = writer._outputs.get("ddp")
        report(
            {
                "n": command.get("n"),
                "role_phase": "fault",
                "effective_role": "none",
                "reason": failures[0],
                "node_submissions": getattr(ddp, "last_node_submission", {}),
                "node_safe_submissions": getattr(ddp, "last_node_safe_submission", {}),
            }
        )
        raise RuntimeError(failures[0])
    if terminal_status:
        report(terminal_status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    config = Config.get_instance(parser.parse_args().config)
    serve(
        config,
        sys.stdin,
        lambda value: print(json.dumps(value, allow_nan=False), flush=True),
    )
