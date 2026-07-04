from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
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
)

REQUIRED_COMMANDS = (
    "git",
    "codex",
    "claude",
)


class PreflightError(RuntimeError):
    """Raised when the local automation environment is not ready."""


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    resolved = shutil.which(command[0])

    if resolved is None:
        raise PreflightError(
            f"Command was not found on PATH: {command[0]}"
        )

    resolved_command = [resolved, *command[1:]]

    return subprocess.run(
        resolved_command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def find_repository_root(start: Path) -> Path:
    result = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
    )

    if result.returncode != 0:
        raise PreflightError(
            "Current directory is not inside a Git repository.\n"
            f"{result.stderr.strip()}"
        )

    return Path(result.stdout.strip()).resolve()


def check_required_commands() -> None:
    missing = [
        command
        for command in REQUIRED_COMMANDS
        if shutil.which(command) is None
    ]

    if missing:
        raise PreflightError(
            "Missing required commands: " + ", ".join(missing)
        )


def check_required_files(repo_root: Path) -> None:
    missing = [
        relative_path
        for relative_path in REQUIRED_FILES
        if not (repo_root / relative_path).is_file()
    ]

    if missing:
        formatted = "\n".join(f"- {path}" for path in missing)
        raise PreflightError(
            "Missing required automation files:\n" + formatted
        )


def check_project_python(repo_root: Path) -> Path:
    python_executable = repo_root / ".python" / "python.exe"

    if not python_executable.is_file():
        raise PreflightError(
            f"Bundled project Python was not found: {python_executable}"
        )

    command = [
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
    ]

    result = run_command(command, cwd=repo_root)

    if result.returncode != 0:
        raise PreflightError(
            "Bundled project Python verification failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return python_executable


def check_tool_versions(repo_root: Path) -> dict[str, str]:
    commands = {
        "git": ["git", "--version"],
        "codex": ["codex", "--version"],
        "claude": ["claude", "--version"],
    }

    versions: dict[str, str] = {}

    for name, command in commands.items():
        result = run_command(command, cwd=repo_root)

        if result.returncode != 0:
            raise PreflightError(
                f"Failed to run {name} version check.\n"
                f"{result.stderr.strip()}"
            )

        versions[name] = result.stdout.strip()

    return versions


def check_git_state(repo_root: Path) -> tuple[str, str]:
    branch_result = run_command(
        ["git", "branch", "--show-current"],
        cwd=repo_root,
    )
    status_result = run_command(
        ["git", "status", "--short"],
        cwd=repo_root,
    )

    if branch_result.returncode != 0:
        raise PreflightError(branch_result.stderr.strip())

    if status_result.returncode != 0:
        raise PreflightError(status_result.stderr.strip())

    branch = branch_result.stdout.strip()
    status = status_result.stdout.strip()

    return branch, status


def run_preflight(start: Path) -> int:
    check_required_commands()
    repo_root = find_repository_root(start)
    check_required_files(repo_root)
    python_executable = check_project_python(repo_root)
    versions = check_tool_versions(repo_root)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LIGHT-BELT dual-agent automation pipeline."
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check the repository and required local tools.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        if args.preflight:
            return run_preflight(Path.cwd())

        print("No action selected. Use --preflight.")
        return 2

    except (PreflightError, subprocess.TimeoutExpired) as exc:
        print("AGENT_PIPELINE_PREFLIGHT_FAILED", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

