# Phase 32 WLED 灯效迁移参考与落地状态

> 研究日期：2026-08-19；实施状态更新：2026-08-21
> WLED 参考版本：v16.0.1，commit `29b389df1c1aaec6ff53aea742d17063b985906c`（仅作算法、架构和许可证研究来源）
> 结论状态：Phase 32 已按 clean-room 边界实现 `flowing_bands`、`onset_ripple`、`heat_fire`；真实灯带表现均 **NOT HARDWARE VERIFIED**

## 一、结论

WLED 灯效可以作为视觉算法的研究来源，但不能作为 LIGHT-BELT 的运行时、参数或协议合同。迁移的定义是：只借鉴与 LIGHT-BELT 原有效果及当前 Show 组合能力完全不同的新视觉算法，重新设计为原生 LIGHT-BELT `BaseEffect` 和命名参数。

Phase 32 的长期成果不是“移植三个效果”，而是建立两条可重复执行的产品化路径：

1. **ordinary WLED Effect → LIGHT-BELT Native Effect**：研究视觉原理后，按 RK3588 的时钟、拓扑、颜色和参数合同 clean-room 重写。
2. **WLED Audio Reactive Effect → LIGHT-BELT Native Audio Effect**：先审计音频依赖和 Audio Sync V2 可用性，再设计通用 `AudioFeatures` 与 RK3588 原生视觉语义。

`flowing_bands`、`onset_ripple`、`heat_fire` 是这套流程的第一组落地样本，不是候选全集，也不是未来工作的数量上限。Juggle 保留为未实施 ordinary 候选；固定 WLED v16.0.1 中的 37 个显式 Audio Reactive effects 已另行完成全量源码 inventory。所有新增 ID 都不是 WLED mode alias；参数、状态、随机数、时间步和测试向量均由 LIGHT-BELT 自己定义。
三个效果的实际参数范围、默认值、状态和 common-control 语义见
[灯效与参数手册](effect-reference.md)。WLED Audio Sync V2 是独立输入适配合同，见
[WLED Audio Sync V2 输入合同](wled-audio-sync-v2.md)，不要把它与 WLED native effect ownership 混为一谈。
全量 Audio Reactive 分类与逐项依据见
[WLED v16.0.1 Audio Reactive effect inventory](wled-audio-reactive-effect-inventory.md)。

下列效果与现有能力重叠，不作为首批新效果：Solid、Breathe、Wipe、Theater、Twinkle、Meteor、Scanner。它们最多作为现有效果的参数/组合改进，不应因 WLED 中有同名 mode 就新增 LIGHT-BELT ID。

迁移必须兼容所有非过期内容，尤其是 current runtime、Show schema、`ColorSpec`、`virtual_path`、`OutputTransform`，以及在实际需要时才接入 Host 和 `energy-wakeup`。不接受或模拟 WLED mode ID、`speed/intensity/custom` 参数槽、metadata、42Hz 调度、Segment、palette 编号、JSON/API 或数值兼容。Phase 32 不增加 WLED 协议、不扩展 Audio Sync V2，也不建立兼容层。

## 二、现行权威边界

### 2.1 Show 基准

- `assets/energy-wakeup/energy-wakeup.yaml` 是不可修改的原始来源。
- `config/shows/energy-wakeup.yaml` 是唯一批准且可运行的现行兼容基准。
- 新效果只需证明不破坏上述基准的加载和既有语义；不得通过修改原始来源或基准 Show 来证明迁移成功。

原 `config/shows/` 中的 32 个文件现已按用途归档至 `config/shows/archive/` 下的六个分类目录，均属于历史边界，不是现行需求、同步清单、门禁或设计证据。其 all-effects、应急、A/B、staged Show 也只可作为明确标记的历史回放材料；本研究不以它们选择候选或判断兼容性。

### 2.2 LIGHT-BELT 的不可破坏合同

