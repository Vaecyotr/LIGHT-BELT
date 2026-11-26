"""Parent side of the single-sender Engine control channel."""

import json
import logging
import sys
import subprocess
import threading
import time

_log = logging.getLogger(__name__)


class EnginePreparationError(RuntimeError):
    """A managed Engine preparation fault already recorded in its status."""


def _drain_stderr(proc: subprocess.Popen, label: str) -> None:
    """Read proc.stderr line-by-line in a daemon thread and log each line as a warning."""
    def _reader():
        for raw in proc.stderr:
            _log.warning("[%s] %s", label, raw.decode(errors="replace").rstrip())
    threading.Thread(target=_reader, daemon=True, name=f"stderr-{label}").start()


def _kill_proc(proc: subprocess.Popen | None, name: str = "engine") -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _log.warning("%s did not terminate; sending SIGKILL", name)
            proc.kill()
            proc.wait(timeout=3)
    except Exception as exc:
        raise RuntimeError(f"Unable to stop {name}: {exc}") from exc


class ManagedAdapter:
    def __init__(self, profile_path: str, mpv_socket_path: str,
                 python_executable: str = sys.executable) -> None:
        self._profile = profile_path
        self._mpv_socket = mpv_socket_path
        self._python = python_executable
        self._aux_poll_thread: threading.Thread | None = None
        self._aux_stop_event: threading.Event | None = None
        self._aux_error: str | None = None
        self.sender = None
        self.changed = threading.Condition()
        self.number = 0
        self._held_number = None
        self.last_recovery = 0.0
        self.seek_generation = 0
        self.command = None
        self.status = {"role_phase": "idle", "effective_role": "none"}

    def configure(self, spec, *, wait=False):
        with self.changed:
            if spec["role"] == "none":
                self._close_sender()
                return
            if self.sender is not None and self.sender.poll() is not None:
                if self.command == spec and self.status["role_phase"] in (
                    "idle",
                    "fault",
                ):
                    if wait and self.status["role_phase"] == "fault":
                        raise EnginePreparationError(self.status.get("reason", "lighting failed"))
                    return
                failure = self.status if self.status["role_phase"] == "fault" else None
                self._close_sender()
                if failure is not None:
                    self.status = failure
            if self.sender is None:
                self.sender = subprocess.Popen(
                    [
                        self._python,
                        "-m",
                        "light_engine.managed",
                        "--config",
                        self._profile,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                _drain_stderr(self.sender, "managed-engine")
                threading.Thread(
                    target=self._read, args=(self.sender,), daemon=True
                ).start()
            self._send_spec(spec)
            if wait:
                ready_phase = "held" if spec.get("await_media") else "applied"
                if not self.changed.wait_for(
                    lambda: (ready_phase == "held" and self._held_number == self.number)
                    or (self.status.get("n") == self.number and
                        self.status["role_phase"] in (ready_phase, "fault", "idle")),
                    10,
                ):
                    reason = "lighting content did not become ready"
                    self.status.update(n=self.number, role_phase="fault", reason=reason)
                    raise EnginePreparationError(reason)
                if self.status["role_phase"] == "fault" and not (
                    ready_phase == "held" and self._held_number == self.number
                ):
                    raise EnginePreparationError(self.status.get("reason", "lighting failed"))

    def refresh_audio(self):
        """Revise source eligibility without changing the current media operation."""
        with self.changed:
            if self.command and self.sender is not None and self.sender.poll() is None:
                self._send_spec(self.command)

    def _send_spec(self, spec):
        if "program_target" in spec:
            from .engine_adapter import _lighting_audio_target
            spec = dict(spec, target=_lighting_audio_target(spec))
        if spec == self.command:
            return
        self.number += 1
        if self.status["role_phase"] != "fault":
            self.status = {"role_phase": "preparing",
                           "effective_role": self.status["effective_role"]}
        else:
            for field in ("node_submissions", "node_safe_submissions", "submitted_ms", "frame_seq"):
                self.status.pop(field, None)
        payload = dict(spec, n=self.number, mpv_socket=self._mpv_socket)
        try:
            self.sender.stdin.write((json.dumps(payload, allow_nan=False) + "\n").encode())
            self.sender.stdin.flush()
        except OSError as exc:
            self.status.update(n=self.number, role_phase="fault", reason=str(exc))
            raise
        self.command = spec

    def _read(self, process):
        try:
            for line in process.stdout:
                msg = json.loads(line)
                with self.changed:
                    if process is self.sender and msg.get("n") == self.number:
                        if msg.get("role_phase") == "held":
                            self._held_number = self.number
                            self.changed.notify_all()
                        elif msg.get("role_phase") == "fault":
                            self._held_number = None
                        if (self.status["role_phase"] == "fault"
                                and msg.get("role_phase") not in ("applied", "fault", "idle")):
                            continue
                        if "reason" not in msg:
                            self.status.pop("reason", None)
                        self.status.update(msg)
                        if msg.get("node_submissions"):
                            from .engine_adapter import _record_ddp_submissions

                            _record_ddp_submissions(msg)
                        self.changed.notify_all()
        finally:
            with self.changed:
                if process is self.sender and self.status.get("role_phase") not in (
                    "idle",
                    "fault",
                ):
                    self.status.update(
                        n=self.number, role_phase="fault",
                        effective_role="none",
                        reason="lighting sender closed",
                    )
                    self.changed.notify_all()

    def _close_sender(self):
        proc = self.sender
        if proc:
            if proc.stdin:
                try:
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _kill_proc(proc)
        self.sender = self.command = None
        self.status = {"role_phase": "idle", "effective_role": "none"}

    def on_playback_start(self, show, start_ms):
        from . import engine_adapter as host

        host._sync_lighting(playing=True, start_ms=start_ms, wait=True)
        if show.get("aux_triggers"):
            self._start_aux_poll(show["aux_triggers"], start_ms or 0)

    def on_playback_stop(self):
        owned_trigger = self._aux_poll_thread is not None
        self._stop_aux_poll()
        if not owned_trigger:
            return
        from . import starry_sky

        self._aux_error = None
        try:
            starry_sky.ensure_off()
        except OSError as exc:
            self._aux_error = str(exc)
            _log.warning("Starry sky stop submission failed: %s", exc)
        return self._aux_error

    def on_playback_seek_prepare(self):
        self._stop_aux_poll()
        self.seek_generation += 1
        self.hold_show_for_media_change()

    def hold_show_for_media_change(self):
        if self.command and self.command["role"] == "show":
            self.configure(
                dict(self.command, seek_generation=self.seek_generation, await_media=True),
                wait=True,
            )

    def resume_aux(self, show):
        if show and show.get("aux_triggers"):
            self._start_aux_poll(show["aux_triggers"], None)
        return show is not None

    def _start_aux_poll(self, triggers, start_ms):
        self._stop_aux_poll()
        actions = sorted(
            ((item["at_ms"], item["action"] == "on") for item in triggers
             if item.get("target") == "starry_sky" and item.get("action") in {"on", "off"}),
            key=lambda entry: entry[0],
        )
        if not actions:
            return
        stop = self._aux_stop_event = threading.Event()
        self._aux_poll_thread = threading.Thread(
            target=self._aux_poll_loop, args=(actions, start_ms, stop),
            daemon=True, name="aux-triggers-poll",
        )
        self._aux_poll_thread.start()

    def _stop_aux_poll(self):
        if self._aux_stop_event is not None:
            self._aux_stop_event.set()
            self._aux_poll_thread.join()
            self._aux_poll_thread = self._aux_stop_event = None

    def _aux_poll_loop(self, actions, start_ms, stop):
        from . import engine_adapter as host, starry_sky

        desired = None
        position_ms = start_ms
        while not stop.is_set():
            mpv = host._mpv
            if mpv is not None:
                response = mpv._send(["get_property", "time-pos"])
                if response.get("error") == "success" and isinstance(response.get("data"), (float, int)):
                    position_ms = response["data"] * 1000
            if position_ms is None:
                stop.wait(1)
                continue
            wanted = starry_sky.action_at_position(actions, position_ms)
            if wanted != desired and not stop.is_set():
                desired = wanted
                try:
                    starry_sky.ensure_on() if wanted else starry_sky.ensure_off()
                except OSError as exc:
                    self._aux_error = str(exc)
                    _log.warning("Starry sky trigger submission failed at %.0f ms: %s", position_ms, exc)
                else:
                    self._aux_error = None
            stop.wait(1)

    def recover_sender(self):
        # Keep repair in the existing Host watchdog and the playback session lock.
        if (
            self.sender
            and self.sender.poll() is not None
            and self.status["role_phase"] == "fault"
            and time.monotonic() - self.last_recovery >= 5
        ):
            from . import engine_adapter as host

            self.last_recovery = time.monotonic()
            try:
                host._push_wled_off()
            except RuntimeError as exc:
                _log.warning("WLED state unconfirmed after sender exit: %s", exc)
            self.command = None
            host._reconcile_lighting()

    def shutdown(self):
        with self.changed:
            self._close_sender()
        self.on_playback_stop()
