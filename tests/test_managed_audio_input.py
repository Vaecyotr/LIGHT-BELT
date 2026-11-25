import threading
import time

import numpy as np
import pytest
from scipy.io import wavfile

from light_engine.analysis.managed_audio_input import ManagedAudioInput
from light_engine.analysis.pulse_capture import PCMChunk
from light_engine.config import Config
from light_engine.models import AudioFeatures


@pytest.mark.parametrize("rate", [44100, 48000])
@pytest.mark.parametrize("bpm", [60, 90, 120, 180])
def test_labelled_pcm_clicks_at_supported_tempos(rate, bpm, tmp_path, record_property):
    duration = 14
    beats = np.arange(0.5, duration - 0.3, 60 / bpm)
    samples = np.zeros(rate * duration, dtype=np.float32)
    t = np.arange(round(0.075 * rate)) / rate
    click = 0.5 * np.sin(2 * np.pi * 100 * t) * np.exp(-t / 0.016)
    for beat in beats:
        i = round(beat * rate)
        samples[i:i + len(click)] += click
    path = tmp_path / "clicks.wav"
    wavfile.write(path, rate, samples)
    source = ManagedAudioInput(Config())
    events, tempos, phases, confidences = [], [], [], []
    try:
        source.configure("auto", {"kind":"file","path":str(path)})
        for sec in np.arange(0, duration, 0.025):
            _, music = source.poll(sec)
            if 4 <= sec < duration - 0.3 and source.status()["event_id"]:
                events.append(sec)
            if sec >= 8 and music and music.tempo_confidence >= 0.18:
                tempos.append(music.tempo_bpm)
                confidences.append(music.tempo_confidence)
                ideal = ((sec - 0.5) * bpm / 60) % 1
                phases.append(abs((music.beat_phase - ideal + 0.5) % 1 - 0.5))
    finally:
        source.close()
    expected = beats[beats >= 4]
    assert len(events) == len(expected)
    assert np.max(np.abs(expected - events)) < 0.08
    assert tempos and np.median(tempos) == pytest.approx(bpm, abs=3)
    assert np.median(phases) < 0.08
    record_property("median_bpm", float(np.median(tempos)))
    record_property("median_confidence_after_lock", float(np.median(confidences)))
    record_property("median_phase_error_cycles", float(np.median(phases)))
    record_property("max_event_error_ms", float(np.max(np.abs(expected - events)) * 1000))


def test_managed_file_input_returns_legacy_features_and_music_state(tmp_path):
    sample_rate = 44100
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    audio = (0.25 * np.sin(2 * np.pi * 110 * t) * 32767).astype(np.int16)
    path = tmp_path / "tone.wav"
    wavfile.write(path, sample_rate, audio)
    source = ManagedAudioInput(Config())
    source.configure("device", {"kind": "file", "path": str(path)})

    features, state = source.poll(0.5)

    assert features is not None
    assert state is not None
    assert features.timestamp == 0.5
    assert source.status()["source_kind"] == "file"
    source.close()


def test_managed_none_source_does_not_manufacture_silence_state():
    source = ManagedAudioInput(Config())
    source.configure("none", {"kind": "none"})

    assert source.poll(0.0) == (None, None)
    assert source.status()["quality"] == "unavailable"
    source.close()


def test_hot_switch_fades_new_continuous_levels_without_altering_measurement(tmp_path):
    rate = 44100
    t = np.arange(rate) / rate
    now = [1_000_000_000]
    source = ManagedAudioInput(Config(), clock_ns=lambda: now[0])
    try:
        for name in ("first", "second"):
            path = tmp_path / (name + ".wav")
            wavfile.write(path, rate, (0.2*np.sin(2*np.pi*100*t)).astype("float32"))
            source.configure("auto", {"kind":"file","path":str(path)})
            feature, _ = source.poll(.3)
            if name == "first":
                assert feature.rms > .9
        assert feature.rms == 0 and not feature.silence
        assert source.status()["event_id"] is None
        now[0] += 75_000_000
        middle, _ = source.poll(.375)
        assert middle.rms == pytest.approx(.5, abs=.02)
        now[0] += 75_000_000
        final, _ = source.poll(.45)
        assert final.rms > .9
    finally:
        source.close()


