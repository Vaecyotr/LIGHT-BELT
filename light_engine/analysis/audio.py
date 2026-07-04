"""Audio analysis: spectrum, RMS, frequency bands, beat/onset detection.

Uses NumPy and SciPy for core signal processing.
Avoids librosa dependency for ARM64 compatibility.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np
from scipy import signal
from scipy.fft import rfft, rfftfreq

from light_engine.config import Config
from light_engine.models import AudioFeatures
from light_engine.util import (
    AttackReleaseEnvelope,
    EMASmoother,
    RollingHistory,
    noise_gate,
    safe_div,
)

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """Real-time audio feature extractor.

    Extracts RMS energy, frequency band energy, spectral flux,
    and provides beat/onset detection.

    All time constants are configurable. Frequency bands are configurable.
    Avoids future data leakage by using only causal analysis.
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config.get_instance()
        self._config = config

        # Configurable frequency bands
        self._bass_range = config.get("system.audio.freq_bands.bass", [20, 200])
        self._mid_range = config.get("system.audio.freq_bands.mid", [200, 2000])
        self._treble_range = config.get("system.audio.freq_bands.treble", [2000, 12000])

        # Window and hop
        self._window_size = config.get("system.audio.window_size", 0.05)
        self._hop_size = config.get("system.audio.hop_size", 0.025)
        self._target_sr = config.get("system.audio.sample_rate", 44100)

        # History for dynamic normalization
        history_len = int(
            config.get("system.audio.history_duration", 3.0) / self._hop_size
        )
        self._rms_history = RollingHistory(max(10, history_len))
        self._bass_history = RollingHistory(max(10, history_len))
        self._mid_history = RollingHistory(max(10, history_len))
        self._treble_history = RollingHistory(max(10, history_len))
        self._flux_history = RollingHistory(max(10, history_len))

        # Envelope followers
        self._rms_env = AttackReleaseEnvelope(attack=0.4, release=0.15)
        self._bass_env = AttackReleaseEnvelope(attack=0.5, release=0.2)

        # Beat detection state
        self._beat_threshold = EMASmoother(0.9)
        self._beat_cooldown = 0
        self._last_spectrum: Optional[np.ndarray] = None  # typed, reset by reset()

        # Cached window function and frequency bins (not recreated per frame)
        self._window_cache: Optional[Tuple[np.ndarray, np.ndarray]] = None
        self._cached_sr: int = 0
        self._cached_n: int = 0

        # Silence threshold
        self._noise_floor = 0.001

    def _get_window_and_freqs(self, sr: int, n: int) -> Tuple[np.ndarray, np.ndarray]:
        """Get or create cached window function and frequency bins.

        Cache key includes both sample rate AND window length to handle
        variable-length input samples.
        """
        if self._window_cache is None or self._cached_sr != sr or self._cached_n != n:
            window = np.hanning(n)
            freqs = rfftfreq(n, 1.0 / sr)
            # Precompute band masks (truncate bands to Nyquist)
            nyquist = sr / 2
            bass_mask = (freqs >= self._bass_range[0]) & (freqs <= min(self._bass_range[1], nyquist - 1))
            mid_mask = (freqs >= self._mid_range[0]) & (freqs <= min(self._mid_range[1], nyquist - 1))
            treble_mask = (freqs >= self._treble_range[0]) & (freqs <= min(self._treble_range[1], nyquist - 1))
            self._window_cache = (window, freqs)
            self._cached_sr = sr
            self._cached_n = n
            # Store masks
            self._bass_mask = bass_mask
            self._mid_mask = mid_mask
            self._treble_mask = treble_mask
        return self._window_cache

    def analyze(
        self, samples: np.ndarray, timestamp: float, sample_rate: Optional[int] = None
    ) -> AudioFeatures:
        """Analyze an audio buffer and return features.

        Args:
            samples: 1D float32 array of audio samples.
            timestamp: Current time in seconds.
            sample_rate: Sample rate of provided samples. Uses config default if None.

        Returns:
            AudioFeatures with extracted metrics.
        """
        sr = sample_rate or self._target_sr
        features = AudioFeatures(timestamp=timestamp)

        # Handle edge cases
        if samples is None or len(samples) == 0 or np.all(samples == 0):
            features.silence = True
            return features

        # Remove DC offset
        samples = samples - np.mean(samples)

        # Compute RMS
        rms = float(np.sqrt(np.mean(samples ** 2)))
        rms = min(1.0, rms * 10.0)  # Scale up for typical audio levels

        # Add to history and normalize
        self._rms_history.push(rms)
        p95 = self._rms_history.percentile(95)
        rms_norm = safe_div(rms, max(0.0001, p95), 0.0)
        rms_norm = min(1.0, rms_norm)

        features.rms = rms_norm
        features.silence = rms_norm < 0.01

        # FFT for frequency analysis
        n = len(samples)
        window, freqs = self._get_window_and_freqs(sr, n)
        spectrum = np.abs(rfft(samples * window))
        power = spectrum ** 2

        # Compute band energies
        total_power = np.sum(power)
        bass_power = np.sum(power[self._bass_mask]) if hasattr(self, '_bass_mask') else 0.0
        mid_power = np.sum(power[self._mid_mask]) if hasattr(self, '_mid_mask') else 0.0
        treble_power = np.sum(power[self._treble_mask]) if hasattr(self, '_treble_mask') else 0.0

        # Normalize bands
        features.bass = safe_div(bass_power, max(0.0001, total_power), 0.0)
        features.mid = safe_div(mid_power, max(0.0001, total_power), 0.0)
        features.treble = safe_div(treble_power, max(0.0001, total_power), 0.0)

        # Spectral flux (transient detection)
        # Normalize spectrum to unit sum to avoid amplitude-driven saturation.
        spec_sum = np.sum(spectrum)
        if spec_sum > 0:
            norm_spectrum = spectrum / spec_sum
        else:
            norm_spectrum = spectrum

        if (self._last_spectrum is None
                or not isinstance(self._last_spectrum, np.ndarray)
                or self._last_spectrum.shape != norm_spectrum.shape):
            # First frame or shape changed: flux is zero, store for next frame
            flux = 0.0
            self._last_spectrum = norm_spectrum.copy()
        else:
            # Positive-only spectral difference (onset, not offset)
            diff = np.maximum(norm_spectrum - self._last_spectrum, 0.0)
            flux = float(np.sum(diff))
            flux = min(1.0, flux * 5.0)  # scale normalized flux
            self._last_spectrum = norm_spectrum.copy()

        self._flux_history.push(flux)
        flux_p95 = self._flux_history.percentile(90)
        features.spectral_flux = min(1.0, safe_div(flux, max(0.0001, flux_p95), 0.0))

        # Beat detection (simple flux-based)
        self._beat_threshold.update(flux)
        threshold = self._beat_threshold.value * 2.5
        if self._beat_cooldown > 0:
            self._beat_cooldown -= 1
        if flux > threshold and self._beat_cooldown == 0 and not features.silence:
            features.beat = True
            # ~200ms cooldown measured in analysis frames
            self._beat_cooldown = max(1, round(0.2 / self._hop_size))

        # Onset strength
        features.onset = features.spectral_flux

        # Handle invalid values
        for field in ['rms', 'bass', 'mid', 'treble', 'spectral_flux', 'onset']:
            val = getattr(features, field)
            if np.isnan(val) or np.isinf(val):
                setattr(features, field, 0.0)

        return features

    def reset(self) -> None:
        """Reset all internal state."""
        self._rms_history.clear()
        self._bass_history.clear()
        self._mid_history.clear()
        self._treble_history.clear()
        self._flux_history.clear()
        self._rms_env.reset(0.0)
        self._bass_env.reset(0.0)
        self._beat_cooldown = 0
        self._last_spectrum = None
        self._window_cache = None
        self._cached_sr = 0
        self._cached_n = 0
