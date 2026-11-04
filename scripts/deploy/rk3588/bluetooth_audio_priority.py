#!/usr/bin/env python3
"""Give active Bluetooth A2DP playback priority over local mpv audio.

PulseAudio's Bluetooth policy remains the sole owner of A2DP routing.  This
helper only mutes the dynamically discovered LIGHT-BELT local-media sink input
while any A2DP source is RUNNING.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Iterator


MEDIA_NAME = "LIGHT-BELT-LocalMedia"
RESTORE_DELAY = 0.20
OWNERSHIP_PROPERTY = "light_belt.bluetooth_priority_owned"
A2DP_SOURCE_RE = re.compile(r"^bluez_source\..*\.a2dp_source$")
RELEVANT_EVENT_RE = re.compile(r"on (?:source|sink-input) #")


class PactlError(RuntimeError):
    """Raised when the pi user's PulseAudio session cannot be queried."""


@dataclass(frozen=True)
class SinkInput:
    index: int
    application_name: str | None
    muted: bool
    owned: bool = False


def parse_short_sources(text: str) -> list[tuple[str, str]]:
    """Return ``(name, state)`` pairs from ``pactl list short sources``."""
    sources: list[tuple[str, str]] = []
    for raw in text.splitlines():
        fields = raw.split()
        if len(fields) >= 3:
            sources.append((fields[1], fields[-1]))
    return sources


def parse_sink_inputs(text: str) -> list[SinkInput]:
    """Parse the stable fields needed from ``pactl list sink-inputs``."""
    results: list[SinkInput] = []
    index: int | None = None
    application_name: str | None = None
    muted = False
    owned = False

    def flush() -> None:
        nonlocal index, application_name, muted, owned
        if index is not None:
            results.append(SinkInput(index, application_name, muted, owned))
        index = None
        application_name = None
        muted = False
        owned = False

    for raw in text.splitlines():
        match = re.match(r"^Sink Input #(\d+)\s*$", raw)
        if match:
            flush()
            index = int(match.group(1))
            continue
        stripped = raw.strip()
        if stripped.startswith("Mute:"):
            muted = stripped.split(":", 1)[1].strip().lower() == "yes"
            continue
        match = re.match(r'^application\.name\s*=\s*"(.*)"\s*$', stripped)
        if match:
            application_name = match.group(1)
            continue
        match = re.match(
            rf'^{re.escape(OWNERSHIP_PROPERTY)}\s*=\s*"?(1|true)"?\s*$',
            stripped,
            flags=re.IGNORECASE,
        )
        if match:
            owned = True
    flush()
    return results


