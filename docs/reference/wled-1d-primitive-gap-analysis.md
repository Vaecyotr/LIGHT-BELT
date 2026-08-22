# WLED v16.0.1 → LIGHT-BELT 1D primitive gap analysis

> 审计日期：2026-08-22
>
> 阶段：Phase 32 research closeout；**不授权实现，不进入 Phase 33**
>
> 唯一 WLED 上游：v16.0.1，commit
> [`29b389df1c1aaec6ff53aea742d17063b985906c`](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c)
>
> 所有灯带观感、组播、跨板接缝和真实输出均 **NOT HARDWARE VERIFIED**。

## 1. 结论先行

WLED mode ID 不是 LIGHT-BELT visual primitive。按状态模型、空间几何和时间推进去掉方向、速度、颜色、
palette、数量、宽度、尾迹和 audio driver 后，本次结论是：

- LIGHT-BELT 的 20 个 native effect ID 可归并为 **8 个核心 1D 像素 renderer families**；此外有
  2 个输入/组合 recipe（`spectrum`、`video_audio_fusion`）和 1 个 meta-effect（`demo`）。
- 固定 WLED 源码中有 **124 个 ordinary 1D effects**，去重后是 **25 个 visual families**。
  默认 particle-system enabled、GIF disabled 构建只注册其中 118 个 slots；本研究使用源码全集 124，
  避免让编译开关改变能力判断。
- 固定的 37 个显式 Audio Reactive effects 中，**28 个是 1D**：24 ordinary + 4 particle。
  它们去声后是 17 个 visual families；13 个非粒子 family 均可映回上述 25 个普通 family，
  4 个 particle family 保持范围外。因此当前实现建议的 family 宇宙仍是 **25**，不是
  `124 + 28` 个待迁移 ID。
- 25 个 family 的处理结论是：`EXISTING_PRIMITIVE=2`、`PARAM_EXTENSION=16`、
  `NEW_PRIMITIVE=2`、`OUT_OF_SCOPE=5`。
- 只有两个候选通过“当前不能自然表达、不是参数差异、覆盖多个 recipe、适配 1D +
  `virtual_path`”四项门槛：**history/time-to-space stream** 与
  **coherent noise field**。本轮只建议，不实现。

## 2. 口径与边界

“primitive”在本文中指可复用的像素状态/几何/时间推进机制，不指名称、默认参数、WLED slot、
palette ID 或某个输入到颜色的 recipe。下列差异不能单独产生 LIGHT-BELT effect ID：

- start/end/center/edges、forward/reverse/bidirectional；
- speed、width、gap、count、spacing、trail、decay；
- solid color、palette、color timeline；
- loudness、spectrum、peak、dominant frequency 对已有参数的驱动。

RK3588 host 仍保持 `EffectContext → BaseEffect.process() → PixelFrame`、Engine 独占 sequence/timestamp、
`OutputTransform` 只应用一次全局 brightness、物理拓扑不进入 effect。WLED `Segment`、FX/SX/IX/FP
slots、42 Hz、palette IDs、数值输出和运行时所有权均不在迁移目标内。

来源计数固定于 pinned
[`FX.cpp`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp)
与
[`FX.h`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.h)。
普通审计排除 metadata `v/f` 的 37 个显式 AR effects、2D-only paths 和 particle IDs；AR 审计再独立
加入它们，避免重复计数。

## 3. LIGHT-BELT CURRENT PRIMITIVE MATRIX

### 3.1 八个核心 1D renderer families

| # | LIGHT-BELT primitive family | 当前 IDs | 核心机制 |
|---:|---|---|---|
| 1 | uniform field + scalar signal | `static`, `breath`, `calm`, `audio_pulse`, `bass_pulse`, `step_pulse`, `video_ambient` | 全路径同色/同亮度；时间、视频或音频只产生当前标量/颜色 |
| 2 | coordinate color/wave field | `color_wave` | 空间坐标与时间相位生成连续颜色场 |
| 3 | periodic mask/train | `chase`, `theater_phase`, `flowing_bands` | 周期 width/gap mask、相位或离散 band highlight |
| 4 | moving emitter with optional trail | `single_dot`, `comet` | 一个运动头部，尾迹可为零或衰减历史 |
| 5 | progress/front fill | `color_wipe` | 标量 progress 转换为累计点亮长度 |
| 6 | stochastic event field | `twinkle` | 随机位置出生、持有颜色、随时间衰减 |
| 7 | expanding event wavefront | `onset_ripple` | 有界事件出生、传播、宽度与指数衰减 |
| 8 | diffusive scalar field | `heat_fire` | 1D heat 注入、冷却、向前扩散与固定步状态 |

