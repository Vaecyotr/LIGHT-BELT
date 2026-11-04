#!/usr/bin/env python3
"""Generate an offline evidence bundle for a LIGHT-BELT distribution review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tomllib
from datetime import date
from email.parser import Parser
from pathlib import Path
from typing import Any


MEDIA_EXTENSIONS = {
    ".aac", ".aiff", ".avi", ".bmp", ".flac", ".gif", ".jpeg", ".jpg",
    ".m4a", ".m4v", ".mkv", ".mov", ".mp3", ".mp4", ".oga", ".ogg", ".opus", ".otf", ".png",
    ".svg", ".tif", ".tiff", ".ttf", ".wav", ".webm", ".webp", ".woff", ".woff2", ".wma", ".wmv",
}
PRUNED_DIRS = {
    ".git", ".cache", ".pytest_cache", "__pycache__", "node_modules",
    "tmp", "temp", "build", "coverage",
}
LICENSE_NAME = re.compile(r"(?:license|licence|copying|notice)", re.IGNORECASE)
MAX_WALK_FILES = 50_000
MAX_LICENSE_FILE_BYTES = 16 * 1024 * 1024
HASH_INPUTS = (
    "pyproject.toml", "uv.lock", "host_services/requirements.txt",
    "host_services/main.py", "kiosk/package.json", "kiosk/package-lock.json",
    "scripts/deploy/rk3588/setup-python.sh", "scripts/deploy/rk3588/setup-system.sh",
    "firmware/esp32_ws2811_node/platformio.ini",
    "firmware/stm32_rgbcct_node/platformio.ini",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_output_links(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValueError(f"output path crosses a symlink or junction: {current}")
    if path.is_dir():
        stack = [path]
        while stack:
            directory = stack.pop()
            for child in directory.iterdir():
                info = child.lstat()
                if _is_reparse(info):
                    raise ValueError(f"output tree contains a symlink or junction: {child}")
                if stat.S_ISDIR(info.st_mode):
                    stack.append(child)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(root: Path, *args: str, warnings: list[str] | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
    except OSError as exc:
        if warnings is not None:
            warnings.append(f"git {' '.join(args)} could not run: {exc}")
        return None
    if result.returncode:
        if warnings is not None:
            warnings.append(f"git {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
        return None
    return result.stdout.strip()


def _git_state(root: Path, warnings: list[str]) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"available": False, "head": None, "branch": None, "available_refs": [], "dirty": None, "dirty_paths": [], "history_scope": "no local Git metadata found"}
    head = _git(root, "rev-parse", "HEAD", warnings=warnings)
    branch = _git(root, "branch", "--show-current", warnings=warnings)
    refs = _git(root, "for-each-ref", "--format=%(refname)", warnings=warnings)
    status = _git(root, "status", "--porcelain=v1", warnings=warnings)
    if head is None or branch is None or refs is None or status is None:
        return {"available": False, "head": head, "branch": branch or None, "available_refs": (refs or "").splitlines(), "dirty": None, "dirty_paths": [], "history_scope": "Git evidence incomplete; see warnings"}
    dirty_paths = status.splitlines() if status else []
    return {
        "available": True,
        "head": head,
        "branch": branch or None,
        "available_refs": refs.splitlines(),
        "dirty": bool(dirty_paths),
        "dirty_paths": dirty_paths,
        "history_scope": "all refs visible to this local checkout; no network fetch performed",
    }


def _is_reparse(info: Any) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _walk_files(start: Path, warnings: list[str], *, strict_links: bool = False) -> list[Path]:
    found: list[Path] = []
    if not start.exists():
        return found
    try:
        start_info = start.lstat()
    except OSError as exc:
        warnings.append(f"cannot inspect scan root {start}: {exc}")
        return found
    if _is_reparse(start_info):
        if strict_links:
            raise ValueError(f"output tree contains a symlink or junction: {start}")
        warnings.append(f"skipped symlink or reparse scan root: {start}")
        return found
    stack = [(start, 0)]
    while stack:
        directory, depth = stack.pop()
        if depth > 16:
            warnings.append(f"scan depth limit reached under {directory}")
            continue
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError as exc:
            warnings.append(f"cannot scan {directory}: {exc}")
            continue
        for path in entries:
            try:
                info = path.lstat()
            except OSError as exc:
                warnings.append(f"cannot inspect {path}: {exc}")
                continue
            if _is_reparse(info):
                if strict_links:
                    raise ValueError(f"output tree contains a symlink or junction: {path}")
                warnings.append(f"skipped symlink or reparse point: {path}")
                continue
            if stat.S_ISDIR(info.st_mode):
                if path.name.lower() not in PRUNED_DIRS:
                    stack.append((path, depth + 1))
            elif stat.S_ISREG(info.st_mode):
                found.append(path)
                if len(found) >= MAX_WALK_FILES:
                    warnings.append(f"scan file limit reached under {start} ({MAX_WALK_FILES})")
                    return found
    return found


def _media_files(root: Path, warnings: list[str]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    tracked = set((_git(root, "ls-files", "--", "assets", "tests/fixtures", "artifacts/runs", warnings=warnings) or "").splitlines()) if (root / ".git").exists() else set()
    for relative_root in ("assets", "tests/fixtures", "artifacts/runs"):
        start = root / relative_root
        if not start.is_dir():
            continue
        files = _walk_files(start, warnings)
        for path in files:
            if path.suffix.lower() in MEDIA_EXTENSIONS:
                found.append({
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "tracked_in_worktree": path.relative_to(root).as_posix() in tracked,
                })
    return found


def _history_media(root: Path, warnings: list[str]) -> list[dict[str, Any]]:
    if not (root / ".git").exists():
        return []
    listing = _git(root, "rev-list", "--objects", "--all", warnings=warnings)
    if listing is None:
        return []
    items: list[dict[str, Any]] = []
    for line in listing.splitlines():
        parts = line.split(" ", 1)
        if len(parts) != 2 or Path(parts[1]).suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        items.append({"object_id": parts[0], "path": parts[1]})
        if len(items) >= MAX_WALK_FILES:
            break
    if items:
        # A single batch process avoids launching one Git process per historical blob.
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
                input="".join(f"{item['object_id']}\n" for item in items), capture_output=True,
                text=True, encoding="utf-8", errors="replace", check=False,
            )
            if proc.returncode == 0:
                by_id = {line.split()[0]: int(line.split()[2]) for line in proc.stdout.splitlines() if len(line.split()) == 3 and line.split()[1] == "blob"}
                for item in items:
                    item["size_bytes"] = by_id.get(item["object_id"])
            else:
                warnings.append(f"git cat-file history sizing failed ({proc.returncode}): {proc.stderr.strip()}")
        except (OSError, ValueError) as exc:
            warnings.append(f"git cat-file history sizing failed: {exc}")
    return items


def _lock_inventory(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = []
    for package in lock.get("package", []):
        packages.append({
            "name": package.get("name"), "version": package.get("version"),
            "source": package.get("source"), "marker": package.get("resolution-markers"),
            "dependencies": package.get("dependencies", []),
            "wheels": package.get("wheels", []), "sdist": package.get("sdist"),
        })
    npm_lock = _read_json(root / "kiosk" / "package-lock.json")
    npm_packages = []
    for package_path, package in npm_lock.get("packages", {}).items():
        if not package_path:
            continue
        npm_packages.append({
            "name": package_path.removeprefix("node_modules/"),
            "version": package.get("version"), "license": package.get("license"),
            "integrity": package.get("integrity"), "resolved": package.get("resolved"),
            "dev": package.get("dev", False), "optional": package.get("optional", False),
            "os": package.get("os"), "cpu": package.get("cpu"),
            "link": package.get("link", False),
            "dependencies": package.get("dependencies", {}),
            "optionalDependencies": package.get("optionalDependencies", {}),
            "peerDependencies": package.get("peerDependencies", {}),
            "peerDependenciesMeta": package.get("peerDependenciesMeta", {}),
        })
    groups = pyproject.get("dependency-groups", {})
    uv_config = pyproject.get("tool", {}).get("uv", {})
    default_groups = uv_config.get("default-groups", ["dev"])
    setup = root / "scripts" / "deploy" / "rk3588" / "setup-python.sh"
    sync_command = setup.read_text(encoding="utf-8") if setup.is_file() else ""
    dev_default = "--no-dev" not in sync_command and "dev" in default_groups
    return (
        {"version": lock.get("version"), "requires_python": lock.get("requires-python"), "packages": packages},
        {"lockfile_version": npm_lock.get("lockfileVersion"), "packages": npm_packages},
        {
            "project": pyproject.get("project", {}), "dependency_groups": groups,
            "uv_default_groups": default_groups,
            "deployment_sync_script": "scripts/deploy/rk3588/setup-python.sh",
            "deployment_sync_requests_host_extra": "--extra host" in sync_command,
            "deployment_sync_includes_default_dev_group": dev_default,
            "note": "Static configuration evidence only; not a target deployment SBOM.",
        },
    )


def _site_packages(root: Path) -> list[Path]:
    candidates = []
    for environment in (root / ".python", root / ".venv"):
        candidates.extend((environment / "Lib" / "site-packages", environment / "lib" / "python3.11" / "site-packages"))
        candidates.extend((environment / "lib").glob("python*/site-packages"))
    return sorted({p for p in candidates if p.is_dir()}, key=lambda p: str(p).lower())


def _system_packages(root: Path) -> dict[str, Any]:
    relative = "scripts/deploy/rk3588/setup-system.sh"
    path = root / relative
    requested = []
    collecting = False
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not collecting and "apt-get install -y" in line:
                collecting = True
                line = line.split("apt-get install -y", 1)[1]
            if collecting:
                line = line.split("#", 1)[0].strip()
                continuing = line.endswith("\\")
                line = line.rstrip("\\").strip()
                requested.extend(shlex.split(line))
                if not continuing:
                    break
    return {
        "installer_script": relative if path.is_file() else None,
        "requested_packages": requested,
        "versions_pinned": False,
        "mpv_license_build_mode": "unknown",
        "ffmpeg_package_or_configuration": "not directly pinned; may be an mpv/OpenCV native dependency",
        "chromium": "not requested by active setup-system.sh; base-image/browser provenance unknown",
    }


def _distribution_inventory(root: Path, output: Path, warnings: list[str]) -> list[dict[str, Any]]:
    distributions: list[dict[str, Any]] = []
    for site in _site_packages(root):
        site_real = site.resolve()
        for dist_info in sorted(site.glob("*.dist-info"), key=lambda p: p.name.lower()):
            metadata_path = dist_info / "METADATA"
            if not metadata_path.is_file():
                continue
            metadata = Parser().parsestr(metadata_path.read_text(encoding="utf-8", errors="replace"))
            name = metadata.get("Name") or dist_info.name.rsplit("-", 1)[0]
            version = metadata.get("Version") or "unknown"
            environment = site.relative_to(root).parts[0]
            safe_dist_name = re.sub(r"[^A-Za-z0-9._+-]+", "_", f"{name}-{version}")
            license_candidates: dict[Path, Path] = {}
            record = dist_info / "RECORD"
            if record.is_file():
                try:
                    with record.open("r", encoding="utf-8", newline="") as stream:
                        for row in csv.reader(stream):
                            if not row or not LICENSE_NAME.search(Path(row[0]).name):
                                continue
                            logical = site / row[0]
                            candidate = logical.resolve()
                            if candidate.is_relative_to(site_real) and candidate.is_file() and candidate.stat().st_size <= MAX_LICENSE_FILE_BYTES:
                                license_candidates[candidate] = site / candidate.relative_to(site_real)
                            elif not candidate.is_relative_to(site_real):
                                warnings.append(f"license path outside site-packages skipped: {row[0]} in {record}")
                except (OSError, csv.Error) as exc:
                    warnings.append(f"cannot parse wheel RECORD {record}: {exc}")
            # Metadata layouts predating PEP 639 may omit license files from RECORD.
            licenses_dir = dist_info / "licenses"
            if licenses_dir.is_dir():
                for candidate in _walk_files(licenses_dir, warnings):
                    if LICENSE_NAME.search(candidate.name):
                        resolved = candidate.resolve()
                        if resolved.is_relative_to(site_real) and resolved.stat().st_size <= MAX_LICENSE_FILE_BYTES:
                            license_candidates[resolved] = site / resolved.relative_to(site_real)
            copied = []
            dest_base = output / "LICENSES" / f"installed-{environment.lstrip('.')}" / safe_dist_name
            for source in sorted(license_candidates):
                relative = source.relative_to(site_real)
                destination = dest_base / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
                copied.append({"source": str(license_candidates[source]), "copied_to": destination.relative_to(output).as_posix(), "sha256": _sha256(source)})
            distributions.append({
                "name": name, "version": version,
                "metadata_license": metadata.get("License"),
                "license_expression": metadata.get("License-Expression"),
                "license_files": copied,
                "license_status": "license-file-found" if copied else "unknown",
                "environment": environment,
                "environment_path": str(dist_info),
                "evidence_scope": "locally installed developer environment; target runtime may differ",
            })
    return distributions


def generate(root: Path | str, output: Path | str, audit_date: str | None = None) -> dict[str, Any]:
    root = Path(root).resolve(strict=True)
    raw_output = Path(output).absolute()
    _reject_output_links(raw_output)
    output = raw_output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    media = _media_files(root, warnings)
    history = _history_media(root, warnings)
    uv, npm, project = _lock_inventory(root)
    installed = _distribution_inventory(root, output, warnings)
    git = _git_state(root, warnings)
    pyproject = root / "pyproject.toml"
    unresolved = [
        "Target RK3588 image and apt package versions/build configuration are not captured.",
        "Target Python architecture-specific wheels and bundled native libraries are not captured.",
        "Controller firmware binaries, versions, and source/license provenance are not captured.",
        "Included demonstration/media assets require confirmed ownership and redistribution rights.",
        "Seller, sales territories, and final packaging format are not specified.",
    ]
    inventory = {
        "audit_date": audit_date or date.today().isoformat(),
        "release_status": "BLOCKED",
        "statement": "Evidence inventory only; not a target SBOM or a compliance pass.",
        "environment": {
            "generator_python": sys.version.split()[0],
            "scope": "current local checkout and locally installed developer distributions",
            "target": "RK3588 production image and controller/media shipping scope not fully identified",
        },
        "uv_lock": uv, "npm_lock": npm, "project_configuration": project,
        "system_packages": _system_packages(root),
        "installed_python": {"distributions": installed},
        "kiosk_assets": [
            {"path": p.relative_to(root).as_posix(), "size_bytes": p.stat().st_size, "sha256": _sha256(p)}
            for p in _walk_files(root / "kiosk" / "dist", warnings)
        ],
        "media_inventory": media,
        "git_history_media_objects": history,
        "git": git,
        "warnings": warnings,
        "unresolved": unresolved,
    }
    notices = [
        "# Third-party notices (generated evidence inventory)", "",
        "Release status: **BLOCKED**. This file is not a compliance approval and does not identify the final target binary configuration.",
        "Local license texts are copied from installed distribution metadata into `LICENSES/`. Missing license files remain `unknown`.",
        "The lockfiles describe resolved dependency records; they do not prove which artifacts are present in the RK3588 image.", "",
        "## Locally installed Python distributions", "",
    ]
    for item in installed:
        notices.append(f"- **{item['name']} {item['version']}** — {item['metadata_license'] or item['license_expression'] or 'unknown'}; local evidence: {item['license_status']}." )
    notices += ["", "## Kiosk package-lock records", "", "All package-lock records are included, including build, optional, and platform-specific entries."]
    for item in npm["packages"]:
        notices.append(f"- **{item['name']} {item['version'] or 'unknown'}** — {item['license'] or 'unknown'}; dev={item['dev']}, optional={item['optional']}, integrity={item['integrity'] or 'not recorded'}." )
    notices += ["", "## System package requests", "", "APT package versions are not pinned; the list records installer requests only."]
    notices += [f"- {package}" for package in inventory["system_packages"]["requested_packages"]]
    notices += ["", f"- FFmpeg configuration: {inventory['system_packages']['ffmpeg_package_or_configuration']}", f"- Chromium: {inventory['system_packages']['chromium']}"]
    notices += ["", "## Unresolved release evidence", ""] + [f"- {item}" for item in unresolved] + [""]
    (output / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "THIRD_PARTY_NOTICES.md").write_text("\n".join(notices), encoding="utf-8")
    inputs = []
    candidates = [root / relative for relative in HASH_INPUTS]
    generator_source = Path(__file__).resolve()
    if generator_source.is_relative_to(root):
        candidates.append(generator_source)
    candidates.extend(root / item["path"] for item in media)
    dist = root / "kiosk" / "dist"
    if dist.is_dir():
        candidates.extend(_walk_files(dist, warnings))
    for distribution in installed:
        dist_info = Path(distribution["environment_path"])
        candidates.extend(p for p in (dist_info / "METADATA", dist_info / "RECORD") if p.is_file())
        candidates.extend(Path(item["source"]) for item in distribution["license_files"])
    for path in sorted(set(candidates)):
        if path.is_file() and not path.is_symlink():
            inputs.append({"path": path.relative_to(root).as_posix(), "size_bytes": path.stat().st_size, "sha256": _sha256(path)})
    source_inputs = {
        "git": git,
        "warnings": warnings,
        "environment": inventory["environment"],
        "inputs": inputs,
        "history_scope": git["history_scope"],
    }
    (output / "source_inputs.json").write_text(json.dumps(source_inputs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument("--output", type=Path, help="output directory (default: <root>/docs/compliance/generated)")
    parser.add_argument("--audit-date", help="date to label this evidence capture (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    output = args.output or args.root / "docs" / "compliance" / "generated"
    inventory = generate(args.root, output, args.audit_date)
    print(f"release_status={inventory['release_status']} output={Path(output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
