#!/usr/bin/python3
"""Create or migrate per-device Host credentials without executing env files."""

import argparse
import os
import re
from pathlib import Path
import secrets
import shlex


def read_values(content):
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid Host EnvironmentFile assignment")
        parsed = shlex.split(value, comments=True)
        if len(parsed) != 1:
            raise ValueError(f"Invalid Host environment value for {key}")
        values[key] = parsed[0]
    secret = values.get("LIGHT_BELT_JWT_SECRET", "")
    if secret == "light-belt-dev-secret-change-in-production" or len(secret.encode("utf-8")) < 32:
        raise ValueError("Host JWT secret must contain at least 32 bytes")
    if values.get("LIGHT_BELT_PAIRING_CODE", "").strip() in {"", "123456"}:
        raise ValueError("Host pairing code must be independent of the development default")
    return values


def ensure_environment(path, legacy=None, uid=None, gid=None):
    path = Path(path)
    for location in (path, *path.parents):
        if location.is_symlink():
            raise ValueError(f"Refusing Host environment symlink: {location}")
    if path.exists():
        values = read_values(path.read_text(encoding="utf-8"))
    else:
        if legacy is not None and Path(legacy).exists():
            content = Path(legacy).read_bytes().decode("utf-8")
        else:
            content = (f"LIGHT_BELT_JWT_SECRET={secrets.token_hex(32)}\n"
                       f"LIGHT_BELT_PAIRING_CODE={secrets.randbelow(90000000) + 10000000}\n")
        values = read_values(content)
        created = []
        parent = path.parent
        while not parent.exists():
            created.append(parent)
            parent = parent.parent
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if uid is not None:
            for directory in created:
                os.chown(directory, uid, gid)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
    path.chmod(0o600)
    if uid is not None:
        os.chown(path.parent, uid, gid)
        os.chown(path, uid, gid)
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--uid", required=True, type=int)
    parser.add_argument("--gid", required=True, type=int)
    args = parser.parse_args()
    path = args.home / ".config/light-belt/host.env"
    ensure_environment(path, Path("/etc/light-belt/host.env"), args.uid, args.gid)
    print(f"Persistent Host credentials ready at {path}")


if __name__ == "__main__":
    main()
