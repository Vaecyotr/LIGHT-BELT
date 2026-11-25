from dataclasses import replace

import pytest

from light_engine.models import AudioFeatures, AudioObservation


def test_audio_observation_carries_source_epoch_and_independent_clocks() -> None:
    observation = AudioObservation(
        features=AudioFeatures(timestamp=1.25),
        source_kind="phone_pcm",
        source_id="phone-a",
        source_epoch=3,
        sample_seq=17,
        clock_domain="monotonic",
        analysis_time_s=4.5,
        media_time_s=None,
        captured_ns=4_500_000_000,
        received_ns=4_510_000_000,
        age_ms=10.0,
        quality="fresh",
    )

    assert observation.source_id == "phone-a"
    assert observation.media_time_s is None
    assert observation.age_ms == pytest.approx(10.0)


def test_audio_observation_rejects_invalid_quality_and_cross_clock_age() -> None:
    with pytest.raises(ValueError, match="quality"):
        AudioObservation(features=AudioFeatures(timestamp=0), quality="unknown")

    with pytest.raises(ValueError, match="received_ns"):
        AudioObservation(
            features=AudioFeatures(timestamp=0),
            captured_ns=2,
            received_ns=1,
        )


def test_audio_observation_does_not_mutate_legacy_feature_model() -> None:
    features = AudioFeatures(timestamp=2, beat=True, peak=True)
    observation = AudioObservation(features=features, quality="held")

    assert observation.features is features
    assert features.beat is True


def test_audio_observation_exposes_capabilities_and_single_beat_identity() -> None:
    observation = AudioObservation(
        features=AudioFeatures(timestamp=1.0, beat=True),
        source_kind="wled",
        source_epoch=4,
        sample_seq=22,
        beat_event=True,
        event_id="4:22",
        capabilities=("spectrum16", "dominant_frequency", "beat_event"),
    )

    assert observation.capabilities == (
        "spectrum16",
        "dominant_frequency",
        "beat_event",
    )
    assert observation.event_id == "4:22"
