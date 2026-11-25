"""Bounded targeted PCM capture from PulseAudio using ``parec``."""

from __future__ import annotations

import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np


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
        self._process = None
        self._queue: deque[PCMChunk] = deque(maxlen=max_blocks)
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._sample_seq = 0
        self._dropped_blocks = 0
        self._error: str | None = None

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
        if self._process is not None:
            return self
        self._process = self._popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
        )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader, name="parec-capture", daemon=True
        )
        self._thread.start()
        return self

    def _reader(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        frames = max(1, self.sample_rate * self.block_ms // 1000)
        byte_count = frames * self.channels * 2
        discontinuity = False
        partial = b""
        stream = self._process.stdout
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
        return {
            "running": self._process is not None and self._process.poll() is None,
            "queued_blocks": len(self._queue),
            "dropped_blocks": self._dropped_blocks,
            "sample_seq": self._sample_seq,
            "error": self._error,
        }

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        process = self._process
        self._process = None
        if process is not None:
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
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._condition:
            self._queue.clear()

    def __enter__(self) -> "ParecCapture":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.close()
