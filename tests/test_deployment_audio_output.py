"""Exercise the audio entry logic with Jammy pactl JSON and mutable server state."""
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/deploy/rk3588/audio_output.py"
SPEC = importlib.util.spec_from_file_location("audio_output", MODULE)
audio = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audio)

INPUT = "input:analog-stereo"
OUTPUT = "output:analog-stereo"
DUPLEX = OUTPUT + "+" + INPUT
SINK = "alsa_output.platform-rt5616-sound.HiFi__Speaker__sink"
SOURCE = "bluez_source.AA_BB_CC_DD_EE_FF.a2dp_source"


@pytest.fixture
def server(monkeypatch):
    monkeypatch.delenv("LIGHT_BELT_AUDIO_SINK", raising=False)
    card = {"name": "alsa_card.platform-rt5616-sound", "owner_module": "8", "active_profile": INPUT,
            "profiles": {
                INPUT: {"available": True, "sinks": 0, "sources": 1, "priority": 1},
                OUTPUT: {"available": True, "sinks": 1, "sources": 0, "priority": 30},
                DUPLEX: {"available": True, "sinks": 1, "sources": 1, "priority": 20},
                "output:hdmi-stereo": {"available": True, "sinks": 1, "sources": 0, "priority": 99},
            }}
    sink = {"name": SINK, "owner_module": 8, "index": 7, "state": "SUSPENDED"}
    state = {"card": card, "sink": sink, "default": "auto_null", "sources": [], "modules": "",
             "sink-inputs": [], "writes": [], "publish_card": True, "publish_sink": True,
             "reject": set(), "driver_error": False}
    clock = [0]
    monkeypatch.setattr(audio.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(audio.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    def call(*args, timeout):
        if args[:2] == ("--format=json", "list"):
            assert args[2] != "modules", "Jammy JSON omits the module index"
            if state["driver_error"]:
                raise audio.AudioError("Connection refused")
            items = {"cards": [card] if state["publish_card"] else [], "sinks": [sink] if
                     card["active_profile"] in (OUTPUT, DUPLEX) and state["publish_sink"] else []}
            return json.dumps(items[args[2]] if args[2] in items else state[args[2]])
        if args == ("list", "short", "modules"):
            return state["modules"]
        if args[0] == "get-default-sink":
            return state["default"]
        state["writes"].append(args)
        if args[0] == "set-card-profile":
            if args[2] in state["reject"]:
                raise audio.AudioError("rejected profile")
            card["active_profile"] = args[2]
        elif args[0] == "set-default-sink":
            state["preferred"] = args[1]
            if not any(port["name"] == sink.get("active_port") and port["availability"] == "not available"
                       for port in sink.get("ports", [])):
                state["default"] = args[1]
        elif args[0] == "move-sink-input":
            next(item for item in state["sink-inputs"] if str(item["index"]) == args[1])["sink"] = 7
        else:
            pytest.fail(f"unexpected write {args}")
        return ""

    monkeypatch.setattr(audio, "_pactl", call)
    return state


def test_input_only_creates_output_then_repeat_and_check_are_read_only(server):
    assert audio.run(wait=4) == 0
    assert server["writes"] == [
        ("set-card-profile", server["card"]["name"], DUPLEX), ("set-default-sink", SINK)]
    server["writes"].clear()
    assert audio.run(wait=4) == audio.run(check=True, wait=4) == 0
    assert server["writes"] == []


@pytest.mark.parametrize("unavailable", [True, False])
def test_falls_back_to_available_output_without_selecting_hdmi(server, unavailable):
    if unavailable:
        server["card"]["profiles"][DUPLEX]["available"] = False
    else:
        server["reject"].add(DUPLEX)
    assert audio.run(wait=4) == 0
    assert server["card"]["active_profile"] == OUTPUT


def test_missing_output_is_diagnosed_and_original_input_restored(server, capsys):
    server["publish_sink"] = False
    assert audio.run(wait=3) == 1
    assert server["card"]["active_profile"] == INPUT
    assert "no RT5616 sink published" in capsys.readouterr().err
    assert [write[2] for write in server["writes"]] == [DUPLEX, INPUT]


def test_only_input_profiles_fail_without_writes(server, capsys):
    server["card"]["profiles"][DUPLEX]["available"] = False
    server["card"]["profiles"][OUTPUT]["available"] = False
    assert audio.run(wait=2) == 1
    assert "no available playback profile" in capsys.readouterr().err
    assert server["writes"] == []


def test_check_never_changes_input_only_card(server):
    assert audio.run(check=True, wait=3) == 1
    assert server["writes"] == []


def test_only_existing_policy_route_moves_and_check_detects_wrong_sink(server):
    server["card"]["active_profile"] = DUPLEX
    server["default"] = SINK
    server["sources"] = [{"name": SOURCE, "state": "RUNNING"}]
    server["modules"] = (
        '9\tmodule-bluetooth-policy\t\t\n'
        f'11\tmodule-loopback\tsource="{SOURCE}" source_dont_move="true" '
        'sink_input_properties="media.role=music"\t\n'
        f'12\tmodule-loopback\tsource="{SOURCE}" sink=other_sink\t\n'
    )
    server["sink-inputs"] = [{"index": 20, "owner_module": "11", "sink": 1},
                             {"index": 21, "owner_module": None, "sink": 1},
                             {"index": 22, "owner_module": "12", "sink": 1}]
    assert audio.run(check=True, wait=3) == 1
    assert server["writes"] == []
    assert audio.run(wait=3) == 0
    assert server["writes"] == [("move-sink-input", "20", SINK)]
    assert server["sink-inputs"][1]["sink"] == 1
    assert server["sink-inputs"][2]["sink"] == 1


def test_active_a2dp_without_route_fails_check(server, capsys):
    server["card"]["active_profile"] = DUPLEX
    server["default"] = SINK
    server["sources"] = [{"name": SOURCE, "state": "RUNNING"}]
    assert audio.run(check=True, wait=3) == 1
    assert "no PulseAudio policy playback route" in capsys.readouterr().err


def test_explicit_existing_sink_does_not_change_card_profile(server, monkeypatch):
    server["card"]["active_profile"] = OUTPUT
    monkeypatch.setenv("LIGHT_BELT_AUDIO_SINK", SINK)
    assert audio.run(wait=3) == 0
    assert server["writes"] == [("set-default-sink", SINK)]


def test_unplugged_port_keeps_preferred_sink_and_defers_playback_until_plugged(server, capsys, monkeypatch):
    server["card"]["active_profile"] = DUPLEX
    port = {"name": "analog-output-headphones", "availability": "not available"}
    server["sink"].update(active_port=port["name"], ports=[port])
    server["sources"] = [{"name": SOURCE, "state": "RUNNING"}]
    assert audio.run(wait=3) == 0
    assert server["preferred"] == SINK and server["default"] == "auto_null"
    assert server["writes"] == [("set-default-sink", SINK)]
    server["writes"].clear()
    assert audio.run(check=True, wait=3) == 0
    assert "NOT HARDWARE VERIFIED" in capsys.readouterr().out
    monkeypatch.setattr(audio.sys, "argv", ["audio_output.py", "--check-playback"])
    assert audio.main() == 1
    assert "not available" in capsys.readouterr().err
    assert server["writes"] == []

    # PulseAudio reevaluates the configured default when the jack becomes available.
    port["availability"] = "available"
    server["default"] = server["preferred"]
    server["modules"] = (f'11\tmodule-loopback\tsource="{SOURCE}" source_dont_move="true" '
                         'sink_input_properties="media.role=music"\t\n')
    server["sink-inputs"] = [{"index": 20, "owner_module": "11", "sink": 7}]
    assert audio.main() == 0
    assert server["writes"] == []


def test_available_active_port_still_requires_correct_default_and_playback(server, capsys):
    server["card"]["active_profile"] = DUPLEX
    server["sink"].update(active_port="speaker", ports=[
        {"name": "headphones", "availability": "not available"},
        {"name": "speaker", "availability": "available"},
    ])
    assert audio.run(check=True, wait=3) == 1
    assert "default sink" in capsys.readouterr().err
    server["default"] = SINK
    assert audio.run(check=True, wait=3) == 0
    assert audio.run(check=True, playback=True, wait=3) == 1
    assert "no RUNNING A2DP source" in capsys.readouterr().err


@pytest.mark.parametrize(("failure", "message"), [
    ("publish_card", "expected one RT5616 ALSA card, found 0"),
    ("publish_sink", "no RT5616 sink published"),
    ("driver_error", "Connection refused"),
])
def test_missing_card_sink_or_driver_still_fails(server, capsys, failure, message):
    server["card"]["active_profile"] = DUPLEX
    server["sink"].update(active_port="headphones", ports=[
        {"name": "headphones", "availability": "not available"},
    ])
    server[failure] = failure == "driver_error"
    assert audio.run(wait=3) == 1
    assert message in capsys.readouterr().err
    assert server["writes"] == []
