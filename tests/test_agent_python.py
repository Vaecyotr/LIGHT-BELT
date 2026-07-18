from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent_pipeline = load_script("agent_pipeline")
agent_campaign = load_script("agent_campaign")
agent_worktree = load_script("agent_worktree")


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def project_python_paths(root: Path) -> tuple[Path, Path]:
    if sys.platform == "win32":
        return (
            root / ".python" / "Scripts" / "python.exe",
            root / ".python" / "python.exe",
        )
    return (
        root / ".python" / "bin" / "python",
        root / ".python" / "python",
    )


def test_pipeline_prefers_standard_venv_python(tmp_path: Path) -> None:
    standard, legacy = project_python_paths(tmp_path)
    touch(standard)
    touch(legacy)

    assert agent_pipeline.find_project_python(tmp_path) == standard


def test_pipeline_accepts_legacy_project_python(tmp_path: Path) -> None:
    _, legacy = project_python_paths(tmp_path)
    touch(legacy)

    assert agent_pipeline.find_project_python(tmp_path) == legacy


def test_pipeline_reports_missing_project_python(tmp_path: Path) -> None:
    with pytest.raises(agent_pipeline.PipelineError, match="Project Python"):
        agent_pipeline.find_project_python(tmp_path)


def test_campaign_prefers_standard_venv_python(tmp_path: Path) -> None:
    standard, legacy = project_python_paths(tmp_path)
    touch(standard)
    touch(legacy)

    assert agent_campaign.find_project_python(tmp_path) == standard


def test_worktree_cleanup_refuses_real_python_directory(tmp_path: Path) -> None:
    python_dir = tmp_path / ".python"
    python_dir.mkdir()

    if os.name == "nt":
        message = "not a junction or symlink"
    else:
        message = "not a symlink"

    with pytest.raises(agent_worktree.WorktreeError, match=message):
        agent_worktree._remove_python_link_if_present(tmp_path)

    assert python_dir.is_dir()


class _FakeReparseStat:
    st_file_attributes = getattr(
        agent_pipeline.stat,
        "FILE_ATTRIBUTE_REPARSE_POINT",
        0x400,
    )


class _FakePath:
    def __init__(self, result):
        self.result = result
        self.stat_called = False
        self.lstat_called = False

    def stat(self):
        self.stat_called = True
        raise AssertionError("stat() must not be used for junction detection")

    def lstat(self):
        self.lstat_called = True
        return self.result


def test_pipeline_reparse_detection_uses_lstat() -> None:
    fake = _FakePath(_FakeReparseStat())
    assert agent_pipeline.is_windows_reparse_point(fake)
    assert fake.lstat_called
    assert not fake.stat_called


def test_worktree_reparse_detection_uses_lstat() -> None:
    fake = _FakePath(_FakeReparseStat())
    assert agent_worktree._is_windows_reparse_point(fake)
    assert fake.lstat_called
    assert not fake.stat_called
