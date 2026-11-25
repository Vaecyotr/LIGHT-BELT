import asyncio
import json

from host_services.bluez_backend import LinuxBluezBackend
from host_services.audio_routing import PulseAudioRouter
from light_engine.analysis.managed_audio_input import ManagedAudioInput
from light_engine.config import Config


def test_program_pcm_target_is_bound_to_current_mpv_process():
    async def run():
        async def pactl(*args):
            if args == ("--format=json", "list", "sinks"):
                return json.dumps([{"name": "rt5616", "index": 2}])
            if args == ("--format=json", "list", "sink-inputs"):
                return json.dumps([
                    {"index": 19, "sink": 2, "properties": {
                        "application.name": "LIGHT-BELT-LocalMedia",
                        "application.process.id": "100",
                    }},
                    {"index": 20, "sink": 2, "properties": {
                        "application.name": "LIGHT-BELT-LocalMedia",
                        "application.process.id": "200",
                    }},
                ])
            raise AssertionError(args)

        router = PulseAudioRouter(runner=pactl)
        router._generation = 4
        backend = LinuxBluezBackend(
            bus=object(), router=router, program_pid=lambda: 200,
            require_program_pid=True,
        )
        backend._source_monitor = {"rt5616": "rt5616.monitor"}

        target = await backend._program_target("rt5616")

        assert target == {
            "kind": "program_pcm",
            "source_id": "LIGHT-BELT-LocalMedia",
            "device": "rt5616.monitor",
            "monitor_stream": 20,
            "pa_generation": 4,
            "flow_generation": 0,
            "flow_identity": "mpv:200:20",
            "pa_sink": "rt5616",
            "pa_sink_index": 2,
            "pa_monitor_source": "rt5616.monitor",
            "pa_owner_pid": 200,
        }

    asyncio.run(run())


def test_program_pcm_target_fails_closed_without_mpv_identity_when_required():
    async def run():
        router = PulseAudioRouter()
        backend = LinuxBluezBackend(
            bus=object(), router=router, require_program_pid=True
        )

        assert await backend._program_target("rt5616") is None

    asyncio.run(run())


def test_pa_stream_lifecycle_reuses_index_but_rebinds_engine_capture():
    async def run():
        async def pactl(*args):
            if args == ("--format=json", "list", "sinks"):
                return json.dumps([{"name": "rt5616", "index": 2}])
            if args == ("--format=json", "list", "sink-inputs"):
                return json.dumps([{"index": 19, "sink": 2, "properties": {
                    "application.name": "LIGHT-BELT-LocalMedia",
                    "application.process.id": "200",
                }}])
            raise AssertionError(args)

        captures = []

        class Capture:
            sample_rate = 48000

            def __init__(self, **kwargs):
                captures.append(kwargs)

            def start(self):
                return self

            def close(self):
                pass

            def read_latest(self):
                return None

            def status(self):
                return {"running": True}

        router = PulseAudioRouter(runner=pactl)
        backend = LinuxBluezBackend(
            bus=object(), router=router, program_pid=lambda: 200,
            require_program_pid=True,
        )
        backend._source_monitor = {"rt5616": "rt5616.monitor"}
        audio = ManagedAudioInput(Config(), capture_factory=Capture)
        first = await backend._program_target("rt5616")
        first_epoch = audio.configure("device", first)

        router._observe_event("Event 'change' on sink-input #19")
        changed = await backend._program_target("rt5616")
        assert audio.configure("device", changed) == first_epoch
        assert len(captures) == 1

        router._observe_event("Event 'remove' on sink-input #19")
        router._observe_event("Event 'new' on sink-input #19")
        replacement = await backend._program_target("rt5616")
        replacement_epoch = audio.configure("device", replacement)

        assert replacement["monitor_stream"] == first["monitor_stream"]
        assert replacement["flow_generation"] > first["flow_generation"]
        assert replacement_epoch > first_epoch
        assert len(captures) == 2
        audio.close()

    asyncio.run(run())
