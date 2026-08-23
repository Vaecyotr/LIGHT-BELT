"""Safe explicit cue-local modulation of approved effect parameters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from light_engine.effects import get_effect_registration
from light_engine.effects.scalar_source import ScalarSource
from light_engine.models import EffectContext
from light_engine.show.models import ParameterModulationBindingSpec, ParameterModulationSpec


RAW_AUDIO_SOURCES = frozenset(
    {
        "audio.raw_level",
        "audio.dominant_frequency",
        "audio.dominant_magnitude",
    }
)


@dataclass(frozen=True)
class ParameterModulationResult:
    """Validated final runtime parameters for one render."""

    values: Mapping[str, object]


class CueParameterModulator:
    """Apply one cue's bindings while retaining deterministic smoothing state."""

    def __init__(
        self,
        effect_id: str,
        authored_params: Mapping[str, object],
        spec: ParameterModulationSpec | None,
    ) -> None:
        self._effect_id = effect_id
        self._authored_params = dict(authored_params)
        self._spec = spec
        self._previous: dict[str, float] = {}
        if spec is not None:
            registration = get_effect_registration(effect_id)
            parameter_specs = {item.name: item for item in registration.parameter_specs}
            seen: set[str] = set()
            if not spec.bindings:
                raise ValueError("parameter modulation requires at least one binding")
            for binding in spec.bindings:
                parameter = parameter_specs.get(binding.target)
                if binding.target in {"brightness", "speed", "intensity"}:
                    raise ValueError(
                        f"parameter modulation cannot target common {binding.target}"
                    )
                if parameter is None or not (
                    parameter.kind == "float"
                    and parameter.runtime_mutable
                    and parameter.modulatable
                ):
                    raise ValueError(
                        f"parameter modulation target {binding.target!r} is not approved"
                    )
                if binding.target in seen:
                    raise ValueError(
                        f"duplicate parameter modulation target {binding.target!r}"
                    )
                seen.add(binding.target)
                if binding.mode not in {"modulate", "drive"}:
                    raise ValueError(f"unknown parameter modulation mode {binding.mode!r}")
                if binding.mode == "modulate" and binding.target not in self._authored_params:
                    raise ValueError(
                        f"modulate target {binding.target!r} requires authored base"
                    )

    def reset(self) -> None:
        self._previous.clear()

    def apply(self, ctx: EffectContext, params: Mapping[str, object]) -> ParameterModulationResult:
        if self._spec is None:
            return ParameterModulationResult(params)
        final = dict(params)
        for binding in self._spec.bindings:
            source = _sample_source(binding, ctx)
            if source is None:
                if binding.mode == "modulate" and binding.fallback is None:
                    self._previous.pop(binding.target, None)
                    final[binding.target] = self._authored_params[binding.target]
                    continue
                mapped = binding.fallback
                if mapped is None:  # Loader validation makes this unreachable.
                    raise ValueError(
                        f"parameter modulation {binding.target!r} requires fallback"
                    )
            else:
                mapped = binding.output_min + (
                    binding.output_max - binding.output_min
                ) * source
            smoothed = self._smooth(binding, float(mapped), ctx.delta_time)
            if binding.mode == "modulate":
                final[binding.target] = float(self._authored_params[binding.target]) * smoothed
            else:
                final[binding.target] = smoothed
        registration = get_effect_registration(self._effect_id)
        return ParameterModulationResult(dict(registration.validator(final)))

    def _smooth(
        self,
        binding: ParameterModulationBindingSpec,
        target: float,
        delta_time: float,
    ) -> float:
        if binding.smoothing_seconds == 0.0:
            value = target
        else:
            initial = (
                1.0
                if binding.mode == "modulate"
                else target if binding.fallback is None else float(binding.fallback)
            )
            previous = self._previous.get(binding.target, initial)
            alpha = -math.expm1(-float(delta_time) / binding.smoothing_seconds)
            value = previous + alpha * (target - previous)
        lower = min(binding.output_min, binding.output_max)
        upper = max(binding.output_min, binding.output_max)
        value = max(lower, min(upper, value))
        self._previous[binding.target] = value
        return value


def _sample_source(
    binding: ParameterModulationBindingSpec,
    ctx: EffectContext,
) -> float | None:
    if binding.source not in RAW_AUDIO_SOURCES:
        return ScalarSource(binding.source).sample_optional(ctx)
    audio = ctx.audio_features
    if audio is None:
        return None
    raw = float(getattr(audio, binding.source.removeprefix("audio.")))
    assert binding.input_min is not None and binding.input_max is not None
    normalized = (raw - binding.input_min) / (binding.input_max - binding.input_min)
    return max(0.0, min(1.0, normalized))
