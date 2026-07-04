"""Null output for benchmarking - discards all frames."""

from light_engine.models import PixelFrame
from light_engine.outputs import LightOutput


class NullOutput(LightOutput):
    """Discards all frames. Used for performance benchmarking."""

    def open(self) -> None:
        self._open = True

    def send_frame(self, frame: PixelFrame) -> None:
        pass

    def close(self) -> None:
        self._open = False
