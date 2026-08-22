"""Deterministic fixed-step one-dimensional heat simulation."""

from __future__ import annotations

import hashlib
import math
import random
from collections.abc import Mapping
from typing import Any

from light_engine.effects.base import (
    BaseEffect,
    runtime_float,
    runtime_int,
    runtime_motion_time,
    runtime_rgb,
)
from light_engine.models import DigitalStrip, EffectContext, PixelFrame, RGBCCTColor, ZoneOutput


def _validate_number(values: Mapping[str, Any], key: str, lower: float, upper: float) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    if not lower <= float(value) <= upper:
        raise ValueError(f"{key} must be in [{lower}, {upper}]")


def validate_heat_fire_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    for key, lower, upper in (
        ("cooling_per_second", 0.0, 60.0),
        ("spark_rate", 0.0, 60.0),
        ("spark_strength", 0.0, 1.0),
        ("diffusion", 0.0, 1.0),
    ):
        _validate_number(values, key, lower, upper)
    zone = values.get("spark_zone_px")
    if zone is not None and (type(zone) is not int or not 1 <= zone <= 10000):
        raise ValueError("spark_zone_px must be an integer in [1, 10000]")
    _validate_color(values)
    return dict(values)


def _validate_color(values: Mapping[str, Any]) -> None:
    color = values.get("color")
    if color is None:
        return
    if not isinstance(color, (list, tuple)) or len(color) != 3:
        raise ValueError("color must contain exactly 3 RGB channels")
    if any(
        type(channel) not in {int, float}
        or not math.isfinite(float(channel))
        or not 0.0 <= float(channel) <= 1.0
        for channel in color
    ):
        raise ValueError("color channels must be finite numbers in [0, 1]")


class HeatFireEffect(BaseEffect):
    """Own a 60 Hz heat state with per-tick deterministic random input."""

    STEP_HZ = 60

    def __init__(self, name: str = "heat_fire", *, seed: int | None = None):
        super().__init__(name)
        self._seed = random.getrandbits(64) if seed is None else int(seed)
        self._heat: dict[str, list[float]] = {}
        self._strip_ticks: dict[str, int] = {}
        self._last_target_tick = 0

    def _rng(self, strip_id: str, tick: int) -> random.Random:
        digest = hashlib.sha256(f"{self._seed}:{strip_id}:{tick}".encode()).digest()
        return random.Random(int.from_bytes(digest[:8], "little"))

    @staticmethod
    def _step(
        heat: list[float],
        rng: random.Random,
        cooling: float,
        spark_rate: float,
        spark_strength: float,
        diffusion: float,
        spark_zone: int,
    ) -> None:
        for index in range(len(heat)):
            heat[index] = max(0.0, heat[index] - rng.random() * cooling / 60.0)
        previous = heat.copy()
        for index in range(1, len(heat)):
            below = previous[index - 1]
            heat[index] = min(1.0, previous[index] * (1.0 - diffusion) + below * diffusion)
        if heat and rng.random() < spark_rate / 60.0:
            position = rng.randrange(min(len(heat), spark_zone))
            heat[position] = min(1.0, heat[position] + spark_strength * (0.5 + 0.5 * rng.random()))

    def process(self, ctx: EffectContext) -> PixelFrame:
        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", 0.0)))
        motion_time = runtime_motion_time(ctx, cue_time)
        target_tick = int(math.floor(motion_time * self.STEP_HZ + 1e-9))
        if target_tick < self._last_target_tick:
            self.reset()
        self._last_target_tick = target_tick
        cooling = runtime_float(ctx, "cooling_per_second", 0.8)
        spark_rate = runtime_float(ctx, "spark_rate", 8.0)
        spark_strength = runtime_float(ctx, "spark_strength", 0.9)
        diffusion = runtime_float(ctx, "diffusion", 0.35)
        spark_zone = runtime_int(ctx, "spark_zone_px", 3)
        color = runtime_rgb(ctx, "color", (1.0, 0.32, 0.04))
        strips = []
        active = set()
        for strip_def in ctx.mode_parameters.get("strip_defs", ()):
            strip_id = strip_def["id"]
            count = strip_def["pixel_count"]
            active.add(strip_id)
            if strip_id not in self._heat or len(self._heat[strip_id]) != count:
                self._heat[strip_id] = [0.0] * count
                self._strip_ticks[strip_id] = 0
            heat = self._heat[strip_id]
            for tick in range(self._strip_ticks[strip_id], target_tick):
                self._step(heat, self._rng(strip_id, tick), cooling, spark_rate, spark_strength, diffusion, spark_zone)
            self._strip_ticks[strip_id] = target_tick
            pixels = []
            for value in heat:
                glow = min(1.0, value * ctx.intensity)
                pixels.append(tuple(channel * glow for channel in color))
            strips.append(DigitalStrip(strip_id, count, pixels))
        for stale_id in set(self._heat) - active:
            self._heat.pop(stale_id, None)
            self._strip_ticks.pop(stale_id, None)
        zones = [ZoneOutput(zone["id"], RGBCCTColor()) for zone in ctx.mode_parameters.get("zone_defs", ())]
        return PixelFrame(ctx.timestamp, ctx.sequence, strips, zones)

    def reset(self) -> None:
        self._heat.clear()
        self._strip_ticks.clear()
        self._last_target_tick = 0
