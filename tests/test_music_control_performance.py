"""Full-suite sustained-history and processing-throughput acceptance."""

import time

import numpy as np

from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.models import AudioFeatures
from tests.test_music_control import _stream_fixture


def test_history_bounded_after_300_second_generated_fixture():
    analyzer = MusicControlAnalyzer()
    total_frames = 300 * 60
    for i in range(total_frames):
        timestamp = i / 60.0
        beat = i % 30 == 0
        features = AudioFeatures(
            timestamp=timestamp,
            rms=0.8 if beat else 0.08,
            bass=1.0 if beat else 0.12,
            mid=0.2,
            treble=0.05,
            spectral_flux=1.0 if beat else 0.0,
            beat=beat,
            onset=1.0 if beat else 0.0,
            silence=False,
        )
        analyzer.update(features)
    assert analyzer.history_size <= analyzer.history_bound
    assert analyzer.history_size <= 2488


def test_processing_cost_exceeds_60_fps_capacity():
    states, _ = _stream_fixture("rhythmic_120bpm.wav")
    analyzer = MusicControlAnalyzer()
    features = [
        AudioFeatures(
            timestamp=state.timestamp,
            rms=state.energy,
            bass=state.bass_ambient,
            mid=0.1,
            treble=0.05,
            spectral_flux=state.spectral_motion,
            beat=state.beat_strength > 0.8,
            onset=state.transient,
            silence=state.energy < 0.01,
        )
        for state in states
    ]
    durations: list[float] = []
    for feature in features:
        start = time.perf_counter()
        analyzer.update(feature)
        durations.append(time.perf_counter() - start)
    average = sum(durations) / len(durations)
    p95 = float(np.percentile(durations, 95))
    assert average < 1.0 / 60.0
    assert p95 < 1.0 / 60.0
