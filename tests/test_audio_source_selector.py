from dataclasses import replace

from light_engine.analysis.source_selector import AudioSourceSelector
from light_engine.models import AudioFeatures, AudioObservation


def _observation(kind="phone_pcm", source_id="phone-a", epoch=1, seq=1, **kw):
    return AudioObservation(
        features=AudioFeatures(timestamp=0.0, rms=0.6, beat=True, onset=0.7),
        source_kind=kind,
        source_id=source_id,
        source_epoch=epoch,
        sample_seq=seq,
        clock_domain="monotonic",
        received_ns=kw.pop("received_ns", 100),
        **kw,
    )


def test_source_selector_rejects_old_source_epoch_and_out_of_order_windows() -> None:
    selector = AudioSourceSelector(stale_after_ms=250, clock_ns=lambda: 100)
    epoch = selector.select("phone_pcm", "phone-a")
    assert selector.publish(_observation(epoch=epoch, seq=2))
    assert not selector.publish(_observation(epoch=epoch - 1, seq=3))
    assert not selector.publish(_observation(epoch=epoch, seq=1))
    assert selector.poll().features.rms == 0.6


def test_source_selector_held_window_clears_events_and_stale_clears_values() -> None:
    now = [100]
    selector = AudioSourceSelector(stale_after_ms=50, clock_ns=lambda: now[0])
    epoch = selector.select("phone_pcm", "phone-a")
    selector.publish(_observation(epoch=epoch, received_ns=90))

    assert selector.poll().quality == "fresh"
    held = selector.poll()
    assert held.quality == "held"
    assert held.features.rms == 0.6
    assert held.features.beat is False
    assert held.features.onset == 0.0

    now[0] = 200_000_000
    stale = selector.poll()
    assert stale.quality == "stale"
    assert stale.features.rms == 0.0
    assert stale.features.silence is True


def test_source_selector_new_selection_invalidates_prior_snapshot() -> None:
    selector = AudioSourceSelector(clock_ns=lambda: 1)
    old_epoch = selector.select("phone_pcm", "phone-a")
    selector.publish(_observation(epoch=old_epoch))
    new_epoch = selector.select("wled", "esp32-1")
    assert new_epoch > old_epoch
    assert selector.poll().quality in {"warming", "unavailable"}


def test_source_selector_delivers_beat_event_once_per_window():
    selector = AudioSourceSelector(clock_ns=lambda: 100)
    epoch = selector.select("phone_pcm", "phone-a")
    event = AudioObservation(
        features=AudioFeatures(timestamp=0.0, beat=True),
        source_kind="phone_pcm",
        source_id="phone-a",
        source_epoch=epoch,
        sample_seq=1,
        clock_domain="monotonic",
        received_ns=100,
        beat_event=True,
        event_id=f"{epoch}:1",
        capabilities=("beat_event",),
    )
    assert selector.publish(event)
    first = selector.poll()
    repeated = selector.poll()

    assert first.beat_event is True
    assert first.event_id == f"{epoch}:1"
    assert repeated.beat_event is False
    assert repeated.event_id is None
    assert repeated.features.beat is False
