from __future__ import annotations

from pathlib import Path
import re


DEPLOY = Path("scripts/deploy/rk3588")
SYSTEMD = Path("systemd")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def deployment_text() -> str:
    paths = list(DEPLOY.rglob("*.sh")) + list(DEPLOY.rglob("*.py")) + list(SYSTEMD.rglob("*.service"))
    return "\n".join(read(path) for path in paths)


def test_no_permanent_manual_bluetooth_loopback_creation():
    assert "pactl load-module module-loopback" not in deployment_text()


def test_no_historical_phone_or_device_specific_source_is_hard_coded():
    text = deployment_text()
    assert "44_55_C4_50_7F_58" not in text
    assert not re.search(r"bluez_source\.[0-9A-Fa-f_]{8,}\.a2dp_source", text)


def test_priority_unit_is_user_scoped_without_synthetic_session_environment():
    unit = read(SYSTEMD / "user" / "light-belt-bluetooth-priority.service")
    assert "WantedBy=default.target" in unit
    assert "User=" not in unit
    assert "PULSE_SERVER=" not in unit
    assert "XDG_RUNTIME_DIR=" not in unit
    assert "DBUS_SESSION_BUS_ADDRESS=" not in unit


def test_verifier_defers_user_manager_lifecycle_when_unit_is_statically_enabled():
    verifier = read(DEPLOY / "verify-install.sh")
    assert '[[ -f "$PRIORITY_UNIT" && -L "$PRIORITY_LINK" ]]' in verifier
    assert "reboot/no-SSH lifecycle is NOT HARDWARE VERIFIED" in verifier


def test_all_bluetooth_execstart_paths_use_current_layout():
    for path in SYSTEMD.rglob("*.service"):
        text = read(path)
        if "Bluetooth" not in text and "bluetooth" not in text:
            continue
        for line in text.splitlines():
            if line.startswith("ExecStart=") and "/home/pi/LIGHT-BELT" in line:
                assert "/scripts/deploy/rk3588/" in line


def test_bootstrap_integrates_bluetooth_before_service_install():
    script = read(DEPLOY / "bootstrap.sh")
    assert script.index("run_repo_script setup-bluetooth.sh") < script.index("run_repo_script install-services.sh")


def test_verifier_allows_zero_policy_loopbacks_when_idle():
    verifier = read(DEPLOY / "verify-install.sh")
    assert "ALL_LOOPBACKS <= 1" in verifier
    assert "idle zero is allowed" in verifier


def test_current_mpv_source_has_stable_local_media_identity():
    source = read(Path("host_services/engine_adapter.py"))
    assert "--audio-client-name=LIGHT-BELT-LocalMedia" in source


def test_deployment_docs_preserve_hardware_status_semantics():
    docs = read(Path("docs/current/rk3588-bootstrap.md"))
    assert "历史实机验证" in docs
    assert "历史 prototype/user-observed" in docs
    assert "NOT HARDWARE VERIFIED" in docs
    assert "0.20" in docs
