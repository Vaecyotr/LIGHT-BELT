"""Frozen APP-facing Host API V1 compatibility vocabulary.

This module is deliberately independent from ``light_engine`` effect
registries.  Its fixed effect catalogue is the stable discovery surface
promised to released APP clients.  Target discovery remains layout-derived as
an existing V1 compatibility feature.  Request validation and command
adaptation may remain broader than the effect catalogue so an installed Host
can continue to run compatible local extensions.
"""

from __future__ import annotations

from copy import deepcopy


APP_V1_EFFECTS: tuple[dict[str, object], ...] = (
    {"effect_type": "static", "name": "Static", "params": ["color", "intensity"], "effect_params": []},
    {"effect_type": "breath", "name": "Breath", "params": ["color", "intensity"], "effect_params": ["period", "min_brightness"]},
    {"effect_type": "chase", "name": "Chase", "params": ["speed", "intensity"], "effect_params": ["width", "gap", "direction"]},
    {"effect_type": "color_wave", "name": "Color Wave", "params": ["speed", "intensity"], "effect_params": ["width"]},
    {"effect_type": "comet", "name": "Comet", "params": ["speed", "intensity"], "effect_params": ["tail_length", "decay"]},
    {"effect_type": "audio_pulse", "name": "Audio Pulse", "params": ["color", "intensity"], "effect_params": ["attack", "release"]},
    {"effect_type": "bass_pulse", "name": "Bass Pulse", "params": ["color", "intensity"], "effect_params": ["attack", "release"]},
    {"effect_type": "spectrum", "name": "Spectrum", "params": ["intensity"], "effect_params": ["bass_zones", "mid_zones", "treble_zones"]},
    {"effect_type": "video_ambient", "name": "Video Ambient", "params": ["intensity"], "effect_params": ["smoothing"]},
    {"effect_type": "video_audio_fusion", "name": "Video Audio Fusion", "params": ["intensity"], "effect_params": ["video_weight", "audio_weight"]},
    {"effect_type": "calm", "name": "Calm", "params": ["color", "intensity"], "effect_params": ["period"]},
    {"effect_type": "demo", "name": "Demo", "params": [], "effect_params": ["cycle_interval", "effects"]},
)

# ``twinkle`` is the released special-device action advertised by the
# ``starry_sky`` target.  It is part of the V1 request vocabulary even though
# it is not a general-purpose entry in the fixed effects catalogue above.
APP_V1_EFFECT_TYPES: tuple[str, ...] = tuple(
    effect["effect_type"] for effect in APP_V1_EFFECTS
) + ("twinkle",)

APP_V1_WS_MESSAGE_TYPES: tuple[str, ...] = (
    "session.connected",
    "runtime.state",
    "playback.progress",
    "device.status",
    "error.event",
    "heartbeat",
    "scene.applied",
)

APP_V1_SUPPORTS: dict[str, bool] = {
    "playback": True,
    "resume": True,
    "seek": True,
    "lights": True,
    "effects": True,
    "color_temperature": True,
    "transitions": True,
    "websocket": True,
    "audio": True,
    "scenes": True,
    "brightness_scale": True,
}

_PUBLIC_TARGET_FIELDS = ("target_id", "name", "supported_effects")


def _public_target(target: dict) -> dict:
    """Keep layout discovery, but never serialize physical target metadata."""
    return {
        field: deepcopy(target[field])
        for field in _PUBLIC_TARGET_FIELDS
        if field in target
    }


def capabilities(targets: list[dict]) -> dict[str, object]:
    """Return a fresh APP V1 document with layout-derived target discovery.

    Target discovery is an existing V1 compatibility feature.  Effect metadata
    is different: it is a frozen public catalogue, never a reflection of the
    live engine Registry.
    """
    return {
        "targets": [_public_target(target) for target in targets],
        "effects": deepcopy(list(APP_V1_EFFECTS)),
        "websocket": {"message_types": list(APP_V1_WS_MESSAGE_TYPES)},
        "supports": deepcopy(APP_V1_SUPPORTS),
    }
