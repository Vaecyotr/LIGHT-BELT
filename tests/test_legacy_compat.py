"""Compatibility tests for Phase 0-2 outputs during RoutedFrame transition."""

from __future__ import annotations

from light_engine.mapping.physical import PhysicalFrame
from light_engine.models import PixelFrame, RoutedFrame
from light_engine.outputs import LightOutput, send_all


class RecordingOutput(LightOutput):
    def __init__(self) -> None:
        super().__init__()
        self.frames: list[PixelFrame] = []

    def open(self) -> None:
        self._open = True

    def send_frame(self, frame: PixelFrame) -> None:
        self.frames.append(frame)

    def close(self) -> None:
        self._open = False


def test_send_all_unwraps_routed_frame_for_legacy_outputs() -> None:
    logical = PixelFrame(timestamp=0.0, sequence=11)
    routed = RoutedFrame(
        logical=logical,
        physical=PhysicalFrame(sequence=11, timestamp=0.0),
    )
    output = RecordingOutput()
    output.open()

    send_all({"legacy": output}, routed)

    assert output.frames == [logical]
    assert output.health().frames_sent == 1


def test_send_all_still_accepts_plain_pixel_frame() -> None:
    logical = PixelFrame(timestamp=0.0, sequence=12)
    output = RecordingOutput()
    output.open()

    send_all({"legacy": output}, logical)

    assert output.frames == [logical]
    assert output.health().frames_sent == 1
