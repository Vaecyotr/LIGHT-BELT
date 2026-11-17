"""Phase 40 software-contract and authoring-navigation freeze checks."""

from __future__ import annotations

from pathlib import Path

from scripts.dev.export_authoring_contract import authoring_contract


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/current/show-authoring-source-index.md"
GUIDE = ROOT / "docs/current/SHOW_AUTHORING_TEAMMATE_MANUAL.md"


def test_phase40_plan_declares_bounded_closed_frozen_state() -> None:
    plan = (ROOT / "docs/IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    assert "Phase 40 lighting-language software-contract closure accepted" in plan
    assert "CLOSED/FROZEN" in plan
    assert "Do not begin or prepare Phase 41" in plan
    assert "Repository-wide pytest is explicitly user-waived" in plan
    assert "NOT HARDWARE VERIFIED" in plan


def test_authoring_index_links_every_required_authority_and_source() -> None:
    text = INDEX.read_text(encoding="utf-8")
    required = (
        "CLAUDE.md",
        "CLOSED_LOOP_SPEC.md",
        "IMPLEMENTATION_PLAN.md",
        "show-v2-authoring.md",
        "effect-reference.md",
        "effect-parameter-metadata.md",
        "export_authoring_contract.py",
        "light_engine/models.py",
        "wled-audio-sync-v2.md",
        "color-source.md",
        "parameter-modulation.md",
        "test_virtual_paths.py",
        "test_show_branch_lifecycle_schema_phase34.py",
        "config/layout.yaml",
        "config/profiles/rk3588-host-service.yaml",
        "host-api-v1.md",
        "host-api-v1.openapi.yaml",
        "test_app_host_api_v1_freeze.py",
    )
    for item in required:
        assert item in text
    assert "CLOSED/FROZEN" in text
    assert "not hardware or product-release verification" in text


def test_teammate_manual_explains_frozen_authoring_contract() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "不是高于源码/合同的第二套权威" in text
    assert "22 个 Native Effect" in text
    for topic in ("parameter_modulation", "ColorSource", "virtual_path", "pre_roll"):
        assert topic in text


def test_guide_discovery_reaches_the_frozen_live_inventory() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    contract = authoring_contract()
    effects = contract["effects"]
    assert isinstance(effects, list)
    assert len(effects) == 22
    parameters = [parameter for effect in effects for parameter in effect["parameters"]]
    assert len(parameters) == 111
    assert sum(bool(parameter["modulatable"]) for parameter in parameters) == 11
    assert {effect["color_source_support"] for effect in effects} == {
        "GLOBAL",
        "POSITIONAL",
        "EVENT",
        "NOT_APPLICABLE",
    }
    for source in (
        "timeline",
        "spatial_palette",
        "video_average",
        "video_dominant",
        "audio_spectrum_palette",
        "dominant_frequency_palette",
    ):
        assert source in (ROOT / "docs/reference/color-source.md").read_text(
            encoding="utf-8"
        )
