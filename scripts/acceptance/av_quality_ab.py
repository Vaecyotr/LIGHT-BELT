"""Deterministic physical-output A/B fixture; run --help for the three steps."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import wave
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

FPS = 30
SECONDS = 6
RATE = 48000


def fixture(folder: Path, overwrite: bool = False) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    targets = [folder / "input.avi", folder / "input.wav"]
    if not overwrite and any(path.exists() for path in targets):
        raise FileExistsError("Fixture input already exists; use a fresh folder or --overwrite-fixture")
    writer = cv2.VideoWriter(str(folder / "input.avi"), cv2.VideoWriter_fourcc(*"FFV1"), FPS, (320, 180))
    if not writer.isOpened():
        raise RuntimeError("FFV1 video writer unavailable")
    for i in range(FPS * SECONDS):
        t = i / FPS
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        if t < 3:
            frame[18:162] = (36, 16, 4)
            y = 100 + int(8 * np.sin(t * 2))
            cv2.line(frame, (0, y), (319, y + 8), (110, 60, 20), 4)
        else:
            frame[18:162] = (18, 55, 170)
            cv2.circle(frame, (160, 85), 30, (40, 170, 240), -1)
        if 1 <= t < 2:
            cv2.putText(frame, "SUBTITLE", (85, 150), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()
    t = np.arange(RATE * SECONDS) / RATE
    phase = np.mod(t, .5)
    kick = .55 * np.sin(2 * np.pi * 65 * t) * np.exp(-phase * 26) * ((t < 2) | (t >= 4))
    treble = .06 * np.sin(2 * np.pi * 6000 * t) * (t >= 1) * (t < 5)
    samples = np.int16(np.clip(kick + treble, -1, 1) * 32767)
    with wave.open(str(folder / "input.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(samples.tobytes())


def capture(folder: Path, root: Path, label: str) -> None:
    sys.path.insert(0, str(root.resolve()))
    from light_engine.clock import OfflineRenderClock
    from light_engine.config import Config
    from light_engine.engine import Engine
    from light_engine.outputs import NullOutput

    random.seed(42)
    np.random.seed(42)
    config = Config()
    engine = Engine(config, clock=OfflineRenderClock(FPS))
    engine.load_video(str((folder / "input.avi").resolve()))
    engine.load_audio(str((folder / "input.wav").resolve()))
    engine.set_effect("video_audio_fusion")
    output = NullOutput()
    frames = []
    trace = []
    def record(frame):
        if frame.metadata.get("SAFE_STATE"):
            return
        frames.append(frame)
        trace.append({"timestamp": frame.timestamp,
                      "audio": asdict(engine._latest_audio) if engine._latest_audio else None,
                      "music": asdict(engine._latest_music_control_state) if engine._latest_music_control_state else None,
                      "video": asdict(engine._latest_video) if engine._latest_video else None})
    output.send_frame = record
    engine._outputs = {"recording": output}
    with patch("light_engine.engine.time.sleep", new=lambda _: None):
        engine.run(max_frames=FPS * SECONDS - 1)
    if len(frames) != FPS * SECONDS - 1:
        raise RuntimeError(f"Expected {FPS * SECONDS - 1} media frames, received {len(frames)}")
    pixels = []
    for frame in frames:
        streams = [node.pixels for node in frame.digital_frames if node.pixels]
        streams += [out.pixels for node in frame.digital_frames for out in node.outputs if out.pixels]
        if not streams:
            raise RuntimeError("layout produced no mapped digital outputs")
        pixels.append(np.asarray(streams[0], dtype=np.float64))
    np.savez_compressed(folder / (label + ".npz"), pixels=np.asarray(pixels),
                        timestamps=np.asarray([f.timestamp for f in frames]))
    (folder / (label + "-trace.json")).write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(f"{label}: {len(frames)} frames, {len(pixels[0])} pixels, {root}")


def compare(folder: Path, first: str, second: str) -> None:
    with np.load(folder / (first + ".npz")) as a, np.load(folder / (second + ".npz")) as b:
        x, y, times = a["pixels"], b["pixels"], a["timestamps"]
        if x.shape != y.shape or not np.allclose(times, b["timestamps"]):
            raise ValueError("output frame sizes or timestamps do not match")
    video = cv2.VideoCapture(str(folder / "input.avi"))
    writer = cv2.VideoWriter(str(folder / "silent.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (640, 360))
    if not writer.isOpened():
        raise RuntimeError("MP4 video writer unavailable")
    for i in range(len(x)):
        video.set(cv2.CAP_PROP_POS_FRAMES, min(int(round(times[i] * FPS)), FPS * SECONDS - 1))
        ok, frame = video.read()
        if not ok:
            raise RuntimeError(f"cannot read input at frame {i}")
        canvas = np.zeros((360, 640, 3), dtype=np.uint8)
        canvas[:180, :320] = frame
        cv2.putText(canvas, "INPUT", (330, 35), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 2)
        for j, (name, pixels) in enumerate((("A", x[i]), ("B", y[i]))):
            row = np.rint(np.clip(pixels, 0, 1) * 255).astype(np.uint8)[None, :, ::-1]
            canvas[205 + j * 65:245 + j * 65, 120:620] = cv2.resize(row, (500, 40), interpolation=cv2.INTER_NEAREST)
            cv2.putText(canvas, name[:12], (5, 235 + j * 65), cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
        writer.write(canvas)
    writer.release()
    video.release()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(folder / "silent.mp4"), "-ss", str(times[0]), "-i", str(folder / "input.wav"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(folder / "comparison.mp4")], check=True)
    graph = np.full((400, 900, 3), 255, dtype=np.uint8)
    ymax = max(float(x.mean(axis=(1, 2)).max()), float(y.mean(axis=(1, 2)).max()), .001) * 1.1
    for tick in range(5):
        row = 340 - tick * 70
        cv2.line(graph, (85, row), (875, row), (210, 210, 210), 1)
        cv2.putText(graph, f"{ymax * tick / 4:.3f}", (5, row + 5), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 1)
    for tick in range(7):
        col = 85 + int(tick * 790 / 6)
        cv2.putText(graph, str(tick), (col, 360), cv2.FONT_HERSHEY_SIMPLEX, .4, (0, 0, 0), 1)
    metrics = {}
    for name, data, color in ((first, x, (220, 50, 30)), (second, y, (20, 60, 220))):
        lum = data.mean(axis=(1, 2))
        pts = np.array([(85 + int(t * 790 / SECONDS), int(340 - v * 280 / ymax)) for t, v in zip(times, lum)], dtype=np.int32)
        cv2.polylines(graph, [pts], False, color, 2)
        metrics[name] = {"mean_output": float(lum.mean()), "mean_absolute_frame_change": float(np.abs(np.diff(data, axis=0)).mean()), "max_output": float(data.max()), "segments": {}}
        for segment, start, end in (("dark_kicks", 0, 2), ("dark_sustained", 2, 3), ("bright_kicks", 4, 6)):
            selected = data[(times >= start) & (times < end)]
            quantized = np.rint(np.clip(selected, 0, 1) * 255).astype(np.uint8)
            metrics[name]["segments"][segment] = {"mean_output": float(selected.mean()), "mean_absolute_frame_change": float(np.abs(np.diff(selected, axis=0)).mean()), "black_pixel_fraction_8bit": float(np.all(quantized == 0, axis=2).mean()), "saturated_channel_fraction_8bit": float((quantized == 255).mean())}
    cv2.putText(graph, f"{first}: blue   {second}: red", (12, 24), cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 0, 0), 1)
    cv2.putText(graph, "Mean mapped RGB channel value vs time (seconds)", (12, 390), cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 0), 1)
    cv2.imwrite(str(folder / "trajectory.png"), graph)
    (folder / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("fixture", "capture", "compare"))
    parser.add_argument("--folder", type=Path, default=Path("tmp/av-quality"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--label", default="working")
    parser.add_argument("--first", default="baseline")
    parser.add_argument("--second", default="working")
    parser.add_argument("--overwrite-fixture", action="store_true", help="replace generated input.avi and input.wav")
    args = parser.parse_args()
    if args.action == "fixture":
        fixture(args.folder, args.overwrite_fixture)
    elif args.action == "capture":
        capture(args.folder, args.root, args.label)
    else:
        compare(args.folder, args.first, args.second)


if __name__ == "__main__":
    main()
