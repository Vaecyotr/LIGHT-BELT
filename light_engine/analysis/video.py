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
from light_engine.util import ColorSmoother

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
        self._dominant_smooth = ColorSmoother(alpha=float(smooth))

        # Previous frame for scene change detection
        self._prev_frame: Optional[np.ndarray] = None
        self._prev_rgb: Optional[Tuple[float, float, float]] = None

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

        # Compute average color excluding detected black borders.
        avg_rgb = self._average_color(small, mask)

        # Compute dominant color via quantized histogram
        dom_rgb = self._dominant_color(small, mask)

        # Compute brightness
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        brightness = cv2.mean(gray, mask.view(np.uint8))[0] / 255.0

        # Compute saturation
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        saturation = cv2.mean(hsv, mask.view(np.uint8))[1] / 255.0

        # Zone colors
        zone_colors = self._zone_colors(small, mask)

        # Scene change detection
        scene_change = 0.0
        if self._prev_frame is not None:
            diff = cv2.absdiff(small, self._prev_frame)
            scene_change = float(np.mean(diff)) / 255.0
        self._prev_frame = small

        # Discard the previous hue only on a large, opposing channel change.
        # A pan with an unchanged palette can have a high pixel difference.
        if self._prev_rgb is not None and scene_change > self._scene_change_threshold:
            delta = [new - old for new, old in zip(avg_rgb, self._prev_rgb)]
            if min(delta) < -self._scene_change_threshold and max(delta) > self._scene_change_threshold:
                self._color_smooth.reset(*avg_rgb)
                self._dominant_smooth.reset(*dom_rgb)
        self._prev_rgb = avg_rgb
        sr, sg, sb = self._color_smooth.update(*avg_rgb)
        dr, dg, db = self._dominant_smooth.update(*dom_rgb)

        return VideoFeatures(
            timestamp=timestamp,
            average_rgb=(sr, sg, sb),
            dominant_rgb=(dr, dg, db),
            zone_colors=zone_colors,
            brightness=brightness,
            saturation=saturation,
            scene_change=scene_change,
            edge_profiles=self._edge_profiles(small, mask),
        )

    def _edge_profiles(self, frame, mask):
        rows = np.flatnonzero(mask.any(axis=1))
        cols = np.flatnonzero(mask.any(axis=0))
        picture = frame[rows[0]:rows[-1]+1, cols[0]:cols[-1]+1]
        h, w = picture.shape[:2]
        # An inward band includes nearby features such as a sun just below the
        # top edge. Each position is averaged independently along its depth.
        dy, dx = max(1, round(h / 6)), max(1, round(w / 8))
        bands = {"top": picture[:dy], "bottom": picture[-dy:],
                 "left": picture[:, :dx].transpose(1, 0, 2),
                 "right": picture[:, -dx:].transpose(1, 0, 2)}
        profiles = {}
        for edge, band in bands.items():
            rgb = band[:, :, ::-1].astype(np.float32) / 255
            luma = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
            weights = 0.001 + luma ** 3
            size = (min(64, band.shape[1]), 1)
            weighted = cv2.resize(rgb * weights[:, :, None], size, interpolation=cv2.INTER_AREA)
            total = cv2.resize(weights, size, interpolation=cv2.INTER_AREA)
            colors = (weighted / total[:, :, None])[0].clip(0, 1)
            profiles[edge] = tuple(map(tuple, colors.tolist()))
        return profiles

    def _black_border_mask(self, frame: np.ndarray) -> np.ndarray:
        """Exclude paired dark bars while preserving dark picture content."""
        h, w = frame.shape[:2]
        mask = np.ones((h, w), dtype=bool)

        def paired_bars(dark_lines: np.ndarray) -> tuple[int, int]:
            count = len(dark_lines)
            limit = count // 4
            start = 0
            while start < limit and dark_lines[start]:
                start += 1
            end = 0
            while end < limit and dark_lines[count - end - 1]:
                end += 1
            # A uniformly dark frame and a dark edge of the picture are ambiguous.
            if not start or not end or start == limit or end == limit:
                return 0, 0
            if abs(start - end) > max(2, int(0.2 * max(start, end))):
                return 0, 0
            return start, end

        # Dim saturated pixels (such as evening sky) can have black-level
        # luma while still carrying picture color well above the matte.
        threshold = int(self._black_threshold)
        dark = cv2.inRange(frame, (0, 0, 0), (threshold,) * 3) != 0
        top, bottom = paired_bars(np.mean(dark, axis=1) >= self._black_ratio_limit)
        if top:
            mask[:top] = False
            mask[h - bottom:] = False
        # Evaluate columns within the picture, excluding detected horizontal bars.
        left, right = paired_bars(np.mean(dark[top:h - bottom], axis=0) >= self._black_ratio_limit)
        if left:
            mask[:, :left] = False
            mask[:, w - right:] = False
        return mask

    def _average_color(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> Tuple[float, float, float]:
        """Compute average RGB color of non-masked pixels."""
        b, g, r, _ = cv2.mean(frame, mask.view(np.uint8))
        return r / 255.0, g / 255.0, b / 255.0

    def _dominant_color(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> Tuple[float, float, float]:
        """Extract dominant color using quantized histogram.

        Uses 8 bins per channel (512 total), suitable for real-time use.
        """
        bins = (frame >> 5).astype(np.uint16)
        indices = (bins[:, :, 2] << 6) | (bins[:, :, 1] << 3) | bins[:, :, 0]
        hist = np.bincount(indices[mask], minlength=512)
        dominant_idx = np.argmax(hist)

        return self._average_color(frame, mask & (indices == dominant_idx))

    def _zone_colors(
        self, frame: np.ndarray, mask: np.ndarray
    ) -> dict[str, Tuple[float, float, float]]:
        """Sample edge cells and column ``cols // 2`` for the center zone."""
        h, w = frame.shape[:2]
        cols, rows = self._zone_grid
        cell_h = max(1, h // rows)
        cell_w = max(1, w // cols)

        zones = {}
        # Horizontal zones (left/center/right)
        if cols >= 3:
            for ci, name in [(0, "left"), (cols // 2, "center"), (cols - 1, "right")]:
                x1 = ci * cell_w
                x2 = (ci + 1) * cell_w if ci < cols - 1 else w
                cell = frame[:, x1:x2]
                cell_mask = mask[:, x1:x2]
                zones[name] = self._average_color(cell, cell_mask)

        # Vertical zones (top/bottom)
        if rows >= 3:
            for ri, name in [(0, "top"), (rows - 1, "bottom")]:
                y1 = ri * cell_h
                y2 = (ri + 1) * cell_h if ri < rows - 1 else h
                cell = frame[y1:y2, :]
                cell_mask = mask[y1:y2, :]
                zones[name] = self._average_color(cell, cell_mask)

        return zones

    def reset(self) -> None:
        """Reset internal state."""
        self._color_smooth.reset(0.0, 0.0, 0.0)
        self._dominant_smooth.reset(0.0, 0.0, 0.0)
        self._prev_frame = None
        self._prev_rgb = None
