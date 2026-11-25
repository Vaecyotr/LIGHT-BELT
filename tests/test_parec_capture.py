from io import BytesIO

import numpy as np

from light_engine.analysis.pulse_capture import ParecCapture


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
