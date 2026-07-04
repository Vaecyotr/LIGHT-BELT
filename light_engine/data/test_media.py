"""Generate small, copyright-free test media files for end-to-end testing.

All media is generated programmatically. No copyright issues.
Files are temporary and not committed to version control.
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import wave
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def generate_test_wav(
    path: Optional[str] = None,
    duration: float = 5.0,
    sample_rate: int = 44100,
) -> str:
    """Generate a test WAV file with varied content.

    Contains: silence, low-freq sine, mid-freq sine, high-freq sine,
    drum-like bursts, and volume changes.

    Returns path to the generated file.
    """
    if path is None:
        path = os.path.join(tempfile.gettempdir(), "light_engine_test.wav")

    total_samples = int(duration * sample_rate)
    t = np.arange(total_samples, dtype=np.float32) / sample_rate
    audio = np.zeros(total_samples, dtype=np.float32)

    # 0-1s: silence
    # 1-2s: 80Hz bass sine
    mask = (t >= 1.0) & (t < 2.0)
    audio[mask] = 0.5 * np.sin(2 * np.pi * 80 * t[mask])

    # 2-3s: 1000Hz mid sine
    mask = (t >= 2.0) & (t < 3.0)
    audio[mask] = 0.3 * np.sin(2 * np.pi * 1000 * t[mask])

    # 3-4s: 8000Hz treble sine
    mask = (t >= 3.0) & (t < 4.0)
    audio[mask] = 0.2 * np.sin(2 * np.pi * 8000 * t[mask])

    # 4-5s: drum bursts (low frequency pulses)
    mask = (t >= 4.0) & (t < 5.0)
    burst_env = np.exp(-((t[mask] - np.floor(t[mask] * 4) / 4) / 0.02) ** 2)
    audio[mask] = 0.8 * burst_env * np.sin(2 * np.pi * 60 * t[mask])

    # Normalize
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9

    # Write WAV
    audio_int16 = (audio * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())

    return path


def generate_test_video(
    path: Optional[str] = None,
    duration: float = 6.0,
    fps: float = 30.0,
    width: int = 320,
    height: int = 240,
) -> str:
    """Generate a test MP4 video with varied content.

    Contains: red, green, blue frames, black borders, gradients,
    scene changes, and variable brightness.

    Returns path to the generated file.
    """
    if path is None:
        path = os.path.join(tempfile.gettempdir(), "light_engine_test.mp4")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(path, fourcc, fps, (width, height))
    total_frames = int(duration * fps)

    for i in range(total_frames):
        t = i / fps
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        if t < 1.0:
            # Red frame
            frame[:, :] = (0, 0, 255)
        elif t < 2.0:
            # Green frame
            frame[:, :] = (0, 255, 0)
        elif t < 3.0:
            # Blue frame
            frame[:, :] = (255, 0, 0)
        elif t < 4.0:
            # Color gradient
            for y in range(height):
                for x in range(width):
                    frame[y, x] = (
                        int(255 * y / height),  # B
                        int(255 * x / width),   # G
                        int(255 * (1 - y / height)),  # R
                    )
        elif t < 4.5:
            # Black borders (letterbox)
            frame[:, :] = (0, 255, 0)
            border = 40
            frame[:border, :] = 0
            frame[-border:, :] = 0
            frame[:, :border] = 0
            frame[:, -border:] = 0
        elif t < 5.5:
            # Variable brightness
            brightness = int(255 * (0.2 + 0.8 * (math.sin(t * 4) + 1) / 2))
            frame[:, :] = (brightness, brightness // 2, brightness // 4)
        else:
            # Scene changes: flash between colors
            segment = int((t - 5.5) * 4) % 4
            colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0), (255, 255, 255)]
            frame[:, :] = colors[segment]

        out.write(frame)

    out.release()
    return path


def cleanup_test_media(*paths: str) -> None:
    """Remove generated test media files."""
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass
