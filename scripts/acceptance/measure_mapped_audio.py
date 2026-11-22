"""Compare mapped strip codes for one Show with original and silent audio."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np

from light_engine.cli import _configure_engine_show
from light_engine.clock import OfflineRenderClock
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.models import AudioFeatures
from light_engine.outputs import NullOutput


def capture(args, muted):
    config = Config.get_instance(args.profile)
    engine = Engine(config, clock=OfflineRenderClock(config.get("system.output_fps")))
    _configure_engine_show(engine, str(args.show))
    engine.load_video(str(args.video))
    engine.load_audio(str(args.audio))
    stamps, codes, levels = [], [], []

    def record(frame):
        if frame.metadata.get("SAFE_STATE") or frame.timestamp + 1e-8 < args.start:
            return
        if frame.timestamp + 1e-8 >= args.end:
            return
        colors = [rgb for node in frame.digital_frames for strip in node.outputs for rgb in strip.pixels]
        stamps.append(frame.timestamp)
        levels.append(engine._latest_audio.rms)
        codes.append(np.rint(np.asarray(colors) * 255))

    output = NullOutput()
    output.send_frame = record
    engine._outputs = {"capture": output}
    if muted:
        engine._get_audio_features = lambda: AudioFeatures(
            timestamp=engine.timestamp, pcm_rms=0.0, silence=True)
    with patch("light_engine.engine.time.sleep", new=lambda _: None):
        engine.run(duration=args.end)
    return np.asarray(stamps), np.asarray(codes), np.asarray(levels)


def measure(args):
    t, original, rms = capture(args, False)
    other_t, silent, _ = capture(args, True)
    if t.size == 0 or not np.array_equal(t, other_t):
        raise ValueError("Comparison requires matching nonempty timelines")
    active_mean = original.mean(axis=(1, 2))
    silent_mean = silent.mean(axis=(1, 2))
    valid = silent_mean > 0
    gain = active_mean[valid] / silent_mean[valid]
    correlation = None
    if len(gain) > 1 and np.ptp(gain) > 0 and np.ptp(rms[valid]) > 0:
        correlation = float(np.corrcoef(rms[valid], gain)[0, 1])
    return {
        "frames": len(t), "groups": original.shape[1],
        "mean_channel_with_audio": float(original.mean()),
        "mean_channel_silent": float(silent.mean()),
        "changed_pixel_fraction": float(np.any(original != silent, axis=2).mean()),
        "decreased_pixel_fraction": float(np.any(original < silent, axis=2).mean()),
        "nonblack_frame_gain_range": [float(gain.min()), float(gain.max())] if len(gain) else None,
        "rms_gain_pearson": correlation,
        "frames_trace": [{"time": round(time, 6), "rms": float(level),
                          "mean_audio": float(active), "mean_silent": float(quiet)}
                         for time, level, active, quiet in zip(t, rms, active_mean, silent_mean)],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("show", "video", "audio", "profile", "output"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    args = parser.parse_args()
    if not 0 <= args.start < args.end:
        parser.error("Use a nonempty interval within the media timeline")
    args.output.write_text(json.dumps(measure(args), indent=2), encoding="utf-8")