class PactlClient:
    """Small subprocess adapter for the current user's PulseAudio session."""

    def __init__(self) -> None:
        self._subscription: subprocess.Popen[str] | None = None

    @staticmethod
    def _run(*args: str) -> str:
        try:
            completed = subprocess.run(
                ["pactl", *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PactlError(str(exc)) from exc
        if completed.returncode:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise PactlError(message or f"pactl {' '.join(args)} failed")
        return completed.stdout

    def bluetooth_active(self) -> bool:
        return any(
            A2DP_SOURCE_RE.fullmatch(name) and state == "RUNNING"
            for name, state in parse_short_sources(self._run("list", "short", "sources"))
        )

    def sink_inputs(self) -> list[SinkInput]:
        return parse_sink_inputs(self._run("list", "sink-inputs"))

    def set_sink_input_mute(self, index: int, muted: bool) -> None:
        self._run("set-sink-input-mute", str(index), "1" if muted else "0")

    def set_sink_input_owned(self, index: int, owned: bool) -> None:
        if owned:
            self._run("update-sink-input-proplist", str(index), f"{OWNERSHIP_PROPERTY}=1")
        else:
            self._run("remove-sink-input-proplist", str(index), OWNERSHIP_PROPERTY)

    def subscribe(self) -> Iterator[str]:
        process = subprocess.Popen(
            ["pactl", "subscribe"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._subscription = process
        try:
            if process.stdout is None:
                raise PactlError("pactl subscribe has no stdout")
            yield from process.stdout
            return_code = process.wait()
            if return_code:
                message = process.stderr.read().strip() if process.stderr else ""
                raise PactlError(message or f"pactl subscribe exited {return_code}")
        finally:
            self._subscription = None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

    def close(self) -> None:
        if self._subscription is not None and self._subscription.poll() is None:
            self._subscription.terminate()


class BluetoothAudioPriority:
    """Event-driven priority state machine with explicit mute ownership."""

    def __init__(
        self,
        client: PactlClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        restore_delay: float = RESTORE_DELAY,
        log: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.sleep = sleep
        self.restore_delay = restore_delay
        self.log = log
        self.active = False
        self.owned_mutes: set[int] = set()

    def _local_media(self) -> list[SinkInput]:
        return [
            sink_input
            for sink_input in self.client.sink_inputs()
            if sink_input.application_name == MEDIA_NAME
        ]

    def suppress_local_media(self) -> None:
        current = {item.index: item for item in self._local_media()}
        self.owned_mutes.intersection_update(current)
        for item in current.values():
            if item.owned:
                self.owned_mutes.add(item.index)
            if item.muted:
                continue
            self.client.set_sink_input_owned(item.index, True)
            self.client.set_sink_input_mute(item.index, True)
            self.owned_mutes.add(item.index)

    def restore_owned_mutes(self) -> None:
        current = {item.index: item for item in self._local_media()}
        owned_indexes = self.owned_mutes | {
            item.index for item in current.values() if item.owned
        }
        for index in owned_indexes:
            item = current.get(index)
            if item is None:
                continue
            if item.muted:
                self.client.set_sink_input_mute(index, False)
            if item.owned:
                self.client.set_sink_input_owned(index, False)
        self.owned_mutes.clear()

    def initial_sync(self) -> None:
        self.owned_mutes = {
            item.index for item in self._local_media() if item.owned
        }
        self.active = self.client.bluetooth_active()
        if self.active:
            self.suppress_local_media()
            self.log("Bluetooth already active; local media suppressed")
        else:
            if self.owned_mutes:
                self.restore_owned_mutes()
            self.log("Bluetooth inactive; existing local-media mute state preserved")

    def reevaluate(self) -> None:
        current_active = self.client.bluetooth_active()
        if current_active:
            if not self.active:
                self.log("Bluetooth active; local media suppressed immediately")
            self.active = True
            self.suppress_local_media()
            return

        if not self.active:
            return

        self.sleep(self.restore_delay)
        if self.client.bluetooth_active():
            self.active = True
            self.suppress_local_media()
            self.log("Bluetooth resumed inside restore debounce")
            return

        self.restore_owned_mutes()
        self.active = False
        self.log("Bluetooth inactive after debounce; owned suppression released")

    def handle_event(self, event: str) -> None:
        if RELEVANT_EVENT_RE.search(event):
            self.reevaluate()

    def shutdown(self) -> None:
        self.restore_owned_mutes()
        self.active = False


def main() -> int:
    client = PactlClient()
    service = BluetoothAudioPriority(client, log=lambda message: print(
        f"[bluetooth-priority] {message}", flush=True
    ))
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        client.close()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print(
        "[bluetooth-priority] "
        f"media={MEDIA_NAME} restore_delay={RESTORE_DELAY:.2f}s",
        flush=True,
    )
    try:
        while not stopping:
            try:
                service.initial_sync()
                for event in client.subscribe():
                    if stopping:
                        break
                    service.handle_event(event)
            except PactlError as exc:
                if stopping:
                    break
                print(f"[bluetooth-priority] PulseAudio unavailable: {exc}", file=sys.stderr, flush=True)
                time.sleep(2)
    finally:
        try:
            service.shutdown()
        except PactlError as exc:
            print(f"[bluetooth-priority] cleanup incomplete: {exc}", file=sys.stderr, flush=True)
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
