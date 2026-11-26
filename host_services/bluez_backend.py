"""Linux BlueZ D-Bus Agent and PulseAudio backend.

The module imports dbus-next only when started so non-Linux Host tests can
inject a backend without installing or importing Linux system bindings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from typing import Any, Callable

from .audio_routing import PulseAudioRouter
from .bluetooth import BackendUnavailable


BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
TRANSPORT_IFACE = "org.bluez.MediaTransport1"
PLAYER_IFACE = "org.bluez.MediaPlayer1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_PATH = "/org/light_belt/agent"


class LinuxBluezBackend:
    def __init__(
        self,
        *,
        bus=None,
        router: PulseAudioRouter | None = None,
        sink: str | None = None,
        challenge_timeout: float = 60.0,
        pair_timeout: float = 90.0,
        max_connections: int = 2,
        program_pid: Callable[[], int | None] | None = None,
        require_program_pid: bool = False,
    ) -> None:
        if not sys.platform.startswith("linux") and bus is None:
            raise BackendUnavailable("real Bluetooth backend requires Linux")
        self.bus = bus
        self.router = router or PulseAudioRouter()
        self.sink = sink or os.environ.get("LIGHT_BELT_AUDIO_SINK")
        self.challenge_timeout = challenge_timeout
        self.pair_timeout = pair_timeout
        self.max_connections = max_connections
        self.program_pid = program_pid
        self.require_program_pid = require_program_pid
        self._callbacks = None
        self._objects: dict[str, dict[str, dict[str, Any]]] = {}
        self._challenges: dict[str, dict[str, Any]] = {}
        self._challenge_waiters: dict[str, asyncio.Future] = {}
        self._add_window_generation = 0
        self._pair_tasks: dict[str, asyncio.Task] = {}
        self._pair_devices: dict[str, str] = {}
        self._pair_results: dict[str, dict[str, Any]] = {}
        self._agent_interface = None
        self._agent_manager = None
        self._agent_registration_lock = asyncio.Lock()
        self._agent_retry_task: asyncio.Task | None = None
        self._owner = True
        self._agent_registered = False
        self._started = False
        self._closing = False
        self._route_device: str | None = None
        self._route: dict[str, Any] | None = None
        self._route_error: str | None = None
        self._event_task = None
        self._dirty = False
        self._last_discovery = False
        self._sources: dict[str, str] = {}
        self._source_monitor: dict[str, str] = {}
        self._incoming_reservations: set[str] = set()
        self._pair_window_previous: tuple[bool, bool] | None = None

    async def start(self, callbacks) -> None:
        if self._started:
            return
        self._closing = False
        if self.bus is None:
            try:
                from dbus_next import BusType
                from dbus_next.aio import MessageBus
            except ImportError as exc:
                raise BackendUnavailable(
                    "dbus-next is required for Linux BlueZ control"
                ) from exc
            self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        try:
            from dbus_next import Message, Variant
            from dbus_next.errors import DBusError
            from dbus_next.service import ServiceInterface, method
        except ImportError as exc:
            raise BackendUnavailable(
                "dbus-next is required for Linux BlueZ control"
            ) from exc
        self._dbus = (Message, Variant, DBusError)
        self._callbacks = callbacks
        backend = self

        class Agent(ServiceInterface):
            def __init__(self):
                super().__init__("org.bluez.Agent1")

            @method()
            def Release(self):
                backend._agent_released()

            @method()
            async def RequestConfirmation(self, device: "o", passkey: "u"):
                await backend._challenge(device, "confirm", f"{int(passkey):06d}")

            @method()
            async def RequestAuthorization(self, device: "o"):
                await backend._challenge(device, "authorize", None)

            @method()
            async def AuthorizeService(self, device: "o", uuid: "s"):
                if not backend._service_allowed(uuid):
                    raise DBusError(
                        "org.bluez.Error.Rejected", "Service is not allowed"
                    )
                if backend._objects.get(device, {}).get(DEVICE_IFACE, {}).get("Paired"):
                    return
                await backend._challenge(device, "authorize_service", uuid)

            @method()
            async def RequestPinCode(self, device: "o") -> "s":
                answer = await backend._challenge(device, "pin", None)
                return str(answer)

            @method()
            async def RequestPasskey(self, device: "o") -> "u":
                answer = await backend._challenge(device, "passkey", None)
                return int(answer)

            @method()
            def DisplayPinCode(self, device: "o", pincode: "s"):
                backend._display_challenge(device, "display_pin", pincode)

            @method()
            def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
                backend._display_challenge(
                    device, "display_passkey", f"{int(passkey):06d}"
                )

            @method()
            def Cancel(self):
                backend._cancel_challenges()

        self._agent_interface = Agent()
        self.bus.export(AGENT_PATH, self._agent_interface)
        await self._call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "AddMatch",
            "s",
            [
                "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.ObjectManager'"
            ],
        )
        await self._call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "AddMatch",
            "s",
            [
                "type='signal',sender='org.bluez',interface='org.freedesktop.DBus.Properties'"
            ],
        )
        await self._call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "AddMatch",
            "s",
            [
                "type='signal',sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',member='NameOwnerChanged'"
            ],
        )
        self.bus.add_message_handler(self._message_handler)
        # Subscribe before taking the initial snapshot; subsequent signals are
        # merged by re-enumeration so startup changes cannot disappear.
        await self.router.assert_exclusive_policy()
        await self._check_legacy_services()
        await self._register_default_agent()
        self._started = True
        await self.router.start_monitor(self._schedule_emit)
        await self._read_objects()
        await self.set_pairing_window(False)
        self._route = await self.router.recover_owned(
            set(self._sources.values()), {name for name in self._source_monitor}
        )
        if self._route:
            self._route_device = self._route["device"]
        await self._emit()

    async def close(self) -> None:
        self._closing = True
        self._callbacks = None
        await self.router.stop_monitor()
        if self._agent_retry_task and not self._agent_retry_task.done():
            self._agent_retry_task.cancel()
            await asyncio.gather(self._agent_retry_task, return_exceptions=True)
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
            await asyncio.gather(self._event_task, return_exceptions=True)
        if not self._started or not self._owner:
            if self.bus is not None and hasattr(self.bus, "disconnect"):
                self.bus.disconnect()
            return
        if self._route is not None:
            await self.close_speaker_route()
        if self._pair_window_previous is not None:
            try:
                await self.set_pairing_window(False)
            except Exception:
                pass
        self._cancel_challenges()
        for task in list(self._pair_tasks.values()):
            task.cancel()
        if self._agent_manager is not None:
            try:
                await self._agent_manager.call_unregister_agent(AGENT_PATH)
            except Exception:
                pass
        try:
            self.bus.unexport(AGENT_PATH, self._agent_interface)
            self.bus.remove_message_handler(self._message_handler)
        except Exception:
            pass
        self._started = False
        if hasattr(self.bus, "disconnect"):
            self.bus.disconnect()

    async def snapshot(self) -> dict[str, Any]:
        if not self._started:
            return {
                "available": False,
                "devices": [],
                "challenges": [],
                "reason": "BlueZ backend is not started",
            }
        await self._read_objects()
        devices = self._device_snapshot()
        audio_output = await self._audio_output_observation()
        digital_target = None
        digital_error = None
        if self._route_error:
            try:
                await self.router.assert_exclusive_policy()
                recovered = await self.router.recover_owned(
                    set(self._sources.values()), set(self._source_monitor)
                )
                self._route = recovered
                self._route_device = recovered.get("device") if recovered else None
                self._route_error = None
            except BackendUnavailable as exc:
                self._route_error = str(exc)
        if self._route and self._route_device:
            try:
                details = await self.router.route_details(self._route["module_id"])
            except BackendUnavailable as exc:
                # The module index may have been reused by another owner. Do
                # not unload an unverified module or release the mpv gate.
                self._route_error = str(exc)
                self._route = None
                self._route_device = None
            else:
                route = dict(self._route, **details)
                route["monitor_source"] = details["monitor_source"]
                digital_target = self._phone_pcm_target(
                    route, self._route_device
                )
        else:
            try:
                sink = self.sink or (await self.router._runner("get-default-sink")).strip()
                if sink.startswith("alsa_output.platform-rt5616"):
                    digital_target = await self._program_target(sink)
            except Exception as exc:
                digital_error = str(exc)
        return {
            "available": bool(self._owner and self._agent_registered),
            "audio_output_available": audio_output["available"],
            "audio_output": audio_output,
            "audio_error": audio_output.get("reason"),
            "digital_audio_error": digital_error,
            "powered": self._adapter_bool("Powered"),
            "discovering": self._adapter_bool("Discovering"),
            "pairable": self._adapter_bool("Pairable"),
            "discoverable": self._adapter_bool("Discoverable"),
            "devices": devices,
            "challenges": list(self._challenges.values()),
            "operations": dict(self._pair_results),
            "digital_target": digital_target,
            "reserved_slots": len(self._incoming_reservations),
            "reserved_devices": sorted(self._incoming_reservations),
            "speaker_route": dict(self._route) if self._route else None,
            "route_error": self._route_error,
        }

    async def _audio_output_observation(self) -> dict[str, Any]:
        """Observe the configured/default sink without making BlueZ unavailable."""
        try:
            sink = self.sink or (await self.router._runner("get-default-sink")).strip()
            rows = json.loads(await self.router._runner("--format=json", "list", "sinks"))
            selected = next((row for row in rows if row.get("name") == sink), None)
            if selected is None:
                return {"available": False, "sink": sink, "reason": "audio output sink is absent"}
            state = str(selected.get("state", "")).upper()
            active_port = selected.get("active_port")
            port = next(
                (item for item in selected.get("ports", []) if item.get("name") == active_port),
                None,
            )
            port_availability = str((port or {}).get("availability", "unknown")).lower()
            valid_state = state in {"IDLE", "RUNNING", "SUSPENDED"}
            port_unavailable = port_availability in {"no", "not available"}
            available = valid_state and not port_unavailable
            if not valid_state:
                reason = f"audio output sink state is {state or 'unknown'}"
            elif port_unavailable:
                reason = "active audio output port is unavailable"
            else:
                reason = None
            return {
                "available": available,
                "sink": sink,
                "index": int(selected["index"]),
                "state": state or None,
                "active_port": active_port,
                "port_availability": port_availability,
                "reason": reason,
            }
        except Exception as exc:
            return {"available": False, "sink": None, "state": None, "reason": str(exc)}

    async def pair(self, device_id: str, operation_id: str) -> None:
        path = self._device_path(device_id)
        if path is None:
            raise BackendUnavailable("unknown BlueZ device")
        if (
            operation_id in self._pair_tasks
            and not self._pair_tasks[operation_id].done()
        ):
            return
        task = asyncio.create_task(self._pair_transaction(device_id, path))
        self._pair_tasks[operation_id] = task
        self._pair_devices[operation_id] = device_id
        self._pair_results[operation_id] = {"state": "running", "device_id": device_id}
        task.add_done_callback(
            lambda completed, op=operation_id: self._pair_done(op, completed)
        )

    async def cancel_pair(self, operation_id: str) -> None:
        task = self._pair_tasks.get(operation_id)
        if task is None:
            raise BackendUnavailable("pairing operation is not pending")
        self._invalidate_challenges(
            lambda challenge: challenge.get("operation_id") == operation_id
        )
        path = self._device_path(self._pair_devices.get(operation_id, ""))
        if path:
            try:
                await self._call(BLUEZ, path, DEVICE_IFACE, "CancelPairing")
            except BackendUnavailable:
                task.cancel()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._pair_devices.pop(operation_id, None)
        await self._emit()

    async def _pair_transaction(self, device_id: str, path: str) -> None:
        try:
            await asyncio.wait_for(
                self._call(BLUEZ, path, DEVICE_IFACE, "Pair"), self.pair_timeout
            )
        except asyncio.TimeoutError as exc:
            try:
                await self._call(BLUEZ, path, DEVICE_IFACE, "CancelPairing")
            except Exception:
                pass
            raise BackendUnavailable("BlueZ pairing operation timed out") from exc
        await self._read_objects()
        if not self._device_props(device_id).get("Paired", False):
            raise BackendUnavailable("BlueZ Pair returned without Paired=true")

    async def connect(self, device_id: str) -> None:
        path = self._require_device_path(device_id)
        await self._call(BLUEZ, path, DEVICE_IFACE, "Connect")
        await self._read_objects()
        if not self._device_props(device_id).get("Connected", False):
            raise BackendUnavailable("BlueZ Connect returned without Connected=true")
        await self._emit()

    async def disconnect(self, device_id: str) -> None:
        path = self._require_device_path(device_id)
        await self._call(BLUEZ, path, DEVICE_IFACE, "Disconnect")
        await self._read_objects()
        if self._device_props(device_id).get("Connected", False):
            raise BackendUnavailable(
                "BlueZ Disconnect returned while device remains connected"
            )
        await self._emit()

    async def remove(self, device_id: str) -> None:
        path = self._require_device_path(device_id)
        self._invalidate_challenges(lambda challenge: challenge.get("device_id") == device_id)
        for operation_id, target in list(self._pair_devices.items()):
            if target == device_id:
                task = self._pair_tasks.get(operation_id)
                if task is not None and not task.done():
                    task.cancel()
        adapter = self._adapter_path()
        await self._call(BLUEZ, adapter, ADAPTER_IFACE, "RemoveDevice", "o", [path])
        await self._read_objects()
        if self._device_path(device_id) is not None:
            raise BackendUnavailable("BlueZ device remained after RemoveDevice")
        await self._emit()

    async def answer_challenge(
        self, challenge_id: str, device_id: str, accept: bool, value: str | None
    ) -> None:
        challenge = self._challenges.get(challenge_id)
        if challenge is None or challenge.get("device_id") != device_id:
            raise BackendUnavailable("pairing challenge expired or unavailable")
        if challenge.get("expires_at", 0) <= time.monotonic():
            self._resolve_challenge(challenge_id, False, None)
            raise BackendUnavailable("pairing challenge expired")
        self._resolve_challenge(challenge_id, accept, value)

    async def scan(self, enabled: bool) -> None:
        if self._last_discovery == enabled:
            return
        adapter = await self._interface(BLUEZ, self._adapter_path(), ADAPTER_IFACE)
        if enabled:
            await adapter.call_start_discovery()
        else:
            await adapter.call_stop_discovery()
        self._last_discovery = enabled
        await self._read_objects()
        await self._emit()

    async def set_pairing_window(self, enabled: bool) -> None:
        _, Variant, _ = self._dbus
        adapter = await self._interface(
            BLUEZ, self._adapter_path(), "org.freedesktop.DBus.Properties"
        )
        if enabled and self._pair_window_previous is None:
            self._add_window_generation += 1
            await self._read_objects()
            self._pair_window_previous = (
                self._adapter_bool("Pairable"),
                self._adapter_bool("Discoverable"),
            )
        desired = (
            (True, True) if enabled else self._pair_window_previous or (False, False)
        )
        await adapter.call_set(
            "org.bluez.Adapter1", "Pairable", Variant("b", desired[0])
        )
        await adapter.call_set(
            "org.bluez.Adapter1", "Discoverable", Variant("b", desired[1])
        )
        await self._read_objects()
        if (
            self._adapter_bool("Pairable") != desired[0]
            or self._adapter_bool("Discoverable") != desired[1]
        ):
            raise BackendUnavailable("BlueZ pairing-window properties did not settle")
        if not enabled:
            self._add_window_generation += 1
            self._pair_window_previous = None
            self._incoming_reservations.clear()
            self._invalidate_challenges(
                lambda challenge: challenge.get("operation_id") is None
            )
        await self._emit()

    async def set_speaker_route(self, device_id: str) -> dict[str, Any] | None:
        source = self._source_for(device_id)
        if source is None:
            return None
        sink = self.sink or (await self.router._runner("get-default-sink")).strip()
        if not sink:
            raise BackendUnavailable("no PulseAudio output sink is selected")
        if not sink.startswith("alsa_output.platform-rt5616"):
            raise BackendUnavailable(
                "default sink is not the RT5616 output; configure LIGHT_BELT_AUDIO_SINK"
            )
        route = await self.router.open(source, sink, device_id=device_id)
        try:
            route.update(await self.router.route_details(route["module_id"]))
        except BaseException:
            await self.router.close()
            raise
        route["digital_target"] = self._phone_pcm_target(route, device_id)
        self._route_device = device_id
        self._route = route
        self._route_error = None
        return route

    def _phone_pcm_target(self, route: dict[str, Any], device_id: str) -> dict[str, Any]:
        return {
            "kind": "phone_pcm",
            "source_id": device_id,
            "device": route["monitor_source"],
            "monitor_stream": route["sink_input_index"],
            "pa_generation": self.router.generation,
            "flow_generation": self.router.flow_generation(
                "sink-input", route["sink_input_index"]
            ),
            "pa_sink": route["sink"],
            "pa_sink_index": route["sink_index"],
            "pa_monitor_source": route["monitor_source"],
            "pa_source": route["source"],
            "pa_owner_module": route["module_id"],
        }

    async def close_speaker_route(self) -> None:
        await self.router.close()
        self._route = None
        self._route_device = None
        self._route_error = None

    async def _challenge(self, device_path: str, kind: str, value: str | None):
        device_id = self._device_id(device_path)
        operation_id = next((op for op, target in self._pair_devices.items() if target == device_id), None)
        generation = self._add_window_generation
        props = self._objects.get(device_path, {}).get(DEVICE_IFACE, {})
        outgoing = device_id in self._pair_devices.values()
        if (
            not outgoing
            and not props.get("Paired")
            and (
                self._pair_window_previous is None or not self._adapter_bool("Pairable")
            )
        ):
            raise self._dbus[2](
                "org.bluez.Error.Rejected", "Inbound pairing window is closed"
            )
        if (
            not props.get("Paired", False)
            and operation_id is None
            and device_id not in self._incoming_reservations
        ):
            occupied = {
                self._device_id(path)
                for path, item in self._objects.items()
                if item.get(DEVICE_IFACE, {}).get("Connected")
            }
            occupied.update(self._pair_devices.values())
            occupied.update(self._incoming_reservations)
            if len(occupied | {device_id}) > self.max_connections:
                raise self._dbus[2](
                    "org.bluez.Error.Rejected", "Bluetooth connection capacity is full"
                )
            self._incoming_reservations.add(device_id)
        challenge_id = f"{device_id}:{time.monotonic_ns()}"
        future = asyncio.get_running_loop().create_future()
        challenge = {
            "id": challenge_id,
            "device_id": device_id,
            "kind": kind,
            "value": value,
            "expires_at": time.monotonic() + self.challenge_timeout,
            "operation_id": operation_id,
            "add_window_generation": generation,
        }
        self._challenges[challenge_id] = challenge
        self._challenge_waiters[challenge_id] = future
        await self._emit()
        try:
            accepted, answer = await asyncio.wait_for(future, self.challenge_timeout)
        except asyncio.TimeoutError:
            self._challenges.pop(challenge_id, None)
            self._challenge_waiters.pop(challenge_id, None)
            await self._emit()
            self._incoming_reservations.discard(device_id)
            raise self._dbus[2](
                "org.bluez.Error.Rejected", "Pairing confirmation timed out"
            )
        self._challenges.pop(challenge_id, None)
        self._challenge_waiters.pop(challenge_id, None)
        await self._emit()
        current_operation = next((op for op, target in self._pair_devices.items() if target == device_id), None)
        if (not accepted
                or (operation_id is None and generation != self._add_window_generation)
                or current_operation != operation_id
                or self._device_path(device_id) != device_path):
            self._incoming_reservations.discard(device_id)
            raise self._dbus[2](
                "org.bluez.Error.Rejected", "Pairing rejected by local user"
            )
        if kind in {"pin", "passkey"}:
            if answer is None:
                raise self._dbus[2](
                    "org.bluez.Error.Rejected", "Pairing value is required"
                )
            if kind == "passkey" and (
                not str(answer).isdigit() or len(str(answer)) > 6
            ):
                raise self._dbus[2]("org.bluez.Error.Rejected", "Invalid passkey")
            return answer

    def _display_challenge(self, device_path: str, kind: str, value: str) -> None:
        device_id = self._device_id(device_path)
        challenge_id = f"{device_id}:{time.monotonic_ns()}"
        self._challenges[challenge_id] = {
            "id": challenge_id,
            "device_id": device_id,
            "kind": kind,
            "value": value,
            "display_only": True,
            "expires_at": time.monotonic() + self.challenge_timeout,
        }
        self._schedule_emit()

    def _resolve_challenge(
        self, challenge_id: str, accepted: bool, value: str | None
    ) -> None:
        future = self._challenge_waiters.get(challenge_id)
        if future is None or future.done():
            raise BackendUnavailable("pairing challenge already answered")
        future.set_result((accepted, value))

    def _cancel_challenges(self) -> None:
        self._invalidate_challenges(lambda _challenge: True)

    def _invalidate_challenges(self, predicate) -> None:
        for challenge_id, challenge in list(self._challenges.items()):
            if not predicate(challenge):
                continue
            future = self._challenge_waiters.get(challenge_id)
            if future is not None and not future.done():
                future.set_result((False, None))
            self._challenges.pop(challenge_id, None)
            self._challenge_waiters.pop(challenge_id, None)

    def _agent_released(self) -> None:
        self._owner = False
        self._agent_registered = False
        self._cancel_challenges()
        if self._started and not self._closing and (
            self._agent_retry_task is None or self._agent_retry_task.done()
        ):
            self._agent_retry_task = asyncio.create_task(self._retry_agent_registration())
        self._schedule_emit()

    @staticmethod
    def _service_allowed(uuid: str) -> bool:
        return uuid.lower() in {
            "0000110a-0000-1000-8000-00805f9b34fb",
            "0000110b-0000-1000-8000-00805f9b34fb",
            "0000110c-0000-1000-8000-00805f9b34fb",
            "0000110d-0000-1000-8000-00805f9b34fb",
            "0000110e-0000-1000-8000-00805f9b34fb",
        }

    def _pair_done(self, operation_id, task):
        if self._pair_tasks.get(operation_id) is not task:
            return
        self._pair_tasks.pop(operation_id, None)
        self._invalidate_challenges(
            lambda challenge: challenge.get("operation_id") == operation_id
        )
        device = self._pair_devices.pop(operation_id, None)
        if task.cancelled():
            self._pair_results[operation_id] = {"state": "cancelled"}
        elif task.exception() is not None:
            self._pair_results[operation_id] = {
                "state": "failed",
                "reason": str(task.exception()),
            }
        else:
            self._pair_results[operation_id] = {"state": "succeeded"}
        self._pair_results[operation_id]["device_id"] = device
        if len(self._pair_results) > 16:
            for key in list(self._pair_results):
                if key not in self._pair_tasks:
                    del self._pair_results[key]
                    break
        self._schedule_emit()

    async def _interface(self, destination, path, name):
        introspection = await self.bus.introspect(destination, path)
        proxy = self.bus.get_proxy_object(destination, path, introspection)
        return proxy.get_interface(name)

    async def _call(
        self, destination, path, interface, member, signature="", body=None
    ):
        Message = self._dbus[0] if hasattr(self, "_dbus") else None
        if Message is None:
            from dbus_next import Message
        reply = await self.bus.call(
            Message(
                destination=destination,
                path=path,
                interface=interface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
        if reply.message_type.name == "ERROR":
            raise BackendUnavailable(
                f"{reply.error_name}: {reply.body[0] if reply.body else 'D-Bus call failed'}"
            )
        return reply.body[0] if reply.body else None

    async def _read_objects(self):
        raw = await self._call(
            BLUEZ, "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects"
        )
        self._objects = {
            path: {
                iface: {key: _variant_value(value) for key, value in props.items()}
                for iface, props in interfaces.items()
            }
            for path, interfaces in raw.items()
        }
        connected_ids = {
            self._device_id(path)
            for path, ifaces in self._objects.items()
            if DEVICE_IFACE in ifaces and ifaces[DEVICE_IFACE].get("Connected")
        }
        self._incoming_reservations.difference_update(connected_ids)
        await self._refresh_sources()

    def _message_handler(self, message):
        if (
            message.path == "/org/freedesktop/DBus"
            and message.member == "NameOwnerChanged"
        ):
            if len(message.body) == 3 and message.body[0] == BLUEZ:
                asyncio.create_task(self._owner_changed(bool(message.body[2])))
        elif message.member in {
            "InterfacesAdded",
            "InterfacesRemoved",
            "PropertiesChanged",
        }:
            self._schedule_emit()
        return False

    async def _owner_changed(self, present: bool):
        self._owner = present
        self._agent_registered = False
        if not present:
            self._objects.clear()
            self._cancel_challenges()
        else:
            try:
                await self._register_default_agent()
                await self._read_objects()
            except Exception:
                self._owner = False
        await self._emit()

    async def _register_default_agent(self):
        async with self._agent_registration_lock:
            manager = await self._interface(BLUEZ, "/org/bluez", AGENT_MANAGER_IFACE)
            await manager.call_register_agent(AGENT_PATH, "KeyboardDisplay")
            await manager.call_request_default_agent(AGENT_PATH)
            self._agent_manager = manager
            self._owner = True
            self._agent_registered = True

    async def _retry_agent_registration(self):
        while self._started:
            await asyncio.sleep(0.2)
            try:
                await self._register_default_agent()
                await self._read_objects()
                await self._emit()
                return
            except Exception:
                self._owner = False

    def _schedule_emit(self):
        self._dirty = True
        if self._callbacks and (self._event_task is None or self._event_task.done()):
            self._event_task = asyncio.create_task(self._deliver())

    async def _deliver(self):
        while self._dirty and self._callbacks:
            self._dirty = False
            try:
                await self._callbacks("bluez_changed")
            except Exception:
                logging.getLogger(__name__).exception(
                    "Cannot reconcile Bluetooth state"
                )

    async def _emit(self):
        self._schedule_emit()

    async def _check_legacy_services(self):
        checks = [
            ["systemctl", "is-active", "bluetooth-auto-agent.service"],
            ["systemctl", "is-active", "bluetooth-public-mode.service"],
            ["systemctl", "--user", "is-active", "bluetooth-audio-loopback.service"],
            [
                "systemctl",
                "--user",
                "is-active",
                "light-belt-bluetooth-priority.service",
            ],
        ]
        for command in checks:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=2)
            except (OSError, asyncio.TimeoutError) as exc:
                raise BackendUnavailable(
                    "cannot verify legacy service ownership"
                ) from exc
            if (
                process.returncode == 0
                and stdout.decode(errors="replace").strip() == "active"
            ):
                raise BackendUnavailable(
                    f"legacy Bluetooth owner is active: {' '.join(command)}"
                )
            if process.returncode not in (3, 4):
                raise BackendUnavailable(
                    f"cannot confirm inactive service: {command[-1]}"
                )

    def _adapter_path(self):
        return (
            next(
                (p for p, ifaces in self._objects.items() if ADAPTER_IFACE in ifaces),
                None,
            )
            or "/org/bluez/hci0"
        )

    def _adapter_bool(self, key):
        props = self._objects.get(self._adapter_path(), {}).get(ADAPTER_IFACE, {})
        return bool(props.get(key, False))

    def _device_props(self, device_id):
        path = self._device_path(device_id)
        return self._objects.get(path, {}).get(DEVICE_IFACE, {}) if path else {}

    def _device_path(self, device_id):
        return next(
            (
                path
                for path, ifaces in self._objects.items()
                if DEVICE_IFACE in ifaces and self._device_id(path) == device_id
            ),
            None,
        )

    def _require_device_path(self, device_id):
        path = self._device_path(device_id)
        if path is None:
            raise BackendUnavailable("unknown BlueZ device")
        return path

    def _device_id(self, path):
        props = self._objects.get(path, {}).get(DEVICE_IFACE, {})
        address = props.get("Address")
        if address:
            return str(address).upper()
        return path.rsplit("/", 1)[-1].replace("dev_", "").replace("_", ":").upper()

    def _device_path_for_operation(self, operation_id):
        device_id = operation_id.split(":", 1)[-1]
        return self._device_path(device_id)

    def _device_snapshot(self):
        transports = []
        players = {}
        for path, interfaces in self._objects.items():
            if TRANSPORT_IFACE in interfaces:
                props = interfaces[TRANSPORT_IFACE]
                transports.append(
                    {
                        "device": props.get("Device"),
                        "state": props.get("State"),
                        "uuid": props.get("UUID"),
                    }
                )
            if PLAYER_IFACE in interfaces:
                props = interfaces[PLAYER_IFACE]
                device = props.get("Device") or props.get("DevicePath")
                if device:
                    players[device] = props.get("Status")
        rows = []
        for path, interfaces in self._objects.items():
            props = interfaces.get(DEVICE_IFACE)
            if props is None:
                continue
            device_id = self._device_id(path)
            owned_transports = [
                t
                for t in transports
                if t["device"] == path and "110b" in str(t["uuid"]).lower()
            ]
            state = next(
                (t["state"] for t in owned_transports if t["state"] == "active"),
                next((t["state"] for t in owned_transports), "idle"),
            )
            player = players.get(path)
            rows.append(
                {
                    "id": device_id,
                    "name": props.get("Name") or props.get("Alias") or device_id,
                    "paired": bool(props.get("Paired", False)),
                    "connected": bool(props.get("Connected", False)),
                    "services_resolved": bool(props.get("ServicesResolved", False)),
                    "transport_state": state,
                    "player_status": player,
                    "activity": "transmitting" if state == "active" else "idle",
                    "source_available": device_id in self._sources,
                }
            )
        return rows

    def _source_for(self, device_id):
        return self._sources.get(device_id)

    async def _refresh_sources(self):
        try:
            process = await asyncio.create_subprocess_exec(
                "pactl",
                "list",
                "short",
                "sources",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=3)
            if process.returncode:
                raise BackendUnavailable(
                    stderr.decode(errors="replace").strip()
                    or "pactl sources query failed"
                )
        except (OSError, asyncio.TimeoutError) as exc:
            raise BackendUnavailable(
                f"unable to inspect PulseAudio sources: {exc}"
            ) from exc
        sources = {}
        monitors = {}
        for line in stdout.decode(errors="replace").splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            name = fields[1]
            if name.startswith("alsa_output.platform-rt5616") and name.endswith(
                ".monitor"
            ):
                monitors[name.rsplit(".monitor", 1)[0]] = name
            if not name.lower().startswith("bluez_source.") or not name.endswith(
                ".a2dp_source"
            ):
                continue
            match = re.search(r"bluez_source\.([0-9a-f_]+)\.a2dp_source", name, re.I)
            if match:
                device_id = match.group(1).replace("_", ":").upper()
                sources[device_id] = name
        self._sources = sources
        self._source_monitor = monitors

    async def _program_target(self, sink: str):
        expected_pid = self.program_pid() if self.program_pid is not None else None
        if self.require_program_pid and expected_pid is None:
            return None
        sinks = json.loads(await self.router._runner("--format=json", "list", "sinks"))
        selected = next((row for row in sinks if row.get("name") == sink), None)
        monitor = self._source_monitor.get(sink)
        if not selected or not monitor:
            return None
        inputs = json.loads(
            await self.router._runner("--format=json", "list", "sink-inputs")
        )
        matches = [
            row
            for row in inputs
            if str(row.get("sink")) == str(selected["index"])
            and row.get("properties", {}).get("application.name")
            == "LIGHT-BELT-LocalMedia"
            and (
                expected_pid is None
                or str(row.get("properties", {}).get("application.process.id"))
                == str(expected_pid)
            )
        ]
        if len(matches) == 1:
            return {
                "kind": "program_pcm",
                "source_id": "LIGHT-BELT-LocalMedia",
                "device": monitor,
                "monitor_stream": int(matches[0]["index"]),
                "pa_generation": self.router.generation,
                "flow_generation": self.router.flow_generation(
                    "sink-input", int(matches[0]["index"])
                ),
                "flow_identity": f"mpv:{expected_pid}:{matches[0]['index']}",
                "pa_sink": sink,
                "pa_sink_index": int(selected["index"]),
                "pa_monitor_source": monitor,
                "pa_owner_pid": expected_pid,
            }
        return None


def _variant_value(value):
    if hasattr(value, "value"):
        return _variant_value(value.value)
    if isinstance(value, dict):
        return {key: _variant_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_variant_value(item) for item in value]
    return value