`spectrum` 是把 bass/mid/treble 路由到目标 ID 的 recipe；`video_audio_fusion` 是视频场、音频包络、
中心 falloff 与 shimmer 的组合 renderer；`demo` 只是子 effect 轮播器。把三者算成通用 primitive 会夸大
LIGHT-BELT 的正交能力。

### 3.2 二十个 effect 的实际能力

公共事实：compositor 在 renderer 后统一提供 `origin=start|end|center|edges`；`virtual_path` 先按一条
连续逻辑 strip 渲染，再拆回成员，因此支持跨 strip 接缝。Cue audio modulation 目前只生成
brightness/speed/intensity multiplier，来源仅为 `music.*` 与
`audio.rms/bass/mid/treble/spectral_flux/onset`；renderer 仍可直接读取完整 `AudioFeatures`。

| Effect | primitive / state / time | 可变空间维度 | color / audio | `virtual_path` |
|---|---|---|---|---|
| `static` | 无状态 uniform fill | origin 无可见差异 | solid/timeline；B/I modulation | 均匀连续 |
| `breath` | 正弦 scalar envelope；phase/cue time | period, min brightness | solid/timeline；B/I | 均匀连续 |
| `calm` | 低亮 hue drift；phase | period | authored hue center；B/I | 均匀连续 |
| `color_wave` | HSV coordinate wave；phase | width, speed, hue rate | 内建 HSV；B/I/S | 跨接缝连续 |
| `chase` | periodic bright train；position/bounce phase | width, gap, trail, forward/reverse/bounce | static/rainbow/video；beat speed boost + B/I/S | train 连续；video 在 path 上使用合成采样 |
| `comet` | moving head + fading history | speed, tail length, decay | birth color；B/I/S | 单一 path state，尾迹跨接缝 |
| `audio_pulse` | RMS attack/release envelope | attack, release | solid/timeline；内建 RMS | 均匀连续 |
| `bass_pulse` | bass attack/release envelope | attack, release | solid/timeline；内建 bass | 均匀连续 |
| `spectrum` | 三频 target router；三 envelopes | target ID lists | 固定三色；bass/mid/treble | path 合成 ID 会丢成员路由语义 |
| `video_ambient` | video-zone uniform color + smoother | smoothing | video；B/I | path 上退化为合成 video zone |
| `video_audio_fusion` | video + spatial/audio composite；envelopes/phases | video/audio weights, boosts | video + RMS/bass/mid/treble/beat | 连续，但丢各成员 video-zone |
| `color_wipe` | cue-time progress front | speed + compositor origin | solid/timeline；B/I/S | front 跨接缝不重启 |
| `twinkle` | random birth + fade buffer | density, fade time | solid/random/真正随机 palette sample；B/I | 全 path 共用事件场 |
| `demo` | child-effect carousel | interval, child IDs | 取决于 child | 取决于 child |
| `step_pulse` | 50% duty two-level gate | period | low/high colors；B/I | 均匀连续 |
| `single_dot` | cue-time integer point | speed, forward/reverse/bounce | solid/timeline；B/I/S | 点跨接缝不重启 |
| `theater_phase` | stateless `index % 3` mask | speed + compositor origin | solid/timeline；B/I/S | mask 跨接缝连续 |
| `flowing_bands` | fixed A/B mask + one discrete C | band/gap width, gains, step rate, direction, phase | solid/timeline；B/I/S | pattern/highlight 跨接缝 |
| `onset_ripple` | 最多 16 个 event waves | speed, width, decay, floor + origin | solid/timeline；peak/onset/loudness/bands | wave 跨接缝 |
| `heat_fire` | per-path heat array，private 60 Hz ticks | cooling, spark, diffusion, spark zone | authored color × heat；B/I/S | 一条 heat field 跨接缝 |

### 3.3 已经能去掉的 WLED 名称差异

- Solid/Breathe/Wipe/Theater/Twinkle/Meteor/Scanner 分别由 `static`、`breath`、`color_wipe`、
  `theater_phase|chase`、`twinkle`、`comet`、`single_dot|chase|comet` 覆盖。
