"""Exercise the read-only preflight without a running audio server or adapter."""

import os
import subprocess

import pytest

from tests.test_update_transaction import BASH


@pytest.mark.parametrize(("case", "expected"), [
    ("managed", 0), ("automatic", 1), ("duplicate", 1),
    ("foreign-loopback", 1), ("wrong-sink", 1), ("pipewire", 1), ("old-agent", 1),
])
def test_preflight_requires_exclusive_native_rt5616(case, expected):
    assert BASH, "set LIGHT_BELT_BASH to the Git Bash executable"
    script = r'''
set -eu
bluetoothctl() { [[ "$*" = show ]]; }
parec() { return 99; }
busctl() { return 99; }
systemctl() {
    if [[ "$CASE" = old-agent && "$*" = *bluetooth-auto-agent.service ]]; then return 0; fi
    return 3
}
pactl() {
    case "$*" in
        info) if [[ "$CASE" = pipewire ]]; then echo 'Server Name: PulseAudio (on PipeWire)'
              else echo 'Server Name: pulseaudio'; fi ;;
        'get-default-sink') if [[ "$CASE" = wrong-sink ]]; then echo auto_null; else echo alsa_output.platform-rt5616.test; fi ;;
        'list short modules')
            if [[ "$CASE" = automatic ]]; then printf '1\tmodule-bluetooth-policy\t\n'
            else printf '1\tmodule-bluetooth-policy\ta2dp_source=false\n'; fi
            if [[ "$CASE" = duplicate ]]; then printf '2\tmodule-bluetooth-policy\ta2dp_source=false\n'; fi
            if [[ "$CASE" = foreign-loopback ]]; then printf '3\tmodule-loopback\tsource=bluez_source.fixture.a2dp_source\n'; fi ;;
        'list short sources'|'list short sink-inputs') : ;;
        *) echo "Unexpected PA operation: $*" >&2; exit 90 ;;
    esac
}
source scripts/deploy/rk3588/check-managed-audio.sh
'''
    env = {**os.environ, "CASE":case, "LIGHT_BELT_AUDIO_SINK":""}
    result = subprocess.run([BASH,"-c",script],env=env,capture_output=True,timeout=20)
    assert result.returncode == expected, (result.stdout,result.stderr)
