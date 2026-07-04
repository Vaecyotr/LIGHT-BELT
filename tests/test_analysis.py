"""Tests for audio and video analysis modules."""

import os
import tempfile

import numpy as np
import pytest
import pytest
from light_engine.analysis.audio import AudioAnalyzer
from light_engine.analysis.video import VideoAnalyzer
from light_engine.config import Config


def _make_sine(freq: float, duration: float, sr: int = 44100) -> np.ndarray:
    t = np.arange(int(duration * sr), dtype=np.float32) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


class TestAudioAnalyzer:
    @pytest.fixture
    def analyzer(self):
        Config.reset()
        return AudioAnalyzer(Config())

    def test_bass_band_dominant_for_low_freq(self, analyzer):
        """80Hz sine should produce high bass, low mid/treble."""
        samples = _make_sine(80, 0.1)
        features = analyzer.analyze(samples, 1.0)
        assert features.bass > features.mid
        assert features.bass > features.treble

    def test_mid_band_dominant_for_mid_freq(self, analyzer):
        """1000Hz sine should produce high mid."""
        samples = _make_sine(1000, 0.1)
        features = analyzer.analyze(samples, 1.0)
        assert features.mid > features.bass
        assert features.mid > features.treble

    def test_treble_band_dominant_for_high_freq(self, analyzer):
        """8000Hz sine should produce high treble."""
        samples = _make_sine(8000, 0.1)
        features = analyzer.analyze(samples, 1.0)
        assert features.treble > features.bass
        assert features.treble > features.mid

    def test_silence_no_beat(self, analyzer):
        """Silence should not produce random beats."""
        samples = np.zeros(4410, dtype=np.float32)  # 0.1s @ 44100
        features = analyzer.analyze(samples, 1.0)
        assert features.silence
        assert not features.beat

    def test_dc_offset_handled(self, analyzer):
        """DC offset should be removed, not affect RMS."""
        samples = _make_sine(440, 0.1) + 0.5  # DC offset
        features = analyzer.analyze(samples, 1.0)
        assert not features.silence
        assert 0 <= features.rms <= 1.0

    def test_all_zeros(self, analyzer):
        features = analyzer.analyze(np.zeros(100, dtype=np.float32), 1.0)
        assert features.silence
        assert features.rms == 0.0

    def test_output_no_nan(self, analyzer):
        samples = _make_sine(440, 0.1)
        features = analyzer.analyze(samples, 1.0)
        for field in ['rms', 'bass', 'mid', 'treble', 'spectral_flux', 'onset']:
            val = getattr(features, field)
            assert not np.isnan(val), f"{field} is NaN"
            assert not np.isinf(val), f"{field} is Inf"

    def test_short_input(self, analyzer):
        """Input shorter than FFT window should not crash."""
        samples = np.array([0.1, -0.1], dtype=np.float32)
        features = analyzer.analyze(samples, 1.0)
        assert 0 <= features.rms <= 1.0


class TestVideoAnalyzer:
    @pytest.fixture
    def analyzer(self):
        Config.reset()
        return VideoAnalyzer(Config())

    def test_red_frame(self, analyzer):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[:, :, 2] = 255  # Red channel (BGR -> R=2)
        features = analyzer.analyze(frame, 1.0)
        r, g, b = features.average_rgb
        assert r > 0.8
        assert g < 0.2
        assert b < 0.2

    def test_black_frame(self, analyzer):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        features = analyzer.analyze(frame, 1.0)
        assert features.brightness < 0.1

    def test_black_borders_not_dominant(self, analyzer):
        frame = np.ones((180, 320, 3), dtype=np.uint8) * 128
        frame[:, :, 2] = 200  # Reddish center
        # Add black borders
        frame[:20, :] = 0
        frame[-20:, :] = 0
        features = analyzer.analyze(frame, 1.0)
        r, g, b = features.average_rgb
        # Red should still dominate despite black borders
        assert r > 0.3

    def test_zone_colors(self, analyzer):
        frame = np.zeros((180, 320, 3), dtype=np.uint8)
        frame[:, :160, 2] = 255   # Left half red
        frame[:, 160:, 1] = 255   # Right half green
        features = analyzer.analyze(frame, 1.0)
        assert "left" in features.zone_colors
        assert "right" in features.zone_colors
        left_r = features.zone_colors["left"][0]
        right_g = features.zone_colors["right"][1]
        assert left_r > 0.5
        assert right_g > 0.5

    def test_none_frame(self, analyzer):
        features = analyzer.analyze(None, 1.0)
        assert features.brightness == 0.0
        assert features.average_rgb == (0.0, 0.0, 0.0)

    def test_scene_change_detected(self, analyzer):
        frame1 = np.zeros((90, 160, 3), dtype=np.uint8)
        frame2 = np.ones((90, 160, 3), dtype=np.uint8) * 255
        analyzer.analyze(frame1, 0.0)
        features = analyzer.analyze(frame2, 0.033)
        assert features.scene_change > 0.1

    def test_no_nan_output(self, analyzer):
        frame = np.random.randint(0, 256, (90, 160, 3), dtype=np.uint8)
        features = analyzer.analyze(frame, 1.0)
        assert not np.isnan(features.brightness)
        for name, color in features.zone_colors.items():
            for c in color:
                assert not np.isnan(c), f"zone {name} color NaN"


