"""Bounded targeted PCM capture from PulseAudio using ``parec``."""

from __future__ import annotations

import subprocess
import json
import shlex
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np


def validate_pulse_target(
    target: dict, *, timeout: float = 1.0, run: Callable | None = None
) -> bool:
    """Confirm the indexed PA sink-input still has the selected owner and sink."""
    stream_index = target.get("monitor_stream")
    sink_index = target.get("pa_sink_index")
    if (
        not isinstance(stream_index, int)
        or isinstance(stream_index, bool)
        or not isinstance(sink_index, int)
        or isinstance(sink_index, bool)
        or target.get("device") != target.get("pa_monitor_source")
    ):
        return False

    def pactl(*args):
        result = (run or subprocess.run)(
            ["pactl", *args], capture_output=True, text=True, timeout=timeout,
            check=True,
        )
        return result.stdout

    try:
        sinks = json.loads(pactl("--format=json", "list", "sinks"))
        inputs = json.loads(pactl("--format=json", "list", "sink-inputs"))
        sink = next(
            (item for item in sinks if int(item.get("index", -1)) == sink_index),
            None,
        )
        stream = next(
            (item for item in inputs if int(item.get("index", -1)) == stream_index),
            None,
        )
        if sink is None or stream is None:
            return False
        if sink.get("name") != target.get("pa_sink"):
            return False
        if sink.get("monitor_source") != target.get("pa_monitor_source"):
            return False
        if int(stream.get("sink", -1)) != sink_index:
            return False
        if target.get("pa_owner_module") is not None:
            if str(stream.get("owner_module")) != str(target["pa_owner_module"]):
                return False
            modules = pactl("list", "short", "modules")
            for line in modules.splitlines():
                fields = line.split("\t", 2)
                if len(fields) != 3 or fields[0] != str(target["pa_owner_module"]):
                    continue
                args = dict(
                    word.split("=", 1)
                    for word in shlex.split(fields[2])
                    if "=" in word
                )
                return (
                    fields[1] == "module-loopback"
                    and args.get("source") == target.get("pa_source")
                    and args.get("sink") == target.get("pa_sink")
                )
            return False
        properties = stream.get("properties", {})
        return str(properties.get("application.process.id")) == str(
            target.get("pa_owner_pid")
        )
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError):
        return False


@dataclass(frozen=True)
class PCMChunk:
    samples: np.ndarray
    sample_seq: int
    received_ns: int
    discontinuity: bool = False


class ParecCapture:
    """Read interleaved signed-16 PCM from one explicitly named PA source."""

    def __init__(
        self,
        *,
        device: str,
        monitor_stream: int | None = None,
        sample_rate: int = 48_000,
        channels: int = 2,
        block_ms: int = 20,
        max_blocks: int = 10,
        binary: str = "parec",
        popen: Callable = subprocess.Popen,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        target_proof: dict | None = None,
        target_validator: Callable[[dict], bool] | None = None,
    ) -> None:
        if not device:
            raise ValueError("device is required")
        if (
            sample_rate <= 0
            or channels not in (1, 2)
            or block_ms <= 0
            or max_blocks <= 0
        ):
            raise ValueError("invalid PCM capture format or buffer size")
        self.device = device
        self.monitor_stream = monitor_stream
        self.sample_rate = sample_rate
        self.channels = channels
        self.block_ms = block_ms
        self.max_blocks = max_blocks
        self.binary = binary
        self._popen = popen
        self._clock_ns = clock_ns
        self._target_proof = dict(target_proof) if target_proof else None
        self._target_validator = target_validator or validate_pulse_target
        self._process = None
        self._queue: deque[PCMChunk] = deque(maxlen=max_blocks)
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sample_seq = 0
        self._dropped_blocks = 0
        self._error: str | None = None
        self._phase = "idle"

    @property
    def command(self) -> list[str]:
        command = [
            self.binary,
            "--raw",
            "--format=s16le",
            f"--rate={self.sample_rate}",
            f"--channels={self.channels}",
            f"--device={self.device}",
        ]
        if self.monitor_stream is not None:
            command.append(f"--monitor-stream={self.monitor_stream}")
        return command

    def start(self) -> "ParecCapture":
        with self._condition:
            if self._thread is not None:
                return self
            self._stop.clear()
            self._phase = "validating" if self._target_proof is not None else "starting"
            self._thread = threading.Thread(
                target=self._validate_and_read, name="parec-capture", daemon=True
            )
            self._thread.start()
        return self

    def _validate_and_read(self) -> None:
        try:
            if self._target_proof is not None and not self._target_validator(self._target_proof):
                self._error = "PulseAudio capture target changed before binding"
                self._phase = "invalid"
                return
            if self._stop.is_set():
                return
            process = self._popen(
                self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
            )
            with self._condition:
                cancelled = self._stop.is_set()
                if not cancelled:
                    self._process = process
                    self._phase = "running"
            if cancelled:
                self._close_process(process)
                return
            self._reader(process)
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._phase = "fault"
        finally:
            if self._stop.is_set():
                self._phase = "closed"

    def _reader(self, process) -> None:
        assert process.stdout is not None
        frames = max(1, self.sample_rate * self.block_ms // 1000)
        byte_count = frames * self.channels * 2
        discontinuity = False
        partial = b""
        stream = process.stdout
        try:
            while not self._stop.is_set():
                block = stream.read(byte_count)
                if not block:
                    if partial:
                        self._error = "capture ended in a partial sample frame"
                    break
                raw = partial + block
                usable = len(raw) - len(raw) % (self.channels * 2)
                partial = raw[usable:]
                if usable == 0:
                    continue
                pcm = np.frombuffer(raw[:usable], dtype="<i2").astype(np.float32)
                pcm /= 32768.0
                pcm = pcm.reshape((-1, self.channels))
                with self._condition:
                    if len(self._queue) == self.max_blocks:
                        self._dropped_blocks += 1
                        discontinuity = True
                    self._sample_seq += 1
                    self._queue.append(
                        PCMChunk(
                            samples=pcm,
                            sample_seq=self._sample_seq,
                            received_ns=self._clock_ns(),
                            discontinuity=discontinuity,
                        )
                    )
                    discontinuity = False
                    self._condition.notify_all()
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            with self._condition:
                self._condition.notify_all()
        self._phase = "closed" if self._stop.is_set() else "fault"

    def read_latest(self, timeout: float = 0.0) -> PCMChunk | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while not self._queue and not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            if not self._queue:
                return None
            chunks = list(self._queue)
            self._queue.clear()
        return PCMChunk(
            samples=np.concatenate([chunk.samples for chunk in chunks], axis=0),
            sample_seq=chunks[-1].sample_seq,
            received_ns=chunks[-1].received_ns,
            discontinuity=any(chunk.discontinuity for chunk in chunks),
        )

    def status(self) -> dict[str, object]:
        process = self._process
        return {
            "running": process is not None and process.poll() is None,
            "queued_blocks": len(self._queue),
            "dropped_blocks": self._dropped_blocks,
            "sample_seq": self._sample_seq,
            "error": self._error,
            "phase": self._phase,
        }

    @staticmethod
    def _close_process(process) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

    def close(self) -> None:
        with self._condition:
            self._stop.set()
            process, self._process = self._process, None
            thread = self._thread
            self._queue.clear()
            self._condition.notify_all()
        if process is not None:
            self._close_process(process)
        if thread is not None:
            thread.join(timeout=2.0)
            with self._condition:
                if not thread.is_alive() and self._thread is thread:
                    self._thread = None
                self._queue.clear()

    def __enter__(self) -> "ParecCapture":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()
