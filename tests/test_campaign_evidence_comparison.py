"""Maintenance contract for provenance-aware historical evidence comparison."""

import json
import subprocess

import pytest


@pytest.mark.parametrize("difference", ["provenance_only", "rendered_value", "nested_provenance"])
def test_campaign_comparison_ignores_only_top_level_generation_commit(
    tmp_path, assert_campaign_evidence, difference,
):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    old = {"generated_from_head": "0" * 40, "frame": {"value": 0.5, "generated_from_head": "payload"}}
    new = {"generated_from_head": head, "frame": dict(old["frame"])}
    if difference == "rendered_value":
        new["frame"]["value"] = 0.6
    elif difference == "nested_provenance":
        new["frame"]["generated_from_head"] = "changed"
    actual, recorded = tmp_path / "new.json", tmp_path / "old.json"
    actual.write_text(json.dumps(new), encoding="utf-8")
    recorded.write_text(json.dumps(old), encoding="utf-8")
    if difference == "provenance_only":
        assert_campaign_evidence(actual, recorded)
    else:
        with pytest.raises(AssertionError):
            assert_campaign_evidence(actual, recorded)
