"""Phase 40 software-contract and authoring-navigation freeze checks."""

from __future__ import annotations

from pathlib import Path

from scripts.export_authoring_contract import authoring_contract


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/current/show-authoring-source-index.md"
GUIDE = ROOT / "docs/current/ANTIGRAVITY_SHOW_AUTHORING_MANUAL_TASK.md"


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


def test_antigravity_guide_contains_exact_authority_and_all_30_sections() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    authorities = (
        "1. [CLAUDE.md]",
        "2. [CLOSED_LOOP_SPEC.md]",
        "3. [IMPLEMENTATION_PLAN.md]",
        "4. [current Show authoring documentation]",
        "5. live EffectRegistry / exported authoring contract",
        "6. current implementation",
        "7. focused tests and examples",
    )
    for authority in authorities:
        assert authority in text

    headings = (
        "1. What the system is",
        "2. Minimal mental model",
        "3. What the APP controls vs what Show YAML controls",
        "4. Anatomy of one Show",
        "5. Anatomy of one cue",
        "6. Targets / strip IDs / logical paths",
        "7. Common controls",
        "8. Four common spatial origins",
        "9. Motion speed semantics",
        "10. Complete effect catalog",
        "11. For **every** effect",
        "12. ScalarSource",
        "13. Existing `audio_modulation`",
        "14. `parameter_modulation`",
        "15. `modulate` vs `drive`",
        "16. Dominant-frequency explicit normalization",
        "17. ColorSource",
        "18. Spatial palettes",
        "19. Audio-driven colors",
        "20. Video-driven colors",
        "21. `virtual_path`",
        "22. Branch `after`",
        "23. `start_on_release`",
        "24. `pre_roll`",
        "25. Color timeline",
        "26. Combining multiple mechanisms",
        "27. Several complete practical recipes",
        "28. Invalid/unsafe combinations",
        "29. Debugging and validation",
        "30. Glossary",
    )
    positions = [text.index(heading) for heading in headings]
    assert positions == sorted(positions)


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
    for discovery_source in (
        "scripts\\export_authoring_contract.py",
        "light_engine\\effects\\scalar_source.py",
        "docs\\reference\\parameter-modulation.md",
        "docs\\reference\\color-source.md",
        "tests/test_virtual_paths.py",
        "tests/test_show_branch_lifecycle_schema_phase34.py",
        "tests/test_app_host_api_v1_freeze.py",
    ):
        assert discovery_source in text


def test_guide_verification_guards_product_boundaries() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for required in (
        "every registered effect is documented exactly once",
        "every authorable parameter spec is represented",
        "enum choices agree with the live registry",
        "accurate hardware/software terminology is used",
        "ColorSource color sampling vs base renderer brightness envelope is clearly explained",
        "no claim says the APP edits individual effects",
        "no global low-frequency color meaning is claimed",
        "Energy Wakeup is only an existing compatible Show",
    ):
        assert required in text