def test_managed_pcm_input_uses_capture_and_stereo_analyzer():
    class Capture:
        sample_rate = 48000

        def __init__(self, **_kwargs):
            self.chunk = PCMChunk(
                samples=np.tile(
                    np.array([[0.0, 0.0], [0.4, -0.4]], dtype=np.float32), (1200, 1)
                ),
                sample_seq=1,
                received_ns=1_000_000_000,
            )

        def start(self):
            return self

        def read_latest(self):
            chunk, self.chunk = self.chunk, None
            return chunk

        def status(self):
            return {"running": True}

        def close(self):
            pass

    source = ManagedAudioInput(
        Config(), capture_factory=Capture, clock_ns=lambda: 1_000_000_000
    )
    source.configure(
        "device",
        {
            "kind": "phone_pcm",
            "device": "source-a",
            "monitor_stream": 19,
            "source_id": "phone-a",
        },
    )

    features, state = source.poll(0.0)

    assert features is not None and features.silence is False
    assert state is not None
    assert source.status()["source_id"] == "phone-a"
    source.close()


def test_managed_configure_same_target_is_idempotent():
    calls = []

    class Capture:
        sample_rate = 48000

        def __init__(self, **kwargs):
            calls.append(kwargs)

        def start(self):
            return self

        def close(self):
            pass

        def read_latest(self):
            return None

        def status(self):
            return {"running": True}

    source = ManagedAudioInput(Config(), capture_factory=Capture)
    target = {
        "kind": "phone_pcm",
        "device": "source-a",
        "monitor_stream": 19,
        "source_id": "phone-a",
    }
    first = source.configure("device", target)
    second = source.configure("device", target)

    assert first == second
    assert len(calls) == 1
    source.close()


def test_managed_pcm_rebinds_when_pulse_server_generation_changes():
    calls = []

    class Capture:
        sample_rate = 48000

        def __init__(self, **kwargs):
            calls.append(kwargs)

        def start(self):
            return self

        def close(self):
            pass

        def read_latest(self):
            return None

        def status(self):
            return {"running": True}

    source = ManagedAudioInput(Config(), capture_factory=Capture)
    target = {
        "kind": "phone_pcm", "device": "bluez_source.phone.monitor",
        "monitor_stream": 19, "source_id": "phone-a", "pa_generation": "pa-1",
    }
    first = source.configure("device", target)
    target["pa_generation"] = "pa-2"
    second = source.configure("device", target)

    assert second > first
    assert len(calls) == 2
    source.close()


def test_switching_pcm_source_does_not_wait_for_retired_capture_close():
    close_started = threading.Event()
    allow_close = threading.Event()
    captures = []

    class Capture:
        sample_rate = 48000

        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captures.append(self)

        def start(self):
            return self

        def close(self):
            close_started.set()
            assert allow_close.wait(2)

        def read_latest(self):
            return None

        def status(self):
            return {"running": True}

    source = ManagedAudioInput(Config(), capture_factory=Capture)
    source.configure("device", {"kind": "phone_pcm", "device": "source-a", "monitor_stream": 1})

    started = time.monotonic()
    source.configure("device", {"kind": "phone_pcm", "device": "source-b", "monitor_stream": 2})
    assert time.monotonic() - started < 0.2
    assert close_started.wait(1)
    assert source.poll(0.0) == (None, None)
    assert len(captures) == 1

    allow_close.set()
    deadline = time.monotonic() + 1
    while len(captures) == 1 and time.monotonic() < deadline:
        source.poll(0.0)
        time.sleep(0.005)
    try:
        assert len(captures) == 2
        assert source._capture is captures[1]
    finally:
        source.close()


def test_managed_pcm_capture_failure_is_reported_and_does_not_escape_poll():
    now = [1_000_000_000]
    calls = []

    def broken_capture(**_kwargs):
        calls.append(True)
        raise OSError("capture unavailable")

    source = ManagedAudioInput(
        Config(), capture_factory=broken_capture, clock_ns=lambda: now[0]
    )
    source.configure(
        "device", {"kind": "phone_pcm", "device": "source-a", "monitor_stream": 19}
    )

    assert source.poll(0.0) == (None, None)
    assert source.status()["phase"] == "fault"
    assert "capture unavailable" in source.status()["reason"]
    assert len(calls) == 1
    now[0] += 250_000_000
    assert source.poll(0.0) == (None, None)
    assert len(calls) == 2


