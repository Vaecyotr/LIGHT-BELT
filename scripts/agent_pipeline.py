from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/CLOSED_LOOP_SPEC.md",
    "docs/IMPLEMENTATION_PLAN.md",
    ".agent/review.schema.json",
    ".agent/prompts/implementer.md",
    ".agent/prompts/reviewer.md",
    ".agent/prompts/repairer.md",
    ".agent/tasks/TEMPLATE.md",
    "scripts/agent_worktree.py",
)
REQUIRED_COMMANDS = ("git", "codex", "claude")
DEFAULT_TIMEOUT_SECONDS = 3600


class PipelineError(RuntimeError):
    """Raised when the automation pipeline cannot continue safely."""


@dataclass(frozen=True)
class PipelinePaths:
    repo_root: Path
    task_file: Path
    worktree_path: Path
    report_dir: Path
    implementer_prompt: Path


def resolve_command(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise PipelineError(f"Required command was not found on PATH: {name}")
    return resolved


def run_command(command: list[str], *, cwd: Path, timeout: int = 60,
                input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    if not command:
        raise PipelineError("Cannot run an empty command.")
    resolved_command = [resolve_command(command[0]), *command[1:]]
    try:
        return subprocess.run(
            resolved_command,
            cwd=cwd,
            text=True,
            input=input_text,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Command timed out after {timeout} seconds: {' '.join(command)}"
        ) from exc


def find_repository_root(start: Path) -> Path:
    result = run_command(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        raise PipelineError(
            "Current directory is not inside a Git repository.\n"
            f"{result.stderr.strip()}"
        )
    return Path(result.stdout.strip()).resolve()


def check_required_commands() -> None:
    missing = [name for name in REQUIRED_COMMANDS if shutil.which(name) is None]
    if missing:
        raise PipelineError("Missing required commands: " + ", ".join(missing))


def check_required_files(repo_root: Path) -> None:
    missing = [p for p in REQUIRED_FILES if not (repo_root / p).is_file()]
    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise PipelineError("Missing required automation files:\n" + formatted)


def check_project_python(repo_root: Path) -> Path:
    python_executable = repo_root / ".python" / "python.exe"
    if not python_executable.is_file():
        raise PipelineError(f"Bundled project Python was not found: {python_executable}")
    result = run_command(
        [
            str(python_executable),
            "-c",
            (
                "import pathlib, sys, light_engine; "
                "exe=pathlib.Path(sys.executable).resolve(); "
                "cwd=pathlib.Path.cwd().resolve(); "
                "pkg=pathlib.Path(light_engine.__file__).resolve(); "
                "assert exe.name.lower() == 'python.exe'; "
                "assert exe.parent.name == '.python'; "
                "assert exe.parent.parent == cwd; "
                "assert str(pkg).startswith(str(cwd)); "
                "print('PROJECT_PYTHON_OK')"
            ),
        ],
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise PipelineError(
            "Bundled project Python verification failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return python_executable


def check_git_state(repo_root: Path) -> tuple[str, str]:
    branch_result = run_command(["git", "branch", "--show-current"], cwd=repo_root)
    status_result = run_command(["git", "status", "--short"], cwd=repo_root)
    if branch_result.returncode != 0:
        raise PipelineError(branch_result.stderr.strip())
    if status_result.returncode != 0:
        raise PipelineError(status_result.stderr.strip())
    return branch_result.stdout.strip(), status_result.stdout.strip()


def require_clean_main(repo_root: Path) -> None:
    branch, status = check_git_state(repo_root)
    if branch != "main":
        raise PipelineError(
            f"Pipeline must start from main, but current branch is '{branch}'."
        )
    if status:
        raise PipelineError(
            "Main working tree must be clean before starting the pipeline.\n"
            f"{status}"
        )


def validate_phase_id(value: str) -> str:
    import re
    phase_id = value.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", phase_id):
        raise PipelineError(
            "Phase ID must contain only lowercase letters, numbers, and "
            "hyphens; length must be 3 to 64 characters."
        )
    return phase_id


def resolve_task_file(repo_root: Path, task: Path) -> Path:
    task_path = task if task.is_absolute() else repo_root / task
    task_path = task_path.resolve()
    try:
        task_path.relative_to(repo_root)
    except ValueError as exc:
        raise PipelineError("Task file must be inside the repository.") from exc
    if not task_path.is_file():
        raise PipelineError(f"Task file does not exist: {task_path}")
    return task_path


def build_paths(repo_root: Path, *, phase_id: str, task_file: Path) -> PipelinePaths:
    return PipelinePaths(
        repo_root=repo_root,
        task_file=task_file,
        worktree_path=(repo_root / ".agent-worktrees" / phase_id).resolve(),
        report_dir=(repo_root / ".agent" / "reports" / phase_id).resolve(),
        implementer_prompt=(repo_root / ".agent" / "prompts" / "implementer.md").resolve(),
    )


def create_worktree(*, repo_root: Path, phase_id: str,
                    task_file: Path, timeout: int) -> Path:
    python_executable = check_project_python(repo_root)
    result = run_command(
        [
            str(python_executable),
            "scripts/agent_worktree.py",
            "--phase-id", phase_id,
            "--task", str(task_file),
            "--base-branch", "main",
            "--create",
        ],
        cwd=repo_root,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise PipelineError(
            "Failed to create isolated agent worktree.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    worktree_path = (repo_root / ".agent-worktrees" / phase_id).resolve()
    if not worktree_path.is_dir():
        raise PipelineError(
            f"Worktree command succeeded but path is missing: {worktree_path}"
        )
    return worktree_path


def copy_task_into_worktree(*, task_file: Path,
                            worktree_path: Path, phase_id: str) -> Path:
    destination_dir = worktree_path / ".agent" / "tasks"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{phase_id}.md"
    shutil.copy2(task_file, destination)
    return destination


def build_codex_prompt(*, implementer_prompt: Path,
                       task_in_worktree: Path, report_path: Path) -> str:
    base_prompt = implementer_prompt.read_text(encoding="utf-8-sig")
    worktree_root = task_in_worktree.parents[2]
    task_relative = task_in_worktree.relative_to(worktree_root)
    report_relative = report_path.relative_to(worktree_root)
    return (
        f"{base_prompt}\n\n"
        "Orchestrator-supplied paths:\n\n"
        f"- Current task file: `{task_relative.as_posix()}`\n"
        f"- Write the implementation report to: `{report_relative.as_posix()}`\n\n"
        "Additional execution requirements:\n\n"
        "- Work only inside the current worktree.\n"
        "- Do not create or switch Git branches.\n"
        "- Do not commit changes.\n"
        "- Ensure the report file is written before exiting.\n"
    )


def run_codex_implementation(*, worktree_path: Path, prompt: str,
                             report_path: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return run_command(
        [
            "codex", "exec", "--ephemeral",
            "--sandbox", "workspace-write",
            "--cd", str(worktree_path),
            "--output-last-message", str(report_path),
            "-",
        ],
        cwd=worktree_path,
        timeout=timeout,
        input_text=prompt,
    )


def save_process_log(*, report_dir: Path, name: str,
                     result: subprocess.CompletedProcess[str]) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (report_dir / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_preflight(start: Path) -> int:
    check_required_commands()
    repo_root = find_repository_root(start)
    check_required_files(repo_root)
    python_executable = check_project_python(repo_root)
    versions = {}
    for name in REQUIRED_COMMANDS:
        result = run_command([name, "--version"], cwd=repo_root)
        if result.returncode != 0:
            raise PipelineError(
                f"Failed to run {name} version check.\n{result.stderr.strip()}"
            )
        versions[name] = result.stdout.strip()
    branch, status = check_git_state(repo_root)
    print("AGENT_PIPELINE_PREFLIGHT_OK")
    print(f"repository={repo_root}")
    print(f"branch={branch}")
    print(f"python={python_executable}")
    print(f"git={versions['git']}")
    print(f"codex={versions['codex']}")
    print(f"claude={versions['claude']}")
    if status:
        print("working_tree=DIRTY")
        print("git_status:")
        print(status)
    else:
        print("working_tree=CLEAN")
    return 0


def run_implementation_stage(*, phase_id: str, task: Path, timeout: int) -> int:
    check_required_commands()
    repo_root = find_repository_root(Path.cwd())
    check_required_files(repo_root)
    require_clean_main(repo_root)
    task_file = resolve_task_file(repo_root, task)
    paths = build_paths(repo_root, phase_id=phase_id, task_file=task_file)
    if paths.report_dir.exists():
        raise PipelineError(
            "Report directory already exists for this Phase. "
            "Remove it or choose a new Phase ID:\n"
            f"{paths.report_dir}"
        )
    worktree_path = create_worktree(
        repo_root=repo_root,
        phase_id=phase_id,
        task_file=task_file,
        timeout=timeout,
    )
    try:
        task_in_worktree = copy_task_into_worktree(
            task_file=task_file,
            worktree_path=worktree_path,
            phase_id=phase_id,
        )
        report_path = (
            worktree_path / ".agent" / "reports" / phase_id /
            "codex-implementation.md"
        )
        prompt = build_codex_prompt(
            implementer_prompt=paths.implementer_prompt,
            task_in_worktree=task_in_worktree,
            report_path=report_path,
        )
        result = run_codex_implementation(
            worktree_path=worktree_path,
            prompt=prompt,
            report_path=report_path,
            timeout=timeout,
        )
        save_process_log(
            report_dir=paths.report_dir,
            name="codex-process.json",
            result=result,
        )
        if report_path.is_file():
            paths.report_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                report_path,
                paths.report_dir / "codex-implementation.md",
            )
        print("AGENT_CODEX_STAGE_FINISHED")
        print(f"phase_id={phase_id}")
        print(f"worktree={worktree_path}")
        print(f"returncode={result.returncode}")
        print(f"report_dir={paths.report_dir}")
        if result.returncode != 0:
            print(
                "Codex exited with a non-zero code. "
                "The worktree was preserved for inspection."
            )
            return 1
        if not report_path.is_file():
            raise PipelineError(
                "Codex completed but did not create the required report file."
            )
        print("AGENT_CODEX_STAGE_OK")
        return 0
    except Exception:
        print(
            "The worktree was preserved because the implementation stage "
            "did not finish cleanly.",
            file=sys.stderr,
        )
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LIGHT-BELT dual-agent automation pipeline."
    )
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--implement", action="store_true")
    parser.add_argument("--phase-id")
    parser.add_argument("--task", type=Path)
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-command timeout in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.preflight:
            return run_preflight(Path.cwd())
        if args.implement:
            if not args.phase_id:
                raise PipelineError("--phase-id is required with --implement.")
            if args.task is None:
                raise PipelineError("--task is required with --implement.")
            if args.timeout <= 0:
                raise PipelineError("--timeout must be greater than zero.")
            return run_implementation_stage(
                phase_id=validate_phase_id(args.phase_id),
                task=args.task,
                timeout=args.timeout,
            )
        print("No action selected. Use --preflight or --implement.")
        return 2
    except PipelineError as exc:
        print("AGENT_PIPELINE_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
