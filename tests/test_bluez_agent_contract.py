import asyncio

import pytest

from host_services.bluez_backend import LinuxBluezBackend, DEVICE_IFACE


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
