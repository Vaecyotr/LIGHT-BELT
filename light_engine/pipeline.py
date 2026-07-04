"""Producer-consumer pipeline with bounded queues.

Separates video reading, audio analysis, effect computation,
and output sending into independent work units.

All queues are bounded — new data replaces old when full.
No unbounded growth. No busy-waiting.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from light_engine.models import (
    AudioFeatures,
    PixelFrame,
    VideoFeatures,
)


@dataclass
class PipelineStats:
    """Statistics for a pipeline stage."""
    frames_produced: int = 0
    frames_consumed: int = 0
    frames_dropped: int = 0
    queue_max_len: int = 0
    total_wait_ms: float = 0.0


class LatestValueQueue:
    """Thread-safe bounded queue that keeps only the latest value.

    Producers always succeed (oldest value dropped if full).
    Consumers get the latest value or None if empty.

    This is the correct pattern for real-time pipelines where
    stale frames should be discarded.
    """

    def __init__(self, maxsize: int = 4):
        self._maxsize = max(1, maxsize)
        self._items: deque = deque(maxlen=self._maxsize)
        self._lock = threading.Lock()
        self._stats = PipelineStats()

    def put(self, item: Any) -> bool:
        """Put item, dropping oldest if full. Returns True if drop occurred."""
        dropped = False
        with self._lock:
            if len(self._items) >= self._maxsize:
                dropped = True
                self._stats.frames_dropped += 1
            self._items.append(item)
            self._stats.frames_produced += 1
            self._stats.queue_max_len = max(
                self._stats.queue_max_len, len(self._items)
            )
        return dropped

    def get(self) -> Optional[Any]:
        """Get latest item and drain queue, or None if empty."""
        with self._lock:
            if self._items:
                self._stats.frames_consumed += 1
                item = self._items[-1]
                self._items.clear()
                return item
            return None

    def get_all(self) -> list[Any]:
        """Drain all items (for batch processing)."""
        with self._lock:
            items = list(self._items)
            self._items.clear()
            self._stats.frames_consumed += len(items)
            return items

    def stats(self) -> PipelineStats:
        with self._lock:
            return PipelineStats(
                frames_produced=self._stats.frames_produced,
                frames_consumed=self._stats.frames_consumed,
                frames_dropped=self._stats.frames_dropped,
                queue_max_len=self._stats.queue_max_len,
                total_wait_ms=self._stats.total_wait_ms,
            )

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class BoundedFIFOQueue:
    """Thread-safe bounded FIFO queue with blocking get.

    Used for non-real-time stages where ordering matters.
    """

    def __init__(self, maxsize: int = 256):
        self._maxsize = max(1, maxsize)
        self._items: deque = deque(maxlen=self._maxsize)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._stats = PipelineStats()

    def put(self, item: Any) -> bool:
        """Put item. If full, drops oldest. Returns True on drop."""
        dropped = False
        with self._lock:
            if len(self._items) >= self._maxsize:
                dropped = True
                self._stats.frames_dropped += 1
            self._items.append(item)
            self._stats.frames_produced += 1
            self._not_empty.notify()
        return dropped

    def get(self, timeout: float = 0.1) -> Optional[Any]:
        """Get next item, blocking with timeout. Returns None if timeout."""
        with self._not_empty:
            if not self._items:
                self._not_empty.wait(timeout)
            if self._items:
                item = self._items.popleft()
                self._stats.frames_consumed += 1
                return item
            return None

    def get_nowait(self) -> Optional[Any]:
        """Get next item without waiting. Returns None if empty."""
        with self._lock:
            if self._items:
                self._stats.frames_consumed += 1
                return self._items.popleft()
            return None

    def stats(self) -> PipelineStats:
        with self._lock:
            return PipelineStats(
                frames_produced=self._stats.frames_produced,
                frames_consumed=self._stats.frames_consumed,
                frames_dropped=self._stats.frames_dropped,
                queue_max_len=self._stats.queue_max_len,
                total_wait_ms=self._stats.total_wait_ms,
            )

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class PipelineWorker(threading.Thread):
    """Base class for pipeline worker threads.

    Each worker reads from an input queue, processes, and writes to an output queue.
    """

    def __init__(
        self,
        name: str,
        input_queue: Optional[LatestValueQueue | BoundedFIFOQueue] = None,
        output_queue: Optional[LatestValueQueue | BoundedFIFOQueue] = None,
    ):
        super().__init__(daemon=True, name=name)
        self._input = input_queue
        self._output = output_queue
        self._running = False
        self._stats = PipelineStats()

    def stop(self) -> None:
        """Signal the worker to stop."""
        self._running = False

    def run(self) -> None:
        """Override in subclass."""
        pass

    def stats(self) -> PipelineStats:
        return self._stats
