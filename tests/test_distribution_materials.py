import json
import os
import subprocess
import stat
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts.compliance.generate_distribution_materials import generate


def test_copied_notices_are_not_excluded_by_environment_ignore_rules(tmp_path):
    root = make_root(tmp_path)
    (root / ".gitignore").write_text(".python/\n.venv/\nvenv/\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    output = root / "docs" / "compliance" / "generated"

    result = generate(root, output)

    for distribution in result["installed_python"]["distributions"]:
        for notice in distribution["license_files"]:
            path = (output / notice["copied_to"]).relative_to(root).as_posix()
            check = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--no-index", path],
                capture_output=True, text=True,
            )
            assert check.returncode == 1, f"Distribution notice would be omitted: {path}"


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "kiosk").mkdir(parents=True)
    (root / "assets" / "demo").mkdir(parents=True)
    (root / "tests" / "fixtures" / "audio").mkdir(parents=True)
    (root / "artifacts" / "runs").mkdir(parents=True)
    (root / "uv.lock").write_text(
        'version = 1\nrequires-python = ">=3.11"\n'
        '[[package]]\nname = "numpy"\nversion = "1.0"\n'
        '[[package]]\nname = "numpy"\nversion = "2.0"\n'
        'resolution-markers = ["python_full_version >= \'3.12\'"]\n',
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname="fixture"\n[dependency-groups]\ndev=["pytest>=8"]\n',
        encoding="utf-8",
    )
    (root / "kiosk" / "package-lock.json").write_text(
        json.dumps({
            "packages": {
                "": {"name": "fixture"},
                "node_modules/example": {
                    "version": "3.4.5", "license": "MIT",
                    "integrity": "sha512-example", "dev": True,
                    "optional": True, "os": ["linux"],
                },
            }
        }),
        encoding="utf-8",
    )
    (root / "assets" / "demo" / "media.mp4").write_bytes(b"demo media")
    (root / "assets" / "demo" / "subtitle.opus").write_bytes(b"opus")
    (root / "assets" / "demo" / "font.woff2").write_bytes(b"font")
    (root / "tests" / "fixtures" / "audio" / "fixture.wav").write_bytes(b"audio")
    (root / "artifacts" / "runs" / "capture.bin").write_bytes(b"run")
    installer = root / "scripts" / "deploy" / "rk3588"
    installer.mkdir(parents=True)
    (installer / "setup-system.sh").write_text(
        "apt-get install -y \\\n    mpv \\\n    pulseaudio\n",
        encoding="utf-8",
    )
    (root / "firmware" / "esp32_ws2811_node").mkdir(parents=True)
    (root / "firmware" / "stm32_rgbcct_node").mkdir(parents=True)
    (root / "firmware" / "esp32_ws2811_node" / "platformio.ini").write_text("[env]\n", encoding="utf-8")
    (root / "firmware" / "stm32_rgbcct_node" / "platformio.ini").write_text("[env]\n", encoding="utf-8")
    dist = root / ".python" / "Lib" / "site-packages" / "example-3.4.5.dist-info"
    (dist / "licenses").mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: example\nVersion: 3.4.5\nLicense: Unknown\n",
        encoding="utf-8",
    )
    (dist / "licenses" / "LICENSE").write_text("Example license text\n", encoding="utf-8")
    missing = root / ".python" / "Lib" / "site-packages" / "opaque-9.0.dist-info"
    missing.mkdir(parents=True)
    (missing / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: opaque\nVersion: 9.0\n",
        encoding="utf-8",
    )
    return root


