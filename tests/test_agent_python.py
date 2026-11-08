from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / "agents" / f"{name}.py"
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


@pytest.mark.parametrize(
    "stderr",
    [
        "fatal: cannot remove: worktree contains modified or untracked files",
        "fatal: failed to remove: worktree is locked",
        "fatal: worktree is not registered",
    ],
    ids=["dirty", "locked", "unknown"],
)
@pytest.mark.parametrize("force", [False, True])
def test_cleanup_failure_preserves_worktree_and_python_link(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
    force: bool,
) -> None:
    repo = tmp_path / "repo"
    worktree = repo / ".agent-worktrees" / "phase-01"
    python_link = worktree / ".python"
    python_link.parent.mkdir(parents=True)
    python_link.mkdir()
    shared_target = tmp_path / "shared-python"
    shared_target.mkdir()
    (shared_target / "venv-marker.txt").write_text("shared", encoding="utf-8")
    (worktree / "user-data.txt").write_text("preserve", encoding="utf-8")
    calls: list[list[str]] = []
    rmtree_calls: list[Path] = []

    def fake_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert not python_link.exists(), "Git must not traverse the shared junction"
        assert (
            (shared_target / "venv-marker.txt").read_text(encoding="utf-8")
            == "shared"
        )
        return subprocess.CompletedProcess(
            ["git", *args], 1, "", stderr
        )

    def simulate_link_removal(path: Path) -> None:
        # A Windows junction can be unlinked without following its target.
        # Model that unlink with a fixture directory so this test needs no
        # elevated symlink privileges.
        (path / ".python").rmdir()

    def forbidden_rmtree(path: Path) -> None:
        rmtree_calls.append(path)
        raise AssertionError("worktree cleanup must never recursively delete")

    monkeypatch.setattr(agent_worktree, "run_git", fake_git)
    monkeypatch.setattr(
        agent_worktree, "_remove_python_link_if_present", simulate_link_removal
    )
    monkeypatch.setattr(
        agent_worktree,
        "shutil",
        SimpleNamespace(rmtree=forbidden_rmtree),
        raising=False,
    )

    with pytest.raises(agent_worktree.WorktreeError):
        agent_worktree.cleanup_worktree(repo, phase_id="phase-01", force=force)

    assert worktree.is_dir()
    assert not python_link.exists()
    assert (shared_target / "venv-marker.txt").read_text(encoding="utf-8") == "shared"
    assert (worktree / "user-data.txt").read_text(encoding="utf-8") == "preserve"
    assert not rmtree_calls
    assert len(calls) == 1
    assert calls[0][:3] == ["worktree", "remove", str(worktree)]
    assert ("--force" in calls[0]) is force


def test_cleanup_success_with_residual_fails_without_recursive_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    worktree = repo / ".agent-worktrees" / "phase-01"
    worktree.mkdir(parents=True)
    (worktree / "residual.txt").write_text("residual", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[:3] == ["show-ref", "--verify", "--quiet"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "")
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    monkeypatch.setattr(agent_worktree, "run_git", fake_git)
    rmtree_calls: list[Path] = []
    monkeypatch.setattr(
        agent_worktree,
        "shutil",
        SimpleNamespace(rmtree=lambda path: rmtree_calls.append(path)),
        raising=False,
    )

    with pytest.raises(agent_worktree.WorktreeError, match="still exists"):
        agent_worktree.cleanup_worktree(repo, phase_id="phase-01", force=False)

    assert worktree.is_dir()
    assert not rmtree_calls
    assert calls[0] == ["worktree", "remove", str(worktree)]
    assert len(calls) == 1


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
