"""Parent side of the single-sender Engine control channel."""

import json
import subprocess
import threading
import time

from .real_engine_adapter import EnginePreparationError, RealEngineAdapter, _drain_stderr, _kill_proc


class ManagedAdapter(RealEngineAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

        self._active_show = show
        host._reconcile_lighting(playing=True, start_ms=start_ms, wait=True)
        if show.get("aux_triggers"):
            self._start_aux_poll(show["aux_triggers"], start_ms or 0)

    def on_playback_stop(self):
        self._stop_aux_poll()
        self._active_show = None
        from . import starry_sky

        starry_sky.ensure_off()

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

    def on_playback_resume_yaml(self):
        if self._active_show and self._active_show.get("aux_triggers"):
            self._start_aux_poll(self._active_show["aux_triggers"], 0)
        return self._active_show is not None

    def process_failure(self, position_ms=None):
        # Keep repair in the existing Host watchdog and the playback session lock.
        if (
            self.sender
            and self.sender.poll() is not None
            and self.status["role_phase"] == "fault"
            and time.monotonic() - self.last_recovery >= 5
        ):
            from . import engine_adapter as host

            self.last_recovery = time.monotonic()
            host._push_wled_off(explicit=True)
            self.command = None
            host._reconcile_lighting()
        return None

    def shutdown(self):
        with self.changed:
            self._close_sender()
        self.on_playback_stop()
