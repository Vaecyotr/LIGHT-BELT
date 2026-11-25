import asyncio

import pytest

from host_services.bluez_backend import LinuxBluezBackend, DEVICE_IFACE
from host_services.bluetooth import BackendUnavailable


def test_confirm_is_bound_to_the_original_screen_and_shows_leading_zeroes():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        device = "/org/bluez/hci0/dev_00_11_22_33_44_55"
        backend._objects[device] = {
            DEVICE_IFACE: {"Address": "00:11:22:33:44:55", "Paired": True}
        }

        class Rejected(Exception):
            pass

        backend._dbus = (None, None, Rejected)
        generation = ["first"]
        backend.terminal_generation = lambda: generation[0]
        pending = asyncio.create_task(backend._challenge(device, "confirm", "004281"))
        await asyncio.sleep(0)
        (challenge,) = backend._challenges.values()
        assert challenge["value"] == "004281"
        generation[0] = "replacement"
        await backend.answer_challenge(challenge["id"], challenge["device_id"], True, None)
        with pytest.raises(Rejected):
            await pending
        assert not backend._challenges

    asyncio.run(run())


def test_idle_phone_connects_without_an_active_pa_source():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        path = "/org/bluez/hci0/dev_00_11_22_33_44_55"
        device_id = "00:11:22:33:44:55"
        backend._objects[path] = {
            DEVICE_IFACE: {"Address": device_id, "Connected": False}
        }

        async def call(destination, device, interface, command):
            assert device == path and command == "Connect"
            backend._objects[path][DEVICE_IFACE]["Connected"] = True

        async def refresh():
            return None

        backend._call = call
        backend._read_objects = refresh
        await backend.connect(device_id)
        assert backend._device_props(device_id)["Connected"]
        assert backend._source_for(device_id) is None

    asyncio.run(run())


def test_pair_done_from_old_task_cannot_remove_replacement_operation_owner():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        old_task = asyncio.create_task(asyncio.sleep(0))
        new_task = asyncio.create_task(asyncio.sleep(10))
        await old_task
        backend._pair_tasks["same-id"] = new_task
        backend._pair_devices["same-id"] = "new-device"
        backend._pair_done("same-id", old_task)
        await asyncio.sleep(0)
        assert backend._pair_tasks["same-id"] is new_task
        assert backend._pair_devices["same-id"] == "new-device"
        new_task.cancel()
        await asyncio.gather(new_task, return_exceptions=True)

    asyncio.run(run())


def test_blueZ_owner_reacquisition_registers_the_agent_again():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        backend._started = True
        calls = []

        class Manager:
            async def call_register_agent(self, path, capability):
                calls.append(("register", path, capability))

            async def call_request_default_agent(self, path):
                calls.append(("default", path))

        async def interface(_destination, _path, _name):
            return Manager()

        async def read_objects():
            return None

        backend._interface = interface
        backend._read_objects = read_objects
        await backend._owner_changed(True)

        assert backend._owner is True
        assert calls == [
            ("register", "/org/light_belt/agent", "KeyboardDisplay"),
            ("default", "/org/light_belt/agent"),
        ]
        await backend.close()

    asyncio.run(run())


def test_agent_release_retries_registration_without_waiting_for_name_owner_change():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        backend._started = True
        calls = []

        class Manager:
            async def call_register_agent(self, *_args):
                calls.append("register")

            async def call_request_default_agent(self, *_args):
                calls.append("default")

        async def interface(*_args):
            return Manager()

        async def read_objects():
            return None

        backend._interface = interface
        backend._read_objects = read_objects
        backend._agent_released()
        await asyncio.sleep(0.25)
        assert backend._owner
        assert calls == ["register", "default"]
        await backend.close()

    asyncio.run(run())


def test_cancelled_challenge_cannot_be_answered_late():
    async def run():
        backend = LinuxBluezBackend(bus=object())
        device = "/org/bluez/hci0/dev_00_11_22_33_44_55"
        backend._objects[device] = {
            DEVICE_IFACE: {"Address": "00:11:22:33:44:55", "Paired": True}
        }

        class Rejected(Exception):
            pass

        backend._dbus = (None, None, Rejected)
        pending = asyncio.create_task(backend._challenge(device, "confirm", "000042"))
        await asyncio.sleep(0)
        challenge_id = next(iter(backend._challenges))
        backend._cancel_challenges()
        with pytest.raises(BackendUnavailable, match="unavailable"):
            await backend.answer_challenge(challenge_id, "00:11:22:33:44:55", True, None)
        with pytest.raises(Rejected):
            await pending

    asyncio.run(run())
