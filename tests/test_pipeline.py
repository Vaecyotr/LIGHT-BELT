"""Tests for producer-consumer pipeline with bounded queues."""

import threading
import time
from light_engine.pipeline import LatestValueQueue, BoundedFIFOQueue


class TestLatestValueQueue:
    def test_put_get(self):
        q = LatestValueQueue(maxsize=4)
        q.put("a")
        q.put("b")
        assert q.get() == "b"  # Latest only
        assert q.get() is None  # Drained

    def test_drops_oldest_when_full(self):
        q = LatestValueQueue(maxsize=2)
        assert q.put("a") is False  # No drop
        assert q.put("b") is False
        assert q.put("c") is True   # Dropped "a"
        assert q.get() == "c"

    def test_get_all(self):
        q = LatestValueQueue(maxsize=4)
        for x in range(3):
            q.put(x)
        items = q.get_all()
        assert items == [0, 1, 2]
        assert q.get() is None

    def test_thread_safety(self):
        q = LatestValueQueue(maxsize=8)
        errors = []
        def producer():
            try:
                for i in range(100):
                    q.put(i)
            except Exception as e:
                errors.append(e)
        def consumer():
            try:
                for _ in range(20):
                    q.get()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)
        threads = [threading.Thread(target=producer) for _ in range(4)]
        threads += [threading.Thread(target=consumer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)
        assert len(errors) == 0

    def test_stats(self):
        q = LatestValueQueue(maxsize=2)
        q.put("a")
        q.put("b")
        q.put("c")
        s = q.stats()
        assert s.frames_produced == 3
        assert s.frames_dropped == 1


class TestBoundedFIFOQueue:
    def test_fifo_order(self):
        q = BoundedFIFOQueue(maxsize=4)
        q.put(1)
        q.put(2)
        q.put(3)
        assert q.get_nowait() == 1
        assert q.get_nowait() == 2
        assert q.get_nowait() == 3

    def test_drops_oldest_when_full(self):
        q = BoundedFIFOQueue(maxsize=2)
        q.put(1)
        q.put(2)
        dropped = q.put(3)
        assert dropped is True
        assert q.get_nowait() == 2  # 1 was dropped

    def test_get_blocking(self):
        q = BoundedFIFOQueue(maxsize=4)
        def delayed_put():
            time.sleep(0.05)
            q.put(42)
        threading.Thread(target=delayed_put, daemon=True).start()
        item = q.get(timeout=1.0)
        assert item == 42
