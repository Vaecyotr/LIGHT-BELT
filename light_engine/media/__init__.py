"""Media I/O: video and audio file reading, frame sampling, audio windowing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from light_engine.media.mpv_adapter import MpvIPCAdapter, MpvIPCError, MpvState

logger = logging.getLogger(__name__)


def _cv2():
    import cv2

    return cv2


def _soundfile():
    import soundfile as sf

    return sf

__all__ = [
    "AudioReader",
    "MpvIPCAdapter",
    "MpvIPCError",
    "MpvState",
    "VideoReader",
]


class VideoReader:
    """Read video files and provide frame sampling."""

    def __init__(self, path: str):
        if not Path(path).exists():
            raise FileNotFoundError(f"Video file not found: {path}")
        self._path = path
        self._cap: Optional[object] = None
        self._fps: float = 30.0
        self._total_frames: int = 0
        self._width: int = 0
        self._height: int = 0
        self._last_pts: float | None = None
        self._last_image: np.ndarray | None = None
        self._previous_pts: float | None = None
        self._previous_image: np.ndarray | None = None
        self._irregular_pts = False

    def open(self) -> VideoReader:
        if self._cap is not None and self._cap.isOpened():
            return self
        cv2 = _cv2()
        self._cap = cv2.VideoCapture(self._path)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open video: {self._path}")
        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(
            "Video opened: %s (%dx%d, %.1f fps, %d frames)",
            self._path, self._width, self._height, self._fps, self._total_frames,
        )
        return self

    @property
    def fps(self) -> float:
        return self._fps

    @property
    def total_frames(self) -> int:
        return self._total_frames

    @property
    def duration(self) -> float:
        return self._total_frames / max(0.001, self._fps)

    @property
    def resolution(self) -> Tuple[int, int]:
        return (self._width, self._height)

    def read_frame(self, timestamp: Optional[float] = None) -> Optional[np.ndarray]:
        """Read the next frame, or seek to timestamp.

        Returns BGR frame as numpy array, or None if at end.
        """
        if self._cap is None:
            return None
        if timestamp is None:
            return self._last_image if self._decode_next() else None
        if timestamp >= self.duration:
            return None
        target = max(0.0, timestamp) + 1e-8
        if self._previous_pts is not None and self._previous_pts <= target < self._last_pts:
            return self._previous_image
        period = 1.0 / max(self.fps, 0.001)
        if self._last_pts is not None and not self._irregular_pts:
            steps = int((target - self._last_pts) / period)
            if 2 <= steps <= 12:
                self._skip_regular_frames(steps, period)
        if self._last_pts is None or not 0 <= target - self._last_pts <= 12 * period:
            # Some OpenCV backends convert millisecond seeks to nominal frame
            # numbers. Decode from an earlier position if that lands too late.
            start = min(target, max(0.0, self.duration - period))
            backoff = period
            while True:
                if not self.seek(start):
                    return None
                if self._decode_next() and self._last_pts <= target:
                    break
                if start == 0:
                    return self._last_image
                start = max(0.0, start - backoff)
                backoff *= 2
        while target - self._last_pts > 1e-7:
            if not self._decode_next():
                # The last picture remains on screen until the video ends.
                return self._last_image if target >= self.duration - period else None
            if self._last_pts > target:
                return self._previous_image
        return self._last_image

    def _skip_regular_frames(self, steps: int, period: float) -> None:
        """Skip BGR conversion only while every intermediate PTS matches the grid."""
        cv2 = _cv2()
        start = self._last_pts
        self._previous_pts = self._last_pts = None
        self._previous_image = self._last_image = None
        for step in range(1, steps + 1):
            if not self._cap.grab():
                return
            pts = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            if abs(pts - (start + step * period)) > 1e-7:
                self._irregular_pts = True
                return
        ok, frame = self._cap.retrieve()
        if ok:
            self._last_pts, self._last_image = pts, frame

    def _decode_next(self) -> bool:
        ok, frame = self._cap.read()
        if not ok:
            return False
        cv2 = _cv2()
        pts = self._cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        if self._last_pts is not None and pts <= self._last_pts:
            # Backends without PTS support can still supply frame position.
            pts = (self._cap.get(cv2.CAP_PROP_POS_FRAMES) - 1) / max(self.fps, 0.001)
        self._previous_pts, self._previous_image = self._last_pts, self._last_image
        self._last_pts, self._last_image = pts, frame
        return True

    def seek(self, timestamp: float) -> bool:
        """Seek to a specific timestamp in seconds."""
        if self._cap is None:
            return False
        self._previous_pts = self._last_pts = None
        self._previous_image = self._last_image = None
        cv2 = _cv2()
        return self._cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None
        self._previous_pts = self._last_pts = None
        self._previous_image = self._last_image = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()


class AudioReader:
    """Read audio files and provide windowed sample access."""

    def __init__(self, path: str):
        if not Path(path).exists():
            raise FileNotFoundError(f"Audio file not found: {path}")
        self._path = path
        self._file = None
        self._block = np.empty(0, dtype=np.float32)
        self._block_start = 0
        self._sample_rate: int = 44100
        self._channels: int = 1
        self._duration: float = 0.0

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def channels(self) -> int:
        return self._channels

    def open(self) -> AudioReader:
        if self._file is not None:
            return self
        try:
            sf = _soundfile()
            self._file = sf.SoundFile(self._path)
        except Exception as e:
            raise RuntimeError(f"Cannot open audio: {self._path}") from e
        self._sample_rate = self._file.samplerate
        self._channels = self._file.channels
        self._duration = len(self._file) / self._sample_rate
        logger.info(
            "Audio opened: %s (%.1f Hz, %d ch, %.1f s)",
            self._path, self._sample_rate, self._channels, self._duration,
        )
        return self

    def get_window(
        self, center_time: float, window_size: float
    ) -> Optional[np.ndarray]:
        """Get audio samples centered at center_time with given window size.

        Args:
            center_time: Center time in seconds.
            window_size: Window size in seconds.

        Returns:
            1D numpy array of samples, or None if outside audio range.
        """
        half = window_size / 2
        start = int((center_time - half) * self._sample_rate)
        end = int((center_time + half) * self._sample_rate)
        return self._read_samples(max(0, start), end)

    def get_window_at(
        self, start_time: float, window_size: float
    ) -> Optional[np.ndarray]:
        """Get audio samples starting at start_time.

        Uses round() for start and a fixed integer window_sample count
        to guarantee consistent window length for every call except
        the final truncated window at end-of-file.
        """
        window_samples = round(window_size * self._sample_rate)
        start = max(0, round(start_time * self._sample_rate))
        return self._read_samples(start, start + window_samples)

    def _read_samples(self, start: int, end: int) -> Optional[np.ndarray]:
        if self._file is None:
            return None
        end = min(end, len(self._file))
        if start >= end:
            return None
        if start < self._block_start or end > self._block_start + len(self._block):
            self._file.seek(start)
            # Amortize compressed-file seeks across overlapping FFT windows.
            block = self._file.read(max(self._sample_rate, end - start), dtype="float32")
            self._block = block.mean(axis=1) if block.ndim == 2 else block
            self._block_start = start
        offset = start - self._block_start
        return self._block[offset:offset + end - start].copy()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
        self._block = np.empty(0, dtype=np.float32)

    def __enter__(self):
        return self.open()

    def __exit__(self, *args):
        self.close()
