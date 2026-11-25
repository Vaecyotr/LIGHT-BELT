from io import BytesIO

import numpy as np

from light_engine.analysis.pulse_capture import ParecCapture, validate_pulse_target


class _Process:
    def __init__(self, command, **_kwargs):
        self.command = command
        self.stdout = BytesIO(
            np.array([[16384, -16384], [0, 0]], dtype="<i2").tobytes()
        )
        self.stderr = BytesIO()
        self.returncode = 0

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):
        return self.returncode


def test_parec_capture_uses_targeted_stereo_raw_command_and_decodes_frames():
    processes = []

    def factory(command, **kwargs):
        process = _Process(command, **kwargs)
        processes.append(process)
        return process

    capture = ParecCapture(
        device="bluez_source.phone.monitor",
        monitor_stream=42,
        sample_rate=48000,
        channels=2,
        block_ms=1,
        popen=factory,
    )
    capture.start()
    chunk = capture.read_latest(timeout=1.0)
    capture.close()

    assert processes[0].command == [
        "parec",
        "--raw",
        "--format=s16le",
        "--rate=48000",
        "--channels=2",
        "--device=bluez_source.phone.monitor",
        "--monitor-stream=42",
    ]
    assert chunk is not None
    assert chunk.samples.shape == (2, 2)
    assert chunk.samples[0, 0] == 0.5
    assert chunk.samples[0, 1] == -0.5


def test_fragmented_stereo_sample_is_joined_before_pcm_decoding():
    class Fragmented(BytesIO):
        def read(self, size):
            return super().read(min(size, 3))

    samples = np.array([[16384, -16384], [123, -456]], dtype="<i2")
    def factory(command, **kwargs):
        proc = _Process(command, **kwargs)
        proc.stdout = Fragmented(samples.tobytes())
        return proc

    capture = ParecCapture(device="sink.monitor", monitor_stream=7, popen=factory)
    try:
        capture.start()
        capture._thread.join(timeout=1)
        chunk = capture.read_latest()
        assert chunk is not None
        np.testing.assert_array_equal(chunk.samples, samples.astype(np.float32) / 32768)
        assert not chunk.discontinuity
    finally:
        capture.close()


def test_invalid_target_proof_prevents_parec_from_binding_reused_index():
    started = []
    capture = ParecCapture(
        device="rt5616.monitor",
        monitor_stream=19,
        target_proof={"pa_sink_index": 2},
        target_validator=lambda _proof: False,
        popen=lambda *_args, **_kwargs: started.append(True),
    ).start()
    capture._thread.join(timeout=1)

    assert started == []
    assert capture.status()["phase"] == "invalid"
    assert capture.status()["error"]
    capture.close()


def test_valid_target_proof_matches_pa_sink_and_mpv_stream_identity():
    outputs = {
        ("--format=json", "list", "sinks"): '[{"index":2,"name":"rt5616","monitor_source":"rt5616.monitor"}]',
        ("--format=json", "list", "sink-inputs"): '[{"index":19,"sink":2,"owner_module":7,"properties":{"application.process.id":"2468"}}]',
        ("list", "short", "modules"): "",
    }

    class Result:
        returncode = 0

        def __init__(self, stdout):
            self.stdout = stdout

    calls = []

    def run(command, **kwargs):
        calls.append(command[1:])
        return Result(outputs[tuple(command[1:])])

    target = {
        "monitor_stream": 19,
        "device": "rt5616.monitor",
        "pa_sink": "rt5616",
        "pa_sink_index": 2,
        "pa_monitor_source": "rt5616.monitor",
        "pa_owner_pid": 2468,
    }

    assert validate_pulse_target(target, run=run)
    target["device"] = "other.monitor"
    assert not validate_pulse_target(target, run=run)


def test_capture_closed_during_spawn_reaps_late_process(monkeypatch):
    from threading import Event, Thread

    spawning, allow_spawn, joining = Event(), Event(), Event()
    process = _Process([])
    process.returncode = None

    def popen(*args, **kwargs):
        spawning.set()
        assert allow_spawn.wait(2)
        return process

    capture = ParecCapture(device="sink.monitor", monitor_stream=5, popen=popen).start()
    assert spawning.wait(2)
    join = capture._thread.join

    def observed_join(*args, **kwargs):
        joining.set()
        join(*args, **kwargs)

    monkeypatch.setattr(capture._thread, "join", observed_join)
    closer = Thread(target=capture.close)
    closer.start()
    try:
        assert joining.wait(2)
    finally:
        allow_spawn.set()
        closer.join(3)
    assert not closer.is_alive()
    assert process.poll() is not None
    assert process.stdout.closed and process.stderr.closed
