from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CampaignError(RuntimeError):
    pass


@dataclass(frozen=True)
class CampaignStep:
    phase_id: str
    task: Path
    model: str | None = None
    reasoning_effort: str | None = None
    max_repairs: int = 2


REASONING_EFFORTS = frozenset({"medium", "high", "xhigh"})


def run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=False,
        check=False,
    )
    if check and result.returncode != 0:
        raise CampaignError(
            f"Command failed ({result.returncode}): {' '.join(command)}"
        )
    return result


def git(
    args: list[str],
    *,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd, check=check)


def repo_root(start: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CampaignError("Current directory is not inside a Git repository.")
    return Path(result.stdout.strip()).resolve()


def project_python_candidates(root: Path) -> tuple[Path, ...]:
    if os.name == "nt":
        return (
            root / ".python" / "Scripts" / "python.exe",
            root / ".python" / "python.exe",
        )
    return (
        root / ".python" / "bin" / "python",
        root / ".python" / "python",
    )


def find_project_python(root: Path) -> Path:
    for candidate in project_python_candidates(root):
        if candidate.is_file():
            return candidate
    expected = "\n".join(f"- {item}" for item in project_python_candidates(root))
    raise CampaignError("Project Python missing. Expected one of:\n" + expected)


def current_branch(root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CampaignError(result.stderr.strip())
    return result.stdout.strip()


def require_clean(root: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CampaignError(result.stderr.strip())
    if result.stdout.strip():
        raise CampaignError(
            "Working tree must be clean before starting the campaign."
        )


def branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def load_manifest(root: Path, manifest_path: Path) -> tuple[str, str, list[CampaignStep]]:
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    if not path.is_file():
        raise CampaignError(f"Campaign manifest not found: {path}")

    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8-sig"))
    campaign_branch = str(data["campaign_branch"])
    start_branch = str(data.get("start_branch", "main"))

    steps: list[CampaignStep] = []
    for item in data["steps"]:
        model_value = item.get("model")
        if model_value is not None and not isinstance(model_value, str):
            raise CampaignError("Campaign step model must be a non-empty string.")
        model = None if model_value is None else model_value.strip()
        if model_value is not None and not model:
            raise CampaignError("Campaign step model must be a non-empty string.")

        effort_value = item.get("reasoning_effort")
        if effort_value is not None and not isinstance(effort_value, str):
            raise CampaignError(
                "Campaign step reasoning_effort must be a string."
            )
        reasoning_effort = (
            None if effort_value is None else effort_value.strip()
        )
        if (
            reasoning_effort is not None
            and reasoning_effort not in REASONING_EFFORTS
        ):
            allowed = ", ".join(sorted(REASONING_EFFORTS))
            raise CampaignError(
                f"Campaign step reasoning_effort must be one of: {allowed}."
            )
        steps.append(
            CampaignStep(
                phase_id=str(item["phase_id"]),
                task=Path(str(item["task"])),
                model=model,
                reasoning_effort=reasoning_effort,
                max_repairs=int(item.get("max_repairs", 2)),
            )
        )

    if not steps:
        raise CampaignError("Campaign manifest contains no steps.")
    return campaign_branch, start_branch, steps


def ensure_campaign_branch(root: Path, campaign_branch: str, start_branch: str) -> None:
    branch = current_branch(root)

    if branch_exists(root, campaign_branch):
        if branch != campaign_branch:
            git(["switch", campaign_branch], cwd=root, check=True)
        return

    if branch != start_branch:
        git(["switch", start_branch], cwd=root, check=True)

    git(["switch", "-c", campaign_branch], cwd=root, check=True)


def phase_already_applied(root: Path, agent_branch: str) -> bool:
    if not branch_exists(root, agent_branch):
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", agent_branch, "HEAD"],
        cwd=root,
        check=False,
    )
    return result.returncode == 0


def archive_failed_report(root: Path, phase_id: str) -> Path | None:
    report_dir = root / ".agent" / "reports" / phase_id
    if not report_dir.exists():
        return None

    final_result = report_dir / "final-result.json"
    if not final_result.is_file():
        raise CampaignError(
            f"Report directory exists without final-result.json: {report_dir}"
        )
    try:
        result = json.loads(final_result.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(
            f"Failed to read existing final result: {final_result}"
        ) from exc
    if result.get("status") != "FAIL":
        raise CampaignError(
            f"Report directory already exists and is not a failed run: {report_dir}"
        )

    archive_root = root / ".agent" / "reports" / ".failed" / phase_id
    archive_root.mkdir(parents=True, exist_ok=True)
    attempt = 1
    while (archive_root / f"attempt-{attempt:03d}").exists():
        attempt += 1
    destination = archive_root / f"attempt-{attempt:03d}"
    report_dir.replace(destination)
    print(f"[RETRY] archived failed report: {destination}")
    return destination


def run_step(
    root: Path,
    campaign_branch: str,
    step: CampaignStep,
) -> None:
    agent_branch = f"agent/{step.phase_id}"

    if phase_already_applied(root, agent_branch):
        print(f"[SKIP] {step.phase_id}: already contained in {campaign_branch}")
        return

    if branch_exists(root, agent_branch):
        raise CampaignError(
            f"Agent branch already exists but is not merged: {agent_branch}"
        )

    archive_failed_report(root, step.phase_id)

    print(f"\n=== START {step.phase_id} ===")
    python_executable = find_project_python(root)
    command = [
        str(python_executable),
        "scripts/agent_pipeline.py",
        "--run",
        "--phase-id",
        step.phase_id,
        "--task",
        str(step.task),
        "--base-branch",
        campaign_branch,
        "--max-repairs",
        str(step.max_repairs),
    ]
    if step.model is not None:
        command.extend(["--model", step.model])
    if step.reasoning_effort is not None:
        command.extend(["--reasoning-effort", step.reasoning_effort])
    result = run(command, cwd=root)
    if result.returncode != 0:
        raise CampaignError(f"Phase failed: {step.phase_id}")

    if not branch_exists(root, agent_branch):
        raise CampaignError(
            f"Pipeline reported success but branch is missing: {agent_branch}"
        )

    git(["merge", "--ff-only", agent_branch], cwd=root, check=True)
    require_clean(root)
    print(f"=== PASS {step.phase_id} ===")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a long LIGHT-BELT multi-phase campaign."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to an explicitly selected active or archived campaign manifest.",
    )
    args = parser.parse_args()

    try:
        root = repo_root(Path.cwd())
        require_clean(root)

        python_executable = find_project_python(root)
        pipeline = root / "scripts" / "agent_pipeline.py"
        if not pipeline.is_file():
            raise CampaignError(f"Pipeline missing: {pipeline}")

        campaign_branch, start_branch, steps = load_manifest(root, args.manifest)
        ensure_campaign_branch(root, campaign_branch, start_branch)
        require_clean(root)

        print("AGENT_CAMPAIGN_START")
        print(f"campaign_branch={campaign_branch}")
        print(f"steps={len(steps)}")

        for index, step in enumerate(steps, start=1):
            print(f"\n[{index}/{len(steps)}] {step.phase_id}")
            run_step(root, campaign_branch, step)

        print("\nAGENT_CAMPAIGN_PASS")
        print(f"campaign_branch={campaign_branch}")
        print("Main was not modified or merged automatically.")
        return 0

    except CampaignError as exc:
        print("\nAGENT_CAMPAIGN_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print(
            "Completed phases remain committed on the campaign branch; "
            "the failing phase was not merged.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
