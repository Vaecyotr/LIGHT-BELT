"""Full-suite real-time audio duration/frame-count acceptance."""

from light_engine.config import Config
from light_engine.engine import Engine
from light_engine.outputs import NullOutput


class TestTenSecondsAudio:
    def test_ten_seconds_audio_produces_about_300_frames(self):
        from light_engine.data.test_media import generate_test_wav, cleanup_test_media
        wav_path = generate_test_wav(None, duration=10.0, sample_rate=44100)
        try:
            Config.reset()
            config = Config()
            engine = Engine(config)
            engine.load_audio(wav_path)
            engine.set_effect("spectrum")
            null = NullOutput()
            null.open()
            engine._outputs = {"null": null}
            engine.run()
            assert 295 <= engine.frame_count <= 305, f"Expected ~300 frames, got {engine.frame_count}"
        finally:
            cleanup_test_media(wav_path)
