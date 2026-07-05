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


def test_pipeline_prefers_standard_venv_python(tmp_path: Path) -> None:
    standard = tmp_path / ".python" / "Scripts" / "python.exe"
    legacy = tmp_path / ".python" / "python.exe"
    touch(standard)
    touch(legacy)

    assert agent_pipeline.find_project_python(tmp_path) == standard


def test_pipeline_accepts_legacy_project_python(tmp_path: Path) -> None:
    legacy = tmp_path / ".python" / "python.exe"
    touch(legacy)

    assert agent_pipeline.find_project_python(tmp_path) == legacy


def test_pipeline_reports_missing_project_python(tmp_path: Path) -> None:
    with pytest.raises(agent_pipeline.PipelineError, match="Project Python"):
        agent_pipeline.find_project_python(tmp_path)


def test_campaign_prefers_standard_venv_python(tmp_path: Path) -> None:
    standard = tmp_path / ".python" / "Scripts" / "python.exe"
    legacy = tmp_path / ".python" / "python.exe"
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
