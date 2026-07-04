"""BASS_PULSE effect - bass energy drives pulse intensity."""

from light_engine.config import Config
from light_engine.effects.base import BaseEffect
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBWColor,
    ZoneOutput,
)
from light_engine.util import AttackReleaseEnvelope


class BassPulseEffect(BaseEffect):
    """Bass energy triggers brightness/diffusion pulse."""

    def __init__(self, name: str = "bass_pulse"):
        super().__init__(name)
        config = Config.get_instance()
        c = config.get("effects.bass_pulse.color", [0.2, 0.6, 1.0])
        self._color: tuple[float, float, float] = (
            float(c[0]), float(c[1]), float(c[2])
        )
        self._env = AttackReleaseEnvelope(
            attack=config.get("effects.bass_pulse.attack", 0.6),
            release=config.get("effects.bass_pulse.release", 0.2),
        )

    def process(self, ctx: EffectContext) -> PixelFrame:
        target = 0.0
        if ctx.audio_features and not ctx.audio_features.silence:
            target = ctx.audio_features.bass * ctx.intensity * 1.5

        bri = self._env.update(target, ctx.delta_time) * ctx.global_brightness

        r, g, b = self._color
        r, g, b = r * bri, g * bri, b * bri

        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            pixels = [(r, g, b)] * sd["pixel_count"]
            strips.append(DigitalStrip(
                strip_id=sd["id"], pixel_count=sd["pixel_count"], pixels=pixels
            ))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=RGBWColor(r=r, g=g, b=b, w=0.0, brightness=bri),
            ))

        return PixelFrame(timestamp=ctx.timestamp, strips=strips, zones=zones)

    def reset(self) -> None:
        self._env.reset(0.0)
