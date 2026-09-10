"""Shared historical-campaign evidence, generated once per test session."""

import json
import subprocess

import pytest


@pytest.fixture(scope="session")
def single_strip_regeneration(tmp_path_factory):
    from scripts.generate_single_strip_acceptance_campaign import generate

    root = tmp_path_factory.mktemp("single-strip-evidence")
    output, baseline = root / "show", root / "baseline"
    generate(output, baseline)
    return output, baseline


@pytest.fixture(scope="session")
def assert_campaign_evidence():
    """Compare all behavior; separately validate generation provenance."""
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    def compare(generated_path, recorded_path):
        actual = json.loads(generated_path.read_text(encoding="utf-8"))
        expected = json.loads(recorded_path.read_text(encoding="utf-8"))
        assert actual.pop("generated_from_head") == head
        historical_head = expected.pop("generated_from_head")
        assert len(historical_head) == 40
        assert all(c in "0123456789abcdef" for c in historical_head)
        assert actual == expected

    return compare
