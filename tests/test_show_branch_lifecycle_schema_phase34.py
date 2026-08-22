"""Focused Show v2 branch lifecycle schema contracts for Phase 34."""

from pathlib import Path

import pytest
import yaml

from light_engine.show import (
    CueBranchSpec,
    ShowValidationError,
    TargetCatalog,
    TargetSelector,
    validate_show_data,
)


_FIXTURE = Path("config/shows/archive/cabin-v2/cabin-show-v2.yaml")
_DIGITAL_IDS = tuple(
    f"strip_{label}"
    for label in (11, 12, 21, 22, 31, 41, 42, 43, 44, 45, 91, 92, 93)
)


def _catalog() -> TargetCatalog:
    return TargetCatalog(
        analog_zones={"zone_32"},
        digital_strips=_DIGITAL_IDS,
        digital_groups={"right_wall": {"strip_42", "strip_43"}},
    )


def _show_data() -> dict:
    return yaml.safe_load(_FIXTURE.read_text(encoding="utf-8"))


def test_omitted_lifecycle_defaults_to_start_on_release_for_archived_v2_fixture() -> None:
    data = _show_data()
    assert "lifecycle" not in data["show"]["cues"][0]["branches"][0]

    show = validate_show_data(data, _catalog())

    assert show.schema_version == 2
    assert show.cues[0].branches[0].lifecycle == "start_on_release"


@pytest.mark.parametrize("lifecycle", ["start_on_release", "pre_roll"])
def test_explicit_branch_lifecycle_values_are_preserved(lifecycle: str) -> None:
    data = _show_data()
    data["show"]["cues"][0]["branches"][0]["lifecycle"] = lifecycle

    show = validate_show_data(data, _catalog())

    assert show.cues[0].branches[0].lifecycle == lifecycle


def test_invalid_branch_lifecycle_is_rejected_at_exact_schema_path() -> None:
    data = _show_data()
    data["show"]["cues"][0]["branches"][0]["lifecycle"] = "on_activation"

    with pytest.raises(ShowValidationError) as exc:
        validate_show_data(data, _catalog())

    assert exc.value.path == "show.cues[0].branches[0].lifecycle"
    assert "start_on_release" in exc.value.reason
    assert "pre_roll" in exc.value.reason


def test_cue_branch_model_default_matches_loader_default() -> None:
    branch = CueBranchSpec(
        path_id="path",
        after_target_id="strip_41",
        target=TargetSelector(kind="digital_set", ids=("strip_42",)),
    )

    assert branch.lifecycle == "start_on_release"
