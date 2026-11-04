#!/usr/bin/env python3
"""BlueZ NoInputNoOutput agent for the unattended LIGHT-BELT appliance."""

from __future__ import annotations

import sys
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib


BLUEZ = "org.bluez"
AGENT_IFACE = "org.bluez.Agent1"
MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_PATH = "/org/light_belt/agent"


class Agent(dbus.service.Object):
    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="s")
    def RequestPinCode(self, _device):
        return "0000"

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def DisplayPinCode(self, _device, _pincode):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="u")
    def RequestPasskey(self, _device):
        return dbus.UInt32(0)

    @dbus.service.method(AGENT_IFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, _device, _passkey, _entered):
        pass

    @dbus.service.method(AGENT_IFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, _device, _passkey):
        return

    @dbus.service.method(AGENT_IFACE, in_signature="o", out_signature="")
    def RequestAuthorization(self, _device):
        return

    @dbus.service.method(AGENT_IFACE, in_signature="os", out_signature="")
    def AuthorizeService(self, _device, _uuid):
        return

    @dbus.service.method(AGENT_IFACE, in_signature="", out_signature="")
    def Cancel(self):
        pass


def main() -> int:
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    Agent(bus, AGENT_PATH)

    for _ in range(60):
        try:
            manager = dbus.Interface(bus.get_object(BLUEZ, "/org/bluez"), MANAGER_IFACE)
            manager.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
            manager.RequestDefaultAgent(AGENT_PATH)
            break
        except dbus.DBusException as exc:
            print(f"[bluetooth-agent] waiting for BlueZ: {exc}", file=sys.stderr, flush=True)
            time.sleep(1)
    else:
        raise SystemExit("BlueZ AgentManager1 did not become ready")

    print("[bluetooth-agent] default NoInputNoOutput agent registered", flush=True)
    GLib.MainLoop().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