def test_generator_preserves_versions_integrity_license_text_and_unknowns(tmp_path):
    root = make_root(tmp_path)
    output = tmp_path / "generated"

    result = generate(root, output, audit_date="2026-10-26")

    assert result["release_status"] == "BLOCKED"
    assert result["audit_date"] == "2026-10-26"
    assert result["system_packages"]["requested_packages"] == ["mpv", "pulseaudio"]
    assert result["system_packages"]["versions_pinned"] is False
    inventory = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
    locked = inventory["uv_lock"]["packages"]
    assert [(p["name"], p["version"]) for p in locked] == [
        ("numpy", "1.0"), ("numpy", "2.0")
    ]
    assert locked[1]["marker"] == ["python_full_version >= '3.12'"]
    npm = inventory["npm_lock"]["packages"]
    example = next(p for p in npm if p["name"] == "example")
    assert example["integrity"] == "sha512-example"
    assert example["dev"] is True and example["optional"] is True
    local = inventory["installed_python"]["distributions"]
    assert next(p for p in local if p["name"] == "example")["license_status"] == "license-file-found"
    assert next(p for p in local if p["name"] == "opaque")["license_status"] == "unknown"
    copied_license = next((output / "LICENSES").rglob("LICENSE"))
    assert copied_license.read_text(encoding="utf-8") == "Example license text\n"
    notices = (output / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "opaque" in notices and "unknown" in notices.lower()
    assert "example 3.4.5" in notices and "mpv" in notices
    assert result["media_inventory"]
    assert all(item["sha256"] and item["size_bytes"] for item in result["media_inventory"])
    inputs = json.loads((output / "source_inputs.json").read_text(encoding="utf-8"))
    assert any(item["path"] == "uv.lock" and item["sha256"] for item in inputs["inputs"])
    assert any(item["path"] == "firmware/esp32_ws2811_node/platformio.ini" for item in inputs["inputs"])
    assert any(item["path"] == "firmware/stm32_rgbcct_node/platformio.ini" for item in inputs["inputs"])
    assert any(item["path"].endswith("subtitle.opus") for item in result["media_inventory"])
    assert any(item["path"].endswith("font.woff2") for item in result["media_inventory"])


def test_scan_limit_and_unavailable_git_are_visible(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    import scripts.compliance.generate_distribution_materials as generator

    monkeypatch.setattr(generator, "MAX_WALK_FILES", 1)
    result = generate(root, tmp_path / "generated")

    assert result["git"]["available"] is False
    assert result["git"]["dirty"] is None
    assert any("limit" in warning.lower() for warning in result["warnings"])
    source = json.loads((tmp_path / "generated" / "source_inputs.json").read_text(encoding="utf-8"))
    assert source["warnings"] == result["warnings"]


def test_media_walk_prunes_simulated_reparse_directory(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    reparse = root / "assets" / "junction"
    reparse.mkdir()
    (reparse / "outside.mp4").write_bytes(b"outside")
    original_lstat = Path.lstat

    def simulated_lstat(path):
        info = original_lstat(path)
        if path == reparse:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", simulated_lstat)
    result = generate(root, tmp_path / "generated")

    assert all("outside.mp4" not in item["path"] for item in result["media_inventory"])
    assert any("reparse" in warning.lower() for warning in result["warnings"])


def test_unsafe_record_license_path_is_not_copied(tmp_path):
    root = make_root(tmp_path)
    site = root / ".python" / "Lib" / "site-packages"
    dist = site / "escape-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: escape\nVersion: 1.0\n", encoding="utf-8")
    (dist / "RECORD").write_text("../../outside/LICENSE,,\n", encoding="utf-8")
    outside = site.parent / "outside" / "LICENSE"
    outside.parent.mkdir()
    outside.write_text("must not copy", encoding="utf-8")

    result = generate(root, tmp_path / "generated")

    escape = next(item for item in result["installed_python"]["distributions"] if item["name"] == "escape")
    assert escape["license_status"] == "unknown"
    assert not list((tmp_path / "generated" / "LICENSES").rglob("*outside*"))
    assert any("outside site-packages" in warning for warning in result["warnings"])


def test_existing_output_tree_reparse_point_is_rejected(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    output = tmp_path / "generated"
    output.mkdir()
    nested = output / "linked"
    nested.mkdir()
    original_lstat = Path.lstat

    def simulated_lstat(path):
        info = original_lstat(path)
        if path == nested:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", simulated_lstat)

    with pytest.raises(ValueError, match="symlink or junction"):
        generate(root, output)


def test_media_walk_does_not_follow_symlink_outside_root(tmp_path):
    root = make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(b"not part of repo")
    try:
        os.symlink(outside, root / "assets" / "linked", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")

    result = generate(root, tmp_path / "generated")

    assert all("secret.mp4" not in item["path"] for item in result["media_inventory"])

