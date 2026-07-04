"""Base effect class and effect registry."""

from __future__ import annotations

from abc import ABC, abstractmethod

from light_engine.models import EffectContext, PixelFrame


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


# Registry of all effects
_EFFECT_REGISTRY: dict[str, type[BaseEffect]] = {}


def register_effect(name: str, cls: type[BaseEffect]) -> None:
    """Register an effect class."""
    _EFFECT_REGISTRY[name] = cls


def create_effect(name: str) -> BaseEffect:
    """Create an effect by name."""
    if name not in _EFFECT_REGISTRY:
        raise KeyError(
            f"Unknown effect: {name}. Available: {list(_EFFECT_REGISTRY.keys())}"
        )
    return _EFFECT_REGISTRY[name](name)


def list_effects() -> list[str]:
    """List all registered effect names."""
    return list(_EFFECT_REGISTRY.keys())
