from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_context(tmp_path: Path):
    repo_root = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    phase_id = "phase-8-config-profiles"
    task_relative = Path(".agent/tasks/phase-8-config-profiles.md")

    write(worktree / ".agent/prompts/implementer.md", "IMPLEMENTER BASE")
    write(worktree / ".agent/prompts/repairer.md", "REPAIRER BASE")
    write(worktree / ".agent/prompts/reviewer.md", "REVIEWER BASE")
    write(worktree / ".agent/review.schema.json", '{"type":"object"}')
    write(worktree / task_relative, "# Phase 8\n\n## Acceptance Criteria\n- ok\n")

    task = agent_pipeline.TaskSpec(
        phase_id=phase_id,
        task_path=repo_root / task_relative,
        task_relative=task_relative,
        allowed_patterns=("scripts/agent_pipeline.py",),
        forbidden_patterns=(),
        targeted_commands=(".\\.python\\Scripts\\python.exe -m pytest tests/test_agent_prompts.py -q",),
        full_commands=(".\\.python\\Scripts\\python.exe -m pytest -q",),
        commit_message="Phase 8: Configuration upgrade",
    )
    return agent_pipeline.PipelineContext(
        repo_root=repo_root,
        base_branch="main",
        base_commit="abc123",
        worktree_path=worktree,
        agent_branch=f"agent/{phase_id}",
        report_dir=repo_root / ".agent" / "reports" / phase_id,
        project_python=repo_root / ".python" / "Scripts" / "python.exe",
        task=task,
    )


def test_implement_prompt_makes_task_primary_context(tmp_path: Path) -> None:
    ctx = make_context(tmp_path)

    prompt = agent_pipeline.build_implement_prompt(ctx, 1)

    assert "Task file: `.agent/tasks/phase-8-config-profiles.md`" in prompt
    assert "Treat the task file as the primary specification" in prompt
    assert "Do not read docs/CLOSED_LOOP_SPEC.md or docs/IMPLEMENTATION_PLAN.md in full" in prompt
    assert "read only the current Phase section" in prompt


def test_repair_prompt_supplies_quality_path_and_diff_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ctx = make_context(tmp_path)
    quality = {
        "iteration": 1,
        "passed": False,
        "commands": [{"command": "pytest", "returncode": 1}],
        "changed_files": ["scripts/agent_pipeline.py"],
        "scope_error": "",
        "recorded_at_utc": "2026-07-05T00:00:00+00:00",
    }
    write(
        ctx.worktree_path
        / ".agent"
        / "reports"
        / ctx.task.phase_id
        / "quality-gate-1.json",
        json.dumps(quality),
    )
    monkeypatch.setattr(
        agent_pipeline,
        "git_diff_text",
        lambda _ctx: "diff --git a/scripts/agent_pipeline.py b/scripts/agent_pipeline.py\n",
    )

    prompt = agent_pipeline.build_repair_prompt(
        ctx,
        2,
        {"verdict": "FAIL", "required_actions": ["Fix the failing test."]},
    )

    quality_path = ".agent/reports/phase-8-config-profiles/quality-gate-1.json"
    diff_path = ".agent/reports/phase-8-config-profiles/current-diff-for-repair-2.patch"
    assert f"Latest quality-gate report: `{quality_path}`" in prompt
    assert f"Current diff artifact: `{diff_path}`" in prompt
    assert "Fix the failing test." in prompt
    assert (ctx.worktree_path / diff_path).read_text(encoding="utf-8").startswith(
        "diff --git"
    )
    assert (ctx.report_dir / "current-diff-for-repair-2.patch").is_file()


def test_run_quality_gate_writes_report_inside_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ctx = make_context(tmp_path)

    monkeypatch.setattr(
        agent_pipeline,
        "shell_command",
        lambda command, cwd, timeout: agent_pipeline.subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="ok",
            stderr="",
        ),
    )
    monkeypatch.setattr(agent_pipeline, "enforce_file_scope", lambda _ctx: [])

    payload = agent_pipeline.run_quality_gate(ctx, iteration=1, timeout=1)

    assert payload["passed"] is True
    worktree_report = (
        ctx.worktree_path
        / ".agent"
        / "reports"
        / ctx.task.phase_id
        / "quality-gate-1.json"
    )
    retained_report = ctx.report_dir / "quality-gate-1.json"
    assert json.loads(worktree_report.read_text(encoding="utf-8"))["passed"] is True
    assert json.loads(retained_report.read_text(encoding="utf-8"))["passed"] is True


def test_repairer_prompt_has_single_diff_read_item() -> None:
    text = (ROOT / ".agent" / "prompts" / "repairer.md").read_text(
        encoding="utf-8-sig"
    )

    assert "The current Git diff for files connected" not in text
    assert "The current git diff" not in text
    assert text.count("current Git diff artifact") == 1
