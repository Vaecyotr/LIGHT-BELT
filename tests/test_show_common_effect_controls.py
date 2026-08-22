"""Show v2 authored common effect controls and composition contracts."""

from __future__ import annotations

import pytest

from light_engine.effects.base import BaseEffect
from light_engine.mapping import ZoneDef
from light_engine.models import AudioFeatures, DigitalStrip, EffectContext, PixelFrame
from light_engine.show import (
    AudioModulationChannelSpec,
    AudioModulationSpec,
    Cue,
    CueRenderJob,
    EffectSpec,
    ShowValidationError,
    TargetCatalog,
    TargetResolver,
    TargetSelector,
    validate_show_data,
)


def _show_data(effect: dict) -> dict:
    return {
        "schema_version": 2,
        "show": {
            "id": "common-controls",
            "duration": 2.0,
            "cues": [
                {
                    "id": "cue",
                    "start": 0.0,
                    "end": 2.0,
                    "target": {"type": "digital_strip", "id": "strip_11"},
                    "effect": effect,
                }
            ],
        },
    }


def _catalog() -> TargetCatalog:
    return TargetCatalog(digital_strips={"strip_11"})


def test_v2_common_controls_default_to_one_for_old_show_shapes() -> None:
    show = validate_show_data(
        _show_data({"mode": "fixed", "id": "static", "params": {}}),
        _catalog(),
    )

    assert show.cues[0].effect.speed == 1.0
    assert show.cues[0].effect.intensity == 1.0


def test_v2_common_speed_coexists_with_effect_specific_params_speed() -> None:
    show = validate_show_data(
        _show_data(
            {
                "mode": "fixed",
                "id": "chase",
                "speed": 0.5,
                "intensity": 0.75,
                "params": {"speed": 7.0, "width": 2},
            }
        ),
        _catalog(),
    )
    effect = show.cues[0].effect

    assert effect.speed == 0.5
    assert effect.intensity == 0.75
    assert effect.params["speed"] == 7.0


def test_v2_adaptive_effect_accepts_common_controls() -> None:
    show = validate_show_data(
        _show_data(
            {
                "mode": "adaptive",
                "speed": 1.25,
                "intensity": 0.8,
                "allowed": {"silence": "static"},
                "fallback": "static",
            }
        ),
        _catalog(),
    )

    assert show.cues[0].effect.speed == 1.25
    assert show.cues[0].effect.intensity == 0.8


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("speed", -0.01, ">= 0.0"),
        ("speed", float("nan"), "finite"),
        ("intensity", float("inf"), "finite"),
    ],
)
def test_v2_common_controls_reject_negative_or_nonfinite_values(
    field: str,
    value: float,
    reason: str,
) -> None:
    data = _show_data({"mode": "fixed", "id": "static", "params": {}})
    data["show"]["cues"][0]["effect"][field] = value

    with pytest.raises(ShowValidationError) as exc:
        validate_show_data(data, _catalog())

    assert exc.value.path == f"show.cues[0].effect.{field}"
    assert reason in exc.value.reason


def test_v1_does_not_retroactively_accept_v2_common_controls() -> None:
    data = _show_data(
        {
            "mode": "fixed",
            "name": "static",
            "parameters": {},
            "speed": 0.5,
        }
    )
    data["schema_version"] = 1

    with pytest.raises(ShowValidationError) as exc:
        validate_show_data(data, _catalog())

    assert exc.value.path == "show.cues[0].effect.speed"
    assert "unknown field" in exc.value.reason


def _audio_modulation() -> AudioModulationSpec:
    channel = AudioModulationChannelSpec(
        source="audio.rms",
        amount=0.5,
        min_multiplier=0.5,
        max_multiplier=1.5,
        smoothing_seconds=0.0,
    )
    return AudioModulationSpec(speed=channel, intensity=channel)


class _CaptureEffect(BaseEffect):
    def __init__(self, name: str = "capture") -> None:
        super().__init__(name)
        self.contexts: list[EffectContext] = []

    def process(self, ctx: EffectContext) -> PixelFrame:
        self.contexts.append(ctx)
        definition = ctx.mode_parameters["strip_defs"][0]
        return PixelFrame(
            timestamp=ctx.timestamp,
            sequence=ctx.sequence,
            strips=[
                DigitalStrip(
                    strip_id=definition["id"],
                    pixel_count=definition["pixel_count"],
                    pixels=[(0.0, 0.0, 0.0)] * definition["pixel_count"],
                )
            ],
        )


def _render_context(effect_spec: EffectSpec, *, base_speed: float = 2.0) -> EffectContext:
    cue = Cue(
        id="cue",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip_11"),
        effect=effect_spec,
        audio_modulation=_audio_modulation(),
    )
    capture = _CaptureEffect(effect_spec.id or effect_spec.fallback or "capture")
    resolver = TargetResolver(
        analog_zones=(),
        digital_strips=(ZoneDef(id="strip_11", pixel_count=1),),
    )
    job = CueRenderJob(cue, 0, resolver, effect=capture)
    job.render(
        EffectContext(
            timestamp=1.0,
            delta_time=0.1,
            sequence=1,
            audio_features=AudioFeatures(timestamp=1.0, rms=1.0, silence=False),
            speed=base_speed,
            intensity=4.0,
        )
    )
    return capture.contexts[-1]


def test_fixed_common_controls_compose_base_then_authored_then_audio() -> None:
    rendered = _render_context(
        EffectSpec(
            mode="fixed",
            id="chase",
            speed=2.0,
            intensity=0.5,
            params={"speed": 7.0},
        )
    )

    assert rendered.speed == pytest.approx(2.0 * 2.0 * 1.5)
    assert rendered.intensity == pytest.approx(4.0 * 0.5 * 1.5)
    assert rendered.mode_parameters["speed"] == 7.0


def test_adaptive_common_speed_uses_selector_base_not_input_context_speed() -> None:
    rendered = _render_context(
        EffectSpec(
            mode="adaptive",
            speed=2.0,
            intensity=0.5,
            allowed={"silence": "static"},
            fallback="static",
        ),
        base_speed=9.0,
    )

    assert rendered.speed == pytest.approx(1.0 * 2.0 * 1.5)
    assert rendered.intensity == pytest.approx(4.0 * 0.5 * 1.5)


def test_common_controls_are_clamped_once_before_effect_context() -> None:
    rendered = _render_context(
        EffectSpec(mode="fixed", id="static", speed=100.0, intensity=100.0),
        base_speed=10.0,
    )

    assert rendered.speed == 10.0
    assert rendered.intensity == 10.0


def test_default_common_controls_leave_fixed_base_context_unchanged() -> None:
    effect = EffectSpec(mode="fixed", id="static")
    cue = Cue(
        id="cue",
        start=0.0,
        end=2.0,
        target=TargetSelector("digital_strip", id="strip_11"),
        effect=effect,
    )
    capture = _CaptureEffect("static")
    resolver = TargetResolver(
        analog_zones=(),
        digital_strips=(ZoneDef(id="strip_11", pixel_count=1),),
    )
    CueRenderJob(cue, 0, resolver, effect=capture).render(
        EffectContext(
            timestamp=1.0,
            delta_time=0.1,
            sequence=1,
            speed=2.5,
            intensity=3.5,
        )
    )

    assert capture.contexts[-1].speed == 2.5
    assert capture.contexts[-1].intensity == 3.5
