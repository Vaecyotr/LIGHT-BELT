"""Run against a checkout: python tests/audio_ab_probe.py --root PATH."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--window-anchor", choices=("forward", "center"), default="forward",
                        help="continuous fixtures: begin at frame time or 25 ms before it")
    args = parser.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
from light_engine.analysis.audio import AudioAnalyzer
from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.config import Config
from light_engine.media import AudioReader


def run(kind):
    sr, hop, size = 44100, 0.025, 2205
    t = np.arange(size) / sr
    rng = np.random.default_rng(42)
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    states, beats = [], 0
    for i in range(320):
        now = i * hop
        if kind == "noise":
            samples = rng.normal(0, .02, size)
        elif kind in ("strong_drums", "weak_drums"):
            amplitude = .3 if kind == "strong_drums" else .003
            samples = amplitude * (np.exp(-t * 55) if i % 20 == 0 else np.zeros_like(t)) * np.sin(2 * np.pi * 80 * t)
        else:
            amplitude = .1
            if kind == "gain_drop" and now >= 4:
                amplitude = .02
            if kind == "crescendo":
                amplitude = .002 + .098 * now / 8
            samples = amplitude * np.sin(2 * np.pi * 73 * (t + now))
        features = audio.analyze(samples.astype(np.float32), now, sr)
        beats += features.beat
        states.append(music.update(features))
    warmed = [s for s in states if s.timestamp >= 2]
    drift = [s for s in states if s.timestamp >= 6]
    return {"beat_count": beats, "tempo": states[-1].tempo_bpm,
            "confidence": states[-1].tempo_confidence,
            "max_transient_after_2s": max(s.transient for s in warmed),
            "max_transient_after_6s": max(s.transient for s in drift),
            "max_bass_pulse_after_6s": max(s.bass_pulse for s in drift),
            "max_abs_trend_after_6s": max(abs(s.energy_trend) for s in drift),
            "mean_trend_after_2s": float(np.mean([s.energy_trend for s in warmed]))}


def run_wav(name):
    path = Path(__file__).resolve().parent / "fixtures/audio/show_orchestration_v1" / name
    reader = AudioReader(str(path)).open()
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    states = []
    try:
        for now in np.arange(0, reader.duration, 1 / 60):
            samples = reader.get_window_at(float(now), 0.05)
            if samples is not None:
                states.append(music.update(audio.analyze(samples, float(now), reader.sample_rate)))
    finally:
        reader.close()
    warm = [s for s in states if s.timestamp >= 4]
    return {"median_tempo": float(np.median([s.tempo_bpm for s in warm])),
            "mean_confidence": float(np.mean([s.tempo_confidence for s in warm])),
            "max_transient": max(s.transient for s in warm),
            "mean_trend": float(np.mean([s.energy_trend for s in warm]))}


def continuous_fixture(name):
    """Event times mark the starts of individual pulses."""
    sr, seconds = 44100, 8
    t = np.arange(sr * seconds) / sr
    labels = np.arange(.5, 7.6, .5).tolist()
    if name == "syncopated":
        labels = [0.5, .875, 1.5, 1.875, 2.5, 2.875, 3.5, 3.875,
                  4.5, 4.875, 5.5, 5.875, 6.5, 6.875, 7.5]
    elif name == "free_rhythm":
        labels = [.47, .91, 1.54, 2.25, 2.61, 3.37, 3.91, 4.68, 5.02, 5.64, 6.39, 7.24]
    elif name in ("noise_only", "sustained_vowel"):
        labels = []
    if name == "noise_only":
        samples = np.random.default_rng(42).normal(0, .025, len(t))
    elif name == "sustained_vowel":
        # Voiced negative control: a sustained vowel with pitch vibrato and
        # slow formant movement, no annotated percussion or underlying beat.
        pitch = 155 + 5 * np.sin(2 * np.pi * 4.7 * t)
        phase = 2 * np.pi * np.cumsum(pitch) / sr
        samples = np.zeros_like(t)
        for harmonic in range(1, 24):
            frequency = harmonic * pitch
            first = np.exp(-0.5 * ((frequency - 680 - 70 * np.sin(t)) / 110) ** 2)
            second = np.exp(-0.5 * ((frequency - 1350) / 160) ** 2)
            samples += (first + 0.6 * second) * np.sin(harmonic * phase) / harmonic
        samples *= 0.18 * np.minimum(1, t / 0.3)
    else:
        samples = np.zeros_like(t)
        if name == "melody_weak_drums":
            samples += .05 * np.sin(2 * np.pi * 440 * t)
        amplitude = .004 if name in ("weak_drums", "melody_weak_drums") else .3
        for onset in labels:
            start = round(onset * sr)
            n = min(round(.12 * sr), len(t) - start)
            local = np.arange(n) / sr
            samples[start:start+n] += amplitude * np.sin(2 * np.pi * 80 * local) * np.exp(-local * 35)
    return samples.astype(np.float32), labels


def run_continuous(name, window_anchor="center"):
    sr, fps, size = 44100, 30, 2205
    samples, labels = continuous_fixture(name)
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    detected, states = [], []
    for frame in range(240):
        now = frame / fps
        window_start = max(0.0, now - .025) if window_anchor == "center" else now
        start = round(window_start * sr)
        window = samples[start:start + size]
        if len(window) < size:
            window = np.pad(window, (0, size - len(window)))
        features = audio.analyze(window, now, sr)
        if features.beat:
            detected.append(now)
        states.append(music.update(features))
    remaining = labels.copy()
    errors = []
    for event in detected:
        candidates = [(abs(event - target), target) for target in remaining if abs(event - target) <= .050001]
        if candidates:
            _, target = min(candidates)
            remaining.remove(target)
            errors.append(event - target)
    warm = [state for state in states if state.timestamp >= 4]
    return {"labels": len(labels), "detections": len(detected), "matched": len(errors),
            "false_positives": len(detected) - len(errors), "missed": len(remaining),
            "precision": len(errors) / len(detected) if detected else None,
            "recall": len(errors) / len(labels) if labels else None,
            "mean_signed_error_ms": round(float(np.mean(errors)) * 1000, 2) if errors else None,
            "mean_abs_error_ms": round(float(np.mean(np.abs(errors))) * 1000, 2) if errors else None,
            "median_tempo_after_4s": float(np.median([s.tempo_bpm for s in warm])),
            "mean_confidence_after_4s": float(np.mean([s.tempo_confidence for s in warm]))}


if __name__ == "__main__":
    result = {"window_anchor": args.window_anchor}
    result.update({name: run(name) for name in ("gain_drop", "crescendo", "strong_drums", "weak_drums", "steady_bass", "noise")})
    result.update({name: run_wav(name) for name in ("rhythmic_120bpm.wav", "piano_irregular.wav", "sustained_bass_pad.wav")})
    result.update({"continuous_" + name: run_continuous(name, args.window_anchor) for name in
                   ("strong_drums", "weak_drums", "syncopated", "free_rhythm", "melody_weak_drums", "noise_only",
                    "sustained_vowel")})
    print(json.dumps(result, indent=2))