- reverse、center-out、edges-in 不产生新 renderer；使用 compositor origin。
- running-light 的 width/gap/trail/rainbow/static/video 变化属于 `chase` 参数。
- 普通 fire/ripple 已分别属于 `heat_fire` 与 `onset_ripple` family。
- 音量驱动 brightness/speed/intensity 不产生音频版 ID。

当前缺口也必须诚实记录：通用 modulator 不能直接绑定 raw level、单个 spectrum bin、peak 或
dominant frequency，也不能驱动 arbitrary effect params；palette 对多数 effect 只是每整秒选择一个当前
RGB，只有 `twinkle(color_source=palette)` 真正从整组 palette 抽样。

## 4. WLED ordinary 1D：124 IDs → 25 families

固定注册表中 120 个 ordinary entries 加上被放在“1D audio effects”段、但 metadata 无 `v/f` 且实际
不读音频的 Perlin Move、Flow Stripe、Wavesins、Shimmer，共 124。固定注册证据：
[`FX.cpp#L10975-L11138`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp#L10975-L11138)。

| # | Visual family；成员 | LIGHT-BELT 覆盖判断 | 分类 |
|---:|---|---|---|
| 1 | Uniform fill：Solid | `static` | `EXISTING_PRIMITIVE` |
| 2 | External pixel-field copy：Copy Segment | 需要跨 renderer framebuffer readback/Segment ownership | `OUT_OF_SCOPE` |
| 3 | Hard gate/flash：Blink, Strobe, Strobe Rainbow, Strobe Mega, Blink Rainbow, Lightning | 扩 `step_pulse` 的 duty/burst/jitter | `PARAM_EXTENSION` |
| 4 | Global brightness envelope：Breathe, Fade, Heartbeat | 扩 `breath` 的 waveform/envelope | `PARAM_EXTENSION` |
| 5 | Global color signal：Random Colors, Colorloop, Tri Fade, TV Simulator, Slow Transition | `static` + timeline / `calm` generator options | `PARAM_EXTENSION` |
| 6 | Wipe/progress front：Wipe, Wipe Random, Sweep, Sweep Random, Tri Wipe, Sunrise | `color_wipe` + origin；软边/曲线为参数 | `PARAM_EXTENSION` |
| 7 | External/target meter：Percent | `color_wipe` 几何已有，缺 external progress binding/slew | `PARAM_EXTENSION` |
| 8 | Periodic chase mask：Theater, Theater Rainbow, Chase, Chase Random, Chase Rainbow, Chase Flash, Chase Flash Rnd, Rainbow Runner, Chase 2, Chase 3, Flow | `chase`/`theater_phase`/`flowing_bands` | `PARAM_EXTENSION` |
| 9 | Moving head/scanner/comet：Scan, Scan Dual, Android, Scanner, Lighthouse, Loading, Two Dots, Multi Comet, Scanner Dual, Meteor, Sinelon, Sinelon Dual, Sinelon Rainbow | `single_dot`/`comet`；缺 count/phase/trajectory convenience | `PARAM_EXTENSION` |
| 10 | Coordinate→palette field：Rainbow, Colorful, Palette, Railway, Solid Pattern, Solid Pattern Tri | `color_wave`/`flowing_bands`；缺通用 palette sampling | `PARAM_EXTENSION` |
| 11 | Analytic periodic wave：Running, Saw, Gradient, Running Dual, Pride 2015, Colorwaves, Bpm, Lake, Plasma, Pacifica, Phased, Sine, Washing Machine, Blends, Wavesins, Flow Stripe | 扩 `color_wave` waveform/layers/mix | `PARAM_EXTENSION` |
| 12 | Coherent noise field：Fill Noise, Noise 1–4, Phased Noise, Noise Pal, Color Clouds | 当前无线性相关 noise basis | `NEW_PRIMITIVE` |
| 13 | History/time-to-space stream：Stream, Stream 2, Rain | 当前无 sample FIFO/ring buffer | `NEW_PRIMITIVE` |
| 14 | Per-pixel event lifecycle：Dynamic, Twinkle, Sparkle, Sparkle Dark, Sparkle+, Fairy, Fairytwinkle, Colortwinkles, Twinklefox, Twinklecat, Glitter, Solid Glitter, Twinkleup, Dynamic Smooth | 扩 `twinkle` event shape/envelope/background | `PARAM_EXTENSION` |
| 15 | Stochastic dissolve/latch：Dissolve, Dissolve Rnd | `twinkle` lifecycle + wipe transition | `PARAM_EXTENSION` |
| 16 | Flicker/candle：Fire Flicker, Candle, Candle Multi | uniform/stochastic envelopes | `PARAM_EXTENSION` |
| 17 | 1D heat transport：Fire 2012 | `heat_fire` | `EXISTING_PRIMITIVE` |
| 18 | Expanding ripple：Ripple, Ripple Rainbow | `onset_ripple`，event source/color options | `PARAM_EXTENSION` |
| 19 | Repeated spots/lobes：Spots, Spots Fade | `flowing_bands`/`color_wave` edge profile | `PARAM_EXTENSION` |
| 20 | Independent movers：Oscillate, Juggle, Chunchun, Dancing Shadows, Perlin Move | `single_dot`/`comet` + additive composition；缺 count/phase/trajectory | `PARAM_EXTENSION` |
| 21 | Soft moving wave packets：Aurora, Shimmer | `color_wave`/`comet` packet profile | `PARAM_EXTENSION` |
| 22 | Firework/spark systems：Fireworks, Fireworks Starburst, Fireworks 1D | 需要对象/fragment runtime | `OUT_OF_SCOPE` |
| 23 | Ballistic/physical objects：Rolling Balls, Bouncing Balls, Popcorn, Drip | 需要 gravity/collision/object runtime | `OUT_OF_SCOPE` |
| 24 | Scripted semantic scene/game：Traffic Light, Tetrix, ICU, Halloween Eyes, PacMan | Show recipes 或独立产品语义，不是基础 primitive | `OUT_OF_SCOPE` |
| 25 | External image/GIF：Image | 需要 asset decoder/frame sampling | `OUT_OF_SCOPE` |

普通 family 计数校验：`2 + 16 + 2 + 5 = 25`。条件注册导致的 118/124 差异来自 Image 以及
Fire 2012、Fireworks 1D、Rolling Balls、Fireworks Starburst、Dancing Shadows 的 build guards，
不是视觉 family 变化。

## 5. Audio Reactive：输入轴与视觉轴必须分开

### 5.1 数量与输入轴

现有 inventory 的总数保持：37 = 29 ordinary renderer + 8 particle renderer；音频总分类保持
`DIRECT_V2=34`、`V2_APPROXIMATED=3`、`INPUT_EXTENSION_REQUIRED=0`。

本次 1D 子集为：

| 1D subset | ordinary | particle | total |
|---|---:|---:|---:|
| effects | 24 | 4 | **28** |
| audio `DIRECT_V2` | 21 | 4 | **25** |
| audio `V2_APPROXIMATED` | 3 | 0 | **3** |
| audio `INPUT_EXTENSION_REQUIRED` | 0 | 0 | **0** |

三个近似项只有 Waterfall、Puddlepeak、Ripple Peak。V2 有 `samplePeak`，但 effect-owned
`binNum/maxVol` 控件不在 wire 上，不能声称 slider parity。固定 packet/export 证据见
[`audio_reactive.cpp#L738-L750`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L738-L750)
与
[`#L1239-L1260`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L1239-L1260)。

### 5.2 完整 1D 双轴表

视觉分类是主 Agent 在 ordinary family 上再次去重后的结论。`NEW_PRIMITIVE` 的 10 个 effect 最终只
指向两个共享 primitive，并不等于十个 renderer。

| Effect | audio | 声音驱动 | 去声后的 visual family | visual | LIGHT-BELT 去重结论 |
|---|---|---|---|---|---|
| Pixels | `DIRECT_V2` | loudness→birth brightness/color index | random fading sparks | `EXISTING_PRIMITIVE` | `twinkle` + birth driver |
| Pixelwave | `DIRECT_V2` | raw→center sample brightness | center-out sample history | `NEW_PRIMITIVE` | shared history stream |
| Juggles | `DIRECT_V2` | loudness→mover brightness | multi sine movers + trail | `PARAM_EXTENSION` | extend `comet` count/phase/trajectory |
| Matripix | `DIRECT_V2` | raw→new edge sample | one-way sample history | `NEW_PRIMITIVE` | shared history stream |
| Gravimeter | `DIRECT_V2` | loudness→extent/cap target | gravity meter | `PARAM_EXTENSION` | external-progress wipe + peak cap |
| Plasmoid | `DIRECT_V2` | loudness→brightness gate | layered analytic wave field | `PARAM_EXTENSION` | extend `color_wave` waveform/layers |
| Puddles | `DIRECT_V2` | raw→spawn gate/width | random fading blocks | `PARAM_EXTENSION` | extend `twinkle` width/gate |
| Midnoise | `DIRECT_V2` | loudness→center extent/noise coordinate | noise-textured meter | `NEW_PRIMITIVE` | coherent noise + external progress |
| Noisemeter | `DIRECT_V2` | raw→extent; loudness→noise texture | edge noise meter | `NEW_PRIMITIVE` | coherent noise + external progress |
| Freqwave | `DIRECT_V2` | dominant frequency→new hue; loudness→value | center-out sample history | `NEW_PRIMITIVE` | shared history stream |
| Freqmatrix | `DIRECT_V2` | dominant frequency→new hue; loudness→value | one-way sample history | `NEW_PRIMITIVE` | shared history stream |
| Waterfall | `V2_APPROXIMATED` | frequency/magnitude→sample; peak→accent | marked one-way history | `NEW_PRIMITIVE` | shared history stream；peak controls approximate |
| Freqpixels | `DIRECT_V2` | frequency→birth color; magnitude→value | random fading sparks | `EXISTING_PRIMITIVE` | `twinkle` + birth driver |
| Noisefire | `DIRECT_V2` | loudness→texture brightness | moving Perlin fire texture | `NEW_PRIMITIVE` | exact mechanism→coherent noise；fire intent→`heat_fire` recipe |
| Puddlepeak | `V2_APPROXIMATED` | peak→spawn; loudness→width | event-triggered fading block | `PARAM_EXTENSION` | `twinkle` width/event gate |
| Noisemove | `DIRECT_V2` | spectrum bins→mover values | noise-trajectory points | `NEW_PRIMITIVE` | coherent noise trajectory + mover params |
| Ripple Peak | `V2_APPROXIMATED` | peak→birth; frequency→color | expanding ripple | `PARAM_EXTENSION` | `onset_ripple` origin/direction/color options |
| Freqmap | `DIRECT_V2` | frequency→position/color; magnitude→value | external-position dot | `PARAM_EXTENSION` | `single_dot`/`comet` external position |
| Gravcenter | `DIRECT_V2` | loudness→center extent/cap | centered gravity meter | `PARAM_EXTENSION` | progress + origin=center + cap |
| Gravcentric | `DIRECT_V2` | loudness→extent/cap/palette index | gravity meter variant | `PARAM_EXTENSION` | same family parameters |
| Gravfreq | `DIRECT_V2` | loudness→extent; frequency→color | frequency-colored meter | `PARAM_EXTENSION` | same geometry + local color recipe |
| DJ Light | `DIRECT_V2` | FFT bins→RGB center sample | center-out RGB history | `NEW_PRIMITIVE` | shared history stream |
| Blurz | `DIRECT_V2` | band→birth color/value | fading sparks + spatial blur | `PARAM_EXTENSION` | `twinkle` blur/smear |
| Rocktaves | `DIRECT_V2` | frequency→pitch class/position; magnitude→value | sine-orbit dot | `PARAM_EXTENSION` | mover sine trajectory + local color recipe |
| PS GEQ 1D | `DIRECT_V2` | 16 bins→16 emitter spawn | spectrum particle emitters | `OUT_OF_SCOPE` | particle runtime not approved |
| PS Sonic Stream | `DIRECT_V2` | selected bin→spawn/lifetime/push | directional particle stream | `OUT_OF_SCOPE` | particle runtime not approved |
| PS Sonic Boom | `DIRECT_V2` | selected bin→explosion count/lifetime | particle explosion | `OUT_OF_SCOPE` | particle runtime not approved |
| PS Springy | `DIRECT_V2` | adjacent bins→spring velocity kick | spring-mass chain | `OUT_OF_SCOPE` | particle/physics runtime not approved |

视觉轴计数：`EXISTING_PRIMITIVE=2`、`PARAM_EXTENSION=12`、`NEW_PRIMITIVE=10`、
`OUT_OF_SCOPE=4`，合计 28。十个 NEW effects 去重为 history stream 6 项与 coherent noise 4 项。

### 5.3 音频字段没有固定视觉含义

`dominant_frequency`、`spectrum`、`loudness`、`peak` 都只是测量事实。它们可以在某个 recipe 中驱动
brightness、position、color、speed、count、spawn 或 progress，但不能获得全局语义。尤其
“低频=红、高频=蓝”只能属于明确的 effect/color recipe；不得进入 `AudioFeatures`、通用 modulator
或项目 palette 默认值。

## 6. Audio Reactive live palettes

WLED Audio Reactive usermod 实际生成 **3 个 live palettes**，不是 37 个音频效果各自一套。固定源码
给出的实际名称和输入是：

1. **Ratio**：以 `fftResult[0]`, `[4]`, `[10]` 的不同 RGB 排列形成 gradient anchors；
2. **Hue**：沿 palette position 选择 bins `0..10`，band value 同时生成 HSV hue 与 value；
3. **Spectrum**：沿 palette position 选择低半部 FFT bins，band value 生成 HSV hue，palette position
   生成 value。

三者只消费 V2 已有的 `fftResult[16]` / RK3588 `spectrum`；不消费 raw/smoothed level、peak、dominant
frequency 或 magnitude，也不增加新信号。固定名称、注册和 mapping 分别见 pinned
[`audio_reactive.cpp#L2227-L2267`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L2227-L2267)
与
[`#L2317-L2319`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L2317-L2319)。

WLED 的普通 renderer 只有在选择该 live palette 且执行 palette lookup 时才随声音换色。因此正确抽象是
“existing effect + opt-in audio-driven color source”，不是 AudioPaletteEffect，也不是每个普通 effect
的 audio alias。

RK3588 当前 `ColorSpec.palette` 对多数 renderer 只是 compositor 每整秒挑一个 current RGB；只有
`twinkle` 真正消费整组 palette。若未来产品需要 live audio palette，应扩 cue-level `ColorSpec` 的显式、
opt-in color-source policy，并定义静音、采样、插值、确定性与 renderer opt-in；本轮禁止实现该 framework。

## 7. 指定假设的验证结果

| 假设 | 结论 | 理由 |
|---|---|---|
| `history_stream` 是真正缺失 primitive | **成立** | Stream/Rain 与 Pixelwave/Matripix/Freqwave/Freqmatrix/Waterfall/DJ Light 都把时间样本变为空间历史；现有效果没有任意 sample FIFO/ring buffer |
| `coherent_noise_field` 是真正缺失 primitive | **成立** | Noise 1–4 等以及 Midnoise/Noisemeter/Noisefire/Noisemove 共享连续相关 noise basis；`color_wave` 是解析相位，`heat_fire` 是热传输，均不能自然表达 |
| Grav*/Noisemeter 只需 external progress | **部分成立** | Grav* 的几何主要是 progress + origin + falling cap；Noisemeter 还需要 coherent-noise texture，不能只加 progress |
| Juggle/Multi-Comet 只需 count/spacing | **基本成立，但还需 trajectory/phase** | renderer family 已是 moving emitter；独立 sine/bounce 轨迹不能只靠固定 spacing |
| Noisefire 复用 `heat_fire` + audio | **按产品意图成立，按算法 parity 不成立** | 若需求是“音频火焰”，复用 heat field 最小；若必须保留 Perlin texture，它属于 coherent noise，不应谎称 heat diffusion 等价 |
| Ripple Peak 复用 `onset_ripple` | **成立** | wave lifecycle 已有；只差 random origin、双向/wrap、local frequency-color recipe，且 B 类 peak controls 只能近似 |
| Pixels/Puddles/Freqpixels 泛化 `twinkle` | **成立** | 共享随机 event birth/fade；需要 event width、external gate/birth color/value、可选 blur，而不是新 renderer |

## 8. 最小 proposal（仅建议）

### A. NO CHANGE

不新增 WLED aliases。下列继续由现有能力或 Show recipe 表达：uniform fill/envelopes、wipe、chase/theater、
coordinate waves、twinkle/sparkle、heat fire、ripple、scanner/comet、方向/origin、颜色/timeline、
brightness/speed/intensity audio modulation。`Noisefire` 若产品只需要“音频火焰”也优先采用
`heat_fire` + explicit audio intensity recipe。

2D、particle、firework/ballistics、semantic games、Copy Segment 和 GIF/Image 不进入当前实现建议。

### B. PARAM EXTENSION

按消灭 recipe 数与正交性排序；这些也必须另行批准后才能实现：

1. **`twinkle` event field**：增加 `event_width_px`、`blur_radius_px`、显式 `event_gate`/birth-value/color
   binding。可统一 Pixels、Puddles、Puddlepeak、Freqpixels、Blurz，并覆盖更多 Sparkle/Twinkle variants。
2. **`comet` moving emitters**：增加 `count`、`phase_spacing`、
   `trajectory=wrap|bounce|sine`；允许 `trail_length=0`。可消灭 Multi Comet、Two Dots、Juggle、
   Sinelon、Rocktaves、Scanner Dual 等独立 recipe。
3. **`color_wipe` external progress**：增加明确的 `[0,1]` progress binding、`slew_seconds` 与可选
   `peak_hold/decay` cap；复用 compositor origin。覆盖 Percent 和 Grav*；Noisemeter 仍需 noise field。
4. **`onset_ripple` wave options**：增加 `event_origin=fixed|random`、
   `propagation=one_way|bidirectional`、`wrap`。覆盖普通 Ripple/Ripple Rainbow/Ripple Peak，不新增 ID。
5. 低优先级：为 `step_pulse` 增加 duty/burst/jitter；为 `color_wave` 增加 waveform/layer/mix；若 live
   audio color 被批准，扩 `ColorSpec` 的 opt-in source，而不是扩 effect catalog。

任何 audio binding 都必须显式指定 source→parameter mapping；不得把 dominant frequency 或 spectrum
隐式赋予颜色/位置含义。

### C. NEW PRIMITIVE

最多两个候选，均等待后续明确批准：

1. **`history_stream`**
   - 当前没有：`comet` 保存的是运动 emitter 尾迹，`onset_ripple` 保存事件 waves，均不是任意输入样本
     FIFO。
   - 非参数差异：核心是每个时间样本成为一个空间 cell，并随方向/速度推进。
   - 多 recipe 复用：Stream/Stream 2/Rain、Pixelwave/Matripix、Freqwave/Freqmatrix/Waterfall/DJ Light。
   - 架构适配：状态是一条有界 logical-path buffer；在 `virtual_path` 上先推进一次再 split，可自然跨 seam；
     sample source 必须是显式 generic input recipe。

2. **`coherent_noise_field`**
   - 当前没有：`color_wave` 无相关噪声基函数；`heat_fire` 的 heat diffusion/sparks 不是 Perlin field；
     `twinkle` 的独立随机事件也不具空间/时间相关性。
   - 非参数差异：核心是连续坐标场 `noise(x,t)` 及其 scale/velocity/threshold/mapping，而不是 palette
     或 direction。
   - 多 recipe 复用：Fill Noise、Noise 1–4、Phased Noise、Noise Pal、Color Clouds，以及
     Midnoise/Noisemeter/Noisefire/Noisemove。
   - 架构适配：只依赖 logical coordinate、cue time/seed 和 bounded state；在一条 `virtual_path` 上采样
     后 split，不需要物理节点知识。

若后续产品需求不需要任意 signal history 或 coherent noise appearance，则两个候选都可以保持未实现；
“新增 0 个 primitive”仍是合法且优于按 WLED ID 批量迁移的结论。

## 9. 停止线与未解决问题

- 本文是源码/架构审计，不是 WLED 数值兼容或硬件观感验收。
- 参数扩展中的 arbitrary audio binding 目前不存在；是否扩通用 modulator、让 renderer 直接读
  `AudioFeatures`，或只提供少量 recipe，需要未来单独设计。
- AR live palette 的精确插值、静音行为、更新率和 deterministic replay 尚未成为 LIGHT-BELT 合同。
- default-build 118 与 source-level 124 的差异必须保留，不能在以后报告中混用。
- 旧 AR inventory 固定 commit 正确，但部分历史行号锚点已漂移；本文件使用重新核验的固定 commit
  行段。未来更新 inventory 时应只修证据锚点，不改变已经核对的 37/29/8/34/3/0 数量。
- 本轮到此停止；proposal 未获实现授权。
