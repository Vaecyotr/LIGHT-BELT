"""Base effect class and effect registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Callable, Mapping as TypingMapping

from light_engine.motion import MotionInterval, constant_speed_motion_interval
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


class BaseEffect(ABC):
    """Abstract base class for all lighting effects."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def process(self, ctx: EffectContext) -> PixelFrame:
        """Process a single frame of this effect."""
        ...

    def reset(self) -> None:
        """Reset effect state (called on mode switch)."""
        pass

    def get_parameters(self) -> dict:
        """Get current effect parameters for display."""
        return {"name": self.name}


@dataclass(frozen=True)
class EffectCapability:
    """Stable capability metadata for one reusable effect ID."""

    display_name: str
    common_params: tuple[str, ...] = ()

    @property
    def common_controls(self) -> frozenset[str]:
        return frozenset(self.common_params) & frozenset({"speed", "intensity"})


@dataclass(frozen=True)
class EffectRegistration:
    """Single authoring/runtime contract for one reusable effect ID."""

    id: str
    renderer: type[BaseEffect]
    factory: Callable[[str], BaseEffect]
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]]
    parameter_keys: frozenset[str]
    capability: EffectCapability


# Registry of complete effect contracts. This is the only effect-ID authority.
_EFFECT_REGISTRY: dict[str, EffectRegistration] = {}


def register_effect(
    name: str,
    cls: type[BaseEffect],
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]] | None = None,
    *,
    parameter_keys: frozenset[str] = frozenset(),
    display_name: str | None = None,
    common_params: tuple[str, ...] = (),
    factory: Callable[[str], BaseEffect] | None = None,
) -> None:
    """Register one complete effect contract and reject duplicate IDs."""
    if name in _EFFECT_REGISTRY:
        raise ValueError(f"Effect already registered: {name}")
    allowed = frozenset(parameter_keys)
    effect_validator = validator or (lambda values: dict(values))

    def validate(values: TypingMapping[str, Any]) -> TypingMapping[str, Any]:
        unknown = set(values) - set(allowed)
        if unknown:
            raise ValueError(f"unknown effect parameters: {sorted(unknown)}")
        validated = dict(effect_validator(values))
        unexpected = set(validated) - set(allowed)
        if unexpected:
            raise ValueError(
                f"effect validator returned unknown parameters: {sorted(unexpected)}"
            )
        return validated

    _EFFECT_REGISTRY[name] = EffectRegistration(
        id=name,
        renderer=cls,
        factory=factory or cls,
        validator=validate,
        parameter_keys=allowed,
        capability=EffectCapability(
            display_name or name.replace("_", " ").title(),
            tuple(common_params),
        ),
    )


def create_effect(name: str) -> BaseEffect:
    """Create an effect by name."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(
            f"Unknown effect: {name}. Available: {list(_EFFECT_REGISTRY.keys())}"
        )
    return _EFFECT_REGISTRY[name].factory(name)


def list_effects() -> list[str]:
    """List all registered effect names."""
    return list(_EFFECT_REGISTRY.keys())


def list_effect_registrations() -> tuple[EffectRegistration, ...]:
    """Return complete effect contracts in stable registration order."""
    return tuple(_EFFECT_REGISTRY.values())


def get_effect_registration(name: str) -> EffectRegistration:
    """Return the complete registered contract for an effect ID."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(f"Unknown effect: {name}")
    return _EFFECT_REGISTRY[name]


def validate_effect_params(name: str, values: TypingMapping[str, Any]) -> TypingMapping[str, Any]:
    return get_effect_registration(name).validator(values)


def get_effect_parameter_keys(name: str) -> frozenset[str]:
    """Return registered authored-show parameter keys for an effect."""
    return get_effect_registration(name).parameter_keys


def apply_common_intensity(frame: PixelFrame, intensity: float) -> PixelFrame:
    """Apply cue-local effect intensity without touching global brightness.

    Renderers whose own algorithm does not consume ``EffectContext.intensity``
    use this helper exactly once.  ``OutputTransform`` remains the sole owner
    of global output brightness.
    """
    if intensity == 1.0:
        return frame

    def scaled(channel: float) -> float:
        return max(0.0, min(1.0, channel * intensity))

    return PixelFrame(
        timestamp=frame.timestamp,
        sequence=frame.sequence,
        strips=[
            DigitalStrip(
                strip_id=strip.strip_id,
                pixel_count=strip.pixel_count,
                pixels=[tuple(scaled(channel) for channel in pixel) for pixel in strip.pixels],
            )
            for strip in frame.strips
        ],
        zones=[
            ZoneOutput(
                zone_id=zone.zone_id,
                color=RGBCCTColor(
                    r=scaled(zone.color.r),
                    g=scaled(zone.color.g),
                    b=scaled(zone.color.b),
                    warm_white=scaled(zone.color.warm_white),
                    cool_white=scaled(zone.color.cool_white),
                ),
            )
            for zone in frame.zones
        ],
        metadata=dict(frame.metadata),
    )


def runtime_param(ctx: EffectContext, key: str, default: Any) -> Any:
    """Return a cue-authored runtime parameter, falling back to effect defaults."""

    return ctx.mode_parameters.get(key, default)


def runtime_float(ctx: EffectContext, key: str, default: float) -> float:
    return float(runtime_param(ctx, key, default))


def runtime_int(ctx: EffectContext, key: str, default: int) -> int:
    return int(runtime_param(ctx, key, default))


def runtime_str(ctx: EffectContext, key: str, default: str) -> str:
    return str(runtime_param(ctx, key, default))


def runtime_bool(ctx: EffectContext, key: str, default: bool) -> bool:
    return bool(runtime_param(ctx, key, default))


def runtime_motion_interval(
    ctx: EffectContext,
    legacy_cue_time: float,
) -> MotionInterval:
    """Return the single internal motion contract used by moving effects.

    The Show compositor supplies a cue-scoped ``MotionInterval`` whose
    ``motion_time`` already includes the composed common speed.  Effects are
    also used directly by focused unit tests and non-Show callers.  For those
    constant-speed compatibility calls, synthesize the equivalent interval
    from cue start; dynamic callers must supply the runtime-owned interval.
    """

    if ctx.motion is not None:
        return ctx.motion
    return constant_speed_motion_interval(legacy_cue_time, ctx.speed)


def runtime_motion_time(ctx: EffectContext, legacy_cue_time: float) -> float:
    """Return current integrated motion time from the shared interval API."""

    return runtime_motion_interval(ctx, legacy_cue_time).motion_time


def runtime_rgb(
    ctx: EffectContext,
    key: str,
    default: tuple[float, float, float],
) -> tuple[float, float, float]:
    value = runtime_param(ctx, key, default)
    if isinstance(value, Mapping):
        return (float(value["r"]), float(value["g"]), float(value["b"]))
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{key} must be an RGB sequence or mapping")
    if len(value) != 3:
        raise ValueError(f"{key} must have exactly 3 RGB channels")
    return (float(value[0]), float(value[1]), float(value[2]))