效果入口是 `EffectContext → BaseEffect.process() → PixelFrame`。效果只产生拓扑无关的逻辑帧，并保留上下文的 `timestamp` 和 `sequence`；它不知道 node、host、port、GPIO、DDP、UDP 或 RS-485。

现有边界如下：

| 能力 | 归属 | 迁移要求 |
|---|---|---|
| 效果状态和画面算法 | 具体 `BaseEffect` | 只增加该算法真正需要的最小状态 |
| 颜色、颜色时间线、palette 语义 | Show `ColorSpec`/compositor | 复用，不另造 WLED palette 编号合同 |
| 单 strip、集合、组和连续路径 | target/`virtual_path` | 复用；跨成员连续效果先在逻辑路径渲染 |
| cue 的 speed、origin、混合、转场、调制 | Show/compositor | 不在效果内复制拓扑和编排逻辑 |
| 全局 brightness | `OutputTransform` | 只应用一次，效果内不得再次当设备亮度处理 |
| sequence、timestamp、物理映射和传输 | Engine/映射/transport | 新效果不得接管 |

当前 runtime 注册 20 个效果。三个新增效果已显式加入唯一 registry、参数 key/validator 和 common capability；新增一个文件仍不会自动注册。Host capabilities、手动效果临时 Show 和 OpenAPI 枚举现已由同一 registry 合同校验或进行漂移检查；固件不执行这些逻辑效果，默认 Show 也没有加入三个新效果。

## 三、WLED 可借鉴什么

WLED v16.0.1 的效果通常由固定 mode、实现函数和 metadata 组成，运行时还依赖 Segment、全局 strip、`millis()`、FastLED、palette 和 MCU 状态。它适合帮助我们理解以下纯视觉思想：波形和相位推进、位置函数、色相/调色板采样、热扩散、粒子运动和衰减。

这些 WLED 机制不是 LIGHT-BELT 的迁移目标：

- 不带入 WLED mode ID、注册编号、metadata 或保留槽语义。
- 不提供或模拟 `speed/intensity/custom1-3` 槽、默认值、palette 编号、JSON/API 和 WLED 数值输出。
- 不带入 `SEGMENT`/`SEGENV`、Segment geometry、`millis()`、FastLED 类型、PROGMEM、硬件随机源或板上 `show()`。
- 不把 WLED 的 42Hz 假定、transition 状态、Bus/ABL/CCT 或实时控制所有权塞进 LIGHT-BELT。
- 不做 WLED compatibility layer、`WledCompat`、通用状态仓库、palette provider、虚拟 tick scheduler、第三份 catalog、代码生成器或 alias 系统。每个效果只实现自己的最小逻辑。

直接让 ESP32 控制节点上的上游 WLED runtime 运行 native effect 也不是等价迁移：它会把所有权从 RK3588 逐帧 DDP 改给板上运行时，失去 RK3588 的媒体时钟、Show compositor、跨目标合成、统一 sequence/timestamp 和一次性 brightness 边界。因此只能作为独立演示，不能替代原生 RK3588 实现。

## 四、长期迁移流程、分类与候选

### 4.1 标准流程

每个 ordinary 或 Audio Reactive 候选都必须按同一顺序通过以下步骤；不能从 WLED 名称直接跳到代码：

