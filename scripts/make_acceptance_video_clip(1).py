"""Build the deterministic local video clip + beat wav for Part 3 acceptance.

The clip content matches `show-video(1).yaml` (64 s):
  0-8s solid red, 8-16s solid green, 16-24s solid blue,
  24-30s red field with a white bar sweeping left->right,
  30-38s near-black, 38-50s four 3s bright hard cuts,
  50-60s solid white (fusion video leg), 60-64s black.

The wav carries 8 low-frequency thumps (~150 Hz, audible on phone speakers and
still inside the WLED bass bins) and drives the `video_audio_fusion` audio leg
through the formal speaker -> microphone -> WLED Audio Sync V2 chain, or as a
deterministic `--audio` input for the fusion A/B contrast only.

`acceptance-silence.wav` is a 10 s digital-silence wav: pass it as Part 1's
`--audio` so `cmd_run` skips its synthetic data source and the audio path is
pinned to defined silence (the live WLED source stays authoritative in Part 2
only when this file is used as designed — silence).

This is a stimulus builder; it records no acceptance evidence.
"""

from __future__ import annotations

import argparse
import math
import struct
import wave
from pathlib import Path

import cv2
import numpy

WIDTH = 640
HEIGHT = 360
FPS = 30
DURATION = 64.0
SAMPLE_RATE = 44100


def _segment_color(local_time: float) -> tuple[int, int, int]:
    if local_time < 8.0:
        base = (0, 0, 255)  # BGR red
    elif local_time < 16.0:
        base = (0, 255, 0)
    elif local_time < 24.0:
        base = (255, 0, 0)
    elif local_time < 30.0:
        base = (0, 0, 255)
    elif local_time < 38.0:
        base = (10, 10, 10)
    elif local_time < 50.0:
        cuts = [(255, 0, 255), (0, 255, 255), (0, 255, 0), (255, 255, 255)]
        base = cuts[int((local_time - 38.0) // 3.0) % len(cuts)]
    elif local_time < 60.0:
        base = (255, 255, 255)
    else:
        base = (0, 0, 0)
    return base


def _frame(timestamp: float) -> numpy.ndarray:
    frame = numpy.full((HEIGHT, WIDTH, 3), _segment_color(timestamp), dtype=numpy.uint8)
    if 24.0 <= timestamp < 30.0:
        progress = (timestamp - 24.0) / 6.0
        bar_x = int(progress * (WIDTH - 41))
        frame[:, bar_x:bar_x + 40] = (255, 255, 255)
    return frame


def build_clip(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        FPS,
        (WIDTH, HEIGHT),
    )
    if not writer.isOpened():
        raise RuntimeError(f"cannot open video writer for {path}")
    total = int(DURATION * FPS)
    for index in range(total):
        writer.write(_frame(index / FPS))
    writer.release()


def build_beats(path: Path) -> None:
    duration = 10.0
    total = int(duration * SAMPLE_RATE)
    samples = bytearray(total * 2)
    for beat in range(8):
        start = int((1.0 + beat * 1.0) * SAMPLE_RATE)
        length = int(0.3 * SAMPLE_RATE)
        for index in range(length):
            envelope = 1.0 - index / length
            value = 0.85 * envelope * math.sin(2.0 * math.pi * 150.0 * index / SAMPLE_RATE)
            offset = (start + index) * 2
            struct.pack_into("<h", samples, offset, int(value * 32767))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes(samples))


def build_silence(path: Path, duration: float = 10.0) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(bytes(int(duration * SAMPLE_RATE) * 2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default="artifacts/runs/single-strip-acceptance-v1")
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_path = out_dir / "acceptance-clip.mp4"
    beats_path = out_dir / "acceptance-beats.wav"
    silence_path = out_dir / "acceptance-silence.wav"
    build_clip(clip_path)
    build_beats(beats_path)
    build_silence(silence_path)
    print(f"wrote {clip_path}")
    print(f"wrote {beats_path}")
    print(f"wrote {silence_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
