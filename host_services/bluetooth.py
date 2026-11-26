"""Fail-closed Bluetooth and single-speaker coordination for the Host."""

from __future__ import annotations

import asyncio
import logging
import secrets
import sys
from typing import Any, Callable, Protocol

_log = logging.getLogger(__name__)


class BackendUnavailable(RuntimeError):
    """The requested Bluetooth or audio operation cannot be verified."""


class BluetoothBackend(Protocol):
    async def start(self, callbacks: Any) -> None: ...
    async def close(self) -> None: ...
    async def snapshot(self) -> dict[str, Any]: ...
    async def pair(self, device_id: str, operation_id: str) -> None: ...
    async def cancel_pair(self, operation_id: str) -> None: ...
    async def connect(self, device_id: str) -> None: ...
    async def disconnect(self, device_id: str) -> None: ...
    async def remove(self, device_id: str) -> None: ...
    async def answer_challenge(
        self, challenge_id: str, device_id: str, accept: bool, value: str | None
    ) -> None: ...
    async def scan(self, enabled: bool) -> None: ...
    async def set_pairing_window(self, enabled: bool) -> None: ...
    async def set_speaker_route(self, device_id: str) -> dict[str, Any] | None: ...
    async def close_speaker_route(self) -> None: ...


class DisabledBackend:
    """Default backend: report unavailable, never pretend a command succeeded."""

    async def start(self, _callbacks: Any) -> None:
        return None

    async def close(self) -> None:
        return None

    async def snapshot(self) -> dict[str, Any]:
        return {
            "available": False,
            "devices": [],
            "challenges": [],
            "reason": "Bluetooth backend is disabled",
        }

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)

        async def unavailable(*_args, **_kwargs):
            raise BackendUnavailable("Bluetooth/audio backend is disabled")

        return unavailable


class LinuxBackend:
    """Linux BlueZ/PulseAudio backend; dbus-next is imported on start only."""

    def __new__(cls, *args, **kwargs):
        from .bluez_backend import LinuxBluezBackend

        return LinuxBluezBackend(*args, **kwargs)


def create_backend(
    *,
    allow_real: bool = False,
    program_pid: Callable[[], int | None] | None = None,
) -> BluetoothBackend:
    """Create the production backend when explicitly enabled on Linux."""
    if not allow_real:
        return DisabledBackend()
    if not sys.platform.startswith("linux"):
        raise BackendUnavailable("real Bluetooth backend requires Linux")
    if program_pid is None:
        return LinuxBackend()
    return LinuxBackend(program_pid=program_pid, require_program_pid=True)


