"""TWINKLE effect - randomly positioned, controllably colored sparks."""

from __future__ import annotations

import colorsys
import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

from light_engine.config import Config
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_param,
    runtime_rgb,
    runtime_str,
)
from light_engine.effects.scalar_source import ScalarSource, validate_scalar_source
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


_DEFAULT_EVENT_SEED = 0


def validate_twinkle_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    for key, lower, upper in (
        ("density", 0.0, 100.0),
        ("fade_time", 0.01, 60.0),
        ("event_width_px", 0.01, 10000.0),
        ("blur_radius_px", 0.0, 10000.0),
    ):
        value = values.get(key)
        if value is not None:
            if type(value) not in {int, float} or not math.isfinite(float(value)):
                raise ValueError(f"{key} must be a finite number")
            if not lower <= float(value) <= upper:
                raise ValueError(f"{key} must be in [{lower}, {upper}]")
    color_source = values.get("color_source")
    if color_source is not None and color_source not in {"solid", "palette", "random"}:
        raise ValueError(
            "color_source must be one of ['palette', 'random', 'solid']"
        )
    color = values.get("color")
    if color is not None:
        if not isinstance(color, (list, tuple)) or len(color) != 3:
            raise ValueError("color must contain exactly 3 RGB channels")
        if any(
            type(channel) not in {int, float}
            or not math.isfinite(float(channel))
            or not 0.0 <= float(channel) <= 1.0
            for channel in color
        ):
            raise ValueError("color channels must be finite numbers in [0, 1]")
    for key in ("event_gate_source", "birth_gain_source"):
        source = values.get(key)
        if source is not None:
            validate_scalar_source(source, field_name=key)
    return dict(values)


