"""The subprocess READY marker includes live audio and output preparation."""

import argparse

import pytest

from light_engine import cli
from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.outputs import NullOutput, OutputMode


@pytest.mark.parametrize("failure", [None, "audio", "output"])
def test_cli_ready_follows_all_resource_initialization(monkeypatch, capsys, failure):
    Config.reset()
    config = Config()
    config._data["outputs"]["enabled"] = ["null"]
    events = []

    class Source:
        stale = False

        def reset(self):
            pass

        def open(self):
            assert "LIGHT_BELT_ENGINE_READY" not in capsys.readouterr().out
            events.append("audio-open")
            if failure == "audio":
                raise OSError("multicast bind failed")

        def close(self):
            events.append("audio-close")

    output = NullOutput()
    output.mode = OutputMode.PRODUCTION
    original_open = output.open

    def open_output():
        assert "LIGHT_BELT_ENGINE_READY" not in capsys.readouterr().out
        events.append("output-open")
        if failure == "output":
            raise OSError("output unavailable")
        original_open()

    monkeypatch.setattr(output, "open", open_output)
    monkeypatch.setattr("light_engine.engine.create_outputs", lambda _config: {"null": output})
    monkeypatch.setattr(cli, "Engine", lambda config, **kwargs: Engine(config, live_audio_source=Source(), **kwargs))
    monkeypatch.setattr(Config, "get_instance", lambda _path=None: config)
    args = argparse.Namespace(config=None, clock="internal", video=None, audio=None,
                              show=None, effect="static", duration=0, max_frames=0,
                              ready_stdout=True)

    result = cli.cmd_run(args)

    stdout = capsys.readouterr().out
    assert result == (1 if failure else 0)
    assert ("LIGHT_BELT_ENGINE_READY" in stdout) == (failure is None)
    assert events.count("audio-open") == 1
    assert "audio-close" in events
    assert not output.is_open()
