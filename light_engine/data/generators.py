"""Synthetic/generative data sources for demo, testing, and benchmarking.

Provides repeatable (seeded) test patterns: video features, audio features,
and combined demo sequences. No copyright media required.
"""

from __future__ import annotations

import colorsys
import math
import random
from typing import Optional

import numpy as np

from light_engine.models import AudioFeatures, VideoFeatures


class SyntheticDataSource:
    """Generates repeatable synthetic video and audio features for testing.

    Uses a fixed random seed for reproducibility.
    No network, no large temp files, no copyrighted media.
    """

    def __init__(self, seed: int = 42):
        self._seed = seed
        self._rng = random.Random(seed)
        self._total_duration = 120.0  # 2 minutes of demo data
        self._phase = 0.0

    def duration(self) -> float:
        return self._total_duration

    def get_video_features(self, timestamp: float) -> VideoFeatures:
        """Generate synthetic video features with color gradients, scene changes.

        Provides: color gradient cycling, dark/bright scenes, standard colors.
        """
        t = timestamp
        rng = self._rng

        # Color gradient: cycle through hues over time
        hue = (t * 30) % 360  # 12 seconds per full cycle
        sat = 0.6 + math.sin(t * 0.3) * 0.2
        val = 0.5 + math.sin(t * 0.5) * 0.3

        # Scene changes: every ~8 seconds
        scene_change = 0.0
        if abs(t % 8.0) < 0.1:
            scene_change = 0.8
            hue = (hue + 120) % 360

        avg_r, avg_g, avg_b = colorsys.hsv_to_rgb(hue / 360, sat, val)
        dom_r, dom_g, dom_b = colorsys.hsv_to_rgb(
            ((hue + 30) % 360) / 360, min(1.0, sat + 0.1), val
        )

        zone_colors = {
            "left": colorsys.hsv_to_rgb(((hue + 60) % 360) / 360, sat, val),
            "right": colorsys.hsv_to_rgb(((hue - 60) % 360) / 360, sat, val),
            "center": (avg_r, avg_g, avg_b),
            "top": colorsys.hsv_to_rgb(((hue + 180) % 360) / 360, sat, val * 0.8),
            "bottom": (avg_r * 0.5, avg_g * 0.5, avg_b * 0.5),
        }

        return VideoFeatures(
            timestamp=timestamp,
            average_rgb=(avg_r, avg_g, avg_b),
            dominant_rgb=(dom_r, dom_g, dom_b),
            zone_colors=zone_colors,
            brightness=val,
            saturation=sat,
            scene_change=scene_change,
        )

    def get_audio_features(self, timestamp: float) -> AudioFeatures:
        """Generate synthetic audio features simulating music.

        Provides: simulated kick drum, sustained energy, silence segments,
        volume changes, irregular beats, band-emphasis segments.
        """
        t = timestamp
        rng = self._rng

        beat_interval = 0.5  # 120 BPM base
        beat_phase = t % beat_interval
        beat = beat_phase < 0.03

        # Kick drum: strong bass on beats
        bass = 0.1 + (0.7 if beat else 0.0) + math.sin(t * 8.0) * 0.1
        bass = min(1.0, bass + rng.uniform(-0.05, 0.05))

        # Mid: harmonic pattern
        mid = 0.15 + math.sin(t * 3.0) * 0.1 + math.sin(t * 7.0) * 0.05
        mid = max(0.0, min(1.0, mid))

        # Treble: cymbal-like pattern
        treble = 0.05 + (0.3 if beat_phase < 0.1 else 0.0)
        treble = max(0.0, min(1.0, treble))

        # RMS overall energy
        rms = 0.3 * bass + 0.4 * mid + 0.3 * treble
        rms = min(1.0, rms * 1.5)

        # Silence segments: 5 seconds every 20 seconds
        in_silence_segment = (t % 20.0) > 15.0
        spectral_flux = 0.0
        if beat:
            spectral_flux = 0.8 + rng.random() * 0.2
        elif not in_silence_segment:
            spectral_flux = 0.1 + rng.random() * 0.1

        if in_silence_segment:
            rms = 0.0
            bass = 0.0
            mid = 0.0
            treble = 0.0
            spectral_flux = 0.0

        return AudioFeatures(
            timestamp=timestamp,
            rms=max(0.0, min(1.0, rms)),
            bass=max(0.0, min(1.0, bass)),
            mid=max(0.0, min(1.0, mid)),
            treble=max(0.0, min(1.0, treble)),
            spectral_flux=max(0.0, min(1.0, spectral_flux)),
            beat=beat,
            onset=max(0.0, min(1.0, spectral_flux)),
            silence=in_silence_segment,
        )