def test_managed_wled_requires_valid_sender_and_monitor_requires_index():
    wled_calls = []
    capture_calls = []

    def wled_factory(**kwargs):
        wled_calls.append(kwargs)
        raise AssertionError("must fail closed before opening WLED")

    def capture_factory(**kwargs):
        capture_calls.append(kwargs)
        raise AssertionError("must fail closed before starting capture")

    source = ManagedAudioInput(
        Config(), wled_factory=wled_factory, capture_factory=capture_factory
    )
    source.configure("mic", {"kind": "wled"})
    assert source.poll(0.0) == (None, None)
    assert "IPv4" in source.status()["reason"]
    assert wled_calls == []

    source.configure("device", {"kind": "monitor", "device": "default.monitor"})
    assert source.poll(0.0) == (None, None)
    assert "monitor_stream" in source.status()["reason"]
    assert capture_calls == []
    source.close()


def test_managed_pcm_uses_50ms_windows_25ms_hop_and_does_not_repeat_events():
    class Capture:
        sample_rate = 48000

        def __init__(self, **_kwargs):
            self.blocks = [
                PCMChunk(np.ones((960, 2), dtype=np.float32) * 0.1, i, i * 20_000_000)
                for i in (1, 2, 3)
            ] + [
                None,
                PCMChunk(np.ones((960, 2), dtype=np.float32) * 0.1, 4, 80_000_000),
            ]

        def start(self):
            return self

        def close(self):
            pass

        def status(self):
            return {"running": True}

        def read_latest(self):
            return self.blocks.pop(0) if self.blocks else None

    source = ManagedAudioInput(
        Config(), capture_factory=Capture, clock_ns=lambda: 100_000_000
    )
    source.configure(
        "device",
        {
            "kind": "phone_pcm",
            "device": "source-a",
            "monitor_stream": 19,
            "source_id": "phone-a",
        },
    )
    source._music._is_beat_event = lambda timestamp, strength: True
    source._audio_analyzer.analyze_stereo = (
        lambda samples, timestamp, sample_rate: AudioFeatures(
            timestamp=timestamp,
            rms=0.5,
            loudness=0.5,
            beat=False,
            silence=False,
        )
    )

    assert source.poll(0.0) == (None, None)
    assert source.poll(0.0) == (None, None)
    first, _ = source.poll(0.0)
    first_status = source.status()
    held, _ = source.poll(0.0)
    held_status = source.status()
    next_window, _ = source.poll(0.0)
    next_status = source.status()

    assert first is not None and first.beat is False
    assert first_status["sample_seq"] == 1
    assert first_status["event_id"] is None
    assert held is not None and held.beat is False
    assert held_status["sample_seq"] == first_status["sample_seq"]
    assert held_status["event_id"] is None
    assert next_window is not None and next_window.beat is False
    assert next_status["sample_seq"] == 2
    assert next_status["event_id"] != first_status["event_id"]
    source.close()


def test_managed_wled_preserves_sixteen_bands_frequency_and_single_beat_event():
    class Wled:
        def __init__(self, **kwargs):
            assert kwargs["expected_sender"] == "192.0.2.10"
            self.count = 0

        def open(self):
            return self

        def close(self):
            pass

        def diagnostics(self):
            return {
                "stale": False,
                "packets_valid": self.count,
                "packet_age_seconds": 0.005,
            }

        def poll(self, timestamp):
            if self.count == 0:
                self.count += 1
            return AudioFeatures(
                timestamp=timestamp,
                rms=0.5,
                loudness=0.5,
                spectrum=tuple(i / 15 for i in range(16)),
                dominant_frequency=880.0,
                beat=True,
                silence=False,
            )

    source = ManagedAudioInput(
        Config(), wled_factory=Wled, clock_ns=lambda: 1_000_000_000
    )
    source.configure("mic", {"kind": "wled", "source_id": "192.0.2.10"})

    first, _ = source.poll(1.0)
    assert first is not None
    status = source.status()
    held, _ = source.poll(1.0)

    assert len(first.spectrum) == 16
    assert first.bass == pytest.approx(sum(first.spectrum[:3]) / 3)
    assert first.mid == pytest.approx(sum(first.spectrum[3:10]) / 7)
    assert first.treble == pytest.approx(sum(first.spectrum[10:]) / 6)
    assert first.dominant_frequency == 880.0
    assert status["capabilities"] == [
        "loudness",
        "raw_level",
        "spectrum16",
        "dominant_frequency",
        "beat_event",
    ]
    assert status["event_id"] is None
    assert held is not None and held.beat is False
    assert source.status()["event_id"] is None
    source.close()