class AudioSystem:
    """Cached Bluetooth facts plus serialized, fail-closed speaker routing."""

    def __init__(
        self,
        backend: BluetoothBackend | None = None,
        *,
        gate_mpv=None,
        notify=None,
        max_connections: int = 2,
        add_window_seconds: float = 60.0,
        pause_delay: float = 0.25,
    ) -> None:
        self.backend = backend or DisabledBackend()
        self.gate_mpv = gate_mpv or _noop_gate
        self.notify = notify or _noop_notify
        self.max_connections = max_connections
        self.add_window_seconds = add_window_seconds
        self._lock = asyncio.Lock()
        self._snapshot: dict[str, Any] = {
            "bluetooth": {"available": False, "devices": [], "challenges": []},
            "audio_output_available": False,
            "audio_output": {"available": False, "reason": "not observed"},
            "speaker": {"device": None, "status": "idle", "route": None},
            "digital_target": None,
        }
        self._pending: dict[str, str] = {}
        self._selected: str | None = None
        self._route: dict[str, Any] | None = None
        self._route_recovery_hold = False
        self._route_recovery_device: str | None = None
        self._add_timer: asyncio.Task | None = None
        self._scan_timer: asyncio.Task | None = None
        self._release_timer = None
        self._sweep = None
        self._closed = False
        self._started = False
        self._admitted = set()
        self._admission_known = False
        self._pause_delay = pause_delay
        self._release_deadline = None
        self._gate = None

    async def _gate_program(self, muted, *, verify=False):
        if verify or self._gate is not muted:
            await self.gate_mpv(muted)
            self._gate = muted

    async def _watch(self):
        while not self._closed:
            await asyncio.sleep(2)
            try:
                await self._on_backend_event()
            except Exception as exc:
                self._snapshot["speaker"] = {
                    "status": "fault",
                    "device": self._route_recovery_device or (self._route or {}).get("device"),
                    "reason": str(exc),
                }
                self._snapshot["digital_target"] = None
                try:
                    await self._gate_program(True)
                except (OSError, RuntimeError) as gate_error:
                    _log.warning("Unable to verify program mute during route recovery: %s", gate_error)
                await self.notify()

    async def start(self) -> None:
        # Keep program audio gated while recovering a PA route left by an
        # earlier Host process.
        await self._gate_program(True)
        await self.backend.start(self._on_backend_event)
        facts = await self._refresh()
        recovered = facts.get("speaker_route")
        if recovered and recovered.get("verified"):
            self._route = dict(recovered)
            self._selected = None
            self._snapshot["speaker"] = {
                "device": recovered.get("device"),
                "status": "routed",
                "route": self._route,
            }
            self._snapshot["digital_target"] = facts.get("digital_target")
        await self._reconcile_locked(facts, immediate=True)
        self._started = True
        if not isinstance(self.backend, DisabledBackend):
            self._sweep = asyncio.create_task(self._watch())

    async def close(self) -> None:
        self._closed = True
        timers = [
            t
            for t in (self._sweep, self._add_timer, self._scan_timer, self._release_timer)
            if t and t is not asyncio.current_task()
        ]
        for task in timers:
            task.cancel()
        if timers:
            await asyncio.gather(*timers, return_exceptions=True)
        async with self._lock:
            if self._route is not None:
                await self._gate_program(True)
                await self.backend.close_speaker_route()
                self._route = None
        await self.backend.close()

    def snapshot(self) -> dict[str, Any]:
        import copy

        return copy.deepcopy(self._snapshot)

    async def _refresh(self) -> dict[str, Any]:
        facts = await self.backend.snapshot()
        operations = facts.get("operations", {})
        for operation_id, result in operations.items():
            if result.get("state") in {"succeeded", "failed", "cancelled"}:
                self._pending.pop(operation_id, None)
        facts.update(
            connected_count=sum(bool(device.get("connected")) for device in facts.get("devices", [])),
            limit=self.max_connections,
            pending_count=len(self._pending),
        )
        self._snapshot.update(
            bluetooth=facts,
            audio_output_available=bool(facts.get("audio_output_available")),
            audio_output=facts.get("audio_output", {"available": False}),
        )
        if facts.get("route_error"):
            await self._revoke_lighting_source()
            if self._route is not None:
                self._route_recovery_device = self._route.get("device")
                self._route_recovery_hold = True
            await self._gate_program(True)
            raise BackendUnavailable(
                f"speaker route ownership is uncertain: {facts['route_error']}"
            )
        if "speaker_route" in facts and self._route is not None:
            actual = facts["speaker_route"]
            if actual is None:
                lost_device = self._route.get("device")
                self._route_recovery_device = lost_device
                self._route_recovery_hold = True
                await self._revoke_lighting_source()
                await self._gate_program(True)
                self._route = None
                self._selected = lost_device
                self._snapshot["speaker"] = {
                    "device": lost_device,
                    "status": "waiting",
                    "route": None,
                }
            elif actual.get("module_id") != self._route.get("module_id"):
                if (
                    self._route_recovery_hold
                    and actual.get("verified")
                    and actual.get("device") == self._route_recovery_device
                ):
                    self._route = dict(actual)
                else:
                    await self._revoke_lighting_source()
                    raise BackendUnavailable("Bluetooth route identity changed")
        if self._route is None or facts.get("speaker_route"):
            self._snapshot["digital_target"] = facts.get("digital_target")
        return facts

    async def _on_backend_event(self, _event: Any = None) -> None:
        if self._closed or not self._started:
            return
        async with self._lock:
            facts = await self._refresh()
            await self._reconcile_locked(facts)
        await self.notify()

    async def _check_after(self, delay):
        await asyncio.sleep(delay)
        if not self._closed:
            await self._on_backend_event()

    async def _reconcile_locked(
        self, facts: dict[str, Any], *, immediate=False
    ) -> None:
        devices = facts.get("devices", [])
        active = [d for d in devices if d.get("connected") and _device_active(d, facts)]
        connected = {device["id"] for device in devices if device.get("connected")}
        if len(connected) > self.max_connections:
            if self._admission_known:
                old = self._admitted & connected
                arrivals = sorted(connected - old)
                for extra in arrivals[max(0, self.max_connections - len(old)) :]:
                    await self.backend.disconnect(extra)
            raise BackendUnavailable(
                "controller exceeded simultaneous connection limit"
            )
        self._admitted, self._admission_known = connected, True
        if self._route_recovery_hold:
            recovering = next((d for d in devices if d["id"] == self._route_recovery_device), None)
            if (recovering is None or not recovering.get("connected")
                    or recovering.get("player_status") in {"paused", "stopped"}):
                if self._selected == self._route_recovery_device:
                    self._selected = None
                self._route_recovery_hold = False
                self._route_recovery_device = None
        if self._selected not in connected:
            self._selected = None
        winner = (self._route or {}).get("device")
        active_ids = [device["id"] for device in active]
        if self._selected is not None:
            target_id = self._selected if self._selected in active_ids else None
        elif winner in active_ids:
            target_id = winner
        else:
            target_id = next(iter(active_ids), None)
        if (
            winner
            and winner in connected
            and winner not in active_ids
            and not immediate
        ):
            old = next(d for d in devices if d["id"] == winner)
            player = old.get("player_status")
            if player in ("playing", "forward-seek", "reverse-seek"):
                self._release_deadline = None
                return
            delay = self._pause_delay if player in ("paused", "stopped") else 1.5
            loop = asyncio.get_running_loop()
            if self._release_deadline is None:
                self._release_deadline = loop.time() + delay
            left = self._release_deadline - loop.time()
            if left > 0:
                if self._release_timer is None or self._release_timer.done():
                    self._release_timer = asyncio.create_task(self._check_after(left))
                return
        self._release_deadline = None
        if self._route is not None and target_id == self._route.get("device"):
            self._selected = None
            self._route_recovery_hold = False
            self._route_recovery_device = None
            self._snapshot["speaker"] = {
                "device": target_id, "status": "routed", "route": self._route,
            }
            return
        if target_id is None:
            if (
                self._route_recovery_hold
                and self._route_recovery_device in connected
            ):
                await self._gate_program(True)
                self._snapshot["speaker"] = {
                    "device": self._route_recovery_device,
                    "status": "waiting",
                    "route": None,
                }
                return
            if self._route is not None:
                await self._revoke_lighting_source()
                await self._gate_program(True)
                await self._close_route_locked()
            await self._gate_program(False)
            self._snapshot["speaker"] = {
                "device": self._selected,
                "status": "waiting" if self._selected else "idle",
                "route": None,
            }
            return
        await self._revoke_lighting_source()
        await self._gate_program(True, verify=True)
        await self._close_route_locked()
        try:
            route = await self.backend.set_speaker_route(target_id)
            if not route or not route.get("verified"):
                raise BackendUnavailable("speaker route readback failed")
            route = dict(route)
            route["device"] = target_id
            self._route = route
            self._selected = None
            self._route_recovery_hold = False
            self._route_recovery_device = None
            self._snapshot["speaker"] = {
                "device": target_id,
                "status": "routed",
                "route": route,
            }
            self._snapshot["digital_target"] = route.get("digital_target")
        except Exception as exc:
            self._route = None
            self._snapshot["speaker"] = {
                "device": target_id,
                "status": "fault",
                "route": None,
            }
            self._snapshot["digital_target"] = None
            await self.notify()
            raise BackendUnavailable(str(exc)) from exc

    def _occupied(self, facts):
        connected = {d["id"] for d in facts["devices"] if d.get("connected")}
        return connected.union(self._pending.values(), facts.get("reserved_devices", ()))

    async def pair(self, device_id: str, *, operation_id: str | None = None) -> str:
        async with self._lock:
            facts = await self._refresh()
            for pending, device in self._pending.items():
                if device == device_id:
                    return pending
            operation_id = operation_id or secrets.token_urlsafe(12)
            if operation_id in self._pending:
                raise BackendUnavailable(
                    "pairing operation already belongs to another device"
                )
            occupied = self._occupied(facts)
            if len(occupied | {device_id}) > self.max_connections:
                raise BackendUnavailable("Bluetooth connection capacity is full")
            if not any(d.get("id") == device_id for d in facts.get("devices", [])):
                raise BackendUnavailable("unknown Bluetooth device")
            self._pending[operation_id] = device_id
            try:
                await self.backend.pair(device_id, operation_id)
            except Exception:
                self._pending.pop(operation_id, None)
                raise
        await self.notify()
        return operation_id

    async def cancel_pair(self, operation_id: str) -> None:
        async with self._lock:
            if operation_id not in self._pending:
                raise BackendUnavailable("pairing operation is not pending")
            await self.backend.cancel_pair(operation_id)
            self._pending.pop(operation_id, None)
        await self.notify()

    async def connect(self, device_id: str) -> None:
        async with self._lock:
            facts = await self._refresh()
            if len(self._occupied(facts) | {device_id}) > self.max_connections:
                raise BackendUnavailable("Bluetooth connection capacity is full")
            await self.backend.connect(device_id)
            await self._refresh()
        await self.notify()

    async def disconnect(self, device_id: str) -> None:
        async with self._lock:
            if self._selected == device_id or (self._route or {}).get("device") == device_id:
                await self._revoke_lighting_source()
                await self._gate_program(True)
                await self._close_route_locked()
                self._selected = None
                if self._route_recovery_device == device_id:
                    self._route_recovery_hold = False
                    self._route_recovery_device = None
            await self.backend.disconnect(device_id)
            facts = await self._refresh()
            await self._reconcile_locked(facts)
        await self.notify()

    async def remove(self, device_id: str) -> None:
        async with self._lock:
            facts = await self._refresh()
            device = next((d for d in facts["devices"] if d["id"] == device_id), None)
            if device is None:
                raise BackendUnavailable("unknown Bluetooth device")
            if (self._route or {}).get("device") == device_id:
                await self._revoke_lighting_source()
                await self._gate_program(True)
                await self._close_route_locked()
            if device.get("connected"):
                await self.backend.disconnect(device_id)
            await self.backend.remove(device_id)
            await self._reconcile_locked(await self._refresh(), immediate=True)
        await self.notify()

    async def answer_challenge(
        self, challenge_id: str, device_id: str, accept: bool, value: str | None = None
    ) -> None:
        facts = await self._refresh()
        challenge = next(
            (
                item
                for item in facts.get("challenges", [])
                if item.get("id") == challenge_id and item.get("device_id") == device_id
            ),
            None,
        )
        if challenge is None or challenge.get("expired"):
            raise BackendUnavailable("pairing challenge is unavailable or expired")
        await self.backend.answer_challenge(challenge_id, device_id, accept, value)
        await self.notify()

    async def scan(self) -> None:
        await self.backend.scan(True)
        if self._scan_timer:
            self._scan_timer.cancel()
        self._scan_timer = asyncio.create_task(self._expire_scan())
        await self.notify()

    async def _expire_scan(self):
        await asyncio.sleep(self.add_window_seconds)
        if self._add_timer is None:
            await self.stop_scan()

    async def stop_scan(self) -> None:
        await self.backend.scan(False)
        await self.notify()

    async def add(self) -> None:
        facts = await self._refresh()
        if (
            int(facts.get("connected_count", 0)) + len(self._pending)
            >= self.max_connections
        ):
            raise BackendUnavailable("Bluetooth connection capacity is full")
        try:
            await self.backend.set_pairing_window(True)
            await self.backend.scan(True)
        except Exception:
            await self.backend.set_pairing_window(False)
            raise
        if self._add_timer is not None:
            self._add_timer.cancel()
        self._add_timer = asyncio.create_task(self._expire_add_window())
        await self.notify()

    async def close_add(self) -> None:
        if self._add_timer is not None:
            if self._add_timer is not asyncio.current_task():
                self._add_timer.cancel()
            self._add_timer = None
        try:
            await self.backend.scan(False)
        finally:
            await self.backend.set_pairing_window(False)
        await self.notify()

    async def _expire_add_window(self) -> None:
        try:
            await asyncio.sleep(self.add_window_seconds)
            await self.close_add()
        except asyncio.CancelledError:
            return

    async def set_speaker(self, device_id: str | None) -> dict[str, Any]:
        async with self._lock:
            facts = await self._refresh()
            if device_id is not None and not any(
                d.get("id") == device_id and d.get("connected")
                for d in facts.get("devices", [])
            ):
                raise BackendUnavailable(
                    "speaker target must be an accepted connected device"
                )
            self._selected = device_id
            if device_id != self._route_recovery_device:
                self._route_recovery_hold = False
                self._route_recovery_device = None
            await self._reconcile_locked(facts, immediate=True)
            result = self.snapshot()["speaker"]
        await self.notify()
        return result

    async def _close_route_locked(self) -> None:
        if self._route is not None:
            await self.backend.close_speaker_route()
            self._route = None
            self._snapshot["digital_target"] = None

    async def _revoke_lighting_source(self):
        self._snapshot["speaker"] = {"device": None, "status": "switching", "route": None}
        self._snapshot["digital_target"] = None
        await self.notify()


def _device_active(device: dict[str, Any], facts: dict[str, Any]) -> bool:
    if device.get("player_status") in {"paused", "stopped", "error"}:
        return False
    active = device.get("activity") in {"transmitting", "playing"} or device.get(
        "transport_state"
    ) in {"active", "pending"}
    return bool(
        active and device.get("source_available", facts.get("source_available", True))
    )


async def _noop_gate(_muted: bool) -> None:
    raise BackendUnavailable("mpv gate callback is not configured")


async def _noop_notify() -> None:
    return None
