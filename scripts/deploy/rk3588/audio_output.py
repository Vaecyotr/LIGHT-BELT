#!/usr/bin/env python3
"""Prepare the NanoPC-T6 RT5616 output in the pi PulseAudio session."""
import json
import os
import shlex
import subprocess
import sys
import time


class AudioError(RuntimeError):
    pass


def _pactl(*args, timeout):
    try:
        result = subprocess.run(["pactl", *args], text=True, capture_output=True,
                                timeout=timeout, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AudioError(f"pactl {' '.join(args)}: {exc}") from exc
    if result.returncode:
        raise AudioError(result.stderr.strip() or f"pactl {' '.join(args)} failed ({result.returncode})")
    return result.stdout


def _items(call, kind):
    try:
        items = json.loads(call("--format=json", "list", kind))
    except ValueError as exc:
        raise AudioError(f"invalid pactl JSON for {kind}") from exc
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise AudioError(f"unexpected pactl JSON for {kind}")
    return items


def _rt5616(cards):
    matches = []
    for card in cards:
        props = card.get("properties") or {}
        identity = " ".join(str(props.get(key, "")) for key in
                            ("device.product.name", "alsa.card_name", "alsa.long_card_name", "device.bus_path"))
        if "rt5616" in (identity + " " + card["name"]).lower() and card["name"].startswith("alsa_card."):
            matches.append(card)
    if len(matches) != 1:
        raise AudioError(f"expected one RT5616 ALSA card, found {len(matches)}")
    return matches[0]


def _output_profiles(card):
    # Jammy's pactl encodes counts as sinks/sources and availability as a boolean.
    return sorted(
        (name for name, profile in card["profiles"].items()
         if profile["available"] is True and profile["sinks"] > 0
         and not any(kind in name.lower() for kind in ("hdmi", "iec958"))),
        key=lambda name: (card["profiles"][name]["sources"] > 0,
                          card["profiles"][name]["priority"], name),
        reverse=True,
    )


def _select_sink(sinks, card, explicit, default):
    if explicit:
        return next((sink for sink in sinks if sink["name"] == explicit), None)
    # Jammy publishes the owner module, not the card index, on sink objects.
    matches = [sink for sink in sinks
               if card.get("owner_module") is not None
               and str(sink.get("owner_module")) == str(card["owner_module"])
               and sink["name"].startswith("alsa_output.")
               and not any(kind in sink["name"].lower() for kind in ("hdmi", "iec958"))]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    for preferred in (default, "alsa_output.platform-rt5616-sound.stereo-fallback"):
        for sink in matches:
            if sink["name"] == preferred:
                return sink
    raise AudioError("multiple RT5616 sinks; set LIGHT_BELT_AUDIO_SINK to select one")


def _route_a2dp(call, sink, check):
    sources = {source["name"]: source for source in _items(call, "sources")
               if source["name"].startswith("bluez_source.") and source["name"].endswith(".a2dp_source")}
    if not sources:
        return
    routes = {}
    # Jammy only includes module IDs in the text output.
    for line in call("list", "short", "modules").splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3 or fields[1] != "module-loopback":
            continue
        module_id, _, arguments = fields
        args = dict(word.split("=", 1) for word in shlex.split(arguments) if "=" in word)
        if (args.get("source") in sources and args.get("source_dont_move") == "true"
                and args.get("sink_input_properties") == "media.role=music" and "sink" not in args):
            routes[module_id] = args["source"]
    connected = set()
    for stream in _items(call, "sink-inputs"):
        source = routes.get(str(stream.get("owner_module")))
        if source is None:
            continue
        connected.add(source)
        if stream["sink"] != sink["index"]:
            if check:
                raise AudioError(f"A2DP policy stream for {source} is on sink #{stream['sink']}; expected {sink['name']}")
            call("move-sink-input", str(stream["index"]), sink["name"])
    for name, source in sources.items():
        if source["state"] == "RUNNING" and name not in connected:
            raise AudioError(f"RUNNING A2DP source {name} has no PulseAudio policy playback route")


def run(check=False, wait=110):
    deadline = time.monotonic() + wait

    def call(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AudioError("audio readiness deadline reached")
        return _pactl(*args, timeout=min(remaining, 3))

    explicit = os.environ.get("LIGHT_BELT_AUDIO_SINK")
    previous_profile = None
    switched_to = None
    last_error = "audio initialization deadline reached"
    while time.monotonic() < deadline:
        try:
            card = None if explicit else _rt5616(_items(call, "cards"))
            sinks = _items(call, "sinks")
            default = call("get-default-sink").strip() if sinks else ""
            sink = _select_sink(sinks, card, explicit, default)
            if sink is None:
                if explicit:
                    raise AudioError(f"configured sink {explicit!r} has not appeared")
                profiles = _output_profiles(card)
                active = card["active_profile"]
                if not profiles:
                    raise AudioError(f"{card['name']} has no available playback profile (active: {active})")
                if check or active in profiles or switched_to is not None:
                    raise AudioError(f"no RT5616 sink published for active profile {active!r}")
                for profile in profiles:
                    try:
                        call("set-card-profile", card["name"], profile)
                    except AudioError as exc:
                        last_error = str(exc)
                    else:
                        previous_profile = (card["name"], active)
                        switched_to = profile
                        last_error = f"waiting for RT5616 sink after enabling {profile}"
                        break
                raise AudioError(last_error)
            previous_profile = None  # A usable output exists. Keep it if routing fails.
            if default != sink["name"]:
                if check:
                    raise AudioError(f"default sink is {default!r}; expected {sink['name']!r}")
                call("set-default-sink", sink["name"])
            _route_a2dp(call, sink, check)
            if not check:
                if call("get-default-sink").strip() != sink["name"]:
                    raise AudioError(f"default sink did not settle on {sink['name']!r}")
                _route_a2dp(call, sink, True)
            print(f"[audio-sink] verified default={sink['name']}")
            return 0
        except (AudioError, KeyError, TypeError, ValueError) as exc:
            last_error = str(exc)
            if check:
                break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    if previous_profile and previous_profile[1]:
        try:
            # Only undo the profile selected by this invocation.
            current = _rt5616(_items(lambda *args: _pactl(*args, timeout=3), "cards"))
            if current["name"] == previous_profile[0] and current["active_profile"] == switched_to:
                _pactl("set-card-profile", *previous_profile, timeout=3)
        except (AudioError, KeyError, TypeError, ValueError) as exc:
            print(f"[audio-sink] could not restore previous profile: {exc}", file=sys.stderr)
    print(f"[audio-sink] {last_error}", file=sys.stderr)
    return 1


def main():
    if sys.argv[1:] not in ([], ["--check"]):
        print("usage: set-default-audio-sink.sh [--check]", file=sys.stderr)
        return 2
    return run(check=bool(sys.argv[1:]), wait=12 if sys.argv[1:] else 110)


if __name__ == "__main__":
    raise SystemExit(main())
