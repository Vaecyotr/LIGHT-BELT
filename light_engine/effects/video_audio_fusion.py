"""VIDEO_AUDIO_FUSION - core demo mode.

Video determines base hue and zone colors (via per-zone video_zone).
Audio RMS drives brightness.
Bass drives pulse/diffusion.
Mid affects saturation.
Treble affects subtle shimmer (capped intensity).
Confident beat phase reinforces the bass pulse.
Silence preserves ambient video light.
"""

from __future__ import annotations

import colorsys
import math

from light_engine.config import Config
from light_engine.color import rgb_to_rgbcct
from light_engine.effects.base import BaseEffect, apply_common_intensity, runtime_float
from light_engine.mapping.resolve import resolve_video_color, sample_edge_pixels
from light_engine.models import (
    DigitalStrip,
    EffectContext,
    PixelFrame,
    ZoneOutput,
)
from light_engine.util import AttackReleaseEnvelope, ColorSmoother


def _apply_mid_saturation(
    rgb: tuple[float, float, float],
    mid: float,
) -> tuple[float, float, float]:
    """Increase saturation gently while preserving hue and value."""

    hue, saturation, value = colorsys.rgb_to_hsv(*rgb)
    boosted = min(1.0, saturation * (1.0 + 0.2 * mid))
    return colorsys.hsv_to_rgb(hue, boosted, value)


