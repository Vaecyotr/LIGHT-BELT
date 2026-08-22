"""COMET effect - reusable moving emitters with an optional decaying tail."""

import colorsys
import hashlib
import math
import random
from collections.abc import Mapping
from typing import Any

from light_engine.config import Config
from light_engine.effects.base import (
    BaseEffect,
    apply_common_intensity,
    runtime_float,
    runtime_motion_time,
    runtime_rgb,
)
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)


def _finite_number(
    values: Mapping[str, Any],
    key: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    value = values.get(key)
    if value is None:
        return
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ValueError(f"{key} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{key} must be <= {maximum}")


def validate_comet_params(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the authored moving-emitter controls for ``comet``.

    ``phase_spacing`` is a fraction of a complete trajectory cycle.  It is
    deliberately independent of logical-path length, so the same cue remains
    meaningful when rendered on a strip or one continuous virtual path.
    """

    _finite_number(values, "speed", minimum=0.0)
    _finite_number(values, "tail_length", minimum=0.0)
    _finite_number(values, "decay", minimum=0.0, maximum=1.0)
    _finite_number(values, "phase_spacing", minimum=0.0, maximum=1.0)

    count = values.get("count")
    if count is not None:
        if type(count) is not int:
            raise ValueError("count must be an integer")
        if not 1 <= count <= 64:
            raise ValueError("count must be in [1, 64]")

    trajectory = values.get("trajectory")
    if trajectory is not None and trajectory not in {"wrap", "bounce", "sine"}:
        raise ValueError("trajectory must be one of ['bounce', 'sine', 'wrap']")
    return dict(values)


class CometEffect(BaseEffect):
    """Meteor/comet effect with a bright head and decaying tail."""

    def __init__(self, name: str = "comet", *, seed: int = 0):
        super().__init__(name)
        config = Config.get_instance()
        self._seed = int(seed)
        self._speed = config.get("effects.comet.speed", 1.5)
        self._tail_len = config.get("effects.comet.tail_length", 0.4)
        self._decay = config.get("effects.comet.decay", 0.85)
        self._positions: dict[str, float] = {}
        self._hues: dict[str, float] = {}
        self._tails: dict[str, list[tuple[float, float, float, float]]] = {}

    def process(self, ctx: EffectContext) -> PixelFrame:
        speed = runtime_float(ctx, "speed", self._speed)
        tail_length = runtime_float(ctx, "tail_length", self._tail_len)
        decay = runtime_float(ctx, "decay", self._decay)
        count = ctx.mode_parameters.get("count", 1)
        phase_spacing = ctx.mode_parameters.get("phase_spacing")
        trajectory = ctx.mode_parameters.get("trajectory", "wrap")
        validate_comet_params(
            {
                "speed": speed,
                "tail_length": tail_length,
                "decay": decay,
                "count": count,
                **({"phase_spacing": phase_spacing} if phase_spacing is not None else {}),
                "trajectory": trajectory,
            }
        )
        authored_color = (
            runtime_rgb(ctx, "color", (1.0, 1.0, 1.0))
            if "color" in ctx.mode_parameters
            else None
        )

        # This branch intentionally remains byte-for-byte algorithmically
        # equivalent to the historical comet.  In particular its per-frame
        # tail decay and hue-wrap behavior are a compatibility contract.
        if count == 1 and trajectory == "wrap" and tail_length > 0.0:
            return self._process_legacy(
                ctx, speed, tail_length, decay, authored_color
            )

        return self._process_moving_emitters(
            ctx,
            speed=speed,
            tail_length=tail_length,
            decay=decay,
            count=count,
            phase_spacing=(1.0 / count if phase_spacing is None else float(phase_spacing)),
            trajectory=trajectory,
            authored_color=authored_color,
        )

    def _process_legacy(
        self,
        ctx: EffectContext,
        speed: float,
        tail_length: float,
        decay: float,
        authored_color: tuple[float, float, float] | None,
    ) -> PixelFrame:
        strips = []

        for sd in ctx.mode_parameters.get("strip_defs", []):
            sid = sd["id"]
            n = sd["pixel_count"]
            if n == 0:
                continue

            if sid not in self._positions:
                self._positions[sid] = 0.0
                self._hues[sid] = (
                    0.0 if authored_color is not None else random.uniform(0, 360)
                )
                self._tails[sid] = []

            self._positions[sid] += speed * ctx.speed * ctx.delta_time
            pos = self._positions[sid]

            # Wrap around
            if pos > n + 2:
                pos -= n + 2
                if authored_color is None:
                    self._hues[sid] = (self._hues[sid] + 60) % 360
                self._tails[sid] = []
            self._positions[sid] = pos

            # Add new head
            if authored_color is None:
                hue = self._hues[sid]
                head_r, head_g, head_b = colorsys.hsv_to_rgb(
                    hue / 360, 1.0, 1.0
                )
            else:
                head_r, head_g, head_b = authored_color
            self._tails[sid].append((pos, head_r, head_g, head_b))

            # Decay and remove old tails
            self._tails[sid] = [
                (t[0], t[1] * decay, t[2] * decay, t[3] * decay)
                for t in self._tails[sid]
            ]

            # Cleanup
            self._tails[sid] = [
                t for t in self._tails[sid]
                if t[1] > 0.01 or t[2] > 0.01 or t[3] > 0.01
            ]

            # Render
            pixels = [(0.0, 0.0, 0.0)] * n
            for t_pos, tr, tg, tb in self._tails[sid]:
                tail_px = int(t_pos) % n
                tail_len = int(n * tail_length)
                for offset in range(tail_len):
                    px = (tail_px - offset) % n
                    factor = 1.0 - offset / max(1, tail_len)
                    cr = tr * factor
                    cg = tg * factor
                    cb = tb * factor
                    if max(cr, cg, cb) > 0.01:
                        existing = pixels[px]
                        pixels[px] = (
                            max(existing[0], cr),
                            max(existing[1], cg),
                            max(existing[2], cb),
                        )
            strips.append(DigitalStrip(strip_id=sid, pixel_count=n, pixels=pixels))

        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zones.append(ZoneOutput(
                zone_id=zd["id"],
                color=RGBCCTColor(),
            ))

        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp, sequence=ctx.sequence, strips=strips, zones=zones
            ),
            ctx.intensity,
        )

    def _process_moving_emitters(
        self,
        ctx: EffectContext,
        *,
        speed: float,
        tail_length: float,
        decay: float,
        count: int,
        phase_spacing: float,
        trajectory: str,
        authored_color: tuple[float, float, float] | None,
    ) -> PixelFrame:
        """Render stateless generic emitters from cue-local time.

        Unlike the preserved legacy branch, this form derives every head and
        tail solely from cue-local progress.  Seeking and FPS changes therefore
        cannot leave behind stale frame-history particles.
        """

        cue_time = max(0.0, float(ctx.mode_parameters.get("cue_local_time", ctx.timestamp)))
        motion_time = runtime_motion_time(ctx, cue_time)
        strips = []
        for strip_def in ctx.mode_parameters.get("strip_defs", []):
            strip_id = strip_def["id"]
            pixel_count = strip_def["pixel_count"]
            if pixel_count <= 0:
                continue
            head_color = self._head_color(ctx, strip_id, authored_color)
            pixels = [(0.0, 0.0, 0.0)] * pixel_count
            distance = motion_time * speed
            tail_pixels = int(pixel_count * tail_length)
            for emitter_index in range(count):
                position, direction = self._trajectory_position(
                    pixel_count,
                    distance,
                    emitter_index * phase_spacing,
                    trajectory,
                )
                self._render_emitter(
                    pixels,
                    position=position,
                    direction=direction,
                    tail_pixels=tail_pixels,
                    decay=decay,
                    color=head_color,
                )
            strips.append(
                DigitalStrip(
                    strip_id=strip_id,
                    pixel_count=pixel_count,
                    pixels=pixels,
                )
            )

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

    def _head_color(
        self,
        ctx: EffectContext,
        strip_id: str,
        authored_color: tuple[float, float, float] | None,
    ) -> tuple[float, float, float]:
        if authored_color is not None:
            return authored_color
        if strip_id not in self._hues:
            # Generic emitters must replay independently from process-global
            # RNG state.  CueRenderJob supplies cue_id in the scoped context;
            # the optional effect seed permits explicit deterministic tests or
            # dependency injection without becoming an authored effect field.
            cue_id = str(ctx.mode_parameters.get("cue_id", "<direct>"))
            identity = f"{self._seed}|{cue_id}|{strip_id}".encode("utf-8")
            digest = hashlib.sha256(identity).digest()
            self._hues[strip_id] = int.from_bytes(digest[:8], "big") / 2**64 * 360.0
        return colorsys.hsv_to_rgb(self._hues[strip_id] / 360, 1.0, 1.0)

    @staticmethod
    def _trajectory_position(
        pixel_count: int,
        distance: float,
        phase: float,
        trajectory: str,
    ) -> tuple[float, int]:
        """Return a continuous head coordinate and its current travel sign."""

        if trajectory == "wrap":
            return (distance + phase * pixel_count) % pixel_count, 1
        span = pixel_count - 1
        if span <= 0:
            return 0.0, 1
        period = 2.0 * span
        if trajectory == "bounce":
            offset = (distance + phase * period) % period
            if offset <= span:
                return offset, 1
            return period - offset, -1

        cycle = (distance / period + phase) % 1.0
        angle = math.tau * cycle
        position = 0.5 * span * (1.0 - math.cos(angle))
        return position, 1 if math.sin(angle) >= 0.0 else -1

    @staticmethod
    def _render_emitter(
        pixels: list[tuple[float, float, float]],
        *,
        position: float,
        direction: int,
        tail_pixels: int,
        decay: float,
        color: tuple[float, float, float],
    ) -> None:
        """Max-compose one head and a distance-shaped tail into a logical path."""

        count = len(pixels)
        for offset in range(max(0, tail_pixels) + 1):
            index = int(position - direction * offset) % count
            taper = 1.0 - offset / (max(0, tail_pixels) + 1)
            gain = taper * decay**offset
            incoming = tuple(channel * gain for channel in color)
            current = pixels[index]
            pixels[index] = tuple(max(old, new) for old, new in zip(current, incoming))

    def reset(self) -> None:
        self._positions.clear()
        self._hues.clear()
        self._tails.clear()
