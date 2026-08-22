"""Engine integration for the configured WLED Audio Sync V2 source."""

from __future__ import annotations

import pytest

from light_engine.clock import OfflineRenderClock
from light_engine.config import Config, ConfigError, validate_config
from light_engine.engine import Engine
from light_engine.models import AudioFeatures
from light_engine.outputs import NullOutput


class FakeLiveSource:
    def __init__(self, features: AudioFeatures, *, open_error: Exception | None = None):
        self.features = features
        self.open_error = open_error
        self.open_count = 0
        self.poll_timestamps: list[float] = []
        self.reset_count = 0
        self.close_count = 0
        self.stale = False

    def open(self):
        self.open_count += 1
        if self.open_error is not None:
            raise self.open_error
        return self

    def poll(self, timestamp: float) -> AudioFeatures:
        self.poll_timestamps.append(timestamp)
        return self.features

    def reset(self) -> None:
        self.reset_count += 1

    def close(self) -> None:
        self.close_count += 1

    def diagnostics(self) -> dict:
        return {"kind": "wled_audio_sync_v2", "open_count": self.open_count}


def _live_config() -> Config:
    Config.reset()
    config = Config()
    config._data["system"]["audio"]["source"]["kind"] = "wled_audio_sync_v2"
    return config


def test_current_production_profile_enables_live_audio_source() -> None:
    Config.reset()
    config = Config("config/profiles/rk3588-host-service.yaml")

    assert config.get("system.audio.source") == {
        "kind": "wled_audio_sync_v2",
        "multicast_group": "239.0.0.1",
        "port": 11988,
        "interface_ipv4": "0.0.0.0",
        "stale_after_ms": 250,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kind", "pcm_microphone"),
        ("multicast_group", "not-an-ip"),
        ("port", 0),
        ("port", 65536),
        ("interface_ipv4", "::1"),
        ("stale_after_ms", 0),
        ("stale_after_ms", float("nan")),
        ("multicast_group", "192.0.2.1"),
    ],
)
def test_live_audio_source_config_rejects_invalid_contract(field, value) -> None:
    config = _live_config()
    config._data["system"]["audio"]["source"][field] = value

    with pytest.raises(ConfigError) as exc_info:
        validate_config(config._data)

    assert exc_info.value.path == "system.audio.source"
    assert exc_info.value.field == field


def test_live_audio_beats_synthetic_and_is_opened_and_closed_per_run(monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    live_features = AudioFeatures(
        timestamp=0.0,
        loudness=0.75,
        spectrum=(0.5,) * 16,
        silence=False,
    )
    source = FakeLiveSource(live_features)
    engine = Engine(
        _live_config(),
        clock=OfflineRenderClock(fps=30.0),
        live_audio_source=source,
    )
    engine.use_synthetic(seed=42)
    engine.set_effect("audio_pulse")
    output = NullOutput()
    output.open()
    engine._outputs = {"null": output}

    engine.run(max_frames=1)

    assert engine._latest_audio is live_features
    assert source.open_count == 1
    assert source.poll_timestamps
    assert source.close_count == 1
    assert engine.diagnostics()["audio_source"]["kind"] == "wled_audio_sync_v2"


def test_explicit_file_audio_has_priority_over_live_source() -> None:
    file_features = AudioFeatures(timestamp=1.0, rms=0.25, silence=False)
    source = FakeLiveSource(AudioFeatures(timestamp=1.0, rms=0.9, silence=False))
    engine = Engine(_live_config(), live_audio_source=source)

    class Reader:
        sample_rate = 44100

        def get_window_at(self, _timestamp, _window):
            return [1.0]

    class Analyzer:
        def analyze(self, _samples, _timestamp, _sample_rate):
            return file_features

    engine._audio_reader = Reader()
    engine._audio_analyzer = Analyzer()

    assert engine._get_audio_features() is file_features
    assert source.poll_timestamps == []


@pytest.mark.parametrize("samples", [None, []])
def test_explicit_file_audio_empty_window_never_falls_through_to_live_or_synthetic(
    samples,
) -> None:
    source = FakeLiveSource(AudioFeatures(timestamp=1.0, rms=0.9, silence=False))
    engine = Engine(_live_config(), live_audio_source=source)
    engine.use_synthetic(seed=42)

    class Reader:
        sample_rate = 44100

        def get_window_at(self, _timestamp, _window):
            return samples

    class Analyzer:
        def analyze(self, _samples, _timestamp, _sample_rate):
            raise AssertionError("empty file audio window must not be analyzed")

    engine._audio_reader = Reader()
    engine._audio_analyzer = Analyzer()
    output = NullOutput()
    output.open()
    engine._outputs = {"null": output}

    engine._begin_run_session()
    assert engine._get_audio_features() is None
    assert source.open_count == 0
    assert source.poll_timestamps == []
    output.close()


def test_live_source_initialization_failure_is_explicit_without_fallback() -> None:
    source = FakeLiveSource(
        AudioFeatures(timestamp=0.0),
        open_error=OSError("multicast unavailable"),
    )
    engine = Engine(_live_config(), live_audio_source=source)
    engine.use_synthetic(seed=42)

    with pytest.raises(RuntimeError, match="Audio Sync V2.*multicast unavailable"):
        engine.run(max_frames=1)

    assert source.poll_timestamps == []
    assert "multicast unavailable" in engine.diagnostics()["last_error"]


def test_entering_live_stale_resets_music_history_exactly_once() -> None:
    source = FakeLiveSource(
        AudioFeatures(timestamp=0.0, rms=0.8, bass=0.7, silence=False)
    )
    engine = Engine(_live_config(), live_audio_source=source)
    engine._live_audio_was_stale = False
    engine._music_control_analyzer.update(source.features)
    initial_history_size = engine._music_control_analyzer.history_size
    assert initial_history_size > 0

    source.stale = True
    source.features = AudioFeatures(timestamp=1.0)
    engine._get_audio_features()
    assert engine._music_control_analyzer.history_size == 0

    engine._music_control_analyzer.update(source.features)
    engine._get_audio_features()
    assert engine._music_control_analyzer.history_size > 0
