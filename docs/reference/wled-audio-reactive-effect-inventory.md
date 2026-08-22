# WLED v16.0.1 Audio Reactive effect inventory

Status: source-level portability inventory; no protocol change is proposed here.

## Pinned upstream and audit boundary

This inventory is pinned to the official WLED [`v16.0.1` release](https://github.com/wled/WLED/releases/tag/v16.0.1), commit [`29b389df1c1aaec6ff53aea742d17063b985906c`](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c). It does not use `main`.

The exhaustive set is defined mechanically: every effect registered in pinned [`FX.cpp`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp) whose metadata capability suffix contains `v` (volume reactive) or `f` (frequency reactive) is included. Numeric IDs come from pinned [`FX.h`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.h#L280-L371). This produces 37 effects: 29 ordinary effects and 8 particle-system effects.

The input contract is checked against the pinned usermod export table and wire packet:

- [`u_data[0..7]`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L1353-L1375) exports `volumeSmth`, `volumeRaw`, `fftResult[16]`, `samplePeak`, `FFT_MajorPeak`, magnitude, `maxVol`, and `binNum` to local effects.
- The 44-byte [Audio Sync V2 packet](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L799-L811) carries `sampleRaw`, `sampleSmth`, `samplePeak`, `fftResult[16]`, `FFT_Magnitude`, and `FFT_MajorPeak`. Its `transmitAudioData()` path clamps each transmitted FFT byte to `0..254`; the RK3588 input adapter therefore normalizes live V2 spectrum as `byte / 254.0`, not by the internal uint8 ceiling.
- `fftBin` is not in the V2 packet. It is also not exported in v16.0.1's eight-entry `u_data` table, and no explicit v16.0.1 Audio Reactive effect reads it. It must not be claimed as available from this wire format.

Generic host mappings are `sampleRaw` → `raw_level`, `sampleSmth` → `loudness`, `fftResult[16]` → `spectrum`, `samplePeak` → `peak`, `FFT_MajorPeak` → `dominant_frequency`, and `FFT_Magnitude` → `dominant_magnitude`. These are input features, not WLED-branded model fields.

## Classification

- **A — DIRECT_V2:** every audio value used by the effect is carried directly by Audio Sync V2. Porting the renderer and state machine is still work, but no audio-input invention is required.
- **B — V2_APPROXIMATED:** V2 carries enough to preserve the visible audio trigger, but not an effect-owned analyzer control. The current packet can drive an approximation; exact WLED control semantics would need an extension or an agreed local policy.
- **C — INPUT_EXTENSION_REQUIRED:** the visible principle requires an audio signal absent from V2, such as `fftBin`, and cannot be meaningfully driven without extending the input contract.

Totals: **A = 34, B = 3, C = 0, total = 37**. The zero in C is a source finding, not permission to add `fftBin`: pinned v16.0.1 simply has no explicit registered effect that consumes it.

In the table, `R` = `volumeRaw`/`raw_level`, `S` = `volumeSmth`/`loudness`, `F16` = `fftResult[16]`/`spectrum`, `P` = `samplePeak`/`peak`, `M` = `FFT_MajorPeak` and/or magnitude. A check means the effect's active path reads that signal; `—` means it does not. The `fftBin` column is deliberately explicit.

## Complete inventory

| Effect (ID) | Form | R | S | F16 | P | M | `fftBin` | Other audio dependency | Visual principle | Palette / color mechanism | Class |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|---|:---:|
| [Pixels (128)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7173-L7194) | 1D | — | ✓ | — | — | — | — | — | Fade a trail and place loudness-bright random pixels. | Segment palette indexed by recent loudness samples, blended with secondary color. | A |
| [Pixelwave (129)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7061-L7083) | 1D | ✓ | — | — | — | — | — | — | Inject an amplitude-bright center pixel and shift it outward as a mirrored wave. | Segment palette mixed with secondary color. | A |
| [Juggles (130)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6924-L6936) | 1D | — | ✓ | — | — | — | — | — | Multiple beat-sine dots juggle over a fading trail; loudness sets brightness. | Segment palette by dot index. | A |
| [Matripix (131)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6942-L6970) | 1D | ✓ | — | — | — | — | — | — | Shift a single raw-amplitude-bright pixel through the strip. | Time-indexed segment palette mixed with secondary color. | A |
| [Gravimeter (132)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6806-L6909) | 1D | — | ✓ | — | — | — | — | — | Symmetric center meter with a falling top marker. | Segment palette across distance; authored colors remain renderer inputs. | A |
| [Plasmoid (133)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7094-L7118) | 1D | — | ✓ | — | — | — | — | — | Moving sine/noise brightness field gated by loudness. | Segment palette by local brightness, blended with secondary color. | A |
| [Puddles (134)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7125-L7167) | 1D | ✓ | ✓ | — | — | — | — | Shared base reads both; non-peak branch is driven by `volumeRaw`. | Spawn fading random puddles whose width follows raw amplitude. | Random segment-palette color per puddle. | A |
| [Midnoise (135)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6976-L7000) | 1D | — | ✓ | — | — | — | — | — | Draw a centered, loudness-sized Perlin-noise band over a fading field. | Segment palette indexed by Perlin noise. | A |
| [Noisemeter (136)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7032-L7055) | 1D | ✓ | ✓ | — | — | — | — | — | Raw level selects bar width; smoothed level animates the internal noise field. | Segment palette indexed by Perlin noise. | A |
| [Freqwave (137)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7384-L7427) | 1D | — | ✓ | — | — | ✓ | — | `FFT_MajorPeak`; lower/upper range and preamp sliders. | Shift a wave history outward; dominant frequency chooses hue and loudness chooses value. | Effect-local HSV mapping, not a global frequency-color rule. | A |
| [Freqmatrix (138)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7290-L7334) | 1D | — | ✓ | — | — | ✓ | — | `FFT_MajorPeak`; lower/upper range and sensitivity sliders. | Shift a matrix-style history; frequency selects hue and loudness sets brightness. | Effect-local HSV mapping. | A |
| [GEQ (139)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7542-L7595) | 2D | — | — | ✓ | — | — | — | Band-count/bin selection and per-column peak history. | Draw equalizer columns and falling peak caps from the 16 bands. | Segment palette by band index, with optional bar-color mode. | A |
| [Waterfall (140)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7488-L7535) | 1D | — | — | — | ✓ | ✓ | — | Effect writes local `binNum` and `maxVol`. | Shift a frequency-colored/magnitude-bright history and insert a distinct peak marker. | Dominant frequency indexes the segment palette; peak uses a fixed accent. | B |
| [Freqpixels (141)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7344-L7366) | 1D | — | — | — | — | ✓ | — | — | Place random pixels whose hue follows dominant frequency and brightness follows magnitude. | Segment palette indexed by log-scaled dominant frequency. | A |
| [Noisefire (143)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7007-L7026) | 1D | — | ✓ | — | — | — | — | — | Animate a fire-like noise texture; loudness controls palette brightness. | Local fire palette rather than a frequency palette. | A |
| [Puddlepeak (144)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7125-L7162) | 1D | ✓ | ✓ | — | ✓ | — | — | Effect writes local `binNum` and `maxVol`; raw read belongs to shared base, peak branch sizes from smoothed level. | Spawn a fading puddle only on a detected peak, sized by loudness. | Random segment-palette color per puddle. | B |
| [Noisemove (145)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7433-L7448) | 1D | — | — | ✓ | — | — | — | — | Map active FFT bands to moving Perlin-noise positions and band-amplitude brightness. | Segment palette by band number, blended with secondary color. | A |
| [Ripple Peak (148)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6651-L6717) | 1D | — | — | — | ✓ | ✓ | — | Effect writes local `binNum` and `maxVol`. | A peak starts symmetric decaying ripples; dominant frequency selects ripple color. | Segment palette indexed by log-scaled dominant frequency. | B |
| [Freqmap (155)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7259-L7284) | 1D | — | — | — | — | ✓ | — | — | Map dominant frequency to pixel position/color and magnitude to brightness over a fade trail. | Segment palette indexed by log-scaled dominant frequency. | A |
| [Gravcenter (156)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6806-L6892) | 1D | — | ✓ | — | — | — | — | — | Loudness grows a symmetric center block while previous energy falls/fades. | Segment palette across distance with authored background/accent colors. | A |
| [Gravcentric (157)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6806-L6900) | 1D | — | ✓ | — | — | — | — | — | Loudness launches symmetric center energy with a different gravity/fade mode. | Segment palette across distance. | A |
| [Gravfreq (158)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6806-L6918) | 1D | — | ✓ | — | — | ✓ | — | — | Loudness controls symmetric extent; dominant frequency controls its color. | Segment palette indexed by log-scaled dominant frequency. | A |
| [DJ Light (159)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7230-L7253) | 1D | — | — | ✓ | — | — | — | — | Build center RGB from high/mid/low bands, modulate brightness, then shift outward. | Direct band-to-RGB composition; no palette lookup. | A |
| [Funky Plank (160)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7601-L7646) | 2D | — | — | ✓ | — | — | — | — | Map FFT bands to colored columns and scroll the result across the matrix. | HSV hue/value derived per band. | A |
| [Blurz (163)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7199-L7224) | 1D | — | — | ✓ | — | — | — | — | Step through FFT bands, place amplitude-bright random pixels, and blur/fade them. | Segment palette indexed by band amplitude, blended with authored mix color. | A |
| [Waverly (165)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6762-L6790) | 2D | — | ✓ | — | — | — | — | — | Scale mirrored Perlin-wave column heights by loudness. | Segment palette mapped over column height. | A |
| [Swirl (175)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L6725-L6755) | 2D | ✓ | ✓ | — | — | — | — | — | Six beat-sine points orbit in symmetry; raw level sets brightness and smoothed level shifts color. | Segment palette with time/loudness-driven indices. | A |
| [Rocktaves (185)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7454-L7481) | 1D | — | — | — | — | ✓ | — | — | Fold dominant frequency by octave so equal pitch classes share color; magnitude sets value. | Effect-local HSV pitch-class mapping. | A |
| [Akemi (186)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L7687-L7748) | 2D | — | — | ✓ | — | — | — | Character sprite geometry and optional simulated sound fallback. | Animate a face/character from bass and draw side GEQ bars from all bands. | Authored face/body colors plus segment palette for GEQ bars. | A |
| [PS Spray (197)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L8941-L9006) | 2D particle | ✓ | ✓ | — | — | — | — | Particle-system physics and emitter controls. | Volume controls emission cadence, speed, lifetime, variance, and hue drift. | Particle hue/segment-palette rendering. | A |
| [PS GEQ 2D (198)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L9014-L9079) | 2D particle | — | — | ✓ | — | — | — | Particle-system physics; threshold derived from intensity. | Place 16 emitters across X; each band's amplitude controls emission and speed. | Particle hue/segment-palette rendering. | A |
| [PS GEQ Nova (199)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L9088-L9150) | 2D particle | — | — | ✓ | — | — | — | Particle-system physics; rotating radial source geometry. | Sixteen spectrum-driven emitters radiate from the center as a rotating nova. | Particle hue/segment-palette rendering. | A |
| [PS Blobs (201)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L9236-L9302) | 2D particle | — | ✓ | — | — | — | — | Real-AR check; otherwise normal particle behavior remains. | Optionally pulse selected particle sizes from loudness. | Particle palette and authored particle properties. | A |
| [PS GEQ 1D (212)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L10355-L10420) | 1D particle | — | — | ✓ | — | — | — | Particle-system sources and threshold derived from intensity. | Distribute spectrum-driven particle sources along the strip. | Particle hue/segment-palette rendering. | A |
| [PS Sonic Stream (214)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L10490-L10586) | 1D particle | — | — | ✓ | — | — | — | Selected base bin; optional mid-band modulation/filter/push controls. | Turn selected-bin energy into a directional particle stream; mids can modulate it. | Authored/particle color with optional position/palette behavior. | A |
| [PS Sonic Boom (215)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L10593-L10676) | 1D particle | — | — | ✓ | — | — | — | Selected base bin; optional mid-band modulation/filter controls. | Selected-bin energy triggers a concentrated particle boom at an authored position. | Authored/particle color with optional position mapping. | A |
| [PS Springy (216)](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L10682-L10844) | 1D particle | — | — | ✓ | — | — | — | AR is optional; selected adjacent-bin pair drives a spring-mass system. | Kick the center mass from spectrum energy, then let spring physics propagate motion. | Particle/segment palette controlled by hue and mode settings. | A |

## Why the three B effects are not A

`Ripple Peak`, `Puddlepeak`, and `Waterfall` all receive `samplePeak`, which is on the V2 wire. They also write `binNum` and `maxVol` back into the local WLED analyzer so their UI can choose the detector bin and threshold. Those two control-coupled analyzer variables are not transmitted. A receiver can preserve the incoming peak event and therefore approximate the visible effect, but it cannot make the effect's local “Select bin” and “Volume (min)” sliders mean exactly what they mean on the analyzing ESP32 node running upstream WLED. Exact parity requires either a defined local peak detector over available bands or an explicit input/control extension. It must not be manufactured silently.

## Palette mechanism and audio boundary

WLED has two distinct palette mechanisms in this area:

1. Effects use the selected segment palette through `SEGMENT.color_from_palette(...)` or `ColorFromPalette(SEGPALETTE, ...)`. Audio may choose the palette index or brightness, but the selected palette remains authored renderer state.
2. When enabled, the Audio Reactive usermod creates three [live usermod palettes](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L2227-L2303). They are regenerated from `fftResult[16]`: one combines bands 0/4/10 into RGB anchors, and two map lower FFT bands to HSV anchors. These palettes do not add a new audio signal; they are a WLED-side rendering of `spectrum`.

Therefore a port may reproduce an effect's palette lookup or choose an authored project palette, but it must document that choice. `dominant_frequency` has no global visual meaning and must never impose a project-wide frequency-to-color mapping. In WLED it selects color only inside effects that explicitly implement such a mapping (`Freqwave`, `Freqmatrix`, `Freqpixels`, `Freqmap`, `Gravfreq`, `Rocktaves`, `Ripple Peak`, and `Waterfall`).

## Porting priority

Recommended order, based on direct V2 coverage, renderer complexity, and usefulness on the current 1D strip topology:

1. **P0 — direct 1D primitives:** `Noisemeter` (136), `Pixelwave` (129), `Pixels` (128), `Blurz` (163), and `DJ Light` (159). Together they cover raw/smoothed volume, spectrum, trails, mirrored motion, noise, and palette/direct-RGB color without new inputs.
2. **P1 — direct frequency semantics:** `Freqmap` (155), `Freqpixels` (141), `Rocktaves` (185), and `Puddles` (134). Keep each effect's frequency/color rule local.
3. **P2 — topology-specific renderers:** `GEQ` (139), `Funky Plank` (160), `Waverly` (165), `Swirl` (175), and `Akemi` (186) only when a 2D target is a real product requirement.
4. **P3 — particle-system family:** IDs 197, 198, 199, 201, 212, 214, 215, and 216 after a reusable particle runtime exists; do not clone eight independent ad hoc simulations.
5. **Hold for policy/extension decision:** the three B effects. Their incoming peak can be rendered now, but their bin/threshold sliders must not pretend to control data that Audio Sync V2 does not provide.

## Re-audit procedure

For a future WLED version, pin the release tag and full commit, enumerate every `FX.cpp` metadata entry ending in `v` or `f`, diff the numeric IDs in `FX.h`, inspect every corresponding function for `u_data` indices and analyzer side effects, then compare the usermod export table with the packed wire struct. Update totals only from that evidence. Never carry this inventory forward from `main` or from effect names alone.
