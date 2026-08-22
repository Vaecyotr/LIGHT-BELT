"""Immutable current-Show gate for Phase 32 infrastructure changes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from light_engine.config import Config
from light_engine.mapping import Layout
from light_engine.models import EffectContext
from light_engine.show import (
    ShowRuntime,
    TargetCatalog,
    black_base_frame,
    load_show,
)


ASSET = Path("assets/energy-wakeup/energy-wakeup.yaml")
RUNTIME_COPY = Path("config/shows/energy-wakeup.yaml")
PROFILE = Path("config/profiles/rk3588-host-service.yaml")
ASSET_SHA256 = "627d23a4c73e66f1913c7b5cbb15cf1b16926e6772289237165535a2278c142d"
RENDER_SHA256 = {
    1.0: "b8fdd0f03e6df638ec278df18bcebf2d5de95cefe5d59929c252917a199b7858",
    28.0: "8f893a00f0da295708820a05517a20c716c104dd8354cee8231b5a1bc0cafedb",
    75.0: "ef04adab6b721be3d221e11b4090feffe010cd3e723e1cd3543d9b05ba6fe61f",
    150.0: "99dabd601ebc7759f1b13d3c602d00c3fc43278e4d48ab4f25eda26ccec29bec",
    225.0: "fc59465b8b5f310cf038add5667627ec67a605a44b93faded75a7d63f1608450",
    300.0: "77ca71ff43e4f2c7dba800ed637b62262654212265c723f685c2e8ca707159dc",
}


def _frame_digest(frame) -> str:
    semantic = {
        "strips": [
            [
                strip.strip_id,
                [[round(channel, 9) for channel in pixel] for pixel in strip.pixels],
            ]
            for strip in frame.strips
        ],
        "zones": [
            [
                zone.zone_id,
                [
                    round(zone.color.r, 9),
                    round(zone.color.g, 9),
                    round(zone.color.b, 9),
                    round(zone.color.warm_white, 9),
                    round(zone.color.cool_white, 9),
                ],
            ]
            for zone in frame.zones
        ],
    }
    encoded = json.dumps(semantic, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _layout() -> Layout:
    Config.reset()
    return Layout.from_config(Config(PROFILE))


def test_energy_wakeup_asset_bytes_and_runtime_yaml_semantics_are_frozen() -> None:
    assert hashlib.sha256(ASSET.read_bytes()).hexdigest() == ASSET_SHA256
    assert yaml.safe_load(RUNTIME_COPY.read_text(encoding="utf-8")) == yaml.safe_load(
        ASSET.read_text(encoding="utf-8")
    )
    text = RUNTIME_COPY.read_text(encoding="utf-8")
    assert "flowing_bands" not in text
    assert "onset_ripple" not in text
    assert "heat_fire" not in text


def test_energy_wakeup_load_compile_and_representative_render_are_unchanged() -> None:
    layout = _layout()
    show = load_show(RUNTIME_COPY, TargetCatalog.from_layout(layout))
    assert show == load_show(ASSET, TargetCatalog.from_layout(layout))

    for sequence, (timestamp, expected) in enumerate(RENDER_SHA256.items(), 1):
        runtime = ShowRuntime.from_layout(show, layout, seed=0)
        base = black_base_frame(
            timestamp=timestamp,
            sequence=sequence,
            analog_zones=layout.zones,
            digital_strips=layout.strips,
        )
        frame = runtime.render(
            EffectContext(
                timestamp=timestamp,
                delta_time=1.0 / 30.0,
                sequence=sequence,
            ),
            base,
        )
        assert _frame_digest(frame) == expected
