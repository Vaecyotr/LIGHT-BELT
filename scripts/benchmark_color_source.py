"""Representative Phase 39 software-only ColorSource benchmark."""

from __future__ import annotations

from pathlib import Path
import sys
from time import perf_counter


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from light_engine.mapping import ZoneDef  # noqa: E402
from light_engine.models import AudioFeatures, EffectContext, VideoFeatures  # noqa: E402
from light_engine.show import (  # noqa: E402
    AudioModulationChannelSpec,
    AudioModulationSpec,
    ColorSourceKeyframe,
    ColorSourceSpec,
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


FRAMES = 600
FPS_FLOOR = 30.0
STRIP_SIZES = (40, 10, 20, 40, 40, 10, 20, 10, 10)
PALETTE = ((1.0, 0.05, 0.0), (0.0, 0.2, 1.0))


def main() -> int:
    strips = tuple(
        ZoneDef(id=f"strip_{index + 1}", pixel_count=size)
        for index, size in enumerate(STRIP_SIZES)
    )
    target = TargetSelector("digital_set", ids=tuple(strip.id for strip in strips))
    sources = (
        ColorSourceSpec(
            type="timeline",
            keyframes=(
                ColorSourceKeyframe(0.0, PALETTE[0]),
                ColorSourceKeyframe(20.0, PALETTE[1]),
            ),
        ),
        ColorSourceSpec(type="spatial_palette", palette=PALETTE),
        ColorSourceSpec(type="video_average", fallback=(0.0, 0.0, 0.0)),
        ColorSourceSpec(type="video_dominant", fallback=(0.0, 0.0, 0.0)),
        ColorSourceSpec(
            type="audio_spectrum_palette", palette=PALETTE, fallback=(0.0, 0.0, 0.0)
        ),
        ColorSourceSpec(
            type="dominant_frequency_palette",
            palette=PALETTE,
            fallback=(0.0, 0.0, 0.0),
            frequency_min_hz=80.0,
            frequency_max_hz=8000.0,
        ),
    )
    effects = ("static", "coherent_noise_field", "breath", "static", "coherent_noise_field", "calm")
    cues = []
    for index, (source, effect_id) in enumerate(zip(sources, effects)):
        combined = index == 4
        cues.append(
            Cue(
                id=f"source-{index}",
                start=0.0,
                end=20.0,
                target=target,
                effect=EffectSpec(
                    mode="fixed",
                    id=effect_id,
                    params={"contrast": 1.0} if combined else {},
                ),
                color_source=source,
                priority=index,
                audio_modulation=(
                    AudioModulationSpec(
                        brightness=AudioModulationChannelSpec(
                            source="audio.rms",
                            amount=0.25,
                            min_multiplier=0.75,
                            max_multiplier=1.25,
                            smoothing_seconds=0.10,
                        )
                    )
                    if combined
                    else None
                ),
                parameter_modulation=(
                    ParameterModulationSpec(
                        (
                            ParameterModulationBindingSpec(
                                target="contrast",
                                mode="modulate",
                                source="audio.bass",
                                output_min=0.8,
                                output_max=1.2,
                                smoothing_seconds=0.10,
                            ),
                        )
                    )
                    if combined
                    else None
                ),
            )
        )
    show = ShowDefinition(2, "phase39-benchmark", 20.0, tuple(cues))
    runtime = ShowRuntime(show, TargetResolver((), strips), seed=39)
    video = VideoFeatures(0.0, (0.1, 0.3, 0.8), (0.8, 0.2, 0.1))
    audio = AudioFeatures(
        0.0,
        loudness=0.7,
        spectrum=tuple(index / 15.0 for index in range(16)),
        dominant_frequency=440.0,
        silence=False,
    )

    started = perf_counter()
    frame = None
    for index in range(FRAMES):
        timestamp = index / 60.0
        ctx = EffectContext(
            timestamp=timestamp,
            delta_time=1 / 60,
            sequence=index + 1,
            video_features=video,
            audio_features=audio,
        )
        base = black_base_frame(
            timestamp=timestamp,
            sequence=index + 1,
            analog_zones=(),
            digital_strips=strips,
        )
        frame = runtime.render(ctx, base)
    elapsed = perf_counter() - started
    fps = FRAMES / elapsed
    assert frame is not None and sum(strip.pixel_count for strip in frame.strips) == 200
    print(
        f"phase39_color_source frames={FRAMES} strips={len(strips)} groups=200 "
        f"layers={len(cues)} combined_modulation_cues=1 "
        f"elapsed_seconds={elapsed:.6f} fps={fps:.3f}"
    )
    print("NOT HARDWARE VERIFIED; current development machine only")
    return 0 if fps > FPS_FLOOR else 1


if __name__ == "__main__":
    raise SystemExit(main())
