import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import DigitalStrip, EffectContext, MusicControlState, PixelFrame, RGBCCTColor, ZoneOutput
from light_engine.show import (
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    CueRenderJob,
    EffectSpec,
    ShowDefinition,
    ShowRuntime,
    TargetResolver,
    TargetSelector,
    black_base_frame,
)


class RecordingEffect(BaseEffect):
    def __init__(self, name: str):
        super().__init__(name)
        self.contexts: list[tuple[float, float]] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contexts.append((ctx.speed, ctx.intensity))
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(strip_id=strip["id"], pixel_count=strip["pixel_count"], pixels=[(0.4, 0.2, 0.1)] * strip["pixel_count"])
                for strip in ctx.mode_parameters["strip_defs"]
            ],
            zones=[
                ZoneOutput(zone_id=zone["id"], color=RGBCCTColor(0.4, 0.2, 0.1, 0.5, 0.8))
                for zone in ctx.mode_parameters["zone_defs"]
            ],
        )


def _channel(source: str) -> AudioModulationChannelSpec:
    return AudioModulationChannelSpec(source, 0.5, 0.5, 1.5, 0.0)


def _ctx(*, state: MusicControlState | None = None) -> EffectContext:
    return EffectContext(timestamp=1.0, delta_time=0.1, sequence=7, speed=2.0, intensity=3.0, music_control_state=state)


def test_fixed_effect_stays_fixed_while_all_channels_modulate_cue_output() -> None:
    cue = Cue(
        id="fixed-comet",
        start=0.0,
        end=10.0,
        target=TargetSelector(kind="all"),
        effect=EffectSpec(mode="fixed", name="comet"),
        audio_modulation=AudioModulationSpec(
            brightness=_channel("music.energy"),
            speed=_channel("music.beat_strength"),
            intensity=_channel("music.bass_pulse"),
        ),
    )
    effect = RecordingEffect("comet")
    resolver = TargetResolver([ZoneDef(id="zone")], [ZoneDef(id="strip", pixel_count=1)])

    job = CueRenderJob(cue, 0, resolver, effect=effect)
    contribution = job.render(
        _ctx(state=MusicControlState(timestamp=1.0, energy=1.0, beat_strength=1.0, bass_pulse=1.0))
    )
    quiet_contribution = job.render(
        _ctx(state=MusicControlState(timestamp=1.0, energy=0.0, beat_strength=0.0, bass_pulse=0.0))
    )

    assert effect.name == "comet"
    assert effect.contexts == [(3.0, 4.5), (1.0, 1.5)]
    assert contribution.digital[0].pixels == ((0.6000000000000001, 0.30000000000000004, 0.15000000000000002),)
    color = contribution.analog[0].color
    assert (color.r, color.g, color.b, color.warm_white, color.cool_white) == pytest.approx((0.6, 0.3, 0.15, 0.75, 1.0))
    assert quiet_contribution.digital[0].pixels[0] == pytest.approx((0.2, 0.1, 0.05))
    quiet_color = quiet_contribution.analog[0].color
    assert (quiet_color.r, quiet_color.g, quiet_color.b, quiet_color.warm_white, quiet_color.cool_white) == pytest.approx((0.2, 0.1, 0.05, 0.25, 0.4))


def test_no_audio_modulation_is_identical_to_disabled_modulation() -> None:
    resolver = TargetResolver([], [ZoneDef(id="strip", pixel_count=1)])
    common = dict(id="cue", start=0.0, end=10.0, target=TargetSelector(kind="digital_strip", id="strip"), effect=EffectSpec(mode="fixed", name="comet"))
    enabled = Cue(**common, audio_modulation=AudioModulationSpec(brightness=_channel("music.energy"), speed=_channel("music.beat_strength"), intensity=_channel("music.bass_pulse")))
    disabled = Cue(**common)

    enabled_output = CueRenderJob(enabled, 0, resolver, effect=RecordingEffect("comet")).render(_ctx())
    disabled_output = CueRenderJob(disabled, 0, resolver, effect=RecordingEffect("comet")).render(_ctx())

    assert enabled_output == disabled_output


def test_brightness_modulation_is_local_to_its_overlapping_cue() -> None:
    modulated = Cue(
        id="modulated",
        start=0.0,
        end=10.0,
        target=TargetSelector(kind="digital_strip", id="left"),
        effect=EffectSpec(mode="fixed", name="comet"),
        audio_modulation=AudioModulationSpec(brightness=_channel("music.energy")),
    )
    unaffected = Cue(
        id="unaffected",
        start=0.0,
        end=10.0,
        target=TargetSelector(kind="digital_strip", id="right"),
        effect=EffectSpec(mode="fixed", name="comet"),
    )
    resolver = TargetResolver([], [ZoneDef(id="left", pixel_count=1), ZoneDef(id="right", pixel_count=1)])
    runtime = ShowRuntime(ShowDefinition(1, "local", 10.0, (modulated, unaffected)), resolver, effect_factory=RecordingEffect)
    base = black_base_frame(timestamp=1.0, sequence=7, analog_zones=(), digital_strips=[ZoneDef(id="left", pixel_count=1), ZoneDef(id="right", pixel_count=1)])

    frame = runtime.render(_ctx(state=MusicControlState(timestamp=1.0, energy=1.0)), base)

    assert frame.strips[0].pixels[0] == pytest.approx((0.6, 0.3, 0.15))
    assert frame.strips[1].pixels[0] == pytest.approx((0.4, 0.2, 0.1))


def test_adaptive_selection_precedes_speed_modulation_and_stays_allowed() -> None:
    cue = Cue(
        id="adaptive",
        start=0.0,
        end=10.0,
        target=TargetSelector(kind="digital_strip", id="strip"),
        effect=EffectSpec(mode="adaptive", allowed={"silence": "calm", "energetic": "comet"}, fallback="calm"),
        audio_modulation=AudioModulationSpec(speed=_channel("music.energy")),
    )
    created: list[RecordingEffect] = []

    def factory(name: str) -> RecordingEffect:
        effect = RecordingEffect(name)
        created.append(effect)
        return effect

    job = CueRenderJob(cue, 0, TargetResolver([], [ZoneDef(id="strip", pixel_count=1)]), effect_factory=factory)
    job.render(_ctx(state=MusicControlState(timestamp=1.0, energy=0.9, spectral_motion=0.5)))

    assert [effect.name for effect in created] == ["comet"]
    assert created[0].contexts == [(1.75, 3.0)]
