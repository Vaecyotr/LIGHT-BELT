import pytest
import numpy as np

from light_engine.analysis.audio import AudioAnalyzer
from light_engine.config import Config
from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import AudioModulationChannelSpec, AudioModulationSpec
from light_engine.show.audio_modulation import CueAudioModulator
from tests.audio_ab_probe import run_continuous


def test_quiet_drums_under_a_melody_supply_regular_tempo_without_locking_on_noise():
    drums = run_continuous("melody_weak_drums")
    assert drums["median_tempo_after_4s"] == pytest.approx(120, abs=3)
    assert drums["mean_confidence_after_4s"] > 0.65
    noise = run_continuous("noise_only")
    assert noise["median_tempo_after_4s"] == 0


def test_repeated_same_tone_attacks_after_silence_are_detected():
    t = np.arange(2205) / 44100
    tone = (0.1 * np.sin(2 * np.pi * 100 * t)).astype(np.float32)
    analyzer = AudioAnalyzer(Config())
    beats = []
    for i in range(120):
        samples = tone if i % 20 == 0 else np.zeros_like(tone)
        beats.append(analyzer.analyze(samples, i * 0.025).beat)
    assert sum(beats) >= 4


def test_pcm_gain_drop_does_not_create_delayed_transient():
    t = np.arange(2205) / 44100
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    late = []
    for i in range(320):
        amplitude = 0.1 if i < 160 else 0.02
        samples = amplitude * np.sin(2 * np.pi * 73 * (t + i * 0.025))
        state = music.update(audio.analyze(samples.astype(np.float32), i * 0.025))
        if i >= 240:
            late.append(state)
    assert max(s.transient for s in late) < 0.1
    assert max(s.bass_pulse for s in late) < 0.1


def test_pcm_real_energy_attack_still_triggers_transient():
    t = np.arange(2205) / 44100
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    states = []
    for i in range(160):
        amplitude = 0.01 if i < 120 else 0.1
        samples = amplitude * np.sin(2 * np.pi * 700 * (t + i * 0.025))
        states.append(music.update(audio.analyze(samples.astype(np.float32), i * 0.025)))
    assert max(s.transient for s in states[120:125]) > 0.5


@pytest.mark.parametrize("gain", [0.01, 0.1])
@pytest.mark.parametrize("direction", [-1, 0, 1])
def test_pcm_trend_tracks_level_change_at_multiple_gains(gain, direction):
    t = np.arange(2205) / 44100
    audio, music = AudioAnalyzer(Config()), MusicControlAnalyzer()
    for i in range(240):
        fraction = i / 239
        level = (0.2 + 0.8 * fraction) if direction > 0 else (1.0 - 0.8 * fraction) if direction < 0 else 1.0
        samples = gain * level * np.sin(2 * np.pi * 73 * (t + i * 0.025))
        state = music.update(audio.analyze(samples.astype(np.float32), i * 0.025))
    if direction == 0:
        assert abs(state.energy_trend) < 0.1
    else:
        assert state.energy_trend * direction > 0.25
    modulator = CueAudioModulator(AudioModulationSpec(brightness=AudioModulationChannelSpec(
        source="music.energy_trend", amount=0.5, min_multiplier=0.5, max_multiplier=1.5,
        smoothing_seconds=0.0)))
    brightness = modulator.multipliers(EffectContext(timestamp=state.timestamp, delta_time=0.025,
                                                      music_control_state=state)).brightness
    if direction == 0:
        assert brightness == pytest.approx(1.0, abs=0.05)
    else:
        assert (brightness - 1.0) * direction > 0.1


@pytest.mark.parametrize("kind", ["noise", "tone"])
def test_near_digital_silence_does_not_drive_music_control(kind):
    rng = np.random.default_rng(42)
    t = np.arange(2205) / 44100
    samples = rng.normal(0, 1e-6, len(t)) if kind == "noise" else 1e-6 * np.sin(2 * np.pi * 100 * t)
    audio = AudioAnalyzer(Config())
    music = MusicControlAnalyzer()
    states = []
    for i in range(20):
        features = audio.analyze(samples.astype(np.float32), i * 0.025)
        assert features.silence
        states.append(music.update(features))
    assert max(s.energy for s in states) == 0
    assert max(s.transient for s in states) == 0


@pytest.mark.parametrize("period", [0.5, 0.75, 1.0])
def test_tempo_expires_after_rhythm_stops(period):
    analyzer = MusicControlAnalyzer()
    for i in range(12):
        analyzer.update(AudioFeatures(timestamp=i * period, rms=1, bass=1))
        analyzer.update(AudioFeatures(timestamp=i * period + 0.1, silence=True))
    assert analyzer._last_state.tempo_bpm > 0
    state = analyzer.update(AudioFeatures(timestamp=11 * period + 2.0, silence=True))
    assert state.tempo_bpm > 0
    state = analyzer.update(AudioFeatures(timestamp=11 * period + 4.1, silence=True))
    assert state.tempo_bpm == 0
    assert state.tempo_confidence == 0
    state = analyzer.update(AudioFeatures(timestamp=11 * period + 4.2, rms=1, bass=1))
    assert state.tempo_bpm == 0
