"""Strict versioned show schema loader."""

from light_engine.show.compositor import (
    AnalogContribution,
    CueRenderJob,
    DigitalContribution,
    FrameContribution,
    ResolvedTarget,
    ShowRuntime,
    TargetResolver,
    black_base_frame,
    compose_frame,
    frame_to_contribution,
    make_scoped_context,
)
from light_engine.show.loader import (
    ShowValidationError,
    TargetCatalog,
    load_show,
    validate_show_data,
)
from light_engine.show.models import (
    AudioControlSpec,
    Cue,
    EffectSpec,
    ShowDefinition,
    TargetSelector,
    TransitionSpec,
)

__all__ = [
    "AnalogContribution",
    "AudioControlSpec",
    "Cue",
    "CueRenderJob",
    "DigitalContribution",
    "EffectSpec",
    "FrameContribution",
    "ResolvedTarget",
    "ShowRuntime",
    "ShowDefinition",
    "ShowValidationError",
    "TargetCatalog",
    "TargetResolver",
    "TargetSelector",
    "TransitionSpec",
    "black_base_frame",
    "compose_frame",
    "frame_to_contribution",
    "load_show",
    "make_scoped_context",
    "validate_show_data",
]
