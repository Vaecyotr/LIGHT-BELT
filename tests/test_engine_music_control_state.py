import pytest

from light_engine.analysis.music_control import MusicControlAnalyzer
from light_engine.clock import Clock
from light_engine.config import Config
from light_engine.effects.base import BaseEffect
from light_engine.engine import Engine
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame
from light_engine.outputs import NullOutput
from light_engine.show import (
    AudioControlSpec,
    Cue,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetSelector,
)


class ReplayClock(Clock):
    def __init__(self, times):
        self._template = list(times)
        self.reset()

    def now(self):
        return self._time

    def tick(self):
        if not self._times:
            self._ended = True
            return 0.0
        previous = self._time
        self._time = self._times.pop(0)
        return max(0.0, self._time - previous)

    def reset(self):
        self._times = list(self._template)
        self._time = 0.0
        self._ended = False

    @property
    def ended(self):
        return self._ended


class DeterministicAudioSource:
    def __init__(self, duration=10.0):
        self._duration = duration

    def duration(self):
        return self._duration

    def get_video_features(self, _timestamp):
        return None

    def get_audio_features(self, timestamp):
        return audio_features_at(timestamp)


class RecordingEffect(BaseEffect):
    def __init__(self, name, sink):
        super().__init__(name)
        self._sink = sink

    def process(self, ctx: EffectContext) -> PixelFrame:
        self._sink.append(ctx)
        level = ctx.music_control_state.energy if ctx.music_control_state else 0.0
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=strip["id"],
                    pixel_count=strip["pixel_count"],
                    pixels=[(level, 0.0, 0.0)] * strip["pixel_count"],
                )
                for strip in ctx.mode_parameters["strip_defs"]
            ],
        )


def audio_features_at(timestamp: float) -> AudioFeatures:
    beat = int(round(timestamp * 20.0)) % 4 == 1
    return AudioFeatures(
        timestamp=timestamp,
        rms=0.55 + timestamp,
        bass=0.80 if beat else 0.30 + timestamp * 0.1,
        mid=0.25 + timestamp * 0.2,
        treble=0.10,
        spectral_flux=0.90 if beat else 0.20,
        beat=beat,
        onset=0.80 if beat else 0.10,
        silence=False,
    )


def state_values(state):
    return tuple(
        round(getattr(state, field), 9)
        for field in (
            "timestamp",
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
    )


def fixed_show(effect_name="recording"):
    return ShowDefinition(
        schema_version=1,
        id="music-control-fixed",
        duration=10.0,
        cues=(
            Cue(
                id="fixed",
                start=0.0,
                end=10.0,
                target=TargetSelector(kind="digital_strip", id="front"),
                effect=EffectSpec(mode="fixed", name=effect_name),
            ),
        ),
    )


def adaptive_show():
    return ShowDefinition(
        schema_version=1,
        id="music-control-adaptive",
        duration=10.0,
        cues=(
            Cue(
                id="adaptive",
                start=0.0,
                end=10.0,
                target=TargetSelector(kind="digital_strip", id="front"),
                effect=EffectSpec(
                    mode="adaptive",
                    allowed={"impact": "impact_recorder", "flowing": "flow_recorder"},
                    fallback="fallback_recorder",
                ),
                audio_control=AudioControlSpec(tempo_sync="auto"),
            ),
        ),
    )


def engine_with_show(clock, show, captured, *, data_source=True):
    Config.reset()
    engine = Engine(Config(), clock=clock)
    if data_source:
        engine._data_source = DeterministicAudioSource()
    runtime = ShowRuntime.from_layout(
        show,
        engine._layout,
        effect_factory=lambda name: RecordingEffect(name, captured),
    )
    engine.set_show_runtime(runtime)
    output = NullOutput()
    output.open()
    engine._outputs = {"null": output}
    return engine


def test_engine_show_runtime_derives_deterministic_music_control_sequence(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured = []
    times = [0.05, 0.10, 0.15, 0.20]
    engine = engine_with_show(ReplayClock(times), fixed_show(), captured)
    expected_analyzer = MusicControlAnalyzer()
    expected = [
        expected_analyzer.update(audio_features_at(timestamp)) for timestamp in times
    ]

    engine.run()

    actual = [ctx.music_control_state for ctx in captured]
    assert [ctx.audio_features for ctx in captured] == [
        audio_features_at(timestamp) for timestamp in times
    ]
    assert [state_values(state) for state in actual] == [
        state_values(state) for state in expected
    ]
    assert engine._music_control_analyzer.history_size <= engine._music_control_analyzer.history_bound


def test_fixed_cue_observes_engine_music_control_state_without_adaptive_selection(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured = []
    engine = engine_with_show(ReplayClock([0.05]), fixed_show(), captured)

    engine.run()

    ctx = captured[0]
    assert ctx.music_control_state == MusicControlAnalyzer().update(audio_features_at(0.05))
    assert ctx.mode_parameters["selection_decision"].selected_effect == "recording"
    assert ctx.mode_parameters["music_state"] == "silence"
    assert ctx.mode_parameters["sync_mode"] == "free_run"


def test_adaptive_cue_uses_engine_provided_music_control_state(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured = []
    engine = engine_with_show(ReplayClock([0.05]), adaptive_show(), captured)

    engine.run()

    ctx = captured[0]
    decision = ctx.mode_parameters["selection_decision"]
    assert ctx.music_control_state == MusicControlAnalyzer().update(audio_features_at(0.05))
    assert decision.selected_effect == "impact_recorder"
    assert decision.music_state == "impact"
    assert decision.reason_code == "EVENT_FALLBACK"
    assert decision.source_features["bass_pulse"] == pytest.approx(
        ctx.music_control_state.bass_pulse
    )


def test_engine_reset_reproduces_music_control_state_sequence(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    clock = ReplayClock([0.05, 0.10, 0.15])
    captured = []
    engine = engine_with_show(clock, fixed_show(), captured)

    engine.run()
    first = [state_values(ctx.music_control_state) for ctx in captured]
    clock.reset()
    engine.reset()
    captured.clear()
    engine.run()
    second = [state_values(ctx.music_control_state) for ctx in captured]

    assert second == first


def test_no_audio_show_runtime_keeps_music_control_state_none(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured = []
    engine = engine_with_show(
        ReplayClock([0.05]),
        fixed_show(),
        captured,
        data_source=False,
    )

    engine.run(max_frames=1)

    assert captured[0].audio_features is None
    assert captured[0].music_control_state is None
    assert engine._latest_music_control_state is None


def test_repeated_timestamp_does_not_advance_music_control_state(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    captured = []
    engine = engine_with_show(ReplayClock([0.05, 0.05]), fixed_show(), captured)

    engine.run(max_frames=2)

    expected = MusicControlAnalyzer()
    expected.update(audio_features_at(0.05))
    assert len(captured) == 1
    assert engine._music_control_analyzer.history_size == expected.history_size
