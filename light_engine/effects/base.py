"""Base effect class and effect registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, Callable, Literal, Mapping as TypingMapping

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


ParameterKind = Literal[
    "float",
    "integer",
    "boolean",
    "enum",
    "rgb",
    "scalar_source",
    "color_timeline",
    "id_list",
    "object",
]
ColorSourceSupport = Literal["GLOBAL", "POSITIONAL", "EVENT", "NOT_APPLICABLE"]

_PARAMETER_KINDS = frozenset(
    {
        "float",
        "integer",
        "boolean",
        "enum",
        "rgb",
        "scalar_source",
        "color_timeline",
        "id_list",
        "object",
    }
)
_COMMON_MODULATION_OWNERS = frozenset({"brightness", "speed", "intensity"})
_COLOR_SOURCE_SUPPORT_VALUES = frozenset(
    {"GLOBAL", "POSITIONAL", "EVENT", "NOT_APPLICABLE"}
)


@dataclass(frozen=True)
class ParameterSpec:
    """Immutable internal authoring semantics for one effect parameter.

    This is deliberately registry-only metadata.  It is neither a Host API
    model nor a second source for renderer defaults: existing validators and
    renderer/config defaults remain the authority for behaviors not expressed
    here.
    """

    name: str
    kind: ParameterKind
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    unit: str | None = None
    runtime_mutable: bool = False
    modulatable: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("parameter spec name must be non-empty")
        if self.kind not in _PARAMETER_KINDS:
            raise ValueError(f"unsupported parameter kind: {self.kind!r}")
        for label, value in (("minimum", self.minimum), ("maximum", self.maximum)):
            if value is not None and not math.isfinite(value):
                raise ValueError(f"parameter spec {label} must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("parameter spec minimum cannot exceed maximum")
        if self.kind == "enum" and not self.choices:
            raise ValueError("enum parameter specs require choices")
        if self.kind != "enum" and self.choices:
            raise ValueError("only enum parameter specs may define choices")
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("parameter spec choices must be unique")
        if self.modulatable:
            if not self.runtime_mutable:
                raise ValueError("modulatable parameters must be runtime-mutable")
            if self.kind != "float":
                raise ValueError("only float parameters may be modulatable")
            if self.name in _COMMON_MODULATION_OWNERS:
                raise ValueError(
                    f"{self.name} is owned by common modulation and cannot be generic-modulatable"
                )


@dataclass(frozen=True)
class EffectRegistration:
    """Single authoring/runtime contract for one reusable effect ID."""

    id: str
    renderer: type[BaseEffect]
    factory: Callable[[str], BaseEffect]
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]]
    parameter_specs: tuple[ParameterSpec, ...]
    capability: EffectCapability
    color_source_support: ColorSourceSupport = "NOT_APPLICABLE"

    @property
    def parameter_keys(self) -> frozenset[str]:
        """Derived compatibility view; specs are the sole parameter authority."""

        return frozenset(spec.name for spec in self.parameter_specs)


# Registry of complete effect contracts. This is the only effect-ID authority.
_EFFECT_REGISTRY: dict[str, EffectRegistration] = {}


def register_effect(
    name: str,
    cls: type[BaseEffect],
    validator: Callable[[TypingMapping[str, Any]], TypingMapping[str, Any]] | None = None,
    *,
    parameter_specs: tuple[ParameterSpec, ...] = (),
    display_name: str | None = None,
    common_params: tuple[str, ...] = (),
    factory: Callable[[str], BaseEffect] | None = None,
    color_source_support: ColorSourceSupport = "NOT_APPLICABLE",
) -> None:
    """Register one complete effect contract and reject duplicate IDs."""
    if name in _EFFECT_REGISTRY:
        raise ValueError(f"Effect already registered: {name}")
    specs = tuple(parameter_specs)
    if color_source_support not in _COLOR_SOURCE_SUPPORT_VALUES:
        raise ValueError(
            f"effect {name!r} has invalid ColorSource support {color_source_support!r}"
        )
    names = tuple(spec.name for spec in specs)
    if len(set(names)) != len(names):
        raise ValueError(f"effect {name!r} has duplicate parameter spec names")
    allowed = frozenset(names)
    effect_validator = validator or (lambda values: dict(values))

    def validate(values: TypingMapping[str, Any]) -> TypingMapping[str, Any]:
        unknown = set(values) - set(allowed)
        if unknown:
            raise ValueError(f"unknown effect parameters: {sorted(unknown)}")
        for spec in specs:
            if spec.name in values:
                _validate_parameter_value(spec, values[spec.name])
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
        parameter_specs=specs,
        capability=EffectCapability(
            display_name or name.replace("_", " ").title(),
            tuple(common_params),
        ),
        color_source_support=color_source_support,
    )


def _validate_parameter_value(spec: ParameterSpec, value: Any) -> None:
    """Apply the type/range portion of the single registry contract.

    Effect-specific validators still own relational rules (for example
    ``highlight_gain >= base_gain``) and domain checks that cannot be stated by
    one spec.  This shared layer keeps their public scalar/enum boundaries from
    silently diverging from exported metadata.
    """

    if spec.kind == "float":
        if type(value) not in {int, float} or not math.isfinite(float(value)):
            raise ValueError(f"{spec.name} must be a finite number")
        number = float(value)
        if spec.minimum is not None and number < spec.minimum:
            if spec.maximum is not None:
                raise ValueError(f"{spec.name} must be in [{spec.minimum}, {spec.maximum}]")
            raise ValueError(f"{spec.name} must be >= {spec.minimum}")
        if spec.maximum is not None and number > spec.maximum:
            if spec.minimum is not None:
                raise ValueError(f"{spec.name} must be in [{spec.minimum}, {spec.maximum}]")
            raise ValueError(f"{spec.name} must be <= {spec.maximum}")
        return
    if spec.kind == "integer":
        if type(value) is not int:
            raise ValueError(f"{spec.name} must be an integer")
        if spec.minimum is not None and value < spec.minimum:
            if spec.maximum is not None:
                raise ValueError(f"{spec.name} must be in [{spec.minimum}, {spec.maximum}]")
            raise ValueError(f"{spec.name} must be >= {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            if spec.minimum is not None:
                raise ValueError(f"{spec.name} must be in [{spec.minimum}, {spec.maximum}]")
            raise ValueError(f"{spec.name} must be <= {spec.maximum}")
        return
    if spec.kind == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{spec.name} must be a boolean")
        return
    if spec.kind == "enum":
        if not isinstance(value, str) or value not in spec.choices:
            raise ValueError(f"{spec.name} must be one of {list(spec.choices)}")
        return
    if spec.kind == "rgb":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
            raise ValueError(f"{spec.name} must contain exactly 3 RGB channels")
        if any(
            type(channel) not in {int, float}
            or not math.isfinite(float(channel))
            or not 0.0 <= float(channel) <= 1.0
            for channel in value
        ):
            raise ValueError(f"{spec.name} channels must be finite numbers in [0, 1]")
        return
    if spec.kind == "scalar_source":
        # Existing Show validators deliberately treat an explicit ``null`` as
        # the same optional no-source state as an omitted field.
        if value is None:
            return
        if not isinstance(value, str):
            raise ValueError(f"{spec.name} must be a scalar source name")
        return
    if spec.kind == "color_timeline":
        if not isinstance(value, Mapping):
            raise ValueError(f"{spec.name} must be a color timeline object")
        return
    if spec.kind == "id_list":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"{spec.name} must be a list of IDs")
        return
    if spec.kind == "object" and not isinstance(value, Mapping):
        raise ValueError(f"{spec.name} must be an object")


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


def get_effect_parameter_specs(name: str) -> tuple[ParameterSpec, ...]:
    """Return authoritative internal metadata for one registered effect."""

    return get_effect_registration(name).parameter_specs


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
