#!/usr/bin/env python3
"""Narrowly disable PulseAudio's automatic A2DP playback loopback."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import tempfile

MARKER = "# LIGHT-BELT managed a2dp_source policy"


def configure(path: Path) -> bool:
    if path.is_symlink():
        raise ValueError(f"refusing PulseAudio config symlink: {path}")
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    indexes = [
        index for index, line in enumerate(lines)
        if re.match(r"^\s*load-module\s+module-bluetooth-policy(?:\s|$)", line)
    ]
    if len(indexes) != 1:
        raise ValueError(f"expected one active module-bluetooth-policy line in {path}, found {len(indexes)}")
    index = indexes[0]
    line = lines[index]
    if MARKER in line and re.search(r"\ba2dp_source\s*=\s*false(?:\s|$)", line):
        return False
    body = line.split("#", 1)[0].rstrip("\r\n")
    newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
    args = re.sub(r"\ba2dp_source\s*=\s*\S+", "a2dp_source=false", body)
    if args == body and re.search(r"\ba2dp_source\s*=", body) is None:
        args += " a2dp_source=false"
    lines[index] = f"{args} {MARKER}{newline}"
    updated = "".join(lines)
    if updated == content:
        return False
    backup = path.with_name(path.name + ".light-belt.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    fd, temp_name = tempfile.mkstemp(prefix=".light-belt-pulse-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, path.stat().st_mode & 0o7777)
        if os.name == "posix":
            os.chown(temp_name, path.stat().st_uid, path.stat().st_gid)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


if __name__ == "__main__":
    import sys
    configure(Path(sys.argv[1]))
