param(
    [string]$PythonVersion = "3.11.9",
    [switch]$Recreate
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$ProjectDrive = [System.IO.Path]::GetPathRoot($RepoRoot)
if ($ProjectDrive -ne "A:\") {
    throw "Refusing to bootstrap outside A: project storage: $RepoRoot"
}

$PythonDir = Join-Path $RepoRoot ".python"
$BrokenBackup = Join-Path $RepoRoot ".python_broken_backup"
$BuildDir = Join-Path $RepoRoot ".python-build"
$TmpDir = Join-Path $RepoRoot ".tmp"
$PipCache = Join-Path $RepoRoot ".pip-cache"
$PackagePath = Join-Path $BuildDir "python.$PythonVersion.nupkg"
$ZipPath = Join-Path $BuildDir "python.$PythonVersion.zip"
$RuntimeDir = Join-Path $BuildDir "python-$PythonVersion"
$BasePython = Join-Path $RuntimeDir "tools\python.exe"
$VenvPython = Join-Path $PythonDir "Scripts\python.exe"

New-Item -ItemType Directory -Force $BuildDir, $TmpDir, $PipCache | Out-Null
$env:TEMP = $TmpDir
$env:TMP = $TmpDir
$env:PIP_CACHE_DIR = $PipCache
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

function Test-ProjectVenv {
    param([string]$PythonPath)
    if (-not (Test-Path $PythonPath -PathType Leaf)) {
        return $false
    }
    & $PythonPath -c "import sys, pathlib, pip, pytest, pyexpat, light_engine; exe=pathlib.Path(sys.executable).resolve(); cwd=pathlib.Path.cwd().resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); assert exe.parent.name.lower() == 'scripts'; assert exe.parent.parent.name == '.python'; assert exe.parent.parent.parent == cwd; assert str(pkg).startswith(str(cwd)); print('PROJECT_VENV_OK')"
    return ($LASTEXITCODE -eq 0)
}

if ($Recreate -and (Test-Path $PythonDir)) {
    Remove-Item -Recurse -Force $PythonDir
}

if ((Test-Path $PythonDir) -and -not (Test-ProjectVenv $VenvPython)) {
    if (Test-Path $BrokenBackup) {
        throw ".python is not a valid standard venv, and .python_broken_backup already exists. Move it manually before retrying."
    }
    Move-Item -LiteralPath $PythonDir -Destination $BrokenBackup
}

if (-not (Test-Path $BasePython -PathType Leaf)) {
    if (-not (Test-Path $PackagePath -PathType Leaf)) {
        $Uri = "https://www.nuget.org/api/v2/package/python/$PythonVersion"
        Invoke-WebRequest -Uri $Uri -OutFile $PackagePath
    }
    Copy-Item -Force $PackagePath $ZipPath
    if (Test-Path $RuntimeDir) {
        Remove-Item -Recurse -Force $RuntimeDir
    }
    Expand-Archive -Force $ZipPath $RuntimeDir
}

& $BasePython -c "import sys, ensurepip, pyexpat, venv; assert sys.version_info[:2] == (3, 11); print(sys.version); print('BASE_PYTHON_311_OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Base Python 3.11 verification failed."
}

if (-not (Test-Path $VenvPython -PathType Leaf)) {
    & $BasePython -m venv $PythonDir
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create .python venv."
    }
}

& $VenvPython -m pip install --disable-pip-version-check "setuptools>=64" wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade packaging tools."
}

& $VenvPython -m pip install --no-build-isolation -e ".[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install project dependencies."
}

if (-not (Test-ProjectVenv $VenvPython)) {
    throw "Project venv verification failed."
}

& $VenvPython -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed."
}

Write-Host "BOOTSTRAP_PYTHON_OK"