1. **WLED effect source pin**：固定 release tag 和完整 commit，记录 effect ID、实现函数、metadata 和许可证来源；禁止引用浮动分支。
2. **Visual audit**：用自己的语言描述画面原理、状态、时间推进、颜色/palette、1D/2D/particle 几何和停止线，不复制实现。
3. **AR audio dependency audit**：对 Audio Reactive effect 逐项记录 `volumeRaw/Smth`、`fftResult[16]`、`samplePeak`、`FFT_MajorPeak/Magnitude`、`fftBin` 和其他 analyzer 耦合；ordinary effect 明确标记“无音频依赖”。
4. **A/B/C classification**：按 `DIRECT_V2`、`V2_APPROXIMATED`、`INPUT_EXTENSION_REQUIRED` 判断输入可移植性。分类只说明音频输入是否充分，不代表 renderer 已实现。
5. **LIGHT-BELT-native parameter design**：只保留产品需要的命名参数，复用 common `speed`/`intensity`、`ColorSpec`、`color_timeline` 和 `virtual_path`，拒绝 WLED 槽位及数值兼容。
6. **Implementation**：实现独立 `BaseEffect`，保持 `PixelFrame`、timestamp/sequence、一次 brightness、硬件无关和有界状态合同。
7. **Registry synchronization**：同步唯一 registry、参数 validator、capabilities 和实际需要的 Host/OpenAPI 消费者；不得建立第二份 catalog。
8. **Focused tests**：用产品 golden vector、边界/非法参数、reset/seek/replay、virtual-path seam、颜色时间线和现行 Show 非回归证明 LIGHT-BELT 合同；不使用 WLED 数值输出冒充验收。

### 4.2 进入实现的筛选规则

只有同时满足以下条件才进入实现：

1. 现有效果及其 `ColorSpec`、`virtual_path`、origin、混合和调制组合无法表达该视觉原语。
2. 能用明确的 LIGHT-BELT 命名参数描述，不依赖 WLED mode 或槽位语义。
3. 能在已批准的逻辑拓扑和输入合同中诚实实现；需要 2D surface、GIF、粒子 runtime 或输入扩展时先停下，另行批准基础能力。
4. 有可聚焦的行为测试和 `energy-wakeup` 非回归检查。

### 4.3 第一组落地与 ordinary backlog

| 候选 | 新增视觉原语 | 状态 |
|---|---|---|
| `flowing_bands` | 固定 A/B 周期中，离散移动的单个 C highlight | 已实现、无状态 |
| Juggle | 多个不同频率的往返点交叉叠亮 | 未实现 ordinary 候选 |
| `heat_fire` | 一维热量注入、扩散、冷却和向上偏置 | 已实现、私有 60 Hz 固定步 |
| `onset_ripple` | 从通用音频事件出生、扩张、衰减和消散的波前 | 已实现、最多 16 条波 |

`heat_fire` 和 `onset_ripple` 是 clean-room LIGHT-BELT 设计，不宣称复现 Fire2012/Ripple 数值输出。Juggle 仍不属于当前 registry。未来 ordinary 迁移继续复用 4.1 的流程，而不是把这张表固化为永久候选全集。

### 4.4 Audio Reactive 全量 inventory

