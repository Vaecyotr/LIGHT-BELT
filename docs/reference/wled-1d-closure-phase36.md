# WLED v16.0.1 → LIGHT-BELT 1D closure (Phase 36)

> Closure date: 2026-08-23
>
> Upstream research remains pinned to WLED v16.0.1 commit
> `29b389df1c1aaec6ff53aea742d17063b985906c`.
>
> Software portability classification only. Visible output and all physical behavior are
> **NOT HARDWARE VERIFIED**.

## Final conclusion

Phase 36 re-audited the original 25 ordinary 1D visual families from
`wled-1d-primitive-gap-analysis.md` against the 22 current native effects. Phase 33 supplied
`history_stream`; Phase 35 supplied `coherent_noise_field`. No other family requires a new
product-relevant state-evolution mechanism.

`NEW_PRIMITIVE = 0`

The four reusable gaps are closed as opt-in parameters without aliases or new effect IDs:

- `step_pulse.duty_cycle`, the HIGH-state fraction with the historical low-first phase
  (default `0.5`; `0` always low, `1` always high);
- `breath.waveform = sine|triangle|smoothstep` (default `sine`);
- `color_wipe.edge_softness_px` and `progress_curve = linear|smoothstep`
  (defaults `0` / `linear`);
- `color_wave.waveform = linear|sine|triangle|saw` and `hue_span_degrees`
  (defaults `linear` / `120`).

Explicit defaults reproduce the omitted-parameter output. The registry remains exactly 22
internal effects. No WLED effect aliases, FX/SX/IX/FP fields, Segment ownership, palette IDs,
topology, protocol, firmware, or APP V1 fields were added.

## Original 25-family final disposition

| # | Original visual family | Final disposition | Native expression / boundary |
|---:|---|---|---|
| 1 | Uniform fill | `COVERED` | `static` |
| 2 | External pixel-field copy | `OUT_OF_SCOPE` | Cross-renderer framebuffer/Segment ownership is outside the cabin authoring model. |
| 3 | Hard gate / flash | `BOUNDED_PARAM_EXTENSION` | `step_pulse.duty_cycle`; burst/jitter recipes do not justify a primitive. |
| 4 | Global brightness envelope | `BOUNDED_PARAM_EXTENSION` | `breath.waveform`; heartbeat/fade are envelope choices. |
| 5 | Global color signal | `DEFER_TO_COLORSOURCE_PHASE39` | Current timeline/calm behavior remains; generalized color sampling belongs to the shared ColorSource. |
| 6 | Wipe / progress front | `BOUNDED_PARAM_EXTENSION` | `color_wipe.edge_softness_px`, `progress_curve`, and common `origin`. |
| 7 | External / target meter | `COVERED` | Phase 33 `color_wipe.progress_source` plus slew. |
| 8 | Periodic chase mask | `COVERED` | `chase`, `theater_phase`, `flowing_bands`. |
| 9 | Moving head / scanner / comet | `COVERED` | `single_dot`; Phase 33 comet count/spacing/trajectory. |
| 10 | Coordinate-to-palette field | `DEFER_TO_COLORSOURCE_PHASE39` | Geometry exists; shared positional palette semantics belong to ColorSource. |
| 11 | Analytic periodic wave | `BOUNDED_PARAM_EXTENSION` | `color_wave.waveform` and `hue_span_degrees`. |
| 12 | Coherent noise field | `COVERED_BY_PHASE35` | `coherent_noise_field`. |
| 13 | History / time-to-space stream | `COVERED` | Phase 33 `history_stream`. |
| 14 | Per-pixel event lifecycle | `COVERED` | Phase 33 `twinkle` width, blur, gate and birth gain. |
| 15 | Stochastic dissolve / latch | `COVERED` | `twinkle` lifecycle composed with wipe/transition authoring. |
| 16 | Flicker / candle | `COVERED` | Breath waveform and stochastic event/envelope recipes. |
| 17 | 1D heat transport | `COVERED` | `heat_fire`. |
| 18 | Expanding ripple | `COVERED` | Phase 33 `onset_ripple` origin, propagation and wrap. |
| 19 | Repeated spots / lobes | `COVERED` | `flowing_bands` or shaped `color_wave`. |
| 20 | Independent movers | `COVERED` | Phase 33 multi-emitter `comet` count/spacing/trajectory. |
| 21 | Soft moving wave packets | `COVERED` | Shaped `color_wave` or `comet` trail. |
| 22 | Firework / spark systems | `OUT_OF_SCOPE` | Requires a particle/fragment runtime with no cabin product need. |
| 23 | Ballistic / physical objects | `OUT_OF_SCOPE` | Gravity/collision/object simulation is not a reusable cabin primitive. |
| 24 | Scripted semantic scene / game | `OUT_OF_SCOPE` | Product-semantic recipes belong in Shows, not effect primitives. |
| 25 | External image / GIF | `OUT_OF_SCOPE` | Asset decoding and image-frame sampling are not 1D lighting-language requirements. |

Totals: `COVERED=13`, `COVERED_BY_PHASE35=1`, `BOUNDED_PARAM_EXTENSION=4`,
`DEFER_TO_COLORSOURCE_PHASE39=2`, `OUT_OF_SCOPE=5`, `NEW_PRIMITIVE=0`.

## Audio Reactive cross-check

The earlier 28-effect 1D Audio Reactive subset introduces no separate visual primitive universe.
Its six history-shaped entries map to `history_stream`; its four coherent-noise-shaped entries map
to `coherent_noise_field`; mover, meter, event and ripple variants map to the covered families above.
The four particle/physics entries remain out of scope. Audio measurements retain no global color
meaning; palette/color drivers are deliberately deferred to Phase 39.

## Closure declaration

**WLED 1D portability research CLOSED.**

Bug fixes and compatibility repairs remain allowed. Proactive WLED effect migration, recipe aliases,
and mode-by-mode parity work are closed for the product-relevant RK3588-hosted 1D cabin scope.
