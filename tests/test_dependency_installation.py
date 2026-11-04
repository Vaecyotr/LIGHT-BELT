from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
PWSH = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(os.name != "nt" or not PWSH, reason="Windows junction protection")
@pytest.mark.parametrize("flag", ["-Recreate", ""])
def test_shared_junction_recreate_is_read_only_even_when_interpreter_invalid(tmp_path, flag):
    """A recreate flag must never delete or move a shared environment."""
    fixture = tmp_path / "repo"
    script = fixture / "scripts/dev/bootstrap_python.ps1"
    script.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/dev/bootstrap_python.ps1", script)
    target = tmp_path / "shared"
    target.mkdir()
    (target / "sentinel").write_text("shared data")
    runner = tmp_path / "check.ps1"
    runner.write_text("""$ErrorActionPreference = 'Stop'
New-Item -ItemType Junction -Path (Join-Path $PSScriptRoot 'repo/.python') -Target (Join-Path $PSScriptRoot 'shared') | Out-Null
$env:PIP_CACHE_DIR = 'unchanged-sentinel'
function global:Invoke-WebRequest { throw 'Network forbidden in this fixture' }
try { & (Join-Path $PSScriptRoot 'repo/scripts/dev/bootstrap_python.ps1') __FLAG__; exit 7 }
catch {
 if ($env:PIP_CACHE_DIR -ne 'unchanged-sentinel') { exit 8 }
 if (-not ((Get-Item -LiteralPath (Join-Path $PSScriptRoot 'repo/.python')).Attributes -band [IO.FileAttributes]::ReparsePoint)) { exit 9 }
 if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'repo/.python-build')) { exit 10 }
 if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'repo/.python_broken_backup')) { exit 11 }
 Write-Output 'SHARED_ENVIRONMENT_PRESERVED'; exit 0
}
""".replace("__FLAG__", flag), encoding="utf-8")
    result = subprocess.run([PWSH, "-NoProfile", "-File", str(runner)], capture_output=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "SHARED_ENVIRONMENT_PRESERVED" in result.stdout
    assert (target / "sentinel").read_text() == "shared data"


def test_export_contains_host_transitive_requirements_and_excludes_dev():
    """The pip compatibility export must carry all host runtime pins and hashes."""
    text = (ROOT / "host_services/requirements.txt").read_text()
    for pin in ("fastapi==0.139.2", "starlette==1.3.1", "uvicorn==0.51.0", "numpy==2.4.6", "pyyaml==6.0.3"):
        assert pin in text
    assert "pytest==" not in text and "httpx==" not in text
    assert "--hash=sha256:" in text


def test_extras_are_the_only_development_dependency_authority():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "dev" in project["project"]["optional-dependencies"]
    assert not project.get("dependency-groups")
