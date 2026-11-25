"""PulseAudio route operations used by the Bluetooth audio coordinator."""

from __future__ import annotations

import asyncio
import json
import os
import itertools
import logging
import re
import shlex
from typing import Any

from .bluetooth import BackendUnavailable


class PulseAudioRouter:
    """Create and verify one owned Bluetooth loopback on the selected sink."""

    def __init__(
        self, *, runner=None, subscriber=None,
        route_property: str = "light_belt.route_owner"
    ) -> None:
        self._runner = runner or self._run
        self._subscriber = subscriber
        self.route_property = route_property
        self._module_id: str | None = None
        self._route: dict[str, Any] | None = None
        self._watch_task: asyncio.Task | None = None
        self._watch_process = None
        self._watch_callback = None
        self._generation = 0
        self._flow_generations: dict[tuple[str, int], int] = {}
        self._flow_generation_counter = itertools.count(1)

    @property
    def generation(self) -> int:
        """Return the observed PulseAudio server incarnation."""
        return self._generation

    def flow_generation(self, kind: str, index: int) -> int:
        """Return the observed lifecycle generation of one PA stream index."""
        return self._flow_generations.get((kind, index), 0)

    def _observe_event(self, event: str) -> None:
        match = re.search(
            r"Event '(new|remove|change)' on (sink-input|source-output) #(\d+)",
            event,
        )
        if match:
            action, kind, index = match.groups()
            key = (kind, int(index))
            if action == "new":
                self._flow_generations[key] = next(self._flow_generation_counter)
            elif action == "remove":
                self._flow_generations.pop(key, None)

    async def _invalidate_observation(self) -> None:
        self._generation += 1
        self._flow_generations.clear()
        if self._watch_callback is not None:
            try:
                result = self._watch_callback()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                logging.getLogger(__name__).exception(
                    "PulseAudio target reconciliation failed after observer loss"
                )

    async def start_monitor(self, callback) -> None:
        self._watch_callback = callback
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = asyncio.create_task(self._monitor_loop())

    async def stop_monitor(self) -> None:
        task, self._watch_task = self._watch_task, None
        process, self._watch_process = self._watch_process, None
        if process is not None and process.returncode is None:
            process.terminate()
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if process is not None and process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=1)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

    async def _monitor_loop(self) -> None:
        delay = 0.2
        while self._watch_callback is not None:
            try:
                if self._subscriber is not None:
                    stream = self._subscriber()
                    if hasattr(stream, "__await__"):
                        stream = await stream
                    async for event in stream:
                        delay = 0.2
                        self._observe_event(str(event))
                        result = self._watch_callback()
                        if hasattr(result, "__await__"):
                            await result
                    await self._invalidate_observation()
                else:
                    process = await asyncio.create_subprocess_exec(
                        "pactl", "subscribe", stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
                    )
                    self._watch_process = process
                    if process.stdout is None:
                        raise BackendUnavailable("pactl subscribe has no stdout")
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        delay = 0.2
                        self._observe_event(line.decode(errors="replace"))
                        result = self._watch_callback()
                        if hasattr(result, "__await__"):
                            await result
                    await process.wait()
                    self._watch_process = None
                    # A subscription ending can mean PA restarted; reconcile.
                    await self._invalidate_observation()
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            except Exception:
                await self._invalidate_observation()
                await asyncio.sleep(delay)
                delay = min(2.0, delay * 2)
            finally:
                process, self._watch_process = self._watch_process, None
                if process is not None and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), 1)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()

    async def _run(self, *args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "pactl",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "LC_ALL": "C"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        if process.returncode:
            message = (
                stderr.decode(errors="replace").strip()
                or stdout.decode(errors="replace").strip()
            )
            raise BackendUnavailable(message or f"pactl {' '.join(args)} failed")
        return stdout.decode(errors="replace")

    async def open(self, source: str, sink: str, *, device_id: str) -> dict[str, Any]:
        await self.assert_exclusive_policy()
        if self._module_id is not None:
            await self.close()
        args = [
            "load-module",
            "module-loopback",
            f"source={source}",
            f"sink={sink}",
            "source_dont_move=true",
            "sink_dont_move=true",
            f"sink_input_properties={self.route_property}={device_id}",
        ]
        module_id = (await self._runner(*args)).strip()
        if not module_id.isdigit():
            raise BackendUnavailable("pactl did not return a loopback module index")
        self._module_id = module_id
        property_value = f"{self.route_property}={device_id}"
        route = {
            "module_id": module_id,
            "source": source,
            "sink": sink,
            "device": device_id,
            "property": property_value,
            "verified": False,
        }
        self._route = route
        try:
            modules = await self._runner("list", "short", "modules")
            if not self._module_matches(modules, route):
                raise BackendUnavailable(
                    "loopback module readback did not match requested route"
                )
            route["verified"] = True
            self._route = route
            return dict(route)
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        module_id = self._module_id
        if module_id is None:
            return
        modules = await self._runner("list", "short", "modules")
        if self._route and self._module_matches(modules, self._route):
            await self._runner("unload-module", module_id)
            modules = await self._runner("list", "short", "modules")
            if self._module_matches(modules, self._route):
                raise BackendUnavailable("owned loopback module remains after unload")
        self._module_id = None
        self._route = None

    async def route_details(self, module_id: str) -> dict[str, Any]:
        route = self._route
        modules = await self._runner("list", "short", "modules")
        if (
            route is None
            or route.get("module_id") != module_id
            or not self._module_matches(modules, route)
        ):
            self._module_id = None
            self._route = None
            raise BackendUnavailable("owned Bluetooth route disappeared or changed")
        sinks = json.loads(await self._runner("--format=json", "list", "sinks"))
        inputs = json.loads(await self._runner("--format=json", "list", "sink-inputs"))
        sink = next((s for s in sinks if s["name"] == route["sink"]), None)
        matches = [s for s in inputs if str(s.get("owner_module")) == module_id]
        if (
            not sink
            or len(matches) != 1
            or str(matches[0]["sink"]) != str(sink["index"])
        ):
            raise BackendUnavailable(
                "owned loopback has no unique stream on the selected sink"
            )
        return {
            "sink_input_index": int(matches[0]["index"]),
            "sink_index": int(sink["index"]),
            "monitor_source": sink["monitor_source"],
        }

    async def recover_owned(
        self, valid_sources: set[str], valid_sinks: set[str]
    ) -> dict[str, Any] | None:
        """Adopt one verifiable orphaned Host route and remove duplicates."""
        modules = await self._runner("list", "short", "modules")
        owned = []
        for line in modules.splitlines():
            fields = line.split("\t", 2)
            if len(fields) != 3 or fields[1] != "module-loopback":
                continue
            args = dict(
                word.split("=", 1) for word in shlex.split(fields[2]) if "=" in word
            )
            owner = args.get("sink_input_properties", "")
            if not owner.startswith(f"{self.route_property}="):
                continue
            device_id = owner.split("=", 1)[1]
            owned.append(
                {
                    "module_id": fields[0],
                    "source": args.get("source"),
                    "sink": args.get("sink"),
                    "device": device_id,
                    "property": owner,
                    "verified": False,
                }
            )
        valid = [
            route
            for route in owned
            if route["source"] in valid_sources
            and route["sink"] in valid_sinks
            and args_are_stable(modules, route)
        ]
        # Multiple owned modules are ambiguous. Remove them all and report no
        # recovered route so the caller can keep program audio gated.
        if len(valid) != 1 or len(owned) != 1:
            for route in owned:
                await self._runner("unload-module", route["module_id"])
            remaining = await self._runner("list", "short", "modules")
            if any(
                f"{self.route_property}=" in line for line in remaining.splitlines()
            ):
                raise BackendUnavailable(
                    "unable to clear ambiguous orphaned Bluetooth routes"
                )
            return None
        route = valid[0]
        route["verified"] = True
        self._module_id = route["module_id"]
        self._route = route
        details = await self.route_details(route["module_id"])
        route.update(details)
        route["monitor_source"] = f"{route['sink']}.monitor"
        return dict(route)

    async def assert_exclusive_policy(self) -> None:
        modules = await self._runner("list", "short", "modules")
        policies = 0
        for line in modules.splitlines():
            fields = line.split("\t", 2)
            if len(fields) < 3:
                continue
            module, args = fields[1], fields[2]
            if module == "module-bluetooth-policy":
                policies += 1
                options = dict(
                    word.split("=", 1) for word in shlex.split(args) if "=" in word
                )
                if options.get("a2dp_source", "true").lower() not in {
                    "false",
                    "0",
                    "no",
                }:
                    raise BackendUnavailable(
                        "native Bluetooth policy may create competing A2DP loopbacks"
                    )
            if module == "module-loopback" and "bluez_source." in args:
                if f"{self.route_property}=" not in args:
                    raise BackendUnavailable("foreign Bluetooth loopback is active")
        if policies != 1:
            raise BackendUnavailable(
                "expected one native Bluetooth policy with automatic routing disabled"
            )

    @staticmethod
    def _module_matches(text: str, route: dict[str, Any]) -> bool:
        for line in text.splitlines():
            fields = line.split("\t", 2)
            if (
                len(fields) != 3
                or fields[0] != route["module_id"]
                or fields[1] != "module-loopback"
            ):
                continue
            args = dict(
                word.split("=", 1) for word in shlex.split(fields[2]) if "=" in word
            )
            return (
                args.get("source") == route["source"]
                and args.get("sink") == route["sink"]
                and args.get("source_dont_move") == "true"
                and args.get("sink_dont_move") == "true"
                and args.get("sink_input_properties") == f"{route['property']}"
            )
        return False


def args_are_stable(text: str, route: dict[str, Any]) -> bool:
    for line in text.splitlines():
        fields = line.split("\t", 2)
        if len(fields) == 3 and fields[0] == route["module_id"]:
            args = dict(
                word.split("=", 1) for word in shlex.split(fields[2]) if "=" in word
            )
            return (
                args.get("source_dont_move") == "true"
                and args.get("sink_dont_move") == "true"
            )
    return False
