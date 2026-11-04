param(
    [string]$PythonVersion = "3.11.9",
    [switch]$Recreate
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot
$PythonDir = Join-Path $RepoRoot ".python"
$VenvPython = Join-Path $PythonDir "Scripts\python.exe"

function Test-InterpreterIdentity {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) { return $false }
    & $VenvPython -B -c "import sys,pathlib,pyexpat; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe',cwd/'.python'/'python.exe']; assert any(p.exists() and p.resolve()==exe for p in candidates); assert sys.version_info[:2]==(3,11); print('INTERPRETER_IDENTITY_OK')" | Out-Host
    return ($LASTEXITCODE -eq 0)
}
function Test-ProjectDependencies {
    & $VenvPython -B -c "import pathlib,light_engine,pytest,httpx,fastapi,uvicorn,websockets,jwt,numpy,scipy,cv2,soundfile,serial,yaml; cwd=pathlib.Path.cwd().resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); assert pkg.is_relative_to(cwd); print('PROJECT_DEPENDENCIES_OK')" | Out-Host
    return ($LASTEXITCODE -eq 0)
}

# This guard precedes directory creation, TEMP/PIP environment writes, downloads,
# recreation and dependency operations. A Junction is an intentional shared venv.
$PythonItem = Get-Item -LiteralPath $PythonDir -Force -ErrorAction SilentlyContinue
if ($null -ne $PythonItem) {
    if ($PythonItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        if ($Recreate) { throw "Shared .python is validation-only; -Recreate is forbidden." }
        if (-not (Test-InterpreterIdentity)) { throw "Shared interpreter identity invalid; no changes made." }
        if (-not (Test-ProjectDependencies)) { throw "Shared environment dependencies incomplete; repair its owner environment explicitly." }
        Write-Host "BOOTSTRAP_PYTHON_OK (shared environment validated; no synchronization)"
        return
    }
}
if ([IO.Path]::GetPathRoot($RepoRoot) -ne "A:\") {
    throw "Refusing to bootstrap outside A: project storage: $RepoRoot"
}
if ((Test-Path -LiteralPath $PythonDir) -and -not $Recreate -and -not (Test-InterpreterIdentity)) {
    throw "Existing .python identity invalid; use an explicit independent environment repair."
}
if ($Recreate -and (Test-Path -LiteralPath $PythonDir)) {
    $ResolvedPython = (Resolve-Path -LiteralPath $PythonDir).Path
    if ($ResolvedPython -ne (Join-Path $RepoRoot ".python")) { throw "Unexpected .python path: $ResolvedPython" }
    Remove-Item -LiteralPath $ResolvedPython -Recurse -Force
}

$BuildDir = Join-Path $RepoRoot ".python-build"
$TmpDir = Join-Path $RepoRoot ".tmp"
$RuntimeDir = Join-Path $BuildDir "python-$PythonVersion"
$BasePython = Join-Path $RuntimeDir "tools\python.exe"
# An already valid independent venv keeps its interpreter and base runtime.
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    New-Item -ItemType Directory -Force -Path $BuildDir, $TmpDir | Out-Null
    if (-not (Test-Path -LiteralPath $BasePython -PathType Leaf)) {
        if (Test-Path -LiteralPath $RuntimeDir) { throw "Incomplete base runtime exists; refusing to replace it: $RuntimeDir" }
        $PackagePath = Join-Path $BuildDir "python.$PythonVersion.nupkg"
        $ZipPath = Join-Path $BuildDir "python.$PythonVersion.zip"
        if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) {
            Invoke-WebRequest -Uri "https://www.nuget.org/api/v2/package/python/$PythonVersion" -OutFile $PackagePath
        }
        Copy-Item -LiteralPath $PackagePath -Destination $ZipPath -Force
        Expand-Archive -LiteralPath $ZipPath -DestinationPath $RuntimeDir
    }
    & $BasePython -B -c "import sys,venv,ensurepip,pyexpat; assert sys.version_info[:2]==(3,11)"
    if ($LASTEXITCODE -ne 0) { throw "Base Python verification failed." }
    & $BasePython -m venv $PythonDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create independent .python." }
}
if (-not (Test-InterpreterIdentity)) { throw "Independent interpreter identity invalid." }

$UvVersion = "0.9.5"
$UvDir = Join-Path $TmpDir "tools\uv-$UvVersion"
$Uv = Join-Path $UvDir "uv.exe"
if (-not (Test-Path -LiteralPath $Uv -PathType Leaf)) {
    New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
    $UvZip = Join-Path $UvDir "uv.zip"
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-x86_64-pc-windows-msvc.zip" -OutFile $UvZip
    Expand-Archive -LiteralPath $UvZip -DestinationPath $UvDir -Force
}
$ActualUv = & $Uv --version
if ($LASTEXITCODE -ne 0 -or $ActualUv -notmatch ('^uv ' + [regex]::Escape($UvVersion) + '( |$)')) { throw "Pinned uv verification failed." }
$PreviousEnvironment = $env:UV_PROJECT_ENVIRONMENT
$PreviousCache = $env:UV_CACHE_DIR
try {
    $env:UV_PROJECT_ENVIRONMENT = $PythonDir
    $env:UV_CACHE_DIR = Join-Path $TmpDir "uv-cache"
    & $Uv sync --locked --no-dev --extra dev --extra host --python $VenvPython --no-python-downloads
    if ($LASTEXITCODE -ne 0) { throw "Locked development/Host synchronization failed." }
} finally {
    $env:UV_PROJECT_ENVIRONMENT = $PreviousEnvironment
    $env:UV_CACHE_DIR = $PreviousCache
}
if (-not (Test-ProjectDependencies)) { throw "Project dependencies incomplete after synchronization." }
Write-Host "BOOTSTRAP_PYTHON_OK"
