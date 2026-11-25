"""Per-cabin control screen enrollment and persistent operating preferences."""

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
from contextlib import closing, contextmanager
from threading import RLock


def control_dir():
    return Path(
        os.getenv("LIGHT_BELT_CONTROL_DIR", "~/.config/light-belt/control")
    ).expanduser()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class ControlTerminal:
    def __init__(self, directory):
        self.directory = directory

    @contextmanager
    def database(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.directory / "terminal.sqlite")) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS terminal (id INTEGER PRIMARY KEY, "
                "code TEXT, expires REAL, attempts INTEGER, session TEXT)"
            )
            db.execute("INSERT OR IGNORE INTO terminal(id) VALUES(1)")
            yield db

    def issue_code(self):
        code = secrets.token_urlsafe(12)
        with self.database() as db:
            db.execute(
                "UPDATE terminal SET code=?, expires=?, attempts=5",
                (digest(code), time.time() + 300),
            )
        return code

    def revoke(self):
        with self.database() as db:
            db.execute("UPDATE terminal SET session=NULL, code=NULL")

    def enroll(self, code):
        with self.database() as db:
            stored, expiry, attempts = db.execute(
                "SELECT code,expires,attempts FROM terminal"
            ).fetchone()
            if stored and expiry > time.time() and attempts > 0:
                if hmac.compare_digest(stored, digest(code)):
                    session = secrets.token_urlsafe(32)
                    db.execute(
                        "UPDATE terminal SET session=?,code=NULL", (digest(session),)
                    )
                    return session
                db.execute("UPDATE terminal SET attempts=attempts-1")
        raise ValueError("登记码无效或已过期")

    def authorized(self, session):
        if not session or not (self.directory / "terminal.sqlite").is_file():
            return False
        with closing(sqlite3.connect(self.directory / "terminal.sqlite")) as db:
            row = db.execute("SELECT session FROM terminal WHERE id=1").fetchone()
        return bool(row and row[0] and hmac.compare_digest(row[0], digest(session)))

    def generation(self):
        if not (self.directory / "terminal.sqlite").is_file():
            return None
        with closing(sqlite3.connect(self.directory / "terminal.sqlite")) as db:
            row = db.execute("SELECT session FROM terminal WHERE id=1").fetchone()
        return row[0] if row else None


class ControlConflict(ValueError):
    pass


class ControlPreferences:
    def __init__(self, directory):
        self.path = directory / "preferences.json"
        self.lock = RLock()
        self.token = secrets.token_urlsafe(16)
        self._unsaved = False
        self.data = {
            "mode": "auto",
            "intent": "follow",
            "volume": 0.5,
            "muted": False,
            "brightness": 0.5,
            "targets": {},
        }
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
        if self.data["mode"] == "device":
            self.data["mode"] = "auto"
        if self.data["mode"] not in ("auto", "mic") or self.data["intent"] not in (
            "off",
            "follow",
            "manual",
            "music",
        ):
            raise ValueError("Invalid stored lighting preference")
        for name in ("volume", "brightness"):
            if (
                type(self.data[name]) not in (int, float)
                or not 0 <= self.data[name] <= 1
            ):
                raise ValueError(f"Invalid stored {name}")
        if type(self.data["muted"]) is not bool or not isinstance(
            self.data["targets"], dict
        ):
            raise ValueError("Invalid stored control preference")

    def save(self, **changes):
        with self.lock:
            data = dict(self.data, **changes)
            if data == self.data and not self._unsaved:
                return
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            self.data = data
            self._unsaved = False

    def emergency_off(self):
        with self.lock:
            self.data = dict(self.data, intent="off")
            self._unsaved = True
            self.token = secrets.token_urlsafe(16)

    def set_mode(self, mode):
        if mode not in ("device", "auto", "mic"):
            raise ValueError("未知的灯光分析来源")
        self.save(mode="auto" if mode == "device" else mode)

    def set_intent(self, intent, expected, **changes):
        if intent not in ("follow", "music", "manual", "off"):
            raise ValueError("未知的灯光设置")
        with self.lock:
            if intent != "off" and expected != self.token:
                raise ControlConflict("灯光设置已改变，请刷新")
            self.save(intent=intent, **changes)
            self.token = secrets.token_urlsafe(16)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enroll", "revoke"))
    terminal = ControlTerminal(control_dir())
    if parser.parse_args().action == "enroll":
        print(terminal.issue_code())
    else:
        terminal.revoke()