class VideoAudioFusionEffect(BaseEffect):
    """Fusion of video color and audio energy for dynamic lighting."""

    def __init__(self, name: str = "video_audio_fusion"):
        super().__init__(name)
        config = Config.get_instance()
        self._video_weight = config.get("effects.video_audio_fusion.video_weight", 0.65)
        self._audio_weight = config.get("effects.video_audio_fusion.audio_weight", 0.35)
        self._bass_boost = config.get("effects.video_audio_fusion.bass_boost", 1.5)
        self._treble_limit = config.get("effects.video_audio_fusion.treble_limit", 0.4)

        self._brightness_env = AttackReleaseEnvelope(attack=0.3, release=0.1)
        self._bass_env = AttackReleaseEnvelope(attack=0.5, release=0.15)
        self._color_sm = ColorSmoother(alpha=0.12)

    def process(self, ctx: EffectContext) -> PixelFrame:
        video_weight = runtime_float(ctx, "video_weight", self._video_weight)
        audio_weight = runtime_float(ctx, "audio_weight", self._audio_weight)
        bass_boost = runtime_float(ctx, "bass_boost", self._bass_boost)
        treble_limit = runtime_float(ctx, "treble_limit", self._treble_limit)
        vf = ctx.video_features
        af = ctx.audio_features

        # ---- Audio features (with safe defaults) ----
        audio_rms = af.rms if af else 0.0
        bass = af.bass if af else 0.0
        mid = af.mid if af else 0.0
        treble = af.treble if af else 0.0
        beat = af.beat if af else False
        silent = af.silence if af else True

        # ---- Brightness: blend video + audio ----
        # Zone RGB carries picture luminance. Multiplying it by global luma
        # again crushes dark scenes before the output gamma and quantization.
        video_gain = 1.0 if vf else 0.5
        target_brightness = video_gain * video_weight + audio_rms * audio_weight
        if silent:
            target_brightness = max(target_brightness, video_gain * 0.3)

        # Edge pixels already retain picture contrast. Follow changes in sound
        # level within a few output ticks rather than holding the last accent.
        has_edges = vf is not None and bool(vf.edge_profiles)
        self._brightness_env.attack = 0.45 if has_edges else 0.3
        self._brightness_env.release = 0.25 if has_edges else 0.1
        bri = self._brightness_env.update(target_brightness, ctx.delta_time)

        # ---- Bass pulse ----
        music = ctx.music_control_state
        if music is None:
            pulse = bass
            accent = 0.3 if beat else 0.0
        else:
            pulse = music.bass_pulse
            accent = 0.3 * music.tempo_confidence * max(0.0, 1.0 - 4.0 * music.beat_phase)
        # Coincident events share a single envelope and cannot stack two flashes.
        target_pulse = min(1.0, max(pulse * bass_boost, accent))
        bass_pulse = self._bass_env.update(0.0 if silent else target_pulse, ctx.delta_time)

        # ---- Global smoothed average (for blend) ----
        avg_rgb = vf.average_rgb if vf else (0.02, 0.02, 0.05)
        sr, sg, sb = self._color_sm.update(*avg_rgb)

        # ---- Treble shimmer cap ----
        treble_shimmer = 0.0 if silent else min(treble_limit, treble * 0.15) * audio_rms

        # ============================================================
        # Digital strips: each strip uses its own video_zone color
        # ============================================================
        strips = []
        for sd in ctx.mode_parameters.get("strip_defs", []):
            sid = sd["id"]
            n = sd["pixel_count"]
            if n == 0:
                continue
            video_zone = sd.get("video_zone", "center")
            direction = sd.get("direction", "forward")

            # Resolve this strip's own video color
            base_rgb = resolve_video_color(video_zone, vf, sid)
            zone_r = base_rgb[0] * 0.7 + sr * 0.3
            zone_g = base_rgb[1] * 0.7 + sg * 0.3
            zone_b = base_rgb[2] * 0.7 + sb * 0.3
            zone_r, zone_g, zone_b = _apply_mid_saturation(
                (zone_r, zone_g, zone_b), mid
            )
            profile = vf.edge_profiles.get(video_zone) if vf else None
            colors = sample_edge_pixels(profile, n) if profile else [(zone_r, zone_g, zone_b)] * n

            pixels = []
            for i in range(n):
                dist_from_center = abs(i - n / 2) / max(1, n / 2)
                pulse_factor = bass_pulse * (1.0 - dist_from_center * 0.7)

                level = bri + pulse_factor * 0.3
                if treble_shimmer > 0.001:
                    phase = math.tau * (i / n - ctx.timestamp)
                    level *= 1.0 + treble_shimmer * math.sin(phase)
                r, g, b = colors[i]
                if profile and max(r, g, b) * level > 1.0:
                    level = 1.0 / max(r, g, b)
                pr, pg, pb = r * level, g * level, b * level

                pixels.append((
                    max(0.0, min(1.0, pr)),
                    max(0.0, min(1.0, pg)),
                    max(0.0, min(1.0, pb)),
                ))

            # Direction reverse
            if direction == "reverse":
                pixels = list(reversed(pixels))

            strips.append(DigitalStrip(strip_id=sid, pixel_count=n, pixels=pixels))

        # ============================================================
        # RGB+CCT zones: each zone uses its own video_zone color
        # ============================================================
        zones = []
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zid = zd["id"]
            video_zone = zd.get("video_zone", "center")

            base_rgb = resolve_video_color(video_zone, vf, zid)
            zr = base_rgb[0] * 0.7 + sr * 0.3
            zg = base_rgb[1] * 0.7 + sg * 0.3
            zb = base_rgb[2] * 0.7 + sb * 0.3
            zr, zg, zb = _apply_mid_saturation((zr, zg, zb), mid)
            zone_bri = bri + bass_pulse * 0.2
            peak = max(zr, zg, zb)
            if peak * zone_bri > 1.0:
                zone_bri = 1.0 / peak
            zones.append(ZoneOutput(
                zone_id=zid,
                color=rgb_to_rgbcct(zr * zone_bri, zg * zone_bri, zb * zone_bri),
            ))

        zone_mapping = {}
        for sd in ctx.mode_parameters.get("strip_defs", []):
            zone_mapping[sd["id"]] = sd.get("video_zone", "center")
        for zd in ctx.mode_parameters.get("zone_defs", []):
            zone_mapping[zd["id"]] = zd.get("video_zone", "center")

        return apply_common_intensity(
            PixelFrame(
                timestamp=ctx.timestamp,
                sequence=ctx.sequence,
                strips=strips,
                zones=zones,
                metadata={
                    "video_rgb": avg_rgb,
                    "audio_rms": round(audio_rms, 3),
                    "bass": round(bass, 3),
                    "beat": beat,
                    "silent": silent,
                    "zone_mapping": zone_mapping,
                },
            ),
            ctx.intensity,
        )

    def reset(self) -> None:
        self._brightness_env.reset(0.0)
        self._bass_env.reset(0.0)
        self._color_sm.reset(0.0, 0.0, 0.0)
