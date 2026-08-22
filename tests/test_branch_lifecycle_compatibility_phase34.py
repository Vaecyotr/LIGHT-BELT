"""Phase 34 compatibility contracts for existing bounded Show v2 branches."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from light_engine.mapping import ZoneDef
from light_engine.models import EffectContext, PixelFrame
from light_engine.show import (
    ShowRuntime,
    TargetCatalog,
    TargetResolver,
    black_base_frame,
    validate_show_data,
)


_FIXTURE = Path("config/shows/archive/cabin-v2/cabin-show-v2.yaml")
_DIGITAL_IDS = tuple(
    f"strip_{label}" for label in (11, 12, 21, 22, 31, 41, 42, 43, 44, 45, 91, 92, 93)
)
_RELEASE_TARGETS = ("strip_42", "strip_43", "strip_44", "strip_45", "strip_93")


def _fixture_data() -> dict:
    import yaml

    return yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))


def _catalog() -> TargetCatalog:
    return TargetCatalog(analog_zones={"zone_32"}, digital_strips=_DIGITAL_IDS)


def _runtime(data: dict) -> tuple[ShowRuntime, tuple[ZoneDef, ...]]:
    show = validate_show_data(data, _catalog())
    strips = tuple(
        ZoneDef(id=strip_id, pixel_count=10 if strip_id == "strip_41" else 20)
        for strip_id in _DIGITAL_IDS
    )
    resolver = TargetResolver((ZoneDef(id="zone_32"),), strips)
    return ShowRuntime(show, resolver), strips


def _render(runtime: ShowRuntime, strips: tuple[ZoneDef, ...], *, timestamp: float, sequence: int) -> PixelFrame:
    base = black_base_frame(
        timestamp=timestamp,
        sequence=sequence,
        analog_zones=(ZoneDef(id="zone_32"),),
        digital_strips=strips,
    )
    return runtime.render(
        EffectContext(timestamp=timestamp, delta_time=0.1, sequence=sequence), base
    )


def _branch_pixels(frame: PixelFrame) -> dict[str, list[tuple[float, float, float]]]:
    return {
        strip.strip_id: strip.pixels
        for strip in frame.strips
        if strip.strip_id in _RELEASE_TARGETS
    }


def _has_light(pixels: dict[str, list[tuple[float, float, float]]]) -> bool:
    return any(channel > 0.0 for strip in pixels.values() for pixel in strip for channel in pixel)


def test_archived_branch_fixture_omits_lifecycle_but_normalizes_to_start_on_release() -> None:
    data = _fixture_data()
    raw_branch = data["show"]["cues"][0]["branches"][0]
    assert "lifecycle" not in raw_branch  # The archived source is intentionally unchanged.

    omitted = validate_show_data(data, _catalog())
    explicit_data = deepcopy(data)
    explicit_data["show"]["cues"][0]["branches"][0]["lifecycle"] = "start_on_release"
    explicit = validate_show_data(explicit_data, _catalog())

    assert omitted.cues[0].branches[0] == explicit.cues[0].branches[0]
    assert omitted.cues[0].branches[0].lifecycle == "start_on_release"
    # The compatibility field must not reinterpret the authored path or target.
    assert omitted.virtual_paths == explicit.virtual_paths
    assert omitted.cues[0].target == explicit.cues[0].target


def test_omitted_lifecycle_keeps_archived_release_timing_and_output() -> None:
    omitted_data = _fixture_data()
    explicit_data = deepcopy(omitted_data)
    explicit_data["show"]["cues"][0]["branches"][0]["lifecycle"] = "start_on_release"
    omitted, strips = _runtime(omitted_data)
    explicit, _ = _runtime(explicit_data)

    # strip_41 is 10 / 110 of the existing authored virtual path.
    release_time = 60.0 * 10.0 / 110.0
    before_omitted = _render(omitted, strips, timestamp=release_time - 0.001, sequence=1)
    before_explicit = _render(explicit, strips, timestamp=release_time - 0.001, sequence=1)
    assert _branch_pixels(before_omitted) == _branch_pixels(before_explicit)
    assert not _has_light(_branch_pixels(before_omitted))

    released_omitted = _render(omitted, strips, timestamp=release_time, sequence=2)
    released_explicit = _render(explicit, strips, timestamp=release_time, sequence=2)
    assert _branch_pixels(released_omitted) == _branch_pixels(released_explicit)
    assert _has_light(_branch_pixels(released_omitted))


def test_omitted_lifecycle_keeps_stateful_chase_fresh_until_first_visible_frame() -> None:
    historical, strips = _runtime(_fixture_data())
    pristine, _ = _runtime(_fixture_data())
    release_time = 60.0 * 10.0 / 110.0

    # These live parent frames must not advance an omitted/start_on_release
    # branch's stateful ChaseEffect while that branch is hidden.
    _render(historical, strips, timestamp=0.0, sequence=1)
    _render(historical, strips, timestamp=release_time - 0.001, sequence=2)
    first_after_history = _render(historical, strips, timestamp=release_time, sequence=3)
    first_pristine = _render(pristine, strips, timestamp=release_time, sequence=3)

    assert _branch_pixels(first_after_history) == _branch_pixels(first_pristine)
    assert _has_light(_branch_pixels(first_after_history))


@pytest.mark.parametrize("lifecycle", ["start_on_release", "pre_roll"])
def test_lifecycle_does_not_change_authored_virtual_path_or_branch_target(lifecycle: str) -> None:
    data = _fixture_data()
    original_path = deepcopy(data["show"]["virtual_paths"])
    original_target = deepcopy(data["show"]["cues"][0]["branches"][0]["target"])
    data["show"]["cues"][0]["branches"][0]["lifecycle"] = lifecycle

    show = validate_show_data(data, _catalog())

    assert [(path.id, path.origin) for path in show.virtual_paths] == [
        (path["id"], path["origin"]) for path in original_path
    ]
    assert [
        [(target.kind, target.id, target.ids) for target in path.targets]
        for path in show.virtual_paths
    ] == [
        [(target["type"], target.get("id"), tuple(target.get("ids", ()))) for target in path["targets"]]
        for path in original_path
    ]
    assert show.cues[0].branches[0].target.ids == tuple(original_target["ids"])