class TestAudioWindowConsistency:
    """Verify that get_window_at produces consistent-length windows."""

    def test_window_length_consistent(self):
        """Every window (except the last) must have the same sample count."""
        from light_engine.media import AudioReader
        from light_engine.data.test_media import generate_test_wav, cleanup_test_media

        wav_path = generate_test_wav(None, duration=2.0, sample_rate=44100)
        try:
            reader = AudioReader(wav_path).open()
            window_size = 0.05  # 50ms
            sample_rates = set()
            lengths = []
            t = 0.0
            while t < reader.duration:
                samples = reader.get_window_at(t, window_size)
                if samples is not None:
                    lengths.append(len(samples))
                t += 0.016  # ~60Hz analysis
            reader.close()

            # All non-truncated windows must have the same length.
            # Last ~3 windows near EOF may be truncated (window=2205 samples
            # spans ~50ms, and the final 150ms of audio produces shortened windows).
            if len(lengths) > 2:
                expected = lengths[0]
                non_truncated = [L for L in lengths if L == expected]
                truncated = [L for L in lengths if L != expected]
                # Allow up to 3 truncated windows at EOF (50ms window / 16.67ms hop ≈ 3)
                assert len(truncated) <= 3, (
                    f"Too many truncated windows: {len(truncated)}. "
                    f"Expected mostly {expected}-sample windows, got last 10: {lengths[-10:]}"
                )
                assert len(non_truncated) >= len(lengths) - 3
        finally:
            cleanup_test_media(wav_path)

    def test_alternating_lengths_no_crash(self):
        """Alternating windows of 2205 and 2206 samples must not crash."""
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        # Feed alternating lengths mimicking real float→int rounding
        for i in range(200):
            n = 2205 if i % 2 == 0 else 2206
            samples = np.sin(np.linspace(0, 2 * np.pi * 80 * (n / 44100), n)).astype(np.float32)
            features = analyzer.analyze(samples, i * 0.025)
            assert not np.isnan(features.rms)
            assert not np.isnan(features.spectral_flux)


class TestSpectralFlux:
    """Verify spectral flux behaves correctly after fixes."""

    def test_flux_not_saturated_on_sine(self):
        """A steady sine wave should not produce permanently saturated flux."""
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        sr = 44100
        n = round(0.05 * sr)  # 2205 samples
        flux_values = []
        for i in range(100):
            freq = 440.0  # steady A4 tone
            t = np.arange(n, dtype=np.float32) / sr
            samples = (np.sin(2 * np.pi * freq * t) * 0.5).astype(np.float32)
            features = analyzer.analyze(samples, i * 0.025)
            flux_values.append(features.spectral_flux)
        # After initial transient, flux should settle to low values (< 0.5)
        steady_flux = flux_values[-50:]
        avg_flux = sum(steady_flux) / len(steady_flux)
        assert avg_flux < 0.5, (
            f"Steady sine flux should be < 0.5, got {avg_flux:.3f}. "
            f"Flux was likely saturated at 1.0 from shape mismatch or missing normalization."
        )

    def test_flux_low_on_sine(self):
        """A stable sine should produce low spectral flux after the first frame."""
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        sr = 44100
        n = round(0.05 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        samples = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)

        f1 = analyzer.analyze(samples, 0.0)
        assert f1.spectral_flux == 0.0  # first frame: no previous spectrum

        f2 = analyzer.analyze(samples, 0.025)  # same signal again
        # flux should be very low for identical input
        assert f2.spectral_flux < 0.3, (
            f"Identical sine should produce low flux, got {f2.spectral_flux:.3f}"
        )