class TwinkleEffect(BaseEffect):
    """Spawn sparks at random valid coordinates, scaled by strip length."""

    def __init__(self, name: str = "twinkle", *, seed: int | None = None):
        super().__init__(name)
        config = Config.get_instance()
        self._density = config.get("effects.twinkle.density", 0.12)
        self._fade_time = config.get("effects.twinkle.fade_time", 0.7)
        self._color_source = config.get("effects.twinkle.color_source", "random")
        color = config.get("effects.twinkle.color", [1.0, 1.0, 1.0])
        self._color = (float(color[0]), float(color[1]), float(color[2]))
        self._pixels: dict[str, list[tuple[float, float, float]]] = {}
        self._spawn_remainders: dict[str, float] = {}
        self._color_event_indices: dict[str, int] = {}
        # The historical default deliberately continues to use the module RNG
        # below.  Event-field controls use this separate, resettable stream so
        # replay is deterministic without changing the legacy random-call
        # sequence when none of the new controls are authored.
        self._event_seed = _DEFAULT_EVENT_SEED if seed is None else int(seed)
        self._event_rng: random.Random | None = None
        self._event_rng_cue_id: str | None = None
        self._last_cue_time: float | None = None

    @staticmethod
    def _random_color() -> tuple[float, float, float]:
        return colorsys.hsv_to_rgb(random.random(), 0.7, 1.0)

    def _spark_color(
        self,
        ctx: EffectContext,
        color_source: str,
        solid: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        if color_source == "random":
            return self._random_color()
        if color_source == "palette":
            palette = runtime_param(ctx, "palette", ())
            if isinstance(palette, Sequence) and palette:
                selected = random.choice(palette)
                return (float(selected[0]), float(selected[1]), float(selected[2]))
        return solid

    @staticmethod
    def _event_random_color(rng: random.Random) -> tuple[float, float, float]:
        return colorsys.hsv_to_rgb(rng.random(), 0.7, 1.0)

    def _event_spark_color(
        self,
        ctx: EffectContext,
        color_source: str,
        solid: tuple[float, float, float],
        rng: random.Random,
        event_identity: object | None = None,
    ) -> tuple[float, float, float]:
        """Select an authored twinkle color from the replayable event stream."""

        sampler = ctx.mode_parameters.get("color_sampler")
        if sampler is not None:
            return sampler.sample_event(ctx, event_identity)

        if color_source == "random":
            return self._event_random_color(rng)
        if color_source == "palette":
            palette = runtime_param(ctx, "palette", ())
            if isinstance(palette, Sequence) and palette:
                selected = rng.choice(palette)
                return (float(selected[0]), float(selected[1]), float(selected[2]))
        return solid

    def _event_random(self, ctx: EffectContext) -> random.Random:
        """Return the cue-scoped event stream without reading global RNG state.

        The compatibility branch never calls this method, so its historic
        module-RNG call sequence is untouched.  Event fields instead derive a
        stable private stream from the explicitly injectable base seed and the
        compositor-provided cue identity.
        """

        cue_id = str(ctx.mode_parameters.get("cue_id", "<direct>"))
        if self._event_rng is None or cue_id != self._event_rng_cue_id:
            digest = hashlib.sha256(
                f"twinkle-event-v1:{self._event_seed}:{cue_id}".encode("utf-8")
            ).digest()
            self._event_rng = random.Random(int.from_bytes(digest[:8], "big"))
            self._event_rng_cue_id = cue_id
        return self._event_rng

    @staticmethod
    def _add_event_field(
        pixels: list[tuple[float, float, float]],
        *,
        position: int,
        color: tuple[float, float, float],
        width: float,
        blur_radius: float,
        birth_gain: float,
    ) -> None:
        """Max-compose one finite-width, optionally softened event field.

        ``position`` is a pixel-center coordinate.  The solid core is centered
        on that pixel; width expands it symmetrically and blur linearly tapers
        the exterior.  The finite logical path is clipped at its ends rather
        than wrapped, so virtual paths retain one continuous seam-free field.
        """

        core_radius = width / 2.0
        center = position + 0.5
        for index, existing in enumerate(pixels):
            distance = abs((index + 0.5) - center)
            if distance < core_radius:
                field_gain = 1.0
            elif blur_radius > 0.0 and distance < core_radius + blur_radius:
                field_gain = 1.0 - (distance - core_radius) / blur_radius
            else:
                continue
            incoming = tuple(channel * birth_gain * field_gain for channel in color)
            pixels[index] = tuple(
                max(previous, contribution)
                for previous, contribution in zip(existing, incoming)
            )

    def process(self, ctx: EffectContext) -> PixelFrame:
        cue_time = float(ctx.mode_parameters.get("cue_local_time", ctx.timestamp))
        if not math.isfinite(cue_time):
            raise ValueError("twinkle cue_local_time must be finite")
        if self._last_cue_time is not None and cue_time < self._last_cue_time:
            self.reset()
        density = runtime_float(ctx, "density", self._density)
        fade_time = runtime_float(ctx, "fade_time", self._fade_time)
        color_source = runtime_str(ctx, "color_source", self._color_source)
        solid = runtime_rgb(ctx, "color", self._color)
        event_width = runtime_float(ctx, "event_width_px", 1.0)
        blur_radius = runtime_float(ctx, "blur_radius_px", 0.0)
        event_gate_source = runtime_param(ctx, "event_gate_source", None)
        birth_gain_source = runtime_param(ctx, "birth_gain_source", None)
        sampler = ctx.mode_parameters.get("color_sampler")
        validate_twinkle_params(
            {
                "density": density,
                "fade_time": fade_time,
                "color_source": color_source,
                "color": solid,
                "event_width_px": event_width,
                "blur_radius_px": blur_radius,
                "event_gate_source": event_gate_source,
                "birth_gain_source": birth_gain_source,
            }
        )
        event_field = (
            event_width != 1.0
            or blur_radius != 0.0
            or event_gate_source is not None
            or birth_gain_source is not None
            or sampler is not None
        )
        event_gate = (
            1.0
            if event_gate_source is None
            else ScalarSource(event_gate_source).sample(ctx)
        )
        birth_gain = (
            1.0
            if birth_gain_source is None
            else ScalarSource(birth_gain_source).sample(ctx)
        )
        event_rng = self._event_random(ctx) if event_field else None
        decay = math.exp(-ctx.delta_time / fade_time)

        strips = []
        active_ids = set()
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            strip_id = strip_def["id"]
            pixel_count = strip_def["pixel_count"]
            active_ids.add(strip_id)
            current = self._pixels.get(strip_id)
            if current is None or len(current) != pixel_count:
                current = [(0.0, 0.0, 0.0)] * pixel_count
                self._spawn_remainders[strip_id] = 0.0
                self._color_event_indices[strip_id] = 0
            current = [
                (
                    (r * decay, g * decay, b * decay)
                    if max(r, g, b) * decay >= 0.01
                    else (0.0, 0.0, 0.0)
                )
                for r, g, b in current
            ]

            expected = density * pixel_count * ctx.delta_time * event_gate
            total = expected + self._spawn_remainders.get(strip_id, 0.0)
            spawn_count = int(total)
            self._spawn_remainders[strip_id] = total - spawn_count
            for _ in range(spawn_count):
                if pixel_count == 0:
                    break
                if event_field:
                    assert event_rng is not None
                    position = event_rng.randrange(pixel_count)
                    event_index = self._color_event_indices.get(strip_id, 0)
                    self._color_event_indices[strip_id] = event_index + 1
                    self._add_event_field(
                        current,
                        position=position,
                        color=self._event_spark_color(
                            ctx,
                            color_source,
                            solid,
                            event_rng,
                            (strip_id, event_index),
                        ),
                        width=event_width,
                        blur_radius=blur_radius,
                        birth_gain=birth_gain,
                    )
                else:
                    # Keep the exact historical random placement/color and
                    # replacement semantics when all new options are absent.
                    position = random.randrange(pixel_count)
                    current[position] = self._spark_color(ctx, color_source, solid)

            self._pixels[strip_id] = current
            strips.append(
                DigitalStrip(
                    strip_id=strip_id,
                    pixel_count=pixel_count,
                    pixels=current,
                )
            )

        for stale_id in set(self._pixels) - active_ids:
            self._pixels.pop(stale_id, None)
            self._spawn_remainders.pop(stale_id, None)
            self._color_event_indices.pop(stale_id, None)

        self._last_cue_time = cue_time

        zones = [
            ZoneOutput(zone_id=zone_def["id"], color=RGBCCTColor())
            for zone_def in ctx.mode_parameters.get("zone_defs", [])
        ]
        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp,
                sequence=ctx.sequence,
                strips=strips,
                zones=zones,
            ),
            ctx.intensity,
        )

    def reset(self) -> None:
        self._pixels.clear()
        self._spawn_remainders.clear()
        self._color_event_indices.clear()
        self._event_rng = None
        self._event_rng_cue_id = None
        self._last_cue_time = None
