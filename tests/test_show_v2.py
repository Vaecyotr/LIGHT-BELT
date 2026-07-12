"""Show v2 authoring, normalization, color, path, origin, and branch contracts."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from light_engine.mapping import ZoneDef
from light_engine.effects.base import BaseEffect
from light_engine.models import DigitalStrip, EffectContext, PixelFrame
from light_engine.show import (
    ColorSpec,
    Cue,
    CueRenderJob,
    EffectSpec,
    ShowRuntime,
    ShowValidationError,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    black_base_frame,
    load_show,
    validate_show_data,
)


DIGITAL_IDS = tuple(f"strip_{label}" for label in (11, 12, 21, 22, 31, 41, 42, 43, 44, 45, 91, 92, 93))


def _catalog() -> TargetCatalog:
    return TargetCatalog(
        analog_zones={"zone_32"},
        digital_strips=DIGITAL_IDS,
        digital_groups={"right_wall": {"strip_42", "strip_43"}},
    )


def _data() -> dict:
    import yaml

    return yaml.safe_load(Path("config/shows/cabin-show-v2.yaml").read_text(encoding="utf-8"))


def _invalid(data: dict, path: str, reason: str | None = None) -> None:
    with pytest.raises(ShowValidationError) as exc:
        validate_show_data(data, _catalog())
    assert exc.value.path == path
    if reason:
        assert reason in exc.value.reason


def _strip(frame, strip_id: str):
    return next(strip for strip in frame.strips if strip.strip_id == strip_id)


def test_cabin_v2_has_three_paths_covering_all_fourteen_logical_runs() -> None:
    show = load_show(Path("config/shows/cabin-show-v2.yaml"), _catalog())
    golden = json.loads(Path("tests/goldens/show_orchestration/v2/cabin_authoring_contract.json").read_text(encoding="utf-8"))

    covered = {member.id for path in show.virtual_paths for member in path.targets}
    assert [path.id for path in show.virtual_paths] == golden["path_ids"]
    assert covered == set(golden["covered_targets"])
    assert show.cues[0].effect.id == "chase"
    assert show.cues[0].effect.params["width"] == 2
    assert show.cues[0].color.mode == "palette"
    assert show.cues[0].branches[0].after_target_id == golden["branch_after"]
    assert list(show.cues[0].branches[0].target.ids) == golden["same_frame_release"]


def test_v1_is_read_only_normalized_to_canonical_effect_fields() -> None:
    old = {
        "schema_version": 1,
        "show": {
            "id": "legacy",
            "duration": 1.0,
            "cues": [{
                "id": "old", "start": 0.0, "end": 1.0,
                "target": {"type": "digital_strip", "id": "strip_11"},
                "effect": {"mode": "fixed", "name": "static", "parameters": {"color": [1, 0, 0]}},
            }],
        },
    }

    show = validate_show_data(old, _catalog())

    assert show.schema_version == 1
    assert show.cues[0].effect.id == "static"
    assert show.cues[0].effect.params["color"] == [1, 0, 0]
    assert show.cues[0].effect.name == "static"  # read-only compatibility view
    assert show.cues[0].origin == "start"


@pytest.mark.parametrize(
    ("target", "path"),
    [
        ({"type": "digital_strip", "ids": ["strip_11"]}, "show.cues[0].target.ids"),
        ({"type": "digital_set", "id": "strip_11", "ids": ["strip_11"]}, "show.cues[0].target.id"),
        ({"type": "digital_set", "ids": ["missing"]}, "show.cues[0].target.ids[0]"),
        ({"type": "analog_group", "id": "anything"}, "show.cues[0].target.type"),
        ({"type": "unknown", "id": "strip_11"}, "show.cues[0].target.type"),
    ],
)
def test_v2_selector_shapes_and_types_fail_at_exact_paths(target: dict, path: str) -> None:
    data = _data()
    data["show"]["cues"][0]["target"] = target
    _invalid(data, path)


def test_v2_rejects_legacy_effect_names_and_unknown_nested_params() -> None:
    legacy = _data()
    legacy["show"]["cues"][0]["effect"] = {"mode": "fixed", "name": "chase", "parameters": {}}
    _invalid(legacy, "show.cues[0].effect.name", "unknown field")

    typo = _data()
    typo["show"]["cues"][0]["effect"]["params"]["widht"] = 2
    _invalid(typo, "show.cues[0].effect.params.widht", "unknown field")


@pytest.mark.parametrize("origin", ["start", "end", "center", "edges"])
def test_all_origin_modes_validate_for_paths_cues_and_branches(origin: str) -> None:
    data = _data()
    data["show"]["virtual_paths"][0]["origin"] = origin
    data["show"]["cues"][0]["origin"] = origin
    data["show"]["cues"][0]["branches"][0]["origin"] = origin
    show = validate_show_data(data, _catalog())
    assert show.virtual_paths[0].origin == origin
    assert show.cues[0].origin == origin
    assert show.cues[0].branches[0].origin == origin


def test_color_spec_shapes_are_strict_and_independent_from_effect_id() -> None:
    solid = _data()
    solid["show"]["cues"][0]["color"] = {"mode": "solid", "color": [0.2, 0.3, 0.4]}
    assert validate_show_data(solid, _catalog()).cues[0].color.color == pytest.approx((0.2, 0.3, 0.4))

    default = _data()
    default["show"]["cues"][0]["color"] = {"mode": "effect_default"}
    assert validate_show_data(default, _catalog()).cues[0].effect.id == "chase"

    bad = _data()
    bad["show"]["cues"][0]["color"] = {"mode": "palette", "colors": []}
    _invalid(bad, "show.cues[0].color.colors", "non-empty")


def test_strip_41_completion_releases_all_five_targets_in_same_logical_frame() -> None:
    data = _data()
    cue = data["show"]["cues"][0]
    cue["effect"] = {"mode": "fixed", "id": "static", "params": {}}
    cue["color"] = {"mode": "solid", "color": [1.0, 0.0, 0.0]}
    show = validate_show_data(data, _catalog())
    resolver = TargetResolver(
        analog_zones=(ZoneDef(id="zone_32"),),
        digital_strips=tuple(ZoneDef(id=strip_id, pixel_count=10 if strip_id == "strip_41" else 20) for strip_id in DIGITAL_IDS),
    )
    runtime = ShowRuntime(show, resolver)

    before = black_base_frame(timestamp=5.0, sequence=10, analog_zones=(ZoneDef(id="zone_32"),), digital_strips=resolver._digital_order)
    before = runtime.render(EffectContext(timestamp=5.0, delta_time=0.1, sequence=10), before)
    assert all(pixel == (0.0, 0.0, 0.0) for pixel in _strip(before, "strip_42").pixels)

    # strip_41 is 10/110 of the authored path, so it completes at 60 * 10/110.
    release_time = 60.0 * 10.0 / 110.0
    base = black_base_frame(timestamp=release_time, sequence=11, analog_zones=(ZoneDef(id="zone_32"),), digital_strips=resolver._digital_order)
    released = runtime.render(EffectContext(timestamp=release_time, delta_time=0.1, sequence=11), base)
    for strip_id in ("strip_42", "strip_43", "strip_44", "strip_45", "strip_93"):
        assert set(_strip(released, strip_id).pixels) == {(1.0, 0.0, 0.0)}


def test_branch_trigger_must_name_a_member_of_its_v2_path() -> None:
    data = _data()
    data["show"]["cues"][0]["branches"][0]["after"]["target"] = "strip_22"
    _invalid(data, "show.cues[0].branches[0].after.target", "member")


@pytest.mark.parametrize(
    ("color", "timestamp", "expected"),
    [
        ({"mode": "effect_default"}, 0.0, (0.2, 0.4, 0.8)),
        ({"mode": "solid", "color": [0.1, 0.2, 0.3]}, 0.0, (0.1, 0.2, 0.3)),
        ({"mode": "palette", "colors": [[1, 0, 0], [0, 1, 0]]}, 1.0, (0.0, 1.0, 0.0)),
    ],
)
def test_one_effect_runs_with_default_solid_and_palette_color(color, timestamp, expected) -> None:
    data = _data()
    cue = data["show"]["cues"][0]
    cue["target"] = {"type": "digital_strip", "id": "strip_11"}
    cue["effect"] = {"mode": "fixed", "id": "static", "params": {}}
    cue["color"] = color
    cue["branches"] = []
    show = validate_show_data(data, _catalog())
    strip = ZoneDef(id="strip_11", pixel_count=2)
    runtime = ShowRuntime(show, TargetResolver(analog_zones=(), digital_strips=(strip,)))
    base = black_base_frame(timestamp=timestamp, sequence=1, analog_zones=(), digital_strips=(strip,))
    frame = runtime.render(EffectContext(timestamp=timestamp, delta_time=0.1, sequence=1), base)
    assert _strip(frame, "strip_11").pixels[0] == pytest.approx(expected)


class _IndexEffect(BaseEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        values = [(index / 10.0, 0.0, 0.0) for index in range(4)]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[DigitalStrip(strip_id="strip_11", pixel_count=4, pixels=values)],
        )


class _RampEffect(BaseEffect):
    def process(self, ctx: EffectContext) -> PixelFrame:
        definition = ctx.mode_parameters["strip_defs"][0]
        count = definition["pixel_count"]
        values = [(index / 10.0, 0.0, 0.0) for index in range(count)]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[DigitalStrip(strip_id=definition["id"], pixel_count=count, pixels=values)],
        )


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("start", [0.0, 0.1, 0.2, 0.3]),
        ("end", [0.3, 0.2, 0.1, 0.0]),
        ("center", [0.3, 0.1, 0.1, 0.3]),
        ("edges", [0.0, 0.2, 0.2, 0.0]),
    ],
)
def test_origin_modes_have_deterministic_logical_coordinate_rendering(origin, expected) -> None:
    cue = Cue(
        id="origin",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip_11"),
        effect=EffectSpec(mode="fixed", id="static"),
        color=ColorSpec(),
        origin=origin,
    )
    resolver = TargetResolver(analog_zones=(), digital_strips=(ZoneDef(id="strip_11", pixel_count=4),))
    contribution = CueRenderJob(cue, 0, resolver, effect=_IndexEffect("index")).render(
        EffectContext(timestamp=0.0, delta_time=0.1, sequence=1)
    )
    assert [pixel[0] for pixel in contribution.digital[0].pixels] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("origin", "expected_indexes"),
    [
        ("start", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        ("end", [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]),
        ("center", [9, 7, 5, 3, 1, 1, 3, 5, 7, 9]),
        ("edges", [0, 2, 4, 6, 8, 8, 6, 4, 2, 0]),
    ],
)
def test_virtual_path_origin_is_inherited_and_changes_actual_path_rendering(
    origin: str, expected_indexes: list[int]
) -> None:
    data = _data()
    path = data["show"]["virtual_paths"][0]
    path["origin"] = origin
    cue = data["show"]["cues"][0]
    cue["target"] = {"type": "virtual_path", "id": path["id"]}
    cue["effect"] = {"mode": "fixed", "id": "static", "params": {}}
    cue.pop("origin", None)
    cue["branches"] = []
    show = validate_show_data(data, _catalog())
    strips = tuple(ZoneDef(id=strip_id, pixel_count=2) for strip_id in DIGITAL_IDS)
    resolver = TargetResolver(analog_zones=(ZoneDef(id="zone_32"),), digital_strips=strips)
    runtime = ShowRuntime(show, resolver, effect_factory=lambda _name: _RampEffect("ramp"))
    base = black_base_frame(timestamp=0.0, sequence=1, analog_zones=(), digital_strips=strips)

    frame = runtime.render(EffectContext(timestamp=0.0, delta_time=0.1, sequence=1), base)

    rendered = [
        pixel[0]
        for member in show.virtual_paths[0].targets
        for pixel in _strip(frame, member.id).pixels
    ]
    assert show.cues[0].origin is None
    assert runtime.jobs[0].origin == origin
    assert rendered == pytest.approx([index / 10.0 for index in expected_indexes])


def test_explicit_cue_origin_overrides_virtual_path_origin_in_rendering() -> None:
    data = _data()
    data["show"]["virtual_paths"][0]["origin"] = "end"
    cue = data["show"]["cues"][0]
    cue["target"] = {"type": "virtual_path", "id": "screen_to_top"}
    cue["effect"] = {"mode": "fixed", "id": "static", "params": {}}
    cue["origin"] = "start"
    cue["branches"] = []
    show = validate_show_data(data, _catalog())
    strips = tuple(ZoneDef(id=strip_id, pixel_count=2) for strip_id in DIGITAL_IDS)
    runtime = ShowRuntime(
        show,
        TargetResolver(analog_zones=(ZoneDef(id="zone_32"),), digital_strips=strips),
        effect_factory=lambda _name: _RampEffect("ramp"),
    )
    base = black_base_frame(timestamp=0.0, sequence=1, analog_zones=(), digital_strips=strips)
    frame = runtime.render(EffectContext(timestamp=0.0, delta_time=0.1, sequence=1), base)

    rendered = [
        pixel[0]
        for member in show.virtual_paths[0].targets
        for pixel in _strip(frame, member.id).pixels
    ]
    assert runtime.jobs[0].origin == "start"
    assert rendered == pytest.approx([index / 10.0 for index in range(10)])


def test_mixed_authored_path_renders_once_then_splits_without_strip_restarts() -> None:
    show = validate_show_data(_data(), _catalog())
    mixed = next(path for path in show.virtual_paths if path.id == "screen_to_bottom_and_left")
    cue = Cue(
        id="mixed",
        start=0.0,
        end=2.0,
        target=TargetSelector("virtual_path", id=mixed.id),
        effect=EffectSpec(mode="fixed", id="static"),
        origin="start",
    )
    mixed_show = type(show)(
        schema_version=2,
        id="mixed",
        duration=2.0,
        cues=(cue,),
        virtual_paths=(mixed,),
    )
    strips = tuple(ZoneDef(id=strip_id, pixel_count=2) for strip_id in DIGITAL_IDS)
    zone = ZoneDef(id="zone_32")
    resolver = TargetResolver(analog_zones=(zone,), digital_strips=strips)
    runtime = ShowRuntime(mixed_show, resolver, effect_factory=lambda _name: _RampEffect("ramp"))
    base = black_base_frame(timestamp=0.0, sequence=1, analog_zones=(zone,), digital_strips=strips)

    frame = runtime.render(EffectContext(timestamp=0.0, delta_time=0.1, sequence=1), base)

    assert [pixel[0] for pixel in _strip(frame, "strip_11").pixels] == pytest.approx([0.0, 0.1])
    assert [pixel[0] for pixel in _strip(frame, "strip_22").pixels] == pytest.approx([0.2, 0.3])
    analog = next(item for item in frame.zones if item.zone_id == "zone_32")
    assert analog.color.r > 0.0
    assert [pixel[0] for pixel in _strip(frame, "strip_91").pixels] == pytest.approx([0.5, 0.6])


def test_parallel_virtual_paths_fork_chase_after_shared_strip_without_phase_restart() -> None:
    show = load_show(Path("config/examples/cabin-show-fork-v2.yaml"), _catalog())
    strips = (
        ZoneDef(id="strip_11", pixel_count=10),
        ZoneDef(id="strip_12", pixel_count=40),
        ZoneDef(id="strip_91", pixel_count=20),
        ZoneDef(id="strip_92", pixel_count=20),
    )
    runtime = ShowRuntime(show, TargetResolver(analog_zones=(), digital_strips=strips))

    def render(timestamp: float, delta_time: float, sequence: int) -> PixelFrame:
        base = black_base_frame(
            timestamp=timestamp,
            sequence=sequence,
            analog_zones=(),
            digital_strips=strips,
        )
        return runtime.render(
            EffectContext(
                timestamp=timestamp,
                delta_time=delta_time,
                sequence=sequence,
            ),
            base,
        )

    render(0.0, 0.1, 1)
    before = render(0.9, 0.8, 2)
    assert _strip(before, "strip_11").pixels[9] == pytest.approx((0.1, 0.4, 1.0))
    for strip_id in ("strip_12", "strip_91", "strip_92"):
        assert all(pixel == (0.0, 0.0, 0.0) for pixel in _strip(before, strip_id).pixels)

    fork = render(1.0, 0.1, 3)
    assert all(pixel == (0.0, 0.0, 0.0) for pixel in _strip(fork, "strip_11").pixels)
    for strip_id in ("strip_12", "strip_91", "strip_92"):
        assert _strip(fork, strip_id).pixels[0] == pytest.approx((0.1, 0.4, 1.0))
        assert all(pixel == (0.0, 0.0, 0.0) for pixel in _strip(fork, strip_id).pixels[1:])
