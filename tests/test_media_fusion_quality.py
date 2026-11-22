"""Soundtrack preparation, media-clock continuity and final strip response."""

from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import cv2
import pytest
import soundfile as sf

from host_services.shows_loader import load_shows
from light_engine.clock import MpvIPCClock
from light_engine.config import Config
from light_engine.effects import create_effect
from light_engine.engine import Engine
from light_engine.media import AudioReader, VideoReader
from light_engine.media.mpv_adapter import MpvState
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures
from light_engine.outputs import NullOutput
from scripts.authoring.prepare_show_audio import prepare_show_audio


def _strips():
    return {"strip_defs": [{"id": "wall", "pixel_count": 12, "video_zone": "average"}]}


def test_treble_replay_preserves_video_hue_and_pixel_sequence():
    effect = create_effect("video_audio_fusion")

    def render():
        effect.reset()
        frames = []
        for i in range(30):
            t = i / 30
            color = VideoFeatures(timestamp=t, average_rgb=(0.0, 0.0, 0.8),
                                  dominant_rgb=(0.0, 0.0, 0.8), brightness=0.3)
            audio = AudioFeatures(timestamp=t, rms=0.5, treble=1.0, silence=False)
            ctx = EffectContext(timestamp=t, delta_time=1/30, video_features=color,
                                audio_features=audio, mode_parameters=_strips())
            frames.append(effect.process(ctx).strips[0].to_uint8())
        return np.array(frames)
    first, replay = render(), render()
    assert np.array_equal(first, replay)
    assert first[:, :, :2].max() == 0
    assert np.ptp(first[-1, :, 2]) > 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="offline authoring requires FFmpeg")
def test_delayed_embedded_soundtrack_drives_mapped_frames_across_paused_rewind(tmp_path, monkeypatch):
    monkeypatch.setattr("light_engine.engine.time.sleep", lambda _: None)
    folder = tmp_path / "ocean"
    folder.mkdir()
    video = folder / "ocean.mkv"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=2",
        "-itsoffset", "0.6", "-f", "lavfi", "-i", "sine=frequency=80:duration=1",
        "-c:v", "mpeg4", "-c:a", "flac", str(video),
    ], check=True)
    track = prepare_show_audio(video)
    data, rate = sf.read(track)
    first_sample = np.flatnonzero(np.abs(data) > 0.01)[0]
    assert first_sample / rate == pytest.approx(0.6, abs=0.01)
    with pytest.raises(FileExistsError):
        prepare_show_audio(video)
    show, = load_shows(tmp_path, tmp_path / "no-manifest")
    assert show["audio_path"] == str(track)

    positions = [0.1, 0.7, 0.7, 0.1, 0.1, 0.1334]
    states = iter(MpvState(t, paused, False) for t, paused in
                  zip(positions, [False, False, True, True, True, False]))
    clock = MpvIPCClock("fixture", adapter=SimpleNamespace(read_state=lambda: next(states)))
    engine = Engine(Config(), clock=clock)
    engine.load_video(show["media_path"])
    engine.load_audio(show["audio_path"])
    engine.set_effect("video_audio_fusion")
    output = NullOutput()
    frames = []
    output.send_frame = frames.append
    engine._outputs = {"recording": output}
    engine.run(max_frames=5)

    def blue(frame):
        return np.mean([pixel[2] for strip in frame.digital_frames for pixel in strip.pixels])
    assert frames[0].metadata["silent"] and frames[3].metadata["silent"]
    assert not frames[1].metadata["silent"] and blue(frames[1]) > blue(frames[0])
    for a, b in [(1, 2), (0, 3), (3, 4)]:
        assert [s.pixels for s in frames[a].digital_frames] == [s.pixels for s in frames[b].digital_frames]
    assert [frame.sequence for frame in frames] == list(range(1, 7))
    assert engine.diagnostics()["audio_source"]["kind"] == "file"


def test_compressed_multichannel_windows_survive_cache_boundaries_and_backward_seek(tmp_path):
    path = tmp_path / "stereo.flac"
    rng = np.random.default_rng(26)
    rate = 8000
    sf.write(path, rng.uniform(-0.8, 0.8, (3 * rate, 2)), rate)
    expected = sf.read(path, dtype="float32")[0].mean(axis=1)
    with AudioReader(str(path)) as reader:
        assert reader.channels == 2
        for t in [0, 0.98, 2.99, 0.4]:
            chunk = reader.get_window_at(t, 0.05)
            start = round(t * rate)
            np.testing.assert_array_equal(chunk, expected[start:start + 400])
            chunk.fill(0)
        np.testing.assert_array_equal(reader.get_window(0, 0.05), expected[:200])
        assert reader.get_window_at(3, 0.05) is None


def test_video_sampling_matches_source_frames_for_forward_seek_rewind_and_eof(tmp_path):
    path = tmp_path / "levels.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"FFV1"), 30, (80, 60))
    if not writer.isOpened():
        pytest.skip("OpenCV FFV1 encoder unavailable")
    try:
        for i in range(90):
            writer.write(np.full((60, 80, 3), i, dtype=np.uint8))
    finally:
        writer.release()
    with VideoReader(str(path)) as reader:
        for i in (0, 3, 6, 6, 65, 74, 13, 16):
            assert (reader.read_frame(i / 30) == i).all()
        assert (reader.read_frame(3 - 1e-10) == 89).all()
        assert reader.read_frame(3) is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="VFR fixture requires FFmpeg")
def test_variable_frame_intervals_hold_the_presented_picture_between_timestamps(tmp_path):
    path = tmp_path / "vfr.mkv"
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
        "testsrc2=size=96x64:rate=10:duration=2", "-vf",
        r"select=gte(t\,1)+not(mod(n\,2))", "-fps_mode", "vfr", "-c:v", "ffv1", str(path),
    ], check=True)
    with VideoReader(str(path)) as sequential:
        frames = [sequential.read_frame() for _ in range(15)]
    pts = [i / 10 for i in range(20) if i >= 10 or i % 2 == 0]
    with VideoReader(str(path)) as sampled:
        for t in (0.1, 0.19, 0.2, 0.61, 1.13, 1.35, 1.89, 1.99, 0.31, 0.8):
            index = max(i for i, start in enumerate(pts) if start <= t)
            np.testing.assert_array_equal(sampled.read_frame(t), frames[index])


def test_mpv_late_poll_preserves_history_and_forward_seek_resets_it(monkeypatch):
    wall = 0.0
    positions = iter([0.1, 0.2, 0.3, 5.0, 5.1])

    def read_state():
        nonlocal wall
        wall += 0.1
        return MpvState(next(positions), False, False)

    monkeypatch.setattr("light_engine.engine.time",
                        SimpleNamespace(perf_counter=lambda: wall, sleep=lambda _: None))
    clock = MpvIPCClock("fixture", adapter=SimpleNamespace(read_state=read_state))
    engine = Engine(Config(), clock=clock)
    engine.use_synthetic()
    engine.set_effect("video_audio_fusion")
    engine._outputs = {"memory": NullOutput()}
    resets = []
    reset = engine._music_control_analyzer.reset

    def record_reset():
        resets.append(clock.now())
        reset()

    monkeypatch.setattr(engine._music_control_analyzer, "reset", record_reset)
    engine.run(max_frames=4)
    assert resets == [0.0, 5.0]
