"""Parent side of the single-sender Engine control channel."""

import json
import subprocess
import threading
import time

from .real_engine_adapter import RealEngineAdapter, _drain_stderr, _kill_proc


class ManagedAdapter(RealEngineAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sender = None
        self.changed = threading.Condition()
        self.number = 0
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
                        raise RuntimeError(self.status.get("reason", "lighting failed"))
                    return
                self._close_sender()
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
            if spec != self.command:
                self.number += 1
                self.status = {"role_phase": "preparing",
                               "effective_role": self.status["effective_role"]}
                payload = dict(spec, n=self.number, mpv_socket=self._mpv_socket)
                try:
                    self.sender.stdin.write(
                        (json.dumps(payload, allow_nan=False) + "\n").encode()
                    )
                    self.sender.stdin.flush()
                except OSError as exc:
                    self.status.update(role_phase="fault", reason=str(exc))
                    raise
                self.command = spec
            if wait:
                if not self.changed.wait_for(
                    lambda: self.status["role_phase"] in ("applied", "fault", "idle"),
                    10,
                ):
                    raise RuntimeError("lighting content did not become ready")
                if self.status["role_phase"] == "fault":
                    raise RuntimeError(self.status.get("reason", "lighting failed"))

    def _read(self, process):
        try:
            for line in process.stdout:
                msg = json.loads(line)
                with self.changed:
                    if process is self.sender and msg.get("n") == self.number:
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
                        role_phase="fault",
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
