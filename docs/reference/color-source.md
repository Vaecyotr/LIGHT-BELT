# Internal Show v2 ColorSource

Status: Phase 39 software contract. This is an INTERNAL/YAML authoring surface;
it is not part of Host/APP API V1. Physical output remains **NOT HARDWARE
VERIFIED**.

## Compatibility boundary

`ColorSource` is an explicit cue-level `color_source` block. It does not alter
or reinterpret the existing cue-level `color` modes `effect_default`, `solid`,
or `palette`, and it does not replace effect parameters named `color_source`
in `chase` or `twinkle`. The two blocks may coexist:

```yaml
color:
  mode: palette
  colors: [[1, 0, 0], [0, 1, 0]]
effect:
  mode: fixed
  id: twinkle
  params:
    color_source: random   # historical effect-local enum
color_source:              # new explicit cue-level source
  type: video_average
  fallback: [0, 0, 0]
```

ColorSource is Show v2 only and fixed-effect only. Effects classified
`NOT_APPLICABLE` reject the block instead of inventing artificial semantics.

## Source types

### Timeline

```yaml
color_source:
  type: timeline
  interpolation: rgb_linear
  keyframes:
    - {time: 0, color: [1, 0, 0]}
    - {time: 4, color: [0, 0, 1]}
```

Time is cue-local. At least two strictly increasing, non-negative keyframes
are required. Sampling clamps to the endpoint colors and interpolates RGB
linearly between keyframes. This block is independent from an effect's
existing `params.color_timeline`.

### Spatial palette

```yaml
color_source:
  type: spatial_palette
  palette: [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
```

For a logical path of `N > 1` pixels, pixel `i` uses coordinate
`i / (N - 1)`. Therefore coordinate 0 is exactly the first palette color and
coordinate 1 is exactly the last; intermediate colors are piecewise RGB-linear.
A one-pixel path samples coordinate 0.5. A `virtual_path` is rendered and
sampled as one continuous logical path before member splitting, including
across physical-controller boundaries.

### Video average and dominant

```yaml
color_source: {type: video_average, fallback: [0, 0, 0]}
color_source: {type: video_dominant, fallback: [0, 0, 0]}
```

These sources read only `VideoFeatures.average_rgb` or
`VideoFeatures.dominant_rgb`. They do not consult per-target `zone_colors` and
do not perform per-virtual-path-member video-zone remapping. Existing
zone-specific video effects retain ownership of that behavior. When video is
absent, the required authored RGB fallback is used.

### Audio spectrum palette

```yaml
color_source:
  type: audio_spectrum_palette
  palette: [[0.1, 0.0, 0.8], [1.0, 0.7, 0.0]]
  fallback: [0, 0, 0]
```

For a positional sample at coordinate `p`, the sampler linearly samples the
current 16-band spectrum at `p * 15`. That normalized band energy then samples
the authored palette at `energy * (palette_length - 1)`. A global sample uses
the arithmetic mean of the 16 bands. No global bass/red or treble/blue meaning
exists. When `AudioFeatures` is absent, the required authored RGB fallback is
used. When `AudioFeatures` exists but the analyzer did not supply a spectrum,
the established model contract exposes sixteen zero bands; this is a present
zero-energy spectrum and therefore samples palette coordinate 0 rather than
the missing-audio fallback.

### Dominant-frequency palette

```yaml
color_source:
  type: dominant_frequency_palette
  frequency_min_hz: 80
  frequency_max_hz: 8000
  palette: [[1, 0, 0], [0, 0, 1]]
  fallback: [0, 0, 0]
```

The coordinate is
`clamp((dominant_frequency - frequency_min_hz) /
(frequency_max_hz - frequency_min_hz), 0, 1)`. Bounds, palette, and fallback
are mandatory. Reversing the authored palette reverses the color tendency;
the engine assigns no global frequency-to-color meaning.

## Runtime sampler and fallback state

One internal `ColorSampler` owns all source interpretation. It exposes:

- current/global sampling;
- normalized-position sampling;
- deterministic event sampling keyed by cue seed and logical event identity.

GLOBAL renderers receive one current color. POSITIONAL renderers sample their
complete logical path and retain the renderer's existing intensity envelope.
EVENT renderers (`twinkle` and `onset_ripple`) sample once at logical event
birth, so an event retains its birth color while it decays or propagates.
Event identity does not depend on the module/global RNG, physical mapping, or
virtual-path member split.

For GLOBAL use of `spatial_palette`, current color is the palette midpoint.
For GLOBAL use of `audio_spectrum_palette`, current color is driven by the
arithmetic mean band energy. These definitions avoid inventing a physical
coordinate for a globally uniform visual.

The Phase 39 fallback contract is deliberately a required fixed RGB color for
video and audio sources. There is no `retain_previous` mode and therefore no
hidden retained-color state to reset. Runtime reset plus replay reconstructs
timeline, input, and deterministic event colors from authored data and replayed
features.

## Interaction with effect brightness and intensity envelopes

**Core Concept (通俗解释与常见误区)**:
ColorSource 主要替换颜色采样策略（RGB 色彩生成），但底层 effect 原 renderer 产生的亮度包络（brightness/intensity envelope）仍然保留。

- 当启用 `color_source` 时，基础 renderer 仍然计算空间和时间上的亮度模式（例如 `chase` 的尾部衰减、`breath` 的周期波形包络、`comet` 的拖尾淡出曲线）。
- 采样得到的 ColorSource 颜色会与原 renderer 计算出的像素亮度包络相乘。
- 旧版 `color` 块与 `color_source` 块可以并存：在支持的 effect 上，`color_source` 负责颜色生成，而 base renderer 的参数负责形态与亮度包络。

> **作者提示（避免误解）**：
> 如果作者在 ColorSource 中配置了满亮颜色（如 `[0, 0, 1]` 纯蓝），但观察到灯带输出整体偏暗或沿灯带亮度不均匀，这**不是** ColorSource 失效，而是底层 effect renderer 自身的亮度包络（如衰减、波宽、min_brightness 等）在起作用。这是设计预期的语义，无需修改 renderer。

## Live effect-support audit

The audit is stored on each live internal `EffectRegistration` and exported by
`scripts/export_authoring_contract.py`; APP V1 does not project it.

| Support | Effects |
|---|---|
| GLOBAL | `static`, `breath`, `audio_pulse`, `bass_pulse`, `calm` |
| POSITIONAL | `chase`, `comet`, `color_wipe`, `single_dot`, `theater_phase`, `flowing_bands`, `heat_fire`, `history_stream`, `coherent_noise_field` |
| EVENT | `twinkle`, `onset_ripple` |
| NOT_APPLICABLE | `color_wave`, `spectrum`, `video_ambient`, `video_audio_fusion`, `demo`, `step_pulse` |

Input-native and multi-color effects in `NOT_APPLICABLE` keep their established
meaning. The engine does not force them into a generic recoloring model.
