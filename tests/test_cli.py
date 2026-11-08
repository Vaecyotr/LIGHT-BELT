"""Phase 28 config-derived topology inspection tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from light_engine.cli import build_topology_inspection, cmd_inspect_topology
from light_engine.config import Config
from light_engine.cli import cmd_run
import pytest


PROFILE = "config/profile-archive/cabin-lighting-v3-production.yaml"
SHOW = "config/shows/archive/cabin-v2/cabin-show-v2.yaml"


def test_cabin_show_inspection_traces_all_fourteen_fixtures() -> None:
    report = build_topology_inspection(Config(Path(PROFILE)), SHOW)

    assert report["summary"] == {
        "digital_strips": 13,
        "analog_zones": 1,
        "physical_fixtures": 14,
    }
    regions = [region for path in report["virtual_paths"] for region in path["regions"]]
    assert {region["logical_id"] for region in regions} == {
        "zone_32",
        "strip_11", "strip_12", "strip_21", "strip_22", "strip_31",
        "strip_41", "strip_42", "strip_43", "strip_44", "strip_45",
        "strip_91", "strip_92", "strip_93",
    }
    strip_42 = next(region for region in regions if region["logical_id"] == "strip_42")
    assert strip_42["node_id"] == 8
    assert strip_42["output_id"] == 1
    assert strip_42["gpio"] == 4
    assert strip_42["host"] == "192.0.2.8"
    assert strip_42["port"] == 4048
    assert strip_42["transport_enabled"] is True
    cob = next(region for region in regions if region["logical_id"] == "zone_32")
    assert cob["node_id"] == 17
    assert cob["gpio"] is None
    assert cob["port"] == "REPLACE_WITH_RS485_PORT"


def test_inspect_topology_cli_prints_validated_json(capsys) -> None:
    Config.reset()
    result = cmd_inspect_topology(argparse.Namespace(config=PROFILE, show=SHOW))

    assert result == 0
    report = json.loads(capsys.readouterr().out)
    assert report["source"] == {"kind": "show_v2", "path": SHOW}
    assert report["hardware_verification"] == "NOT HARDWARE VERIFIED"


@pytest.mark.parametrize('fail_initialization', [False, True])
def test_run_emits_ready_only_after_successful_output_initialization(monkeypatch, capsys, fail_initialization):
    import light_engine.cli as cli

    class EngineFixture:
        _outputs = {}

        def __init__(self, *args, **kwargs):
            pass

        def use_synthetic(self):
            pass

        def set_effect(self, effect):
            pass

        def init_outputs(self):
            assert 'LIGHT_BELT_ENGINE_READY' not in capsys.readouterr().out
            if fail_initialization:
                raise RuntimeError('output unavailable')

        def run(self, on_ready=None, **kwargs):
            self.init_outputs()
            on_ready()
            assert 'LIGHT_BELT_ENGINE_READY' in capsys.readouterr().out

        def get_fps_stats(self):
            return {'frame_count': 0, 'effective_fps': 0, 'processing_capacity': 0}

    monkeypatch.setattr(cli, 'Engine', EngineFixture)
    Config.reset()
    result = cmd_run(argparse.Namespace(config=None, clock='internal', video=None, audio=None,
                                       show=None, effect='static', duration=0, max_frames=0, ready_stdout=True))
    assert result == (1 if fail_initialization else 0)
    if fail_initialization:
        assert 'LIGHT_BELT_ENGINE_READY' not in capsys.readouterr().out


def test_run_mpv_closes_connected_clock_when_show_initialization_fails(monkeypatch):
    import light_engine.cli as cli

    class ClockFixture:
        closed = False

        def __init__(self, _path):
            pass

        def connect(self):
            pass

        def close(self):
            self.closed = True

    class EngineFixture:
        def __init__(self, *_args, **_kwargs):
            pass

    def reject_show(*_args):
        raise ValueError("bad show")

    def reject_external_launch(*_args, **_kwargs):
        pytest.fail("external mpv must not launch")

    clock = ClockFixture("ipc")
    monkeypatch.setattr(cli, "MpvIPCClock", lambda _path: clock)
    monkeypatch.setattr(cli, "Engine", EngineFixture)
    monkeypatch.setattr(cli, "_configure_engine_show", reject_show)
    monkeypatch.setattr(cli.subprocess, "Popen", reject_external_launch)
    Config.reset()

    result = cli.cmd_run_mpv(argparse.Namespace(
        config=None, mpv_socket="ipc", media=None, mpv_binary="mpv", show="bad.yaml",
        effect=None, duration=None, max_frames=None,
    ))

    assert result == 1
    assert clock.closed


def test_run_mpv_reaps_owned_process_after_output_initialization_failure(monkeypatch):
    import light_engine.cli as cli

    class ClockFixture:
        closed = False

        def __init__(self, _path):
            pass

        def connect(self):
            pass

        def close(self):
            self.closed = True

    class EngineFixture:
        def __init__(self, *_args, **_kwargs):
            self._outputs = {}

        def set_effect(self, _effect):
            pass

        def init_outputs(self):
            raise RuntimeError("output initialization failed")

    class OwnedProcess:
        def __init__(self):
            self.terminated = False
            self.killed = False
            self.waits = 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waits += 1
            if self.waits == 1:
                raise subprocess.TimeoutExpired("mpv", timeout)
            return 0

        def kill(self):
            self.killed = True

    clock = ClockFixture("ipc")
    process = OwnedProcess()
    monkeypatch.setattr(cli, "MpvIPCClock", lambda _path: clock)
    monkeypatch.setattr(cli, "Engine", EngineFixture)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *_args, **_kwargs: process)
    Config.reset()

    with pytest.raises(RuntimeError, match="output initialization failed"):
        cli.cmd_run_mpv(argparse.Namespace(
            config=None, mpv_socket="ipc", media="movie.mp4", mpv_binary="mpv",
            show=None, effect="static", duration=None, max_frames=None,
        ))

    assert clock.closed
    assert process.terminated
    assert process.killed
    assert process.waits == 2


@pytest.mark.parametrize("failure_stage", ["connect", "show"])
def test_run_mpv_cleans_owned_resources_when_initialization_fails(
    monkeypatch, failure_stage
):
    import light_engine.cli as cli

    class ClockFixture:
        closed = False

        def __init__(self, _path):
            pass

        def connect(self):
            if failure_stage == "connect":
                raise OSError("IPC connect failed")

        def close(self):
            self.closed = True

    class EngineFixture:
        def __init__(self, *_args, **_kwargs):
            self._outputs = {}

        def set_effect(self, _effect):
            pass

        def init_outputs(self):
            pass

    class OwnedProcess:
        terminated = False
        waits = 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waits += 1
            return 0

        def kill(self):
            pytest.fail("successful terminate should not require kill")

    clock = ClockFixture("ipc")
    process = OwnedProcess()

    def configure_show(*_args):
        if failure_stage == "show":
            raise ValueError("show initialization failed")
        return None

    monkeypatch.setattr(cli, "MpvIPCClock", lambda _path: clock)
    monkeypatch.setattr(cli, "Engine", EngineFixture)
    monkeypatch.setattr(cli, "_configure_engine_show", configure_show)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *_args, **_kwargs: process)
    Config.reset()

    result = cli.cmd_run_mpv(argparse.Namespace(
        config=None, mpv_socket="ipc", media="movie.mp4", mpv_binary="mpv",
        show="show.yaml", effect=None, duration=None, max_frames=None,
    ))

    assert result == 1
    assert clock.closed
    assert process.terminated
    assert process.waits == 1


def test_run_mpv_reaps_owned_process_even_if_clock_close_fails(monkeypatch):
    import light_engine.cli as cli

    class ClockFixture:
        def __init__(self, _path):
            pass

        def connect(self):
            pass

        def close(self):
            raise RuntimeError("clock close failed")

    class EngineFixture:
        _outputs = {}

        def __init__(self, *_args, **_kwargs):
            pass

        def set_effect(self, _effect):
            pass

        def init_outputs(self):
            pass

        def run(self, **_kwargs):
            pass

        def get_fps_stats(self):
            return {"frame_count": 0, "effective_fps": 0, "processing_capacity": 0}

    class OwnedProcess:
        terminated = False
        waits = 0

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.waits += 1
            return 0

    process = OwnedProcess()
    monkeypatch.setattr(cli, "MpvIPCClock", ClockFixture)
    monkeypatch.setattr(cli, "Engine", EngineFixture)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *_args, **_kwargs: process)
    Config.reset()

    with pytest.raises(RuntimeError, match="clock close failed"):
        cli.cmd_run_mpv(argparse.Namespace(
            config=None, mpv_socket="ipc", media="movie.mp4", mpv_binary="mpv",
            show=None, effect="static", duration=None, max_frames=1,
        ))

    assert process.terminated
    assert process.waits == 1
