"""Cabin data uplink (U01): RK -> APP server, PLC source.

Every second the PLC snapshot is read from the local read-only PLC API and
stored as one event. Every second the oldest stored events (up to 100) are
posted to the APP server. Events listed in ``data.accepted`` are deleted;
HTTP 400 drops the batch; anything else keeps the events for the next round.
Configured through ~/.config/light-belt/host.env; without the server address,
cabin ID and device token the uplink does not run.
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from . import plc_status_api

_log = logging.getLogger(__name__)

EVENTS_PATH = "/api/v1/cabin/events"
BATCH_SIZE = 100
INTERVAL_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 10.0
PLC_URL = f"http://127.0.0.1:{plc_status_api.PORT}{plc_status_api.ROUTE}"

# U01 data field (source=plc) -> PLC API point key.
PLC_FIELDS = (
    ("oxygen_concentration", "oxygen_concentration"),
    ("temperature", "temperature"),
    ("humidity", "humidity"),
    ("co2_concentration", "co2_concentration"),
    ("pressure", "pressure"),
    ("air_compressor_on", "air_compressor_status"),
    ("oxygen_generator_on", "oxygen_generator_status"),
    ("cabin_running", "equipment_running"),
    ("run_time", "runtime"),
    ("mode", "mode"),
    ("exhaust_valve_1_on", "exhaust_valve_1_status"),
    ("exhaust_valve_2_on", "exhaust_valve_2_status"),
    ("aux_exhaust_valve_on", "aux_exhaust_valve_status"),
    ("alarm", "equipment_alarm"),
    ("air_inlet_valve_on", "air_inlet_valve_status"),
)


def uplink_dir():
    return Path(os.getenv("LIGHT_BELT_UPLINK_DIR", "~/.config/light-belt/uplink")).expanduser()


def settings_from_environment():
    """Return (url, cabin_id, token), or None when the uplink is not configured."""
    server = os.environ.get("LIGHT_BELT_UPLINK_SERVER", "").strip().rstrip("/")
    cabin_id = os.environ.get("LIGHT_BELT_CABIN_ID", "").strip()
    token = os.environ.get("LIGHT_BELT_DEVICE_TOKEN", "").strip()
    if not (server and cabin_id and token):
        if server or cabin_id or token:
            _log.warning("Uplink needs LIGHT_BELT_UPLINK_SERVER, LIGHT_BELT_CABIN_ID and "
                         "LIGHT_BELT_DEVICE_TOKEN; uplink not started")
        return None
    return server + EVENTS_PATH, cabin_id, token


def plc_event(snapshot, user=None):
    """Build one U01 event from a PLC API 200 response body."""
    points = snapshot["points"]
    read_at = datetime.fromisoformat(snapshot["read_at"])
    return {
        "id": uuid.uuid4().hex,
        "source": "plc",
        "device_id": "plc",
        "ts": int(read_at.timestamp() * 1000),
        "user_id": user["user_id"] if user else None,
        "username": user["username"] if user else None,
        "data": {field: points[key]["value"] for field, key in PLC_FIELDS},
    }


class EventStore:
    """Events wait here, in arrival order, until the APP server accepts them."""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS events ("
                         "seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, "
                         "body TEXT NOT NULL)")
        self._db.commit()

    def add(self, event):
        with self._lock:
            self._db.execute("INSERT INTO events (id, body) VALUES (?, ?)",
                             (event["id"], json.dumps(event, ensure_ascii=False)))
            self._db.commit()

    def oldest(self, limit=BATCH_SIZE):
        with self._lock:
            rows = self._db.execute("SELECT body FROM events ORDER BY seq LIMIT ?",
                                    (limit,)).fetchall()
        return [json.loads(body) for (body,) in rows]

    def delete(self, ids):
        with self._lock:
            self._db.executemany("DELETE FROM events WHERE id = ?", [(i,) for i in ids])
            self._db.commit()

    def count(self):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def close(self):
        with self._lock:
            self._db.close()


def read_plc(url=PLC_URL):
    """Return the PLC API body, or None when no valid snapshot is available."""
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            body = json.load(response)
    except (OSError, ValueError):
        return None
    return body if body.get("status") == "ok" else None


def post_batch(url, token, cabin_id, events):
    """POST one batch; return the event ids that may be deleted locally."""
    body = json.dumps({"cabin_id": cabin_id, "events": events}, ensure_ascii=False).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
    })
    sent = {event["id"] for event in events}
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            _log.warning("APP server rejected an uplink batch (400); dropping %d events", len(events))
            return sent
        _log.warning("APP server returned HTTP %s; keeping %d events", exc.code, len(events))
        return set()
    except (OSError, ValueError) as exc:
        _log.warning("Uplink send failed (%s); keeping %d events", exc, len(events))
        return set()
    accepted = payload.get("data", {}).get("accepted") if isinstance(payload, dict) else None
    if payload.get("ok") is not True or not isinstance(accepted, list):
        _log.warning("Unexpected APP server response; keeping %d events", len(events))
        return set()
    return sent & {i for i in accepted if isinstance(i, str)}


class Uplink:
    def __init__(self, url, cabin_id, token, store, current_user=lambda: None, plc_url=PLC_URL):
        self.url, self.cabin_id, self.token = url, cabin_id, token
        self.store = store
        self.current_user = current_user
        self.plc_url = plc_url
        self._plc_ok = None

    def sample_once(self):
        snapshot = read_plc(self.plc_url)
        if (snapshot is not None) != self._plc_ok:
            self._plc_ok = snapshot is not None
            (_log.info if self._plc_ok else _log.warning)(
                "PLC snapshot %s", "available" if self._plc_ok else "unavailable")
        if snapshot is not None:
            self.store.add(plc_event(snapshot, self.current_user()))

    def send_once(self):
        events = self.store.oldest()
        if events:
            self.store.delete(post_batch(self.url, self.token, self.cabin_id, events))

    async def run(self):
        await asyncio.gather(self._every_second(self.sample_once),
                             self._every_second(self.send_once))

    @staticmethod
    async def _every_second(step):
        while True:
            try:
                await asyncio.to_thread(step)
            except Exception:
                _log.exception("Uplink step failed")
            await asyncio.sleep(INTERVAL_SECONDS)


def start():
    """Start the uplink task when configured; return (task, store) or None."""
    settings = settings_from_environment()
    if settings is None:
        return None
    store = EventStore(uplink_dir() / "events.sqlite3")
    task = asyncio.create_task(Uplink(*settings, store).run())
    _log.info("Uplink to %s started", settings[0])
    return task, store
