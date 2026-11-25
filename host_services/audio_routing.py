"""PulseAudio route operations used by the Bluetooth audio coordinator."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import Any

from .bluetooth import BackendUnavailable


class PulseAudioRouter:
    """Create and verify one owned Bluetooth loopback on the selected sink."""

    def __init__(
        self, *, runner=None, route_property: str = "light_belt.route_owner"
    ) -> None:
        self._runner = runner or self._run
        self.route_property = route_property
        self._module_id: str | None = None
        self._route: dict[str, Any] | None = None

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
