from __future__ import annotations

from pathlib import Path
import re
import configparser
import subprocess
import sys
import importlib.util


DEPLOY = Path("scripts/deploy/rk3588")
SYSTEMD = Path("systemd")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def deployment_text() -> str:
    paths = list(DEPLOY.rglob("*.sh")) + list(DEPLOY.rglob("*.py")) + list(SYSTEMD.rglob("*.service"))
    return "\n".join(read(path) for path in paths)


def test_no_permanent_manual_bluetooth_loopback_creation():
    assert "pactl load-module module-loopback" not in deployment_text()


def test_pulseaudio_policy_edit_is_narrow_and_idempotent(tmp_path):
    path = tmp_path / "default.pa"
    path.write_text("# preserve\nload-module module-bluetooth-policy auto_switch=2\nload-module module-bluetooth-discover\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pulseaudio_policy_test", DEPLOY / "pulseaudio_policy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.configure(path) is True
    expected = "# preserve\nload-module module-bluetooth-policy auto_switch=2 a2dp_source=false # LIGHT-BELT managed a2dp_source policy\nload-module module-bluetooth-discover\n"
    assert path.read_text(encoding="utf-8") == expected
    assert module.configure(path) is False
    assert path.with_name("default.pa.light-belt.bak").read_text(encoding="utf-8").endswith("load-module module-bluetooth-discover\n")


def test_no_historical_phone_or_device_specific_source_is_hard_coded():
    text = deployment_text()
    assert "44_55_C4_50_7F_58" not in text
    assert not re.search(r"bluez_source\.[0-9A-Fa-f_]{8,}\.a2dp_source", text)


def test_legacy_public_agent_and_priority_units_are_retired():
    assert not (SYSTEMD / "bluetooth-auto-agent.service").exists()
    assert not (SYSTEMD / "bluetooth-public-mode.service").exists()
    assert not (SYSTEMD / "user" / "light-belt-bluetooth-priority.service").exists()


def test_verifier_requires_legacy_audio_priority_service_to_be_disabled():
    verifier = read(DEPLOY / "verify-install.sh")
    assert "legacy Bluetooth priority service must be disabled" in verifier


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


def test_verifier_checks_single_host_managed_bluetooth_route():
    verifier = read(DEPLOY / "verify-install.sh")
    assert 'bluetooth_routes_exclusive "$MODULES"' in verifier
    assert 'bluetooth_policy_disables_autoplay "$MODULES"' in verifier
    assert "latency_msec=80" not in verifier


def test_current_mpv_source_has_stable_local_media_identity():
    source = read(Path("host_services/engine_adapter.py"))
    assert "--audio-client-name=LIGHT-BELT-LocalMedia" in source


def test_deployment_docs_preserve_hardware_status_semantics():
    docs = read(Path("docs/current/rk3588-bootstrap.md"))
    assert "NOT HARDWARE VERIFIED" in docs


def test_bluez_update_preserves_pairing_policy_and_enables_controller(tmp_path):
    path = tmp_path / "main.conf"
    path.write_text("# vendor comment\n[General]\n#DiscoverableTimeout = 180\n"
                    "DiscoverableTimeout = 30\nPairableTimeout = 15\nVendorSetting = keep\n"
                    "[Policy]\nAutoEnable = false\n", encoding="utf-8")
    source = read(DEPLOY / "setup-bluetooth.sh")
    program = source.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    result = subprocess.run([sys.executable, "-B", "-c", program, str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    parser = configparser.ConfigParser(strict=False)
    parser.read(path)
    assert parser["General"]["DiscoverableTimeout"] == "30"
    assert parser["General"]["PairableTimeout"] == "15"
    assert parser["General"]["VendorSetting"] == "keep"
    assert parser["Policy"].getboolean("AutoEnable") is True
    before = path.read_bytes()
    result = subprocess.run([sys.executable, "-B", "-c", program, str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert path.read_bytes() == before
