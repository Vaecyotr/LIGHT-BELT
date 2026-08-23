"""Benchmark Phase 38 Show modulation over the current 9-strip/200-group shape."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, EffectContext
from light_engine.show import (
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    EffectSpec,
    ParameterModulationBindingSpec,
    ParameterModulationSpec,
    ShowDefinition,
    ShowRuntime,
    TargetResolver,
    TargetSelector,
    black_base_frame,
)


COUNTS = (40, 10, 20, 40, 40, 10, 20, 10, 10)
FRAMES = 600
FPS = 60.0


def main() -> None:
    strips = tuple(
        ZoneDef(id=f"strip_{index}", pixel_count=count)
        for index, count in enumerate(COUNTS, start=1)
    )
    cue = Cue(
        id="phase38-benchmark",
        start=0.0,
        end=20.0,
        target=TargetSelector("digital_set", ids=tuple(strip.id for strip in strips)),
        effect=EffectSpec(
            "fixed",
            id="coherent_noise_field",
            params={"contrast": 1.0},
        ),
        audio_modulation=AudioModulationSpec(
            intensity=AudioModulationChannelSpec(
                source="audio.rms",
                amount=0.25,
                min_multiplier=0.75,
                max_multiplier=1.25,
                smoothing_seconds=0.1,
            )
        ),
        parameter_modulation=ParameterModulationSpec(
            (
                ParameterModulationBindingSpec(
                    target="contrast",
                    mode="modulate",
                    source="audio.bass",
                    output_min=0.8,
                    output_max=1.5,
                    smoothing_seconds=0.1,
                ),
            )
        ),
    )
    runtime = ShowRuntime(
        ShowDefinition(2, "phase38-benchmark", 20.0, (cue,)),
        TargetResolver((), strips),
    )
    started = perf_counter()
    for index in range(FRAMES):
        timestamp = index / FPS
        level = 0.5 + 0.5 * math.sin(timestamp * 3.0)
        audio = AudioFeatures(
            timestamp=timestamp,
            loudness=level,
            spectrum=(level,) * 16,
            silence=False,
        )
        context = EffectContext(
            timestamp=timestamp,
            delta_time=1.0 / FPS,
            sequence=index,
            audio_features=audio,
        )
        base = black_base_frame(
            timestamp=timestamp,
            sequence=index,
            analog_zones=(),
            digital_strips=strips,
        )
        runtime.render(context, base)
    elapsed = perf_counter() - started
    print(json.dumps({
        "frames": FRAMES,
        "strips": len(strips),
        "groups": sum(COUNTS),
        "elapsed_seconds": round(elapsed, 6),
        "frames_per_second": round(FRAMES / elapsed, 3),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
