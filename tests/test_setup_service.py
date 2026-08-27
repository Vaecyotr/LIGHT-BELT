"""Focused regression tests for the setup-service network-mode boundary.

The bundled test venv does not include Flask. The tiny stub below supplies only
the decorators, jsonify, and request JSON needed by these direct unit tests;
NetworkManager is always mocked.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest


_NETWORK_ENV = (
    "LIGHT_BELT_NETWORK_MODE",
    "LIGHT_BELT_WLAN_INTERFACE",
    "LIGHT_BELT_CABIN_AP_SSID",
    "LIGHT_BELT_CABIN_AP_PASSWORD",
    "LIGHT_BELT_CABIN_AP_IPV4_CIDR",
    "LIGHT_BELT_CABIN_AP_CONNECTION",
)
_SERVICE_PATH = Path("scripts/setup_service.py").resolve()


class _FlaskStub:
    def __init__(self, _name: str):
        self.routes: list[tuple[str, tuple[str, ...]]] = []

    def route(self, path: str, methods: list[str] | None = None):
        def decorate(function):
            self.routes.append((path, tuple(methods or ())))
            return function

        return decorate

    def run(self, **_kwargs) -> None:
        return None


@pytest.fixture
def service(monkeypatch):
    """Import setup_service with the minimum Flask API required by unit tests."""
    for key in _NETWORK_ENV:
        monkeypatch.delenv(key, raising=False)

    flask = ModuleType("flask")
    flask.Flask = _FlaskStub
    flask.jsonify = lambda payload: payload
    flask.request = SimpleNamespace(get_json=lambda silent=True: {})
    module_name = "_setup_service_test_module"
    module = importlib.util.module_from_spec(
        spec := importlib.util.spec_from_file_location(module_name, _SERVICE_PATH)
    )
    assert spec.loader is not None
    monkeypatch.setitem(sys.modules, "flask", flask)
    monkeypatch.setitem(sys.modules, module_name, module)
    spec.loader.exec_module(module)
    return module


def _result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _portable_env(**overrides: str) -> dict[str, str]:
    env = {
        "LIGHT_BELT_NETWORK_MODE": "portable_ap",
        "LIGHT_BELT_WLAN_INTERFACE": "wlp2s0",
        "LIGHT_BELT_CABIN_AP_SSID": "LIGHT-BELT Cabin",
        "LIGHT_BELT_CABIN_AP_PASSWORD": "secure-passphrase",
        "LIGHT_BELT_CABIN_AP_IPV4_CIDR": "192.168.77.1/24",
        "LIGHT_BELT_CABIN_AP_CONNECTION": "LIGHT-BELT Cabin AP",
    }
    env.update(overrides)
    return env


def _install_healthy_nmcli(monkeypatch, service, *, exists: bool = False, ip: str = "192.168.77.1"):
    """Install a stateful command recorder for a managed, AP-capable interface."""
    calls: list[list[str]] = []
    state = {"exists": exists}

    def fake_run(cmd: list[str], timeout: int = 30):
        del timeout
        calls.append(list(cmd))
        if cmd[:2] == ["nmcli", "-g"]:
            values = {
                "GENERAL.TYPE": "wifi\n",
                "GENERAL.NM-MANAGED": "yes\n",
                "WIFI-PROPERTIES.AP": "yes\n",
                "GENERAL.CONNECTION": "LIGHT-BELT Cabin AP\n",
            }
            return _result(stdout=values.get(cmd[2], ""))
        if cmd[:3] == ["nmcli", "connection", "show"]:
            return _result(returncode=0 if state["exists"] else 10)
        if cmd[:3] == ["nmcli", "connection", "add"]:
            state["exists"] = True
        if cmd[:3] == ["ip", "-4", "-o"]:
            return _result(stdout=f"3: wlp2s0    inet {ip}/24 brd 192.168.77.255 scope global\n")
        return _result()

    monkeypatch.setattr(service, "_run", fake_run)
    return calls, state


def test_net_01_default_site_client_keeps_legacy_startup_flow(service, monkeypatch) -> None:
    assert service.load_network_config({}).mode == service.SITE_CLIENT_MODE
    assert service.load_network_config({}).wlan_interface == "wlan0"
    events: list[str] = []
    monkeypatch.setattr(service, "wifi_is_connected", lambda *_args: (False, None, None))
    monkeypatch.setattr(service, "_try_saved_wifi", lambda: events.append("saved") or (False, None))
    monkeypatch.setattr(service, "hotspot_start", lambda: events.append("hotspot") or "10.42.0.1")
    monkeypatch.setattr(service, "cleanup_service", lambda: events.append("cleanup"))
    monkeypatch.setattr(service, "mdns_register", lambda _ip: events.append("mdns"))

    class FakeThread:
        def __init__(self, **_kwargs):
            events.append("watchdog-thread")

        def start(self):
            events.append("watchdog-start")

    monkeypatch.setattr(service.threading, "Thread", FakeThread)

    assert service.main() == 0
    assert events[:2] == ["saved", "hotspot"]


def test_net_01_site_client_excludes_persistent_cabin_after_mode_switch(service, monkeypatch) -> None:
    monkeypatch.setenv("LIGHT_BELT_WLAN_INTERFACE", "wlp2s0")
    monkeypatch.setenv("LIGHT_BELT_CABIN_AP_CONNECTION", "Custom Cabin AP")
    events: list[str] = []
    monkeypatch.setattr(
        service,
        "wifi_is_connected",
        lambda *_args: (True, "Custom Cabin AP", "192.168.77.1"),
    )
    monkeypatch.setattr(service, "_try_saved_wifi", lambda: events.append("saved") or (False, None))
    monkeypatch.setattr(service, "hotspot_start", lambda: events.append("hotspot") or "10.42.0.1")
    monkeypatch.setattr(service, "cleanup_service", lambda: None)
    monkeypatch.setattr(service.threading, "Thread", lambda **_kwargs: SimpleNamespace(start=lambda: None))

    assert service.main() == 0
    assert events == ["saved", "hotspot"]


def test_net_01_saved_site_wifi_never_includes_dedicated_cabin_profiles(service, monkeypatch) -> None:
    monkeypatch.setenv("LIGHT_BELT_CABIN_AP_CONNECTION", "Custom Cabin AP")
    monkeypatch.setattr(
        service,
        "_run",
        lambda *_args, **_kwargs: _result(
            stdout=(
                "LIGHT-BELT Cabin AP:802-11-wireless\n"
                "Custom Cabin AP:802-11-wireless\n"
                "Venue WiFi:802-11-wireless\n"
            )
        ),
    )

    assert service.wifi_saved_connections() == ["Venue WiFi"]


def test_net_01_site_watchdog_recovers_if_cabin_profile_reactivates(service, monkeypatch) -> None:
    monkeypatch.setenv("LIGHT_BELT_WLAN_INTERFACE", "wlp2s0")
    config = service.load_network_config({
        "LIGHT_BELT_WLAN_INTERFACE": "wlp2s0",
        "LIGHT_BELT_CABIN_AP_CONNECTION": "Custom Cabin AP",
    })
    events: list[str] = []
    sleeps = iter((None, RuntimeError("stop watchdog")))

    def sleep(_seconds):
        outcome = next(sleeps)
        if isinstance(outcome, Exception):
            raise outcome

    monkeypatch.setattr(service.time, "sleep", sleep)
    monkeypatch.setattr(service, "WATCHDOG_FAIL_THRESHOLD", 1)
    monkeypatch.setattr(
        service,
        "wifi_is_connected",
        lambda *_args: (True, "Custom Cabin AP", "192.168.77.1"),
    )
    monkeypatch.setattr(service, "_try_saved_wifi", lambda: events.append("saved") or (False, None))
    monkeypatch.setattr(service, "hotspot_start", lambda: events.append("hotspot") or "10.42.0.1")

    with pytest.raises(RuntimeError, match="stop watchdog"):
        service._watchdog(config)

    assert events == ["saved", "hotspot"]


def test_net_02_to_04_and_07_portable_profile_uses_configured_network_values(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    calls, _ = _install_healthy_nmcli(monkeypatch, service)

    assert service.ensure_portable_ap(config) == "192.168.77.1"

    add = next(command for command in calls if command[:3] == ["nmcli", "connection", "add"])
    assert add[add.index("ifname") + 1] == "wlp2s0"  # NET-02
    assert add[add.index("ssid") + 1] == "LIGHT-BELT Cabin"  # NET-03
    assert add[add.index("ipv4.addresses") + 1] == "192.168.77.1/24"  # NET-04
    assert add[add.index("autoconnect") + 1] == "yes"  # NET-07
    assert add[add.index("wifi-sec.key-mgmt") + 1] == "wpa-psk"
    assert "wifi-sec.psk" in add
    assert "open" not in add


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"LIGHT_BELT_WLAN_INTERFACE": ""}, "WLAN_INTERFACE"),
        ({"LIGHT_BELT_CABIN_AP_SSID": ""}, "CABIN_AP_SSID"),
        ({"LIGHT_BELT_CABIN_AP_PASSWORD": ""}, "CABIN_AP_PASSWORD"),
        ({"LIGHT_BELT_CABIN_AP_PASSWORD": "short"}, "CABIN_AP_PASSWORD"),
        ({"LIGHT_BELT_CABIN_AP_IPV4_CIDR": "not-a-cidr"}, "CABIN_AP_IPV4_CIDR"),
    ],
)
def test_net_05_portable_invalid_configuration_fails_before_nmcli(service, monkeypatch, overrides, message) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_run", lambda cmd, **_kwargs: calls.append(cmd) or _result())

    with pytest.raises(ValueError, match=message):
        service.load_network_config(_portable_env(**overrides))

    assert calls == []


def test_net_05_invalid_or_unmanaged_portable_interface_fails_closed(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    calls: list[list[str]] = []
    monkeypatch.setattr(
        service,
        "_run",
        lambda cmd, **_kwargs: calls.append(cmd) or _result(stdout="ethernet\n"),
    )

    with pytest.raises(RuntimeError, match="does not exist or is not Wi-Fi"):
        service.ensure_portable_ap(config)

    assert not any(command[:3] == ["nmcli", "connection", "add"] for command in calls)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("GENERAL.NM-MANAGED", "no\n", "not managed by NetworkManager"),
        ("WIFI-PROPERTIES.AP", "no\n", "has no AP capability"),
    ],
)
def test_net_05_unmanaged_or_non_ap_interface_fails_closed(
    service, monkeypatch, field, value, message
) -> None:
    config = service.load_network_config(_portable_env())
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        values = {
            "GENERAL.TYPE": "wifi\n",
            "GENERAL.NM-MANAGED": "yes\n",
            "WIFI-PROPERTIES.AP": "yes\n",
        }
        return _result(stdout=value if cmd[2] == field else values.get(cmd[2], ""))

    monkeypatch.setattr(service, "_run", fake_run)

    with pytest.raises(RuntimeError, match=message):
        service.ensure_portable_ap(config)

    assert not any(command[:3] == ["nmcli", "connection", "add"] for command in calls)


def test_net_05_invalid_portable_main_returns_failure(service, monkeypatch) -> None:
    monkeypatch.setenv("LIGHT_BELT_NETWORK_MODE", "portable_ap")
    monkeypatch.setattr(
        service,
        "_run",
        lambda *_args, **_kwargs: pytest.fail("invalid config must fail before nmcli"),
    )

    assert service.main() == 2


def test_net_06_portable_creation_failure_never_falls_back_to_open_hotspot(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    calls, _ = _install_healthy_nmcli(monkeypatch, service)
    original_run = service._run

    def creation_fails(cmd, **kwargs):
        if cmd[:3] == ["nmcli", "connection", "add"]:
            calls.append(list(cmd))
            return _result(returncode=5, stderr="AP creation failed")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(service, "_run", creation_fails)

    with pytest.raises(RuntimeError, match="unable to create dedicated Cabin AP profile"):
        service.ensure_portable_ap(config)

    assert not any(command[:4] == ["nmcli", "device", "wifi", "hotspot"] for command in calls)
    assert all("open" not in command for command in calls)


def test_net_08_and_09_repeated_reconcile_is_idempotent_without_duplicate_profiles(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    calls, _ = _install_healthy_nmcli(monkeypatch, service)

    service.ensure_portable_ap(config)
    service.ensure_portable_ap(config)

    adds = [command for command in calls if command[:3] == ["nmcli", "connection", "add"]]
    assert len(adds) == 1
    assert adds[0][adds[0].index("con-name") + 1] == config.cabin_ap_connection
    assert not any("Hotspot 1" in command or "Hotspot 2" in command for command in calls)


@pytest.mark.parametrize("returncode", [8, 124])
def test_net_08_and_09_lookup_failure_never_creates_duplicate_profile(
    service, monkeypatch, returncode
) -> None:
    config = service.load_network_config(_portable_env())
    calls, _ = _install_healthy_nmcli(monkeypatch, service)
    original_run = service._run

    def lookup_fails(cmd, **kwargs):
        if cmd[:3] == ["nmcli", "connection", "show"]:
            calls.append(list(cmd))
            return _result(returncode=returncode, stderr="lookup unavailable")
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(service, "_run", lookup_fails)

    with pytest.raises(RuntimeError, match="unable to inspect dedicated Cabin AP profile"):
        service.ensure_portable_ap(config)

    assert not any(command[:3] == ["nmcli", "connection", "add"] for command in calls)


def test_net_10_portable_watchdog_recovers_only_the_dedicated_ap(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    active_results = iter((False, True))
    recovered: list[object] = []
    monkeypatch.setattr(service, "_portable_ap_is_active", lambda _config: next(active_results))
    monkeypatch.setattr(service, "ensure_portable_ap", lambda received: recovered.append(received) or "192.168.77.1")
    monkeypatch.setattr(
        service,
        "_try_saved_wifi",
        lambda: pytest.fail("portable watchdog must not try saved site Wi-Fi"),
    )

    assert service.portable_ap_watchdog_tick(config) is True
    assert recovered == [config]


def test_net_11_private_ap_gateway_is_healthy_without_internet(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env(LIGHT_BELT_CABIN_AP_IPV4_CIDR="10.42.0.1/24"))
    monkeypatch.setattr(service, "_portable_ap_is_active", lambda _config: True)
    monkeypatch.setattr(service, "_get_wlan_ip", lambda _interface: "10.42.0.1")
    monkeypatch.setattr(
        service,
        "ensure_portable_ap",
        lambda _config: pytest.fail("an active private AP must not be recovered for lack of uplink"),
    )

    assert service.portable_ap_watchdog_tick(config) is True
    assert service.portable_ap_status(config)["ap_active"] is True
    assert service.portable_ap_status(config)["ap_ip"] == "10.42.0.1"


def test_net_12_portable_api_conflicts_do_not_start_threads_or_touch_ap(service, monkeypatch) -> None:
    for key, value in _portable_env().items():
        monkeypatch.setenv(key, value)
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_run", lambda cmd, **_kwargs: calls.append(cmd) or _result())
    monkeypatch.setattr(
        service.threading,
        "Thread",
        lambda **_kwargs: pytest.fail("portable conflict endpoints must not start a worker"),
    )

    for endpoint in (service.api_connect, service.api_hotspot, service.api_scan):
        body, status = endpoint()
        assert status == 409
        assert body["code"] == 3

    assert calls == []


def test_net_12_forget_rejects_cabin_profile_uuid_alias(service, monkeypatch) -> None:
    for key, value in _portable_env().items():
        monkeypatch.setenv(key, value)
    service.flask_request.get_json = lambda silent=True: {"ssid": "cabin-profile-uuid"}
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:4] == ["nmcli", "-g", "connection.id", "connection"]:
            return _result(stdout="LIGHT-BELT Cabin AP\n")
        return _result()

    monkeypatch.setattr(service, "_run", fake_run)

    body, status = service.api_forget()

    assert status == 409
    assert body["code"] == 3
    assert not any(command[:3] == ["nmcli", "connection", "delete"] for command in calls)


@pytest.mark.parametrize("returncode", [10, 124])
def test_net_12_forget_lookup_failure_never_deletes_unknown_profile(
    service, monkeypatch, returncode
) -> None:
    for key, value in _portable_env().items():
        monkeypatch.setenv(key, value)
    service.flask_request.get_json = lambda silent=True: {"ssid": "unknown-or-uuid"}
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _result(returncode=returncode, stderr="lookup unavailable")

    monkeypatch.setattr(service, "_run", fake_run)

    body, status = service.api_forget()

    assert status == 409
    assert body["code"] == 3
    assert not any(command[:3] == ["nmcli", "connection", "delete"] for command in calls)


def test_net_13_portable_cleanup_preserves_persistent_connection(service, monkeypatch) -> None:
    for key, value in _portable_env().items():
        monkeypatch.setenv(key, value)
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_run", lambda cmd, **_kwargs: calls.append(cmd) or _result())
    monkeypatch.setattr(service, "mdns_unregister", lambda: None)

    service.cleanup_service()

    assert calls == []


def test_net_14_site_client_temporary_hotspot_keeps_legacy_lifecycle(service, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        if cmd[:4] == ["nmcli", "device", "wifi", "hotspot"]:
            return _result(returncode=1, stderr="force manual legacy fallback")
        return _result()

    monkeypatch.setattr(service, "_run", fake_run)
    monkeypatch.setattr(service.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(service, "_get_wlan_ip", lambda *_args: None)

    assert service.hotspot_start() == "10.42.0.1"
    service.hotspot_stop()

    manual = next(command for command in calls if command[:3] == ["nmcli", "connection", "add"])
    assert manual[manual.index("con-name") + 1] == "Hotspot"
    assert manual[manual.index("autoconnect") + 1] == "no"
    assert ["nmcli", "connection", "delete", "Hotspot"] in calls


def test_net_15_and_16_status_preserves_legacy_fields_and_adds_portable_state(service, monkeypatch) -> None:
    for key, value in _portable_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(service, "wifi_is_connected", lambda _interface: (True, "LIGHT-BELT Cabin", "192.168.77.1"))
    monkeypatch.setattr(
        service,
        "portable_ap_status",
        lambda _config: {
            "network_mode": "portable_ap",
            "ap_interface": "wlp2s0",
            "ap_ssid": "LIGHT-BELT Cabin",
            "ap_ip": "192.168.77.1",
            "ap_active": True,
        },
    )

    response = service.api_status()
    data = response["data"]

    assert {"connected", "ssid", "ip", "softap_active", "host_service_port", "switch"} <= data.keys()
    assert data["network_mode"] == "portable_ap"
    assert data["ap_interface"] == "wlp2s0"
    assert data["ap_active"] is True


def test_net_17_nmcli_command_logging_redacts_passwords(service, monkeypatch, caplog) -> None:
    secret = "not-for-logs-123"
    seen_by_subprocess: list[list[str]] = []
    monkeypatch.setattr(
        service.subprocess,
        "run",
        lambda cmd, **_kwargs: seen_by_subprocess.append(cmd) or _result(),
    )
    caplog.set_level(logging.DEBUG, logger="wifi-setup")

    service._run(["nmcli", "device", "wifi", "connect", "site", "password", secret])
    service._run(["nmcli", "connection", "modify", "cabin", "wifi-sec.psk", secret])

    assert secret not in caplog.text
    assert all(secret in command for command in seen_by_subprocess)


def test_net_17_timeout_never_exposes_password_or_original_argv(service, monkeypatch, caplog) -> None:
    secret = "timeout-secret-123"

    def timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs["timeout"], stderr=secret)

    monkeypatch.setattr(service.subprocess, "run", timeout)
    caplog.set_level(logging.DEBUG, logger="wifi-setup")

    result = service._run(
        ["nmcli", "connection", "modify", "cabin", "wifi-sec.psk", secret],
        timeout=7,
    )

    assert result.returncode == 124
    assert secret not in caplog.text
    assert secret not in " ".join(result.args)
    assert secret not in result.stderr


def test_net_18_portable_network_code_contains_no_radio_or_bluetooth_reset(service, monkeypatch) -> None:
    config = service.load_network_config(_portable_env())
    calls, _ = _install_healthy_nmcli(monkeypatch, service)
    service.ensure_portable_ap(config)

    forbidden = ("rfkill", "hciconfig", "bluetoothctl", "reboot", "nmcli radio all off")
    source = inspect.getsource(service).lower()
    assert all(token not in source for token in forbidden)
    assert all(not any(token in " ".join(command).lower() for token in forbidden) for command in calls)
