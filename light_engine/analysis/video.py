"""Video analysis: color extraction, brightness, zone analysis.

Uses OpenCV and NumPy for real-time capable analysis.
Performs frame downscaling, black border handling, dominant color extraction,
zone partitioning, and temporal smoothing.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from light_engine.config import Config
from light_engine.models import VideoFeatures
from light_engine.util import ColorSmoother, safe_div

logger = logging.getLogger(__name__)


class VideoAnalyzer:
    """Real-time video feature extractor.

    Extracts average color, dominant color, zone colors, brightness,
    saturation, and scene change intensity.

    Uses configurable analysis resolution and sampling rate.
    """

    def __init__(self, config: Optional[Config] = None):
        if config is None:
            config = Config.get_instance()
        self._config = config

        # Analysis resolution (downscaled)
        size = config.get("system.video.analysis_size", [160, 90])
        self._analysis_size: Tuple[int, int] = (int(size[0]), int(size[1]))

        # Black detection
        self._black_threshold = config.get("system.video.black_threshold", 15)
        self._black_ratio_limit = config.get("system.video.black_ratio_limit", 0.95)

        # Zone grid
        grid = config.get("system.video.zone_grid", [3, 3])
        self._zone_grid: Tuple[int, int] = (int(grid[0]), int(grid[1]))

        # Scene change
        self._scene_change_threshold = config.get(
            "system.video.scene_change_threshold", 0.15
        )

        # Smoothing
        smooth = config.get("system.smoothing.color_smoothing", 0.15)
        self._color_smooth = ColorSmoother(alpha=float(smooth))
        self._brightness_smooth = ColorSmoother(alpha=float(smooth))

        # Previous frame for scene change detection
        self._prev_frame: Optional[np.ndarray] = None

    def analyze(
        self, frame: Optional[np.ndarray], timestamp: float
    ) -> VideoFeatures:
        """Analyze a video frame and return features.

        Args:
            frame: BGR frame as numpy array (uint8), or None if no frame available.
            timestamp: Current time in seconds.

        Returns:
            VideoFeatures with extracted metrics.
        """
        if frame is None:
            return VideoFeatures(
                timestamp=timestamp,
                average_rgb=(0.0, 0.0, 0.0),
                dominant_rgb=(0.0, 0.0, 0.0),
                brightness=0.0,
                saturation=0.0,
                scene_change=0.0,
            )

        # Downscale for performance
        small = cv2.resize(frame, self._analysis_size, interpolation=cv2.INTER_AREA)

        # Detect black borders (simple: check edge rows/cols)
        mask = self._black_border_mask(small)

        # Compute average color (excluding black borders and near-black pixels)
        avg_rgb = self._average_color(small, mask)

        # Compute dominant color via quantized histogram
        dom_rgb = self._dominant_color(small, mask)

        # Compute brightness
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray)) / 255.0

        # Compute saturation
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        saturation = float(np.mean(hsv[:, :, 1])) / 255.0

        # Zone colors
        zone_colors = self._zone_colors(small, mask)

        # Scene change detection
        scene_change = 0.0
        if self._prev_frame is not None:
            diff = cv2.absdiff(small, self._prev_frame)
            scene_change = float(np.mean(diff)) / 255.0
        self._prev_frame = small.copy()

        # Apply smoothing
        sr, sg, sb = self._color_smooth.update(*avg_rgb)
        dr, dg, db = self._color_smooth.update(*dom_rgb)

        return VideoFeatures(
            timestamp=timestamp,
            average_rgb=(sr, sg, sb),
            dominant_rgb=(dr, dg, db),
            zone_colors=zone_colors,
            brightness=brightness,
            saturation=saturation,
            scene_change=scene_change,
        )

    def _black_border_mask(self, frame: np.ndarray) -> np.ndarray:
        """Create a mask that excludes black borders and near-black pixels."""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Create mask: exclude pixels below black threshold
        mask = gray > self._black_threshold

        # Check top/bottom borders (5% each)
        border_h = max(1, int(h * 0.05))
        border_w = max(1, int(w * 0.05))
        # Don't exclude entire frame if mostly dark
        black_ratio = 1.0 - (np.sum(mask) / mask.size)
        if black_ratio < self._black_ratio_limit:
            # Only exclude if not a genuinely dark frame
            mask[:border_h, :] = False
            mask[-border_h:, :] = False
            mask[:, :border_w] = False
            mask[:, -border_w:] = False

        return mask

    def _average_color(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> Tuple[float, float, float]:
        """Compute average RGB color of non-masked pixels."""
        if np.sum(mask) == 0:
            return (0.0, 0.0, 0.0)
        # Convert to float [0,1]
        f = frame.astype(np.float32) / 255.0
        # BGR to RGB
        r = np.mean(f[:, :, 2][mask])
        g = np.mean(f[:, :, 1][mask])
        b = np.mean(f[:, :, 0][mask])
        return (
            float(np.clip(r, 0.0, 1.0)),
            float(np.clip(g, 0.0, 1.0)),
            float(np.clip(b, 0.0, 1.0)),
        )

    def _dominant_color(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> Tuple[float, float, float]:
        """Extract dominant color using quantized histogram.

        Uses 8 bins per channel (512 total), suitable for real-time use.
        """
        if np.sum(mask) == 0:
            return (0.0, 0.0, 0.0)

        f = frame.astype(np.float32) / 255.0
        # Quantize to 8 levels per channel
        n_bins = 8
        r_bins = np.floor(f[:, :, 2][mask] * n_bins).astype(np.int32)
        g_bins = np.floor(f[:, :, 1][mask] * n_bins).astype(np.int32)
        b_bins = np.floor(f[:, :, 0][mask] * n_bins).astype(np.int32)

        # Combine into flat index
        indices = r_bins * n_bins * n_bins + g_bins * n_bins + b_bins
        hist = np.bincount(indices, minlength=n_bins ** 3)
        dominant_idx = np.argmax(hist)

        # Decode index back to RGB
        r_bin = dominant_idx // (n_bins * n_bins)
        g_bin = (dominant_idx // n_bins) % n_bins
        b_bin = dominant_idx % n_bins

        # Return center of bin
        bin_center = (lambda x: (x + 0.5) / n_bins)
        return (
            float(bin_center(r_bin)),
            float(bin_center(g_bin)),
            float(bin_center(b_bin)),
        )

    def _zone_colors(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> dict[str, Tuple[float, float, float]]:
        """Compute average color per zone grid cell."""
        h, w = frame.shape[:2]
        cols, rows = self._zone_grid
        cell_h = max(1, h // rows)
        cell_w = max(1, w // cols)

        zones = {}
        zone_names = ["left", "center", "right", "top", "bottom"]

        # Horizontal zones (left/center/right)
        if cols >= 3:
            for ci, name in enumerate(["left", "center", "right"]):
                x1 = ci * cell_w
                x2 = (ci + 1) * cell_w if ci < cols - 1 else w
                cell = frame[:, x1:x2]
                cell_mask = mask[:, x1:x2]
                if np.sum(cell_mask) > 0:
                    f = cell.astype(np.float32) / 255.0
                    r = float(np.clip(np.mean(f[:, :, 2][cell_mask]), 0.0, 1.0))
                    g = float(np.clip(np.mean(f[:, :, 1][cell_mask]), 0.0, 1.0))
                    b = float(np.clip(np.mean(f[:, :, 0][cell_mask]), 0.0, 1.0))
                    zones[name] = (r, g, b)
                else:
                    zones[name] = (0.0, 0.0, 0.0)

        # Vertical zones (top/bottom)
        if rows >= 3:
            for ri, name in [(0, "top"), (rows - 1, "bottom")]:
                y1 = ri * cell_h
                y2 = (ri + 1) * cell_h if ri < rows - 1 else h
                cell = frame[y1:y2, :]
                cell_mask = mask[y1:y2, :]
                if np.sum(cell_mask) > 0:
                    f = cell.astype(np.float32) / 255.0
                    r = float(np.clip(np.mean(f[:, :, 2][cell_mask]), 0.0, 1.0))
                    g = float(np.clip(np.mean(f[:, :, 1][cell_mask]), 0.0, 1.0))
                    b = float(np.clip(np.mean(f[:, :, 0][cell_mask]), 0.0, 1.0))
                    zones[name] = (r, g, b)
                else:
                    zones[name] = (0.0, 0.0, 0.0)

        return zones

    def reset(self) -> None:
        """Reset internal state."""
        self._color_smooth.reset(0.0, 0.0, 0.0)
        self._brightness_smooth.reset(0.0, 0.0, 0.0)
        self._prev_frame = None
