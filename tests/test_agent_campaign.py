from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_script(filename: str, module_name: str):
    path = ROOT / "scripts" / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


agent_campaign = load_script("agent_campaign", "agent_campaign_model_tests")
agent_pipeline = load_script("agent_pipeline", "agent_pipeline_model_tests")


def write_manifest(tmp_path: Path, step: dict[str, object]) -> Path:
    path = tmp_path / "campaign.json"
    path.write_text(
        json.dumps(
            {
                "campaign_branch": "campaign/test",
                "start_branch": "main",
                "steps": [step],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_manifest_loads_optional_model_configuration(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        {
            "phase_id": "phase-24-authority-topology-contract",
            "task": ".agent/tasks/phase-24-authority-topology-contract.md",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "xhigh",
            "max_repairs": 1,
        },
    )

    _, _, steps = agent_campaign.load_manifest(tmp_path, path)

    assert steps[0].model == "gpt-5.6-sol"
    assert steps[0].reasoning_effort == "xhigh"
    assert steps[0].max_repairs == 1


def test_legacy_manifest_inherits_global_codex_configuration(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        {
            "phase_id": "phase-4-output-transform-health",
            "task": ".agent/tasks/phase-4-output-transform-health.md",
        },
    )

    _, _, steps = agent_campaign.load_manifest(tmp_path, path)

    assert steps[0].model is None
    assert steps[0].reasoning_effort is None


@pytest.mark.parametrize("effort", ["", "low", "extra-high", "HIGH"])
def test_manifest_rejects_invalid_reasoning_effort(
    tmp_path: Path, effort: str
) -> None:
    path = write_manifest(
        tmp_path,
        {
            "phase_id": "phase-24-authority-topology-contract",
            "task": ".agent/tasks/phase-24-authority-topology-contract.md",
            "reasoning_effort": effort,
        },
    )

    with pytest.raises(agent_campaign.CampaignError, match="reasoning_effort"):
        agent_campaign.load_manifest(tmp_path, path)


def test_manifest_rejects_non_string_model(tmp_path: Path) -> None:
    path = write_manifest(
        tmp_path,
        {
            "phase_id": "phase-24-authority-topology-contract",
            "task": ".agent/tasks/phase-24-authority-topology-contract.md",
            "model": 56,
        },
    )

    with pytest.raises(agent_campaign.CampaignError, match="model"):
        agent_campaign.load_manifest(tmp_path, path)


def test_completed_phase_is_skipped_without_starting_pipeline(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    step = agent_campaign.CampaignStep(
        phase_id="phase-24-authority-topology-contract",
        task=Path(".agent/tasks/phase-24-authority-topology-contract.md"),
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        max_repairs=1,
    )
    monkeypatch.setattr(agent_campaign, "phase_already_applied", lambda *_: True)
    monkeypatch.setattr(
        agent_campaign,
        "run",
        lambda *_args, **_kwargs: pytest.fail("pipeline must not run"),
    )

    agent_campaign.run_step(tmp_path, "campaign/test", step)

    assert "[SKIP] phase-24-authority-topology-contract" in capsys.readouterr().out


def test_campaign_passes_model_configuration_to_pipeline(
    tmp_path: Path, monkeypatch
) -> None:
    step = agent_campaign.CampaignStep(
        phase_id="phase-24-authority-topology-contract",
        task=Path(".agent/tasks/phase-24-authority-topology-contract.md"),
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
        max_repairs=1,
    )
    captured: list[str] = []
    branch_created = False

    def fake_run(command, **_kwargs):
        nonlocal branch_created
        captured.extend(command)
        branch_created = True
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(agent_campaign, "phase_already_applied", lambda *_: False)
    monkeypatch.setattr(
        agent_campaign,
        "branch_exists",
        lambda _root, _branch: branch_created,
    )
    monkeypatch.setattr(agent_campaign, "find_project_python", lambda _root: Path("python.exe"))
    monkeypatch.setattr(agent_campaign, "run", fake_run)
    monkeypatch.setattr(
        agent_campaign,
        "git",
        lambda args, **_kwargs: subprocess.CompletedProcess(args, 0),
    )
    monkeypatch.setattr(agent_campaign, "require_clean", lambda _root: None)

    agent_campaign.run_step(tmp_path, "campaign/test", step)

    assert captured[captured.index("--model") + 1] == "gpt-5.6-sol"
    assert captured[captured.index("--reasoning-effort") + 1] == "xhigh"
    assert captured[captured.index("--max-repairs") + 1] == "1"


def test_run_codex_passes_explicit_model_and_reasoning(
    tmp_path: Path, monkeypatch
) -> None:
    worktree = tmp_path / "worktree"
    report_dir = tmp_path / "reports"
    worktree.mkdir()
    task = agent_pipeline.TaskSpec(
        phase_id="phase-24-authority-topology-contract",
        task_path=tmp_path / "task.md",
        task_relative=Path(".agent/tasks/task.md"),
        allowed_patterns=("docs/**",),
        forbidden_patterns=(),
        targeted_commands=(),
        full_commands=("git diff --check",),
        commit_message="Phase 24: contract",
    )
    ctx = agent_pipeline.PipelineContext(
        repo_root=tmp_path,
        base_branch="main",
        base_commit="abc",
        worktree_path=worktree,
        agent_branch="agent/phase-24-authority-topology-contract",
        report_dir=report_dir,
        project_python=Path("python.exe"),
        task=task,
        model="gpt-5.6-sol",
        reasoning_effort="xhigh",
    )
    captured: list[str] = []

    def fake_run_process(command, **_kwargs):
        captured.extend(command)
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[output_index]).write_text("done", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(agent_pipeline, "run_process", fake_run_process)

    agent_pipeline.run_codex(
        ctx,
        "implement",
        report_name="implementation.md",
        process_name="process.json",
        timeout=1,
    )

    assert captured[captured.index("--model") + 1] == "gpt-5.6-sol"
    assert 'model_reasoning_effort="xhigh"' in captured