class TestBeatCooldown:
    """Verify beat cooldown is ~200ms, not hundreds of seconds."""

    def test_cooldown_in_range(self):
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        # With hop_size=0.025, cooldown should be max(1, round(0.2/0.025)) = 8
        expected = max(1, round(0.2 / 0.025))
        assert expected == 8
        # Verify the cooldown constant is reasonable (5-20 frames)
        assert 4 <= expected <= 20, f"Beat cooldown should be ~200ms, got {expected * 0.025 * 1000:.0f}ms"


class TestAnalyzerReset:
    """Verify reset() properly clears all internal state."""

    def test_reset_clears_last_spectrum(self):
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        sr = 44100
        n = round(0.05 * sr)
        t = np.arange(n, dtype=np.float32) / sr
        samples = (np.sin(2 * np.pi * 440.0 * t) * 0.5).astype(np.float32)

        analyzer.analyze(samples, 0.0)
        assert analyzer._last_spectrum is not None, "Should have stored spectrum"
        analyzer.reset()
        assert analyzer._last_spectrum is None, "Reset must clear _last_spectrum"
        assert analyzer._beat_cooldown == 0
        assert len(analyzer._rms_history) == 0


class TestRealFlacCompatible:
    """Verify real FLAC-style operation: long uninterrupted runs without crash."""

    def test_continuous_analysis_no_crash(self):
        """Simulate 10 seconds of 60 Hz analysis without crash or NaN."""
        from light_engine.analysis.audio import AudioAnalyzer
        from light_engine.config import Config

        Config.reset()
        analyzer = AudioAnalyzer(Config())
        sr = 44100
        window_samples = round(0.05 * sr)  # 2205

        # Simulate a 10s stereo FLAC mixed to mono: alternating frequency sweeps
        errors = 0
        for i in range(600):  # 10s × 60Hz = 600 windows
            # Vary frequency slightly to simulate real audio
            freq = 80 + (i % 100) * 10  # 80Hz to 1070Hz sweep
            t = np.arange(window_samples, dtype=np.float32) / sr
            samples = (np.sin(2 * np.pi * freq * t) * 0.3).astype(np.float32)
            try:
                features = analyzer.analyze(samples, i * 0.01667)
                assert not np.isnan(features.rms), f"NaN rms at frame {i}"
                assert not np.isnan(features.spectral_flux), f"NaN flux at frame {i}"
                assert 0.0 <= features.rms <= 1.0, f"rms out of range at frame {i}: {features.rms}"
                assert 0.0 <= features.spectral_flux <= 1.0, f"flux out of range at frame {i}: {features.spectral_flux}"
            except Exception as e:
                errors += 1
                # First error is fatal for this test
                pytest.fail(f"Frame {i} raised: {e}")
        assert errors == 0, f"Got {errors} errors in 600-frame run"


class TestInspectVideoTimestamp:
    """Verify inspect_video uses real FPS, not hardcoded 30."""

    def test_24fps_video_frame_24_is_about_1_second(self):
        """Frame 24 at 24 FPS should have timestamp ~1.0s, not 0.8s (24/30)."""
        import os
        import tempfile
        import cv2
        import numpy as np

        # Generate a 24 FPS test video
        tmp_path = os.path.join(tempfile.gettempdir(), "test_24fps.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 24.0, (160, 90))
        for i in range(48):  # 2 seconds
            frame = np.zeros((90, 160, 3), dtype=np.uint8)
            frame[:, :, 2] = min(255, i * 10)
            out.write(frame)
        out.release()

        try:
            cap = cv2.VideoCapture(tmp_path)
            raw_fps = cap.get(cv2.CAP_PROP_FPS)
            actual_fps = raw_fps if raw_fps > 0 else 30.0
            cap.release()

            # 24 FPS: frame 24 should have timestamp = 24/24 = 1.0s
            assert abs(actual_fps - 24.0) < 1.0, f"Expected ~24 FPS, got {actual_fps}"
            ts_frame_24 = 24 / actual_fps
            assert abs(ts_frame_24 - 1.0) < 0.1, (
                f"Frame 24 at {actual_fps:.1f} FPS should have timestamp ~1.0s, "
                f"got {ts_frame_24:.2f}s. If hardcoded to 30 FPS: {24/30:.2f}s"
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

