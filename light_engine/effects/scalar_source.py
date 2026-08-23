"""Bounded scalar inputs shared by native effects.

ScalarSource deliberately exposes only signals whose existing runtime model
already defines a natural ``[0, 1]`` range.  It is a small source selector,
not an expression or evaluation language.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from light_engine.models import EffectContext


_AUDIO_FIELDS = frozenset(
    {
        "audio.rms",
        "audio.loudness",
        "audio.bass",
        "audio.mid",
        "audio.treble",
        "audio.spectral_flux",
        "audio.onset",
        "audio.peak",
    }
)
_SPECTRUM_SOURCE = re.compile(r"audio\.spectrum\[(\d+)\]")


@dataclass(frozen=True)
class ScalarSource:
    """One validated normalized input selected by a stable generic name."""

    name: str

    def __post_init__(self) -> None:
        _parse_source_name(self.name)

    def sample(self, ctx: EffectContext) -> float:
        """Read one normalized sample; unavailable runtime input is zero."""

        value = self.sample_optional(ctx)
        return 0.0 if value is None else value

    def sample_optional(self, ctx: EffectContext) -> float | None:
        """Read one sample while preserving unavailable-input information."""

        kind, index = _parse_source_name(self.name)
        if kind == "cue_progress":
            return _normalized_value(
                ctx.mode_parameters.get("cue_progress", 0.0),
                self.name,
            )

        audio = ctx.audio_features
        if audio is None:
            return None
        if kind == "spectrum":
            spectrum = audio.spectrum
            if spectrum is None:
                return None
            if index is None or index >= len(spectrum):
                raise ValueError(
                    f"{self.name} is unavailable in a {len(spectrum)}-bin spectrum"
                )
            return _normalized_value(spectrum[index], self.name)
        if kind == "peak":
            peak = audio.peak
            if peak is None:
                return None
            if type(peak) is not bool:
                raise ValueError(f"{self.name} must be a bool, got {peak!r}")
            return 1.0 if peak else 0.0

        value = getattr(audio, kind)
        if value is None:
            return None
        return _normalized_value(value, self.name)


def validate_scalar_source(value: Any, *, field_name: str = "scalar source") -> str:
    """Validate an authored scalar-source name and return it unchanged."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        ScalarSource(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {exc}") from exc
    return value


def _parse_source_name(name: Any) -> tuple[str, int | None]:
    if not isinstance(name, str):
        raise ValueError("scalar source name must be a string")
    if name == "cue_progress":
        return ("cue_progress", None)
    if name in _AUDIO_FIELDS:
        return (name.removeprefix("audio."), None)
    match = _SPECTRUM_SOURCE.fullmatch(name)
    if match is not None:
        index = int(match.group(1))
        if 0 <= index < 16:
            return ("spectrum", index)
        raise ValueError("audio.spectrum index must be in [0, 15]")
    raise ValueError(f"unknown scalar source {name!r}")


def _normalized_value(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number in [0, 1], got {value!r}")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1], got {value!r}")
    return result
