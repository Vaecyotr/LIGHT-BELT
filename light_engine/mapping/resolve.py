"""Unified video-color resolution for effects.

All effects that use video features should call resolve_video_color()
rather than re-implementing the zone→color lookup independently.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from light_engine.models import VideoFeatures

logger = logging.getLogger(__name__)

# Allowed video_zone values
VALID_VIDEO_ZONES = frozenset({
    "left", "center", "right", "top", "bottom",
    "average", "dominant",
})

# Valid direction values
VALID_DIRECTIONS = frozenset({"forward", "reverse"})


def validate_video_zone(value: str, zone_id: str) -> str:
    """Validate a video_zone value. Returns the value or raises ValueError."""
    if value not in VALID_VIDEO_ZONES:
        raise ValueError(
            f"Zone '{zone_id}': invalid video_zone '{value}'. "
            f"Must be one of {sorted(VALID_VIDEO_ZONES)}."
        )
    return value


def validate_direction(value: str, zone_id: str) -> str:
    """Validate a direction value."""
    if value not in VALID_DIRECTIONS:
        raise ValueError(
            f"Zone '{zone_id}': invalid direction '{value}'. "
            f"Must be 'forward' or 'reverse'."
        )
    return value


def resolve_video_color(
    video_zone: str,
    video_features: Optional[VideoFeatures],
    zone_id: str = "unknown",
) -> Tuple[float, float, float]:
    """Resolve the RGB color for a given video_zone from VideoFeatures.

    Args:
        video_zone: One of left/center/right/top/bottom/average/dominant.
        video_features: Current video features (may be None).
        zone_id: Zone identifier for diagnostic messages.

    Returns:
        (r, g, b) tuple in [0, 1]. Never NaN or Inf.
        Falls back to (0.02, 0.02, 0.05) when no video data is available.
    """
    # No video features: return safe dark default
    if video_features is None:
        return (0.02, 0.02, 0.05)

    # Structural zones: look up from zone_colors dict
    if video_zone in ("left", "center", "right", "top", "bottom"):
        if video_zone in video_features.zone_colors:
            r, g, b = video_features.zone_colors[video_zone]
            return (float(r), float(g), float(b))
        else:
            # Zone missing: fall back to average with a diagnostic warning
            logger.debug(
                "video_zone='%s' not in zone_colors for zone '%s', "
                "falling back to average_rgb. Available zones: %s",
                video_zone, zone_id,
                list(video_features.zone_colors.keys()),
            )
            r, g, b = video_features.average_rgb
            return (float(r), float(g), float(b))

    # average: use the full-frame average color
    if video_zone == "average":
        r, g, b = video_features.average_rgb
        return (float(r), float(g), float(b))

    # dominant: use the full-frame dominant color
    if video_zone == "dominant":
        r, g, b = video_features.dominant_rgb
        return (float(r), float(g), float(b))

    # Should not reach here (validated upstream), but safe fallback
    logger.warning(
        "Unexpected video_zone='%s' for zone '%s', using average_rgb",
        video_zone, zone_id,
    )
    r, g, b = video_features.average_rgb
    return (float(r), float(g), float(b))
