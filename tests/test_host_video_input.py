"""Host video input contracts at the Engine and CLI boundaries."""

from __future__ import annotations

from argparse import Namespace

import cv2
import numpy as np
import pytest

from light_engine.cli import cmd_export, cmd_run, cmd_simulator
from light_engine.clock import Clock
from light_engine.config import Config
from light_engine.engine import Engine
import light_engine.engine as engine_module
from light_engine.outputs import NullOutput


class PausedSeekClock(Clock):
    def __init__(self, positions: list[float], paused: list[bool]):
        self._positions = positions
        self._paused_values = paused
        self._position = 0.0
        self._index = -1
        self._is_paused = False

    def now(self) -> float:
        return self._position

    def tick(self) -> float:
        previous = self._position
        self._index += 1
        self._position = self._positions[self._index]
        self._is_paused = self._paused_values[self._index]
        return self._position - previous

    @property
    def paused(self) -> bool:
        return self._is_paused


class RecordingOutput(NullOutput):
    def __init__(self):
        super().__init__()
        self.frames = []

    def send_frame(self, frame):
        self.frames.append(frame)


def _write_color_video(path, fps=30.0, frame_count=30):
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (160, 90)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV mp4v encoder is unavailable")
    try:
        for index in range(frame_count):
            frame = np.zeros((90, 160, 3), dtype=np.uint8)
            if index >= frame_count // 2:
                frame[:, :, 1] = 255
            else:
                frame[:, :, 2] = 255
            writer.write(frame)
    finally:
        writer.release()


def test_real_video_drives_output_on_paused_first_frame_and_after_seek(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
    video_path = tmp_path / "red-then-green.mp4"
    _write_color_video(video_path)

    Config.reset()
    config = Config()
    config._data["system"]["video_analysis_fps"] = 30.0
    config._data["system"]["smoothing"]["max_brightness"] = 1.0
    clock = PausedSeekClock(
        [0.0, 1 / 30, 0.5, 0.5 + 1 / 30], [True, False, True, False]
    )
    engine = Engine(config, clock=clock)
    engine.load_video(str(video_path))
    engine.set_effect("video_audio_fusion")
    output = RecordingOutput()
    output.open()
    engine._outputs = {"recording": output}

    engine.run(max_frames=3)

    authored = [frame for frame in output.frames if not frame.metadata.get("SAFE_STATE")]
    assert len(authored) == 3
    pixels = [frame.digital_frames[0].pixels[0] for frame in authored]
    assert pixels[0][0] > pixels[0][1]
    assert pixels[-1][1] > pixels[-1][0]
    assert engine._latest_video is not None
    assert engine._latest_video.average_rgb[1] > engine._latest_video.average_rgb[0]


def test_long_video_is_sampled_at_requested_position_into_light_output(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
    video_path = tmp_path / "ten-seconds.mp4"
    _write_color_video(video_path, frame_count=300)

    Config.reset()
    config = Config()
    config._data["system"]["video_analysis_fps"] = 30.0
    config._data["system"]["smoothing"]["max_brightness"] = 1.0
    clock = PausedSeekClock([9.0, 9.0 + 1 / 30], [False, False])
    engine = Engine(config, clock=clock)
    engine.load_video(str(video_path))
    engine.set_effect("video_audio_fusion")
    output = RecordingOutput()
    output.open()
    engine._outputs = {"recording": output}

    engine.run(max_frames=1)

    authored = [frame for frame in output.frames if not frame.metadata.get("SAFE_STATE")]
    assert engine._video_reader is not None
    assert engine._video_reader.duration == pytest.approx(10.0, abs=0.1)
    assert engine._latest_video is not None
    assert engine._latest_video.timestamp == pytest.approx(9.0)
    assert engine._latest_video.average_rgb[1] > engine._latest_video.average_rgb[0]
    assert authored[0].digital_frames[0].pixels[0][1] > authored[0].digital_frames[0].pixels[0][0]


def test_short_video_eof_clears_video_features_but_audio_continues(
    tmp_path, monkeypatch
):
    import soundfile as sf

    monkeypatch.setattr(engine_module.time, "sleep", lambda _seconds: None)
    video_path = tmp_path / "short.mp4"
    audio_path = tmp_path / "long.wav"
    _write_color_video(video_path, frame_count=2)
    sample_rate = 44100
    sf.write(audio_path, np.zeros(sample_rate // 2, dtype=np.float32), sample_rate)

    Config.reset()
    config = Config()
    config._data["system"]["video_analysis_fps"] = 10.0
    engine = Engine(config)
    engine.load_video(str(video_path))
    engine.load_audio(str(audio_path))
    engine.set_effect("video_audio_fusion")
    output = RecordingOutput()
    output.open()
    engine._outputs = {"recording": output}

    engine.run()

    assert engine._video_reader is not None
    assert engine._audio_reader is not None
    assert engine._video_reader.duration < engine._audio_reader.duration
    assert engine.frame_count >= 12
    assert engine._latest_video is None


@pytest.mark.parametrize(
    "command",
    [cmd_run, cmd_simulator, cmd_export],
    ids=["run", "simulator", "export"],
)
def test_cli_reports_unreadable_video_and_does_not_select_synthetic(
    command, tmp_path, capsys
):
    bad_video = tmp_path / "not-a-video.mp4"
    bad_video.write_text("not an encoded video", encoding="utf-8")

    Config.reset()
    engine = Engine(Config())
    with pytest.raises(RuntimeError, match="Cannot open video"):
        engine.load_video(str(bad_video))
    assert "Video input failed" in engine.diagnostics()["last_error"]

    result = command(
        Namespace(
            config=None,
            clock="internal",
            video=str(bad_video),
            audio=None,
            show=None,
            effect="video_audio_fusion",
            duration=None,
            max_frames=1,
            seed=42,
            output=str(tmp_path / "lighting.jsonl"),
        )
    )

    assert result == 1
    error = capsys.readouterr().err.lower()
    assert "video" in error
    assert "synthetic" not in error
