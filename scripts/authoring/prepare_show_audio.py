"""Prepare one embedded soundtrack for Host playback and file-based lighting."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


def prepare_show_audio(video: Path, track: int = 0) -> Path:
    """Publish the selected audio stream as the show's single FLAC sidecar."""
    video = video.resolve(strict=True)
    siblings = list(video.parent.iterdir())
    videos = [p for p in siblings if p.suffix.lower() in {".mp4", ".mkv", ".mov"}]
    if videos != [video]:
        raise ValueError("Expected one Host-supported video in its show directory")
    if any(p.suffix.lower() in {".flac", ".wav", ".mp3"} for p in siblings):
        raise FileExistsError("Show directory already contains a playback soundtrack")
    if track < 0:
        raise ValueError("Audio track index must be nonnegative")
    output = video.with_suffix(".flac")
    with TemporaryDirectory(dir=video.parent) as staging:
        temporary = Path(staging) / output.name
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-xerror", "-copyts", "-start_at_zero",
                "-i", str(video), "-map", f"0:a:{track}", "-af", "aresample=async=1:first_pts=0",
                "-c:a", "flac", str(temporary),
            ],
            check=True,
        )
        # Publish only a finished track, without replacing a concurrent result.
        if os.name == "nt":
            temporary.rename(output)
        else:
            os.link(temporary, output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--track", type=int, default=0, help="Zero-based audio stream index")
    args = parser.parse_args()
    try:
        print(prepare_show_audio(args.video, args.track))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Soundtrack preparation failed: {error}\n")
