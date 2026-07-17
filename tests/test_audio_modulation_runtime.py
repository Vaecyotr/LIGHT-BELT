import pytest

from light_engine.models import AudioFeatures, EffectContext, MusicControlState
from light_engine.show import AudioModulationChannelSpec, AudioModulationSpec
from light_engine.show.audio_modulation import CueAudioModulator


def _channel(source: str, *, smoothing_seconds: float = 0.0) -> AudioModulationChannelSpec:
    return AudioModulationChannelSpec(
        source=source,
        amount=0.5,
        min_multiplier=0.75,
        max_multiplier=1.3,
        smoothing_seconds=smoothing_seconds,
    )


def _ctx(*, music: MusicControlState | None = None, audio: AudioFeatures | None = None, dt: float = 0.1) -> EffectContext:
    return EffectContext(timestamp=1.0, delta_time=dt, music_control_state=music, audio_features=audio)


def test_formula_uses_signed_source_range_and_channel_bounds() -> None:
    modulator = CueAudioModulator(AudioModulationSpec(brightness=_channel("music.energy")))

    quiet = modulator.multipliers(_ctx(music=MusicControlState(timestamp=1.0, energy=0.0)))
    loud = modulator.multipliers(_ctx(music=MusicControlState(timestamp=1.0, energy=1.0)))

    assert quiet.brightness == pytest.approx(0.75)
    assert loud.brightness == pytest.approx(1.3)


def test_smoothing_is_deterministic_and_remains_bounded() -> None:
    modulator = CueAudioModulator(
        AudioModulationSpec(speed=_channel("audio.rms", smoothing_seconds=0.5))
    )
    loud_audio = AudioFeatures(timestamp=1.0, rms=1.0, silence=False)

    first = modulator.multipliers(_ctx(audio=loud_audio, dt=0.25))
    second = modulator.multipliers(_ctx(audio=loud_audio, dt=0.25))

    assert first.speed == pytest.approx(1.15)
    assert second.speed == pytest.approx(1.225)
    assert 0.75 <= second.speed <= 1.3


def test_missing_audio_or_music_state_is_neutral_for_every_channel() -> None:
    modulator = CueAudioModulator(
        AudioModulationSpec(
            brightness=_channel("music.energy"),
            speed=_channel("music.beat_strength"),
            intensity=_channel("audio.bass"),
        )
    )

    multipliers = modulator.multipliers(_ctx())

    assert multipliers.brightness == 1.0
    assert multipliers.speed == 1.0
    assert multipliers.intensity == 1.0