固定 [WLED v16.0.1 release](https://github.com/wled/WLED/releases/tag/v16.0.1) / commit [`29b389df1c1aaec6ff53aea742d17063b985906c`](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c) 的源码审计，从 `FX.cpp` metadata 的 `v`/`f` 能力标记机械枚举出 **37** 个显式 Audio Reactive effects：29 个 ordinary renderer、8 个 particle renderer。逐项依赖、视觉原理、palette 机制、ID 和源码行见 [AR inventory](wled-audio-reactive-effect-inventory.md)。

| 类别 | 数量 | Phase 32 解释 |
|---|---:|---|
| A — `DIRECT_V2` | 34 | 所需音频字段直接存在于 Audio Sync V2；仍须 clean-room 重做 RK3588 renderer 和参数 |
| B — `V2_APPROXIMATED` | 3 | `Ripple Peak`、`Puddlepeak`、`Waterfall` 可消费 wire `samplePeak`，但 effect-owned `binNum/maxVol` 控件无法原样复刻 |
| C — `INPUT_EXTENSION_REQUIRED` | 0 | 固定版本没有显式 AR effect 实际读取 `fftBin`；零不是允许虚构该字段 |

`fftBin` 不在 Audio Sync V2 wire packet；Phase 32 不扩展协议。`dominant_frequency` 也没有全局视觉含义，只有具体原生 effect 可以在自己的合同内把频率映射到位置、颜色或其他视觉量。

优先级以当前 1D 产品拓扑和 renderer 复用价值为准：先研究 `Noisemeter`、`Pixelwave`、`Pixels`、`Blurz`、`DJ Light` 等 A 类 1D 原语；2D 和 particle family 在对应 runtime 获批后再迁移；三个 B 类效果必须先决定 peak 控件的近似政策或输入扩展边界。本节是长期 backlog 的入口，不是 Phase 32 顺带实现授权。

### 4.5 明确排除的重叠候选

| WLED 名称 | LIGHT-BELT 已有表达 | 决定 |
|---|---|---|
| Solid | `static`、命名颜色、颜色时间线 | 不新增 |
| Breathe | `breath` 的周期和最小亮度 | 不新增；必要时扩展 `breath` |
| Wipe | `color_wipe` 的确定性累积填充 | 不新增 |
| Theater | `theater_phase` 及 `chase` 的间隙/方向 | 不新增 |
| Twinkle | `twinkle` 的密度、衰减和色源 | 不新增 |
| Meteor | `comet` 的头部、尾迹和衰减 | 不列首批；视觉确有需要时再评估 `comet` |
| Scanner | `single_dot`、`chase`、`comet` 的组合 | 不新增 |

## 五、已实现合同：`flowing_bands`

### 5.1 用户意图

目标不是软边行波、带尾巴的 chase，也不是整条亮暗掩码。空间图样始终是固定的 `A B A B ...`：

- `A` 是使用 `base_gain` 的 authored-color band。
- `B` 永远是黑色 gap。
- `C` 是当前唯一被选中的 A band，使用 `highlight_gain`；C 只替换 A，从不占据 B。
- 时间不平移 A/B 空间图样，只按离散 step 把 C 从一个 A band 移到下一个 A band。

```text
t0：A B A B A B
t1：C B A B A B
t2：A B C B A B
t3：A B A B C B
```

这组产品 golden sequence 是 LIGHT-BELT 自己的定义，不是 WLED Running/Saw 的数值复刻。

### 5.2 最小命名参数

| 参数 | 合同 | 作用 |
|---|---|---|
| `band_width_px` | integer `[1,10000]`，默认 1 | 每个 A band 的像素宽度 |
| `gap_width_px` | integer `[1,10000]`，默认 1 | 每个黑色 B gap 的像素宽度 |
| `base_gain` | finite `[0,1]`，默认 0.125 | 未被选中 A band 的相对增益 |
| `highlight_gain` | finite `[base_gain,1]`，默认 0.625 | 被选中 C band 的相对增益 |
| `steps_per_second` | finite `[0,1000]`，默认 1 | C 每秒跨过的 A band 数；0 时离散 step 不随时间增长 |
| `direction` | `forward`/`reverse` | 方向，不用负速度表达 |
| `phase_offset_steps` | integer `[0,10000]`，默认 0 | 给离散 step 加整数偏移，供多 cue 错位 |
| `color` | 三个 finite `[0,1]` RGB channel，默认白色 | A/C 的 authored color |
| `color_timeline` | 现有 `ColorSpec` 时间线合同 | 由 compositor 解析后替代静态 `color` |

common `speed` 乘进离散步进速率，common `intensity` 乘进 `base_gain`/`highlight_gain` 后再 clamp；两者不是 WLED 参数槽。`base_gain` 和 `highlight_gain` 是效果内部相对振幅，不是设备 brightness，最终亮度仍只由 `OutputTransform` 应用一次。默认值是软件合同，不是硬件观感结论。

### 5.3 计算与路径语义

令 `W=band_width_px`、`G=gap_width_px`、`P=W+G`，cue-local 时间为 `t`：

```text
step       = floor(t * steps_per_second * common_speed) + phase_offset_steps
band_count = ceil(pixel_count / P)
```

当 `step == 0` 时没有 C，所有 A 都使用 `base_gain`。当 `step > 0` 时：

```text
forward highlighted_band = (step - 1) mod band_count
reverse highlighted_band = band_count - 1 - forward_highlighted_band
```

对像素 `i`，若 `(i mod P) >= W`，输出黑色 B；否则它属于 `floor(i/P)` 号 A band，只有该编号等于 `highlighted_band` 时使用 `highlight_gain`，其余使用 `base_gain`。宽 A band 内的所有像素一起从 A 切到 C；末尾不完整 band 仍参与 highlight 轮转。

普通 strip set 在每条 strip 重新建立 A/B 图样和 band index；需要跨灯带连续时使用 `virtual_path`，先渲染整条逻辑路径再 split，因此接缝不会重启 pattern 或 C。path gap 消耗逻辑坐标但不输出，reverse member 在 split 时反转。`origin=center/edges` 由现有 compositor 负责，不在效果内复制拓扑逻辑。

### 5.4 首组行为向量

白色、6 像素、`band_width_px=1`、`gap_width_px=1`、`base_gain=.25`、`highlight_gain=.75`、`steps_per_second=1`、`direction=forward`、`phase_offset_steps=0`、common speed/intensity 均为 1：

```text
t=0 [A,B,A,B,A,B] = [.25,0,.25,0,.25,0]
t=1 [C,B,A,B,A,B] = [.75,0,.25,0,.25,0]
t=2 [A,B,C,B,A,B] = [.25,0,.75,0,.25,0]
t=3 [A,B,A,B,C,B] = [.25,0,.25,0,.75,0]
t=4 [C,B,A,B,A,B] = [.75,0,.25,0,.25,0]
```

这些向量验证固定 A/B、黑色 B、单个离散 C 和 loop，不是 WLED 数值兼容向量。

## 六、同步矩阵：只同步实际受影响的入口

| 变更 | 必须同步 | 不应顺带修改 |
|---|---|---|
| 新增原生效果 | 实现、registry、参数 key/validator、聚焦测试 | Engine、OutputTransform、mapping、transport |
| 修改效果算法/参数 | 上述实现合同、实际引用的现行 fixture、快照测试 | 历史 Show 和归档拓扑 |
| 需要 Host 使用 | registry capabilities、OpenAPI、real adapter 参数透传 | 独立 Host whitelist 或未被该效果使用的 Host 重构 |
| 进入当前 Show | `config/shows/energy-wakeup.yaml` 的非回归验证；若另建 Show，按 README 声明目的/日期/状态 | 不修改 `assets/energy-wakeup/energy-wakeup.yaml`，不改历史归档 Show |
| 对外文档发布 | effect reference/operator 文档 | WLED API 文档或参数表的复制 |

效果若无 Host 或当前 Show 需求，不需要提前接入这些入口。参数 validator 应拒绝 NaN、Inf、越界和未知 authored key；状态和随机数只在具体算法需要时加入，并提供对应 reset/seek/replay 行为。

## 七、许可证与来源事实

WLED v16.0.1 的许可证是 EUPL-1.2-or-later；v0.14.4 仍为 MIT。许可证事实可以指导来源选择，但不构成法律意见，也不是迁移主线。

推荐 clean-room 路径：整理公开行为、参数意图和自有测试向量，再按 LIGHT-BELT 合同独立实现。若研究或采用旧 MIT 版本表达，必须逐效果核查 tag、commit、文件来源和第三方许可证；不能因为旧文件头写 MIT 就推定全部依赖均可使用。不得直接复制或逐句翻译 v16 实现；若未来确需复制，应先完成法务、SPDX、版权、修改日期和源码提供义务评估。

研究来源：

- [WLED v16.0.1 release](https://github.com/wled/WLED/releases/tag/v16.0.1)
- [WLED v16.0.1 full commit](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c)
- [WLED v16.0.1 LICENSE](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/LICENSE)
- [FX.h at the pinned commit](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.h)
- [FX.cpp at the pinned commit](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/wled00/FX.cpp)
- [Audio Reactive usermod at the pinned commit](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp)
- [LIGHT-BELT source-level AR inventory](wled-audio-reactive-effect-inventory.md)
- [Effect metadata](https://kno.wled.ge/interfaces/json-api/#effect-metadata)
- [Custom effects](https://kno.wled.ge/advanced/custom-features/#adding-custom-effects)
- [DDP](https://kno.wled.ge/interfaces/ddp/)
- [v0.14.4 MIT LICENSE](https://github.com/wled/WLED/blob/v0.14.4/LICENSE)

LIGHT-BELT 依据：`CLAUDE.md`、`docs/CLOSED_LOOP_SPEC.md`、`docs/IMPLEMENTATION_PLAN.md`、`light_engine/effects/base.py`、`light_engine/effects/__init__.py`、`light_engine/models.py`、`light_engine/engine/__init__.py`、`light_engine/show/loader.py`、`light_engine/show/compositor.py`、`light_engine/outputs/transform.py`、`light_engine/mapping/physical.py`、`host_services/schemas.py`、`host_services/engine_adapter.py`、`host_services/real_engine_adapter.py`、`config/shows/energy-wakeup.yaml`、`assets/energy-wakeup/energy-wakeup.yaml`。

## 八、落地结果与验收边界

Phase 32 软件验收覆盖：

1. 两条长期迁移路径、标准流程和固定 v16.0.1 AR inventory 可追溯；A/B/C 统计与逐项表一致，且没有由研究文档暗示协议扩展。
2. `config/shows/energy-wakeup.yaml` 仍可加载，既有 cue 解析和输出语义不变；原始来源文件未修改。
3. 每个实现有少量固定时间快照，证明其为新的视觉定义，而不是 WLED 数值复刻。
4. 效果不含 node、GPIO、host、port、transport 或物理映射；`timestamp`/`sequence` 原样保留；brightness 只在 `OutputTransform` 应用一次。
5. 只对确有状态/随机性的算法测试 seed、reset、seek/replay 和状态上限；纯解析效果不增加通用框架。
6. 用当前逻辑帧做聚焦性能检查，覆盖空路径、speed=0、NaN/越界、virtual-path seam、reverse member 和无异常输出。
7. 真实灯带、跨板相位、latch skew、功耗和观感在硬件验收前均标记 **NOT HARDWARE VERIFIED**。

已执行的聚焦合同包括 `flowing_bands` 固定向量与 virtual-path 接缝、compositor origin、
`onset_ripple` 音频维度/上升沿/16-wave 上限，以及 `heat_fire` 30/60 fps 等价、后退 seek、reset/replay
和可变长度。Juggle、2D、GIF/image、particle runtime 和通用 WLED compatibility layer 均未实施；AR inventory 是研究/迁移 backlog，不是 37 个效果已落地的声明。

停止线是：候选与现有效果重叠、算法无法在现有 1D 合同中清楚表达、来源/许可证不清、要求引入 WLED 兼容语义，或会破坏现行 Show/亮度/时序边界。满足任一停止线就不迁移。

## 九、验证限制

Phase 32 已修改 RK3588 effect runtime、registry、Host/OpenAPI 暴露和独立的 UDP-v3 长帧固件路径，但没有复制 WLED runtime/FX 槽、没有建立 WLED compatibility、没有扩展 WLED Audio Sync V2，也没有把逻辑效果下放到固件或修改默认 Show/energy asset。研究与软件测试不能证明运行上游 WLED 的真实 ESP32 节点、灯带、跨板同步、功耗或视觉效果，因此所有硬件结论均为 **NOT HARDWARE VERIFIED**。
