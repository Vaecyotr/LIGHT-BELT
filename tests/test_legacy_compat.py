"""Phase 6 removal tests for the RoutedFrame transition adapter."""

from __future__ import annotations

import light_engine.models as models
from light_engine.mapping.physical import PhysicalFrame
from light_engine.outputs import LightOutput, send_all


class RecordingOutput(LightOutput):
    def __init__(self) -> None:
        super().__init__()
        self.frames: list[PhysicalFrame] = []

    def open(self) -> None:
        self._open = True

    def send_frame(self, frame: PhysicalFrame) -> None:
        self.frames.append(frame)
        self._health.logical_frames_sent += 1

    def close(self) -> None:
        self._open = False


def test_routed_frame_model_is_removed() -> None:
    assert not hasattr(models, "RoutedFrame")


def test_send_all_passes_physical_frame_directly() -> None:
    physical = PhysicalFrame(sequence=11, timestamp=0.0)
    output = RecordingOutput()
    output.open()

    send_all({"physical": output}, physical)

    assert output.frames == [physical]
    assert output.health().logical_frames_submitted == 1
    assert output.health().logical_frames_sent == 1
