"""Target-scoped show rendering and deterministic frame composition."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from light_engine.effects.base import BaseEffect, create_effect
from light_engine.mapping import Layout, ZoneDef
from light_engine.mapping.virtual import VirtualPath
from light_engine.models import (
    ColorRGB,
    DigitalStrip,
    EffectContext,
    PixelFrame,
    RGBCCTColor,
    ZoneOutput,
)
from light_engine.show.models import Cue, ShowDefinition, TargetSelector


@dataclass(frozen=True)
class ResolvedTarget:
    """Immutable selected target view for one authored cue."""

    selector: TargetSelector
    analog_zones: tuple[ZoneDef, ...] = ()
    digital_strips: tuple[ZoneDef, ...] = ()
    virtual_path: VirtualPath | None = None


@dataclass(frozen=True)
class DigitalContribution:
    """Sparse digital contribution.

    ``None`` pixels are absent/no contribution. RGB tuples, including
    ``(0, 0, 0)``, are explicit participating values.
    """

    strip_id: str
    source_start: int
    pixels: tuple[ColorRGB | None, ...]


@dataclass(frozen=True)
class AnalogContribution:
    """Explicit analog RGB+CCT contribution for one zone."""

    zone_id: str
    color: RGBCCTColor


@dataclass(frozen=True)
class FrameContribution:
    """Typed contribution emitted by one cue/effect render."""

    cue_id: str
    priority: int
    declaration_index: int
    blend: str
    timestamp: float
    sequence: int
    digital: tuple[DigitalContribution, ...] = ()
    analog: tuple[AnalogContribution, ...] = ()


class TargetResolver:
    """Resolve Phase 11 target selectors into concrete logical definitions."""

    def __init__(
        self,
        analog_zones: Iterable[ZoneDef],
        digital_strips: Iterable[ZoneDef],
        *,
        analog_groups: Mapping[str, Iterable[str]] | None = None,
        digital_groups: Mapping[str, Iterable[str]] | None = None,
        virtual_paths: Iterable[VirtualPath] = (),
    ):
        self._analog_order = tuple(analog_zones)
        self._digital_order = tuple(digital_strips)
        self._analog_by_id = {zone.id: zone for zone in self._analog_order}
        self._digital_by_id = {strip.id: strip for strip in self._digital_order}
        self._analog_groups = {
            group_id: tuple(member_ids)
            for group_id, member_ids in (analog_groups or {}).items()
        }
        self._digital_groups = {
            group_id: tuple(member_ids)
            for group_id, member_ids in (digital_groups or {}).items()
        }
        self._virtual_by_id = {path.id: path for path in virtual_paths}

    @classmethod
    def from_layout(
        cls,
        layout: Layout,
        *,
        analog_groups: Mapping[str, Iterable[str]] | None = None,
        digital_groups: Mapping[str, Iterable[str]] | None = None,
    ) -> "TargetResolver":
        return cls(
            layout.zones,
            layout.strips,
            analog_groups=analog_groups,
            digital_groups=digital_groups,
            virtual_paths=layout.virtual_paths,
        )

    def resolve(self, selector: TargetSelector) -> ResolvedTarget:
        kind = selector.kind
        if kind == "analog_zone":
            return ResolvedTarget(selector, analog_zones=(self._analog(selector.id),))
        if kind == "digital_strip":
            return ResolvedTarget(selector, digital_strips=(self._digital(selector.id),))
        if kind == "analog_group":
            return ResolvedTarget(selector, analog_zones=self._resolve_analog_group(selector))
        if kind == "digital_group":
            return ResolvedTarget(selector, digital_strips=self._resolve_digital_group(selector))
        if kind == "virtual_path":
            path = self._virtual(selector.id)
            strip_ids = tuple(dict.fromkeys(segment.strip_id for segment in path.segments))
            strips = tuple(self._digital(strip_id) for strip_id in strip_ids)
            return ResolvedTarget(selector, digital_strips=strips, virtual_path=path)
        if kind == "all_analog":
            return ResolvedTarget(selector, analog_zones=self._analog_order)
        if kind == "all_digital":
            return ResolvedTarget(selector, digital_strips=self._digital_order)
        if kind == "all":
            return ResolvedTarget(
                selector,
                analog_zones=self._analog_order,
                digital_strips=self._digital_order,
            )
        raise ValueError(f"unknown target kind {kind!r}")

    def _analog(self, zone_id: str | None) -> ZoneDef:
        if zone_id not in self._analog_by_id:
            raise KeyError(f"unknown analog zone {zone_id!r}")
        return self._analog_by_id[zone_id]

    def _digital(self, strip_id: str | None) -> ZoneDef:
        if strip_id not in self._digital_by_id:
            raise KeyError(f"unknown digital strip {strip_id!r}")
        return self._digital_by_id[strip_id]

    def _virtual(self, path_id: str | None) -> VirtualPath:
        if path_id not in self._virtual_by_id:
            raise KeyError(f"unknown virtual path {path_id!r}")
        return self._virtual_by_id[path_id]

    def _resolve_analog_group(self, selector: TargetSelector) -> tuple[ZoneDef, ...]:
        ids = selector.ids or self._analog_groups.get(selector.id or "", ())
        return tuple(self._analog(zone_id) for zone_id in ids)

    def _resolve_digital_group(self, selector: TargetSelector) -> tuple[ZoneDef, ...]:
        ids = selector.ids or self._digital_groups.get(selector.id or "", ())
        return tuple(self._digital(strip_id) for strip_id in ids)


def black_base_frame(
    *,
    timestamp: float,
    sequence: int,
    analog_zones: Iterable[ZoneDef],
    digital_strips: Iterable[ZoneDef],
    metadata: Mapping[str, Any] | None = None,
) -> PixelFrame:
    """Create the explicit black base frame used by show composition."""

    return PixelFrame(
        timestamp=timestamp,
        sequence=sequence,
        strips=[
            DigitalStrip(
                strip_id=strip.id,
                pixel_count=strip.pixel_count,
                pixels=[(0.0, 0.0, 0.0)] * strip.pixel_count,
            )
            for strip in digital_strips
        ],
        zones=[
            ZoneOutput(zone_id=zone.id, color=RGBCCTColor())
            for zone in analog_zones
        ],
        metadata=dict(metadata or {}),
    )


def make_scoped_context(
    ctx: EffectContext,
    resolved: ResolvedTarget,
    *,
    cue: Cue | None = None,
    declaration_index: int | None = None,
) -> EffectContext:
    """Return an immutable per-target context view for one effect render."""

    if resolved.virtual_path is None:
        strip_defs = tuple(_strip_def(strip) for strip in resolved.digital_strips)
    else:
        strip_defs = (
            MappingProxyType(
                {
                    "id": _virtual_strip_id(resolved.virtual_path.id),
                    "pixel_count": resolved.virtual_path.total_length,
                    "video_zone": "center",
                    "direction": "forward",
                }
            ),
        )
    zone_defs = tuple(_zone_def(zone) for zone in resolved.analog_zones)
    mode_parameters = dict(ctx.mode_parameters)
    mode_parameters.update(
        {
            "strip_defs": strip_defs,
            "zone_defs": zone_defs,
            "target": resolved.selector,
        }
    )
    if cue is not None:
        mode_parameters.update(dict(cue.effect.parameters))
        mode_parameters["cue_id"] = cue.id
        mode_parameters["priority"] = cue.priority
        mode_parameters["blend"] = cue.transition.blend
    if declaration_index is not None:
        mode_parameters["declaration_index"] = declaration_index
    return replace(ctx, mode_parameters=MappingProxyType(mode_parameters))


def frame_to_contribution(
    frame: PixelFrame,
    *,
    resolved: ResolvedTarget,
    cue_id: str,
    priority: int,
    declaration_index: int,
    blend: str,
) -> FrameContribution:
    """Convert an effect frame into target-scoped typed contributions."""

    if blend not in {"replace", "add"}:
        raise ValueError(f"unsupported V1 blend mode {blend!r}")
    if resolved.virtual_path is None:
        digital = tuple(
            DigitalContribution(
                strip_id=strip.strip_id,
                source_start=0,
                pixels=tuple(_validate_rgb(pixel, "digital contribution") for pixel in strip.pixels),
            )
            for strip in frame.strips
        )
    else:
        digital = _virtual_frame_to_digital(frame, resolved.virtual_path)
    analog = tuple(
        AnalogContribution(zone_id=zone.zone_id, color=_copy_rgbcct(zone.color))
        for zone in frame.zones
    )
    return FrameContribution(
        cue_id=cue_id,
        priority=priority,
        declaration_index=declaration_index,
        blend=blend,
        timestamp=frame.timestamp,
        sequence=frame.sequence,
        digital=digital,
        analog=analog,
    )


def compose_frame(base: PixelFrame, contributions: Iterable[FrameContribution]) -> PixelFrame:
    """Compose contributions over ``base`` without mutating any input values."""

    strips = {
        strip.strip_id: [tuple(_validate_rgb(pixel, "base pixel")) for pixel in strip.pixels]
        for strip in base.strips
    }
    strip_order = [strip.strip_id for strip in base.strips]
    zones = {
        zone.zone_id: _copy_rgbcct(zone.color)
        for zone in base.zones
    }
    zone_order = [zone.zone_id for zone in base.zones]

    ordered = sorted(contributions, key=lambda item: (item.priority, item.declaration_index))
    for contribution in ordered:
        _validate_frame_identity(base, contribution)
        if contribution.blend not in {"replace", "add"}:
            raise ValueError(f"unsupported V1 blend mode {contribution.blend!r}")
        for digital in contribution.digital:
            if digital.strip_id not in strips:
                continue
            pixels = list(strips[digital.strip_id])
            for offset, incoming in enumerate(digital.pixels):
                if incoming is None:
                    continue
                index = digital.source_start + offset
                if index < 0 or index >= len(pixels):
                    continue
                incoming_rgb = _validate_rgb(incoming, "incoming pixel")
                if contribution.blend == "replace":
                    pixels[index] = incoming_rgb
                else:
                    pixels[index] = _add_rgb(pixels[index], incoming_rgb)
            strips[digital.strip_id] = pixels
        for analog in contribution.analog:
            if analog.zone_id not in zones:
                continue
            incoming_color = _copy_rgbcct(analog.color)
            if contribution.blend == "replace":
                zones[analog.zone_id] = incoming_color
            else:
                zones[analog.zone_id] = _add_rgbcct(zones[analog.zone_id], incoming_color)

    return PixelFrame(
        timestamp=base.timestamp,
        sequence=base.sequence,
        strips=[
            DigitalStrip(strip_id=strip_id, pixel_count=len(strips[strip_id]), pixels=list(strips[strip_id]))
            for strip_id in strip_order
        ],
        zones=[
            ZoneOutput(zone_id=zone_id, color=_copy_rgbcct(zones[zone_id]))
            for zone_id in zone_order
        ],
        metadata=dict(base.metadata),
    )


class CueRenderJob:
    """One cue with its own effect instance and mutable state."""

    def __init__(
        self,
        cue: Cue,
        declaration_index: int,
        resolver: TargetResolver,
        *,
        effect: BaseEffect | None = None,
    ):
        if cue.effect.mode != "fixed" or cue.effect.name is None:
            raise ValueError("Phase 13 renderer supports fixed effect cues only")
        self.cue = cue
        self.declaration_index = declaration_index
        self.resolved = resolver.resolve(cue.target)
        self.effect = effect if effect is not None else create_effect(cue.effect.name)

    def render(self, ctx: EffectContext) -> FrameContribution:
        scoped = make_scoped_context(
            ctx,
            self.resolved,
            cue=self.cue,
            declaration_index=self.declaration_index,
        )
        frame = self.effect.process(scoped)
        return frame_to_contribution(
            frame,
            resolved=self.resolved,
            cue_id=self.cue.id,
            priority=self.cue.priority,
            declaration_index=self.declaration_index,
            blend=self.cue.transition.blend,
        )

    def reset(self) -> None:
        self.effect.reset()


class ShowRuntime:
    """Render active cue jobs and compose a deterministic logical frame."""

    def __init__(self, show: ShowDefinition, resolver: TargetResolver):
        self.show = show
        self._resolver = resolver
        self._jobs = tuple(
            CueRenderJob(cue, index, resolver) for index, cue in enumerate(show.cues)
        )

    @classmethod
    def from_layout(cls, show: ShowDefinition, layout: Layout) -> "ShowRuntime":
        return cls(show, TargetResolver.from_layout(layout))

    @property
    def jobs(self) -> tuple[CueRenderJob, ...]:
        return self._jobs

    def render(self, ctx: EffectContext, base: PixelFrame) -> PixelFrame:
        active = [
            job.render(ctx)
            for job in self._jobs
            if job.cue.start <= ctx.timestamp < job.cue.end
        ]
        return compose_frame(base, active)

    def reset(self) -> None:
        for job in self._jobs:
            job.reset()


def _strip_def(strip: ZoneDef) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "id": strip.id,
            "pixel_count": strip.pixel_count,
            "video_zone": strip.video_zone,
            "direction": strip.direction,
        }
    )


def _zone_def(zone: ZoneDef) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            "id": zone.id,
            "video_zone": zone.video_zone,
            "direction": zone.direction,
        }
    )


def _virtual_strip_id(path_id: str) -> str:
    return f"__virtual_path__:{path_id}"


def _virtual_frame_to_digital(
    frame: PixelFrame, virtual_path: VirtualPath
) -> tuple[DigitalContribution, ...]:
    strip_id = _virtual_strip_id(virtual_path.id)
    path_strip = next((strip for strip in frame.strips if strip.strip_id == strip_id), None)
    if path_strip is None:
        return ()
    ranges = virtual_path.split(tuple(_validate_rgb(pixel, "virtual path pixel") for pixel in path_strip.pixels))
    return tuple(
        DigitalContribution(
            strip_id=item.strip_id,
            source_start=item.source_start,
            pixels=tuple(item.pixels),
        )
        for item in ranges
    )


def _validate_frame_identity(base: PixelFrame, contribution: FrameContribution) -> None:
    if contribution.timestamp != base.timestamp:
        raise ValueError(
            f"contribution {contribution.cue_id!r} timestamp {contribution.timestamp} "
            f"does not match base timestamp {base.timestamp}"
        )
    if contribution.sequence != base.sequence:
        raise ValueError(
            f"contribution {contribution.cue_id!r} sequence {contribution.sequence} "
            f"does not match base sequence {base.sequence}"
        )


def _validate_rgb(pixel: Sequence[float], label: str) -> ColorRGB:
    if len(pixel) != 3:
        raise ValueError(f"{label} must have exactly 3 channels")
    r, g, b = (float(pixel[0]), float(pixel[1]), float(pixel[2]))
    for channel_name, value in (("r", r), ("g", g), ("b", b)):
        if not math.isfinite(value):
            raise ValueError(f"{label}.{channel_name} must be finite, got {value}")
        if value < 0.0 or value > 1.0:
            raise ValueError(f"{label}.{channel_name} must be in [0, 1], got {value}")
    return (r, g, b)


def _copy_rgbcct(color: RGBCCTColor) -> RGBCCTColor:
    return RGBCCTColor(
        r=color.r,
        g=color.g,
        b=color.b,
        warm_white=color.warm_white,
        cool_white=color.cool_white,
    )


def _add_rgb(base: ColorRGB, incoming: ColorRGB) -> ColorRGB:
    return tuple(min(1.0, max(0.0, base[index] + incoming[index])) for index in range(3))  # type: ignore[return-value]


def _add_rgbcct(base: RGBCCTColor, incoming: RGBCCTColor) -> RGBCCTColor:
    return RGBCCTColor(
        r=min(1.0, max(0.0, base.r + incoming.r)),
        g=min(1.0, max(0.0, base.g + incoming.g)),
        b=min(1.0, max(0.0, base.b + incoming.b)),
        warm_white=min(1.0, max(0.0, base.warm_white + incoming.warm_white)),
        cool_white=min(1.0, max(0.0, base.cool_white + incoming.cool_white)),
    )
