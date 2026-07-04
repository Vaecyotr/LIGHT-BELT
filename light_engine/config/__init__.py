"""Configuration loading and validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

# Default config directory relative to project root
DEFAULT_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


class ConfigError(Exception):
    """Configuration error with path, field, value, and expected info."""

    def __init__(self, path: str, field: str, value: Any, expected: str):
        self.path = path
        self.field = field
        self.value = value
        self.expected = expected
        super().__init__(
            f"Config error in {path}: field '{field}' = {value!r}, expected {expected}"
        )


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: Path) -> dict:
    """Load and parse a YAML file safely (no arbitrary code execution)."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def validate_range(
    value: float,
    field: str,
    path: str,
    min_val: float = 0.0,
    max_val: float = 1.0,
) -> float:
    """Validate a float config value is within range."""
    if not isinstance(value, (int, float)):
        raise ConfigError(path, field, value, f"number in [{min_val}, {max_val}]")
    if value < min_val or value > max_val:
        raise ConfigError(path, field, value, f"number in [{min_val}, {max_val}]")
    return float(value)


def validate_choice(value: str, field: str, path: str, choices: list[str]) -> str:
    """Validate a string config value is one of allowed choices."""
    if value not in choices:
        raise ConfigError(path, field, value, f"one of {choices}")
    return value


def validate_positive_int(value: int, field: str, path: str) -> int:
    """Validate a positive integer config value."""
    if not isinstance(value, int) or value < 0:
        raise ConfigError(path, field, value, "non-negative integer")
    return value


class Config:
    """Application configuration loaded from YAML files.

    Loads system.yaml, layout.yaml, effects.yaml, outputs.yaml.
    Supports optional overrides via environment variable LIGHT_ENGINE_CONFIG_DIR.
    """

    _instance: Optional["Config"] = None

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(
                os.environ.get("LIGHT_ENGINE_CONFIG_DIR", str(DEFAULT_CONFIG_DIR))
            )
        self.config_dir = Path(config_dir)
        self._data: dict[str, Any] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all default config files and merge."""
        files = ["system.yaml", "layout.yaml", "effects.yaml", "outputs.yaml"]
        for fname in files:
            fpath = self.config_dir / fname
            if fpath.exists():
                loaded = load_yaml(fpath)
                self._data = _deep_merge(self._data, loaded)

    @classmethod
    def get_instance(cls, config_dir: Optional[Path] = None) -> "Config":
        """Get or create singleton config instance."""
        if cls._instance is None or config_dir is not None:
            cls._instance = cls(config_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton for testing."""
        cls._instance = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value by dotted key path."""
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def get_or_raise(self, key: str) -> Any:
        """Get a config value, raising if missing."""
        value = self.get(key, _SENTINEL)
        if value is _SENTINEL:
            raise KeyError(f"Required config key not found: {key}")
        return value

    def to_dict(self) -> dict:
        """Return full config as dict."""
        return self._data.copy()


_SENTINEL = object()
