"""Tests for deterministic music-control feature derivation."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from light_engine.analysis.audio import AudioAnalyzer
from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.config import Config
from light_engine.media import AudioReader
from light_engine.models import AudioFeatures, MusicControlState


FIXTURE_DIR = Path("tests/fixtures/audio/show_orchestration_v1")
G7_PATH = Path("tests/goldens/show_orchestration/v1/G7_music_expectations.json")


def _fixture_manifest() -> dict:
    return json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stream_fixture(name: str) -> tuple[list[MusicControlState], MusicControlAnalyzer]:
    Config.reset()
    audio = AudioAnalyzer(Config())
    music = MusicControlAnalyzer()
    reader = AudioReader(str(FIXTURE_DIR / name)).open()
    states: list[MusicControlState] = []
    timestamp = 0.0
    step = 1.0 / 60.0
    try:
        while timestamp < reader.duration:
            samples = reader.get_window_at(timestamp, 0.05)
            if samples is not None:
                features = audio.analyze(samples, timestamp, reader.sample_rate)
                states.append(music.update(features))
            timestamp += step
    finally:
        reader.close()
    return states, music


def _write_summary(
    generated_dir: Path,
    name: str,
    states: list[MusicControlState],
    analyzer: MusicControlAnalyzer,
) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "fixture": name,
        "summary": analyzer.summary(states),
        "final_state": analyzer.state_dict(states[-1]),
    }
    (generated_dir / f"{Path(name).stem}_music_control_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _finite_states(states: list[MusicControlState]) -> None:
    fields = (
        "tempo_bpm",
        "tempo_confidence",
        "beat_phase",
        "beat_strength",
        "beat_regularity",
        "energy",
        "energy_trend",
        "transient",
        "bass_ambient",
        "bass_pulse",
        "spectral_motion",
    )
    for state in states:
        for field in fields:
            value = getattr(state, field)
            assert math.isfinite(value), f"{field} is not finite at {state.timestamp}"


def test_locked_wav_hashes_match_manifest_before_analysis():
    manifest = _fixture_manifest()
    for item in manifest["fixtures"]:
        path = FIXTURE_DIR / item["file"]
        assert _sha256(path) == item["sha256"]
        assert path.stat().st_size == item["size_bytes"]


def test_locked_fixture_music_expectations_and_json_summaries(tmp_path: Path):
    expectations = json.loads(G7_PATH.read_text(encoding="utf-8"))["fixtures"]
    generated_dir = tmp_path / "generated_show_orchestration"
    results: dict[str, tuple[list[MusicControlState], MusicControlAnalyzer]] = {}
    for item in _fixture_manifest()["fixtures"]:
        states, analyzer = _stream_fixture(item["file"])
        _finite_states(states)
        _write_summary(generated_dir, item["file"], states, analyzer)
        results[item["file"]] = (states, analyzer)

    rhythmic = results["rhythmic_120bpm.wav"][0]
    piano = results["piano_irregular.wav"][0]
    crescendo = results["string_crescendo.wav"][0]
    bass = results["sustained_bass_pad.wav"][0]
    silence = results["silence.wav"][0]

    rhythmic_warm = [state for state in rhythmic if state.timestamp >= 4.0]
    piano_warm = [state for state in piano if state.timestamp >= 4.0]
    assert abs(float(np.median([s.tempo_bpm for s in rhythmic_warm])) - 120.0) <= 3.0
    assert float(np.mean([s.tempo_confidence for s in rhythmic_warm])) >= 0.65
    assert float(np.mean([s.beat_regularity for s in rhythmic_warm])) >= 0.75
    assert float(np.mean([s.tempo_confidence for s in piano_warm])) < 0.35
    assert max(s.transient for s in piano) > 0.5

    early_energy = float(np.mean([s.energy for s in crescendo if 0.0 <= s.timestamp <= 0.10]))
    late_energy = float(np.mean([s.energy for s in crescendo if 0.20 <= s.timestamp <= 0.40]))
    rising_trend = float(np.mean([s.energy_trend for s in crescendo if 0.20 <= s.timestamp <= 0.80]))
    assert late_energy > early_energy + 0.25
    assert rising_trend > 0.0

    attack_pulse = max(s.bass_pulse for s in bass if s.timestamp <= 0.25)
    steady_pulse = max(s.bass_pulse for s in bass if s.timestamp >= 2.0)
    steady_ambient = float(np.mean([s.bass_ambient for s in bass if s.timestamp >= 4.0]))
    assert attack_pulse > 0.5
    assert steady_pulse < 0.2
    assert steady_ambient > 0.8
    assert float(np.mean([s.tempo_confidence for s in bass if s.timestamp >= 4.0])) < 0.35

    assert max(s.energy for s in silence) == 0.0
    assert max(s.tempo_confidence for s in silence) == 0.0
    assert max(s.bass_pulse for s in silence) == 0.0
    assert set(expectations) == set(results)


def test_music_control_state_sequence_is_deterministic():
    first, _ = _stream_fixture("rhythmic_120bpm.wav")
    second, _ = _stream_fixture("rhythmic_120bpm.wav")
    first_values = [tuple(round(v, 9) for v in MusicControlAnalyzer().state_dict(s).values()) for s in first]
    second_values = [tuple(round(v, 9) for v in MusicControlAnalyzer().state_dict(s).values()) for s in second]
    assert first_values == second_values


def test_history_is_bounded_across_capacity_boundary():
    analyzer = MusicControlAnalyzer()
    # Fill each sample window, then cross its capacity without waiting 300 seconds.
    capacity = max(analyzer.short_capacity, analyzer.medium_capacity, analyzer.long_capacity)
    for i in range(capacity + 2):
        analyzer.update(AudioFeatures(timestamp=i / 60.0, silence=True))
        assert analyzer.history_size <= analyzer.history_bound
    assert analyzer.history_size == (
        analyzer.short_capacity + analyzer.medium_capacity + analyzer.long_capacity
    )
