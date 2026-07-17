"""Null output for benchmarking - discards all frames."""

from light_engine.mapping.physical import PhysicalFrame
from light_engine.outputs import LightOutput


class NullOutput(LightOutput):
    """Discards all frames. Used for performance benchmarking."""

    def open(self) -> None:
        self._open = True

    def send_frame(self, frame: PhysicalFrame) -> None:
        self._health.logical_frames_sent += 1
        self._health.mark_success()

    def close(self) -> None:
        self._open = False
