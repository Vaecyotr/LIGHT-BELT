# LIGHT-BELT 节目编写完全手册 (Show Authoring Manual)

> **手册定位与适用对象**：
> 本手册是面向 LIGHT-BELT 舱体灯光节目编写者（Show Author）的**操作型中文指南**。它负责把当前冻结的软件合同翻译成可直接使用的节目编写方法，但**不是高于源码/合同的第二套权威**；若未来发现本手册与 `CLAUDE.md`、`CLOSED_LOOP_SPEC.md`、`IMPLEMENTATION_PLAN.md`、`show-v2-authoring.md`、live EffectRegistry/exporter 或当前实现冲突，应以这些上游 authority 为准并修订本手册。
> - **读者对象**：负责设计与编写 Show YAML 节目单的团队成员。无需关注 Python 引擎底层实现、ESP32 固件或网络传输细节，只需理解时间、空间、灯带目标、灯效参数、色彩模式与音频联动规则。
> - **APP 边界**：平板/手机端 APP V1 是面向现场运营人员的**播控与全局状态管理界面**（用于选节目、播放、暂停、调节全局主亮度和音量），**不是**灯效编辑工具；所有灯带分配、灯效、色彩流动与音视频联动均在 Show YAML 中完整声明。
> - **硬件与实物状态**：本文档描述的是当前已冻结的软件编程合同（Software Authoring Contract）。文中所述物理安装与实物部署描述均属软件拓扑模型，在现场物理测试完成前保持 **NOT HARDWARE VERIFIED**。
>
> **版本说明（2026-08-23 校订版）**：本版在原手册基础上按当前 `reference(9)` 源码与 Show v2 合同复核了 CLI、Adaptive/`audio_control`、ScalarSource/Modulation source、Branch/`pre_roll`、Video 原生效果和完整示例；不改变任何引擎或 Show 合同。

---

## 如何使用本手册

根据你的编写目标选择最佳阅读路径：

```
                    ┌─► [路径 1: 新手入门] ──► 第 0 章 (10分钟上手) ──► 第 1 章 ──► 第 2 章 ──► 第 3 章 ──► 第 9 章
                    │
                    ├─► [路径 2: 查阅灯效] ──► 顶部速查表 ───────────► 第 9 章 (22 个 Native Effect 完整图鉴)
[你的编写需求] ─────┼
                    ├─► [路径 3: 音乐联动] ──► 第 7 章 (声音系统) ────► 第 8 章 (Modulation) ──► 第 6 章 (色彩) ──► 第 9 章
                    │
                    └─► [路径 4: 跨灯带流动] ► 第 5 章 (空间与路径) ──► 第 4 章 (运动时钟) ───► 第 9 章 (运动类效果)
```

---

## 一页速查 Cheat Sheet

### 1. 当前 production software profile 的 Target（共 9 条数字灯带 / 200 组像素）
这里按当前 profile 的 **`video_zone` 软件分区**列出；`video_zone` 用于视频取色，不等同于对现场物理位置的重新命名。

- **`video_zone: top`**: `strip_11` (10 组), `strip_12` (40 组)
- **`video_zone: bottom`**: `strip_21` (10 组), `strip_22` (40 组)
- **`video_zone: left`**: `strip_31` (10 组), `strip_32` (40 组)
- **`video_zone: right`**: `strip_41` (10 组), `strip_43` (20 组), `strip_44` (20 组)

### 2. 空间坐标原点 (4 种 Origins)
`origin` 改变的是 **Show 的逻辑坐标映射**，不是 profile 中物理布线的 `direction`：

- `origin: start` —— 从逻辑路径起点向终点推进（0 $\to$ N）。
- `origin: end` —— 从逻辑路径终点向起点推进（N $\to$ 0）。
- `origin: center` —— 从逻辑路径中心向两端对称扩散（$\leftarrow \text{Center} \rightarrow$）。
- `origin: edges` —— 从逻辑路径两端向中心对称聚拢（$\rightarrow \text{Center} \leftarrow$）。

### 3. 通用控件 (Common Controls)
- `speed`（运动速率乘数，默认 `1.0`，`0.0` 冻结运动）
- `intensity`（亮度乘数，默认 `1.0`）

### 4. 色彩模式 (Color Modes)
- **Legacy `ColorSpec`**: `mode: effect_default`（默认）、`mode: solid`（单色 `[r, g, b]`）、`mode: palette`（颜色列表）。
- **Cue 级 `ColorSource` (6 种)**: `timeline`（时间线）、`spatial_palette`（空间调色板）、`video_average`（视频均色）、`video_dominant`（视频主色）、`audio_spectrum_palette`（音频频谱映射）、`dominant_frequency_palette`（主频音高映射）。

### 5. 动态联动 (Modulation)
- `audio_control`：主要服务 **Adaptive effect** 的节拍同步、状态确认、最短保持和切换冷却。
- `audio_modulation`：专管 Cue 通用控制 `brightness`、`speed`、`intensity`。
- `parameter_modulation`：专管白名单内的 11 个特定灯效浮点参数（支持 `modulate` 基准缩放 与 `drive` 范围驱动）。
- `ScalarSource`：少数 effect 参数直接读取的轻量归一化信号选择器，不等同于 `parameter_modulation`。

### 6. 分支生命周期 (Branch Lifecycles)
- `start_on_release`：在 `after` 对应的**归一化路径释放进度**达到之前不计算；释放帧才创建可见状态。
- `pre_roll`：Cue 激活后就在后台使用同一时间/运动输入模拟；达到同一个释放进度时只把已存在的状态揭示出来。
- `after` **不是可见光波前探测器**，也不根据 `chase`/`comet` 的实际头部位置触发。

### 7. 22 个 Native Effect 一览表
| Effect ID | 中文直觉名称 | 视觉机制标签 | 支持 ColorSource 类型 |
|---|---|---|---|
| `static` | 静态常亮 | 纯色空间常亮 | `GLOBAL` |
| `breath` | 呼吸渐变 | 全局周期性明暗呼吸 | `GLOBAL` |
| `calm` | 平静微光 | 低刺激低饱和微光漂移 | `GLOBAL` |
| `step_pulse` | 方波脉冲 | 双色方波硬切跳变 | `NOT_APPLICABLE` |
| `color_wave` | 彩虹波浪 | 连续 HSV 彩虹空间波浪流动 | `NOT_APPLICABLE` |
| `chase` | 流水跑灯 | 定宽亮块间隙跑动/拖尾/弹跳 | `POSITIONAL` |
| `comet` | 彗星拖尾 | 单/多发射源彗星扫过并渐衰 | `POSITIONAL` |
| `color_wipe` | 颜色擦除 | 沿灯带逐步点亮铺满 | `POSITIONAL` |
| `single_dot` | 单点游走 | 孤立单像素无拖尾干净游走 | `POSITIONAL` |
| `theater_phase` | 剧场追光 | 三相掩码步进跳动 | `POSITIONAL` |
| `flowing_bands` | 流动色带 | 空间交替色带高亮巡游 | `POSITIONAL` |
| `twinkle` | 随机星光 | 像素随机闪烁与指数衰减 | `EVENT` |
| `onset_ripple` | 打击涟漪 | 声音冲击触发扩散波浪 | `EVENT` |
| `heat_fire` | 模拟火焰 | 一维物理火焰燃烧与火星爆发 | `POSITIONAL` |
| `history_stream` | 历史光流 | 将时间信号随流速推入空间 | `POSITIONAL` |
| `coherent_noise_field` | 相干噪声场 | 柔和连续的云雾流动纹理 | `POSITIONAL` |
| `audio_pulse` | 全频音频脉冲 | 随总音量冲击全局跳动 | `GLOBAL` |
| `bass_pulse` | 低音律动 | 随重低音能量爆发起伏 | `GLOBAL` |
| `spectrum` | 三频段均衡器 | 低/中/高音独立驱动灯带区域 | `NOT_APPLICABLE` |
| `video_ambient` | 视频环境光 | 实时跟踪屏幕画面边缘色彩 | `NOT_APPLICABLE` |
| `video_audio_fusion` | 视音频融合 | 视频定底色 + 音频驱动扩散闪烁 | `NOT_APPLICABLE` |
| `demo` | 效果巡检轮播 | 定时轮流展示各种基础灯效 | `NOT_APPLICABLE` |

---

# 第 0 章：10 分钟快速开始

### 核心概念速览
- **Show（节目）**：一个完整的 YAML 文件，定义整场演出的总时长（`duration`）以及一组按时间轴排布的片段。
- **Cue（片段）**：演出中的一段灯光事件，拥有开始时间（`start`）、结束时间（`end`）、作用目标（`target`）、灯光效果（`effect`）与色彩（`color`/`color_source`）。
- **Target（目标）**：灯光作用的对象，可以是单条物理灯带（`digital_strip`）、一组灯带（`digital_set`）或多条灯带拼接的逻辑连续路径（`virtual_path`）。
- **Effect（灯效）**：灯光运动与形状算法（如 `chase`、`breath`、`coherent_noise_field`）。
- **Speed & Intensity**：`speed` 控制运动速率（`0.0` 即暂停），`intensity` 控制整体亮度比例。

### 最小完整可运行 Show
这是一个与当前 **9-target production software profile** 兼容、并已通过当前 loader 校验的最小 Show：

```yaml
# [COMPLETE RUNNABLE SHOW]
# created_at: 2026-08-23
# purpose: 最小可运行基础氛围演示节目
# status: approved
# source: independent
# hardware_verified: false

schema_version: 2
show:
  id: minimal_quickstart_show
  duration: 20.0
  defaults:
    fade_in: 0.5
    fade_out: 0.5
    blend: replace
  cues:
    - id: cue_intro_breath
      start: 0.0
      end: 10.0
      priority: 10
      target:
        type: digital_strip
        id: strip_11
      effect:
        mode: fixed
        id: breath
        intensity: 1.0
        params:
          period: 4.0
          min_brightness: 0.1
          color: [1.0, 0.5, 0.2]
    - id: cue_smooth_calm
      start: 9.0
      end: 20.0
      priority: 20
      target:
        type: digital_strip
        id: strip_11
      effect:
        mode: fixed
        id: calm
        intensity: 0.8
        params:
          period: 6.0
          color: [0.2, 0.6, 1.0]
```

### 怎么修改它？
1. **改时间**：修改 `duration`（总时长）以及各 Cue 的 `start` 和 `end`（秒数，`0 <= start < end <= duration`）。
2. **改灯带**：将 `target.id` 改为当前 9 条灯带中的任意一条（例如 `strip_12`、`strip_22`、`strip_44`）。
3. **改效果**：将 `effect.id` 改为第 9 章图鉴中的效果名，并在 `params` 中填入该效果对应的参数。
4. **验证 YAML**：使用 Windows 终端运行以下命令：
   ```powershell
   .\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show your_show.yaml
   ```

---

# 第 1 章：脑中的系统工作模型

在编写 Show YAML 之前，请先建立清晰的分层模型：

```
+-------------------------------------------------------------------------------+
| 控制端 APP (手机/平板)                                                        |
|  * 职责: 仅负责选择节目、Play / Pause / Resume / Stop、全局亮度和音频音量调节    |
|  * 边界: APP 无法编辑灯效参数或时间线，Show 文件的全部内容直接决定灯光行为       |
+-------------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------------+
| Show YAML 节目单 (编写者工作区域)                                             |
|  * 职责: 声明时间轴 (Cue)、逻辑目标 (Target)、灯效 (Effect)、色彩 (Color)、     |
|          动态调制 (Modulation) 与跨灯带空间路径 (Virtual Path)                 |
+-------------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------------+
| RK3588 中央主机 (light_engine 引擎运行时)                                     |
|  * 职责: 加载 Show YAML，实时采样音频与视频信号，驱动 MotionClock 运算，       |
|          生成每一帧的逻辑灯光像素数组，处理多层叠加与明暗衰减                  |
+-------------------------------------------------------------------------------+
                                    | (DDP UDP 协议, 端口 4048)
                                    v
+-------------------------------------------------------------------------------+
| ESP32 控制节点 (运行上游开源 WLED 固件) -> WS2811 数字灯带                     |
|  * 职责: 接收网口送达的 DDP 像素帧并刷新物理 LED                                |
+-------------------------------------------------------------------------------+
```

> [!IMPORTANT]
> **作者视角**：编写者只需关注**“在什么时间、哪个逻辑 Target 上、用什么颜色和运动逻辑呈现灯光”**。你不需要知道任何 IP 地址、GPIO 针脚、DDP 数据包格式或硬件控制协议。

---

# 第 2 章：当前舱体可用 Target 速查表

当前 production software profile（`config/profiles/rk3588-host-service.yaml`）声明 **9 个独立 ESP32/DDP 数字输出目标**，对应 **9 条数字灯带（总计 200 组 WS2811 controllable groups）**。这是软件部署快照；本文不据此宣称九节点实物链路已经完成硬件验收。

### 2.1 当前可用数字灯带速查表

| Target ID | 像素组数 (Groups) | 视频采样区 (Video Zone) | 方向 (Direction) | 物理安装位置说明（保守声明） |
|---|:---:|:---:|:---:|---|
| `strip_11` | 10 | `top` | `forward` | 软件目标：`strip_11`；安装位置以现场实际布局图纸为准 |
| `strip_12` | 40 | `top` | `forward` | 软件目标：`strip_12`；安装位置以现场实际布局图纸为准 |
| `strip_21` | 10 | `bottom` | `forward` | 软件目标：`strip_21`；安装位置以现场实际布局图纸为准 |
| `strip_22` | 40 | `bottom` | `forward` | 软件目标：`strip_22`；安装位置以现场实际布局图纸为准 |
| `strip_31` | 10 | `left` | `forward` | 软件目标：`strip_31`；安装位置以现场实际布局图纸为准 |
| `strip_32` | 40 | `left` | `forward` | 软件目标：`strip_32`；安装位置以现场实际布局图纸为准 |
| `strip_41` | 10 | `right` | `forward` | 软件目标：`strip_41`；安装位置以现场实际布局图纸为准 |
| `strip_43` | 20 | `right` | `forward` | 软件目标：`strip_43`；安装位置以现场实际布局图纸为准 |
| `strip_44` | 20 | `right` | `forward` | 软件目标：`strip_44`；安装位置以现场实际布局图纸为准 |

> [!NOTE]
> - **拓扑快照性质**：上述 9 节点 / 200 组是当前环境的运行快照，并非引擎容量上限。
> - **纯数字 DDP 传输**：当前 production profile 中**没有**激活模拟 RGB+CCT 灯带（`analog_zone`）、STM32 或 RS-485 路径。
> - **`strip_32` 说明**：当前拓扑中 `strip_32` 是一条 40 组像素的**数字灯带**，切勿与历史文档中的模拟 COB `zone_32` 混淆。

### 2.2 舱体编号布局的物理位置参考（辅助信息）

项目当前的舱体编号布局资料给出了下列物理语义，可帮助节目作者理解编号；**软件可用性仍以 production profile 为准，现场最终安装若发生变化则以现场确认覆盖这里的描述**：

| 当前 Target | 编号布局资料中的位置参考 |
|---|---|
| `strip_11` | 屏幕上方 |
| `strip_21` | 屏幕下方 |
| `strip_31` | 屏幕左侧 |
| `strip_41` | 屏幕右侧 |
| `strip_12` | 舱体顶部/天花板边缘 |
| `strip_22` | 地面与墙面交界的底部边缘 |
| `strip_32` | 左侧圆窗/舱门周边 |
| `strip_43`, `strip_44` | 右侧墙面波浪灯带中的当前可用成员 |

同一编号资料还列有 `42`、`45` 两条右侧波浪灯带以及 `91`、`92`、`93` 预留/待拆编号；**它们不在当前 `rk3588-host-service.yaml` 的 9-target catalog 中，因此当前可运行 Show 不得写 `strip_42`、`strip_45`、`strip_91`、`strip_92` 或 `strip_93`。**

---

### 2.3 Target 描述类型

在 Cue 中，你可以使用以下三种方式指定目标：

1. **单条数字灯带 (`digital_strip`)**：
   ```yaml
   # [YAML FRAGMENT]
   target:
     type: digital_strip
     id: strip_11
   ```
2. **离散灯带集合 (`digital_set`)**：
   用于分支释放或多灯带同时激活：
   ```yaml
   # [YAML FRAGMENT]
   target:
     type: digital_set
     ids: [strip_43, strip_44]
   ```
3. **连续虚拟路径 (`virtual_path`)**：
   在 Show 顶层定义并在 Cue 中引用，实现跨物理灯带的连续无缝运动（详见第 5 章）：
   ```yaml
   # [YAML FRAGMENT]
   target:
     type: virtual_path
     id: my_continuous_path
   ```

*(注：`digital_group` 与 `analog_zone` 属于语言规范支持范畴，但当前 production profile 未配置，请勿在面向当前 profile 的可运行 Show 中使用。)*

---

# 第 3 章：Show 与 Cue 的完整骨架

### 3.1 Show 顶层结构
一个完整的 Show v2 YAML 包含以下顶层模块：

```yaml
# [YAML FRAGMENT]
schema_version: 2
show:
  id: example_show_id          # [必填] 唯一英文字符串 ID
  duration: 60.0               # [必填] 总时长（秒），必须 > 0
  defaults:                    # [可选] 全局默认过渡设置
    fade_in: 0.5
    fade_out: 0.5
    blend: replace
  virtual_paths: []            # [可选] 跨灯带虚拟路径列表
  brightness_tracks: []        # [可选] 目标明暗自动化轨迹列表
  cues: []                     # [必填] 按时间轴排序的 Cue 列表
```

### 3.2 Cue 完整字段拆解
每个 Cue 均支持以下字段：

```yaml
# [YAML FRAGMENT]
- id: cue_unique_identifier     # [必填] Cue 唯一名称
  start: 0.0                    # [必填] 开始时间（秒，>= 0）
  end: 10.0                     # [必填] 结束时间（秒，start < end <= duration）
  priority: 10                  # [可选] 优先级（整数 >= 0，默认 0）
  target:                       # [必填] 目标灯带或路径
    type: digital_strip
    id: strip_11
  origin: start                 # [可选] 逻辑空间原点 (start | end | center | edges)
  transition:                   # [可选] 淡入淡出与混合设置
    fade_in: 0.5
    fade_out: 0.5
    blend: replace              # replace (覆盖) | add (线性相加)
  color:                        # [可选] Legacy ColorSpec；本例的 ColorSource 会接管 RGB 采样
    mode: solid
    color: [1.0, 0.5, 0.0]
  effect:                       # [必填] 灯效配置
    mode: fixed
    id: coherent_noise_field    # 本例选择一个支持 ColorSource 且 contrast 可调制的 fixed effect
    speed: 1.0                  # 通用运动速率乘数
    intensity: 1.0              # 通用 effect 强度乘数
    params:
      feature_size_px: 10.0
      drift_rate: 0.3
      contrast: 1.0             # modulate 模式要求基准参数显式存在
  color_source:                 # [可选] Cue 级动态色彩源
    type: spatial_palette
    palette: [[1, 0, 0], [0, 0, 1]]
  audio_modulation:             # [可选] 通用 brightness/speed/intensity 调制
    brightness:
      source: audio.rms
      amount: 0.5
      min_multiplier: 0.2
      max_multiplier: 1.5
      smoothing_seconds: 0.1    # audio_modulation channel 中为必填字段
  parameter_modulation:         # [可选] 安全 effect-local 浮点参数调制
    - target: contrast
      source: audio.treble
      mode: modulate
      output_min: 0.5
      output_max: 2.0
      fallback: 1.0
      smoothing_seconds: 0.1
  branches: []                  # [可选] 仅 fixed cue；详见第 5 章
```

### 3.3 Fixed 模式 vs Adaptive 模式
- **Fixed 模式 (`mode: fixed`)**：指定固定的 `id` 和 `params`。Cue 级 `color_source`、`parameter_modulation` 与 `branches` 都要求 fixed effect。
- **Adaptive 模式 (`mode: adaptive`)**：由引擎根据 `MusicControlState` 将当前音乐归入 8 种状态：`silence`, `calm`, `flowing`, `rhythmic`, `energetic`, `impact`, `transition`, `ambient`，再从 `allowed` 中选择 effect。`fallback` 必须指向 `allowed` 中已经出现的某个 effect。
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: adaptive
    allowed:
      silence: calm
      calm: breath
      flowing: color_wave
      rhythmic: chase
      energetic: chase
      impact: onset_ripple
      transition: color_wave
      ambient: calm
    fallback: breath
  ```

### 3.4 Adaptive 的节拍与切换稳定性：`audio_control`

`audio_control` 主要对 **Adaptive cue** 有意义：它决定何时认为节拍足够可靠、Adaptive 的 common speed 如何跟随节拍，以及音乐状态切换需要多稳定。Fixed cue 虽然 schema 能解析该块，但 fixed selector 不消费这些 Adaptive 决策参数，因此节目作者不应把它当作 fixed effect 的普通调制器。

| 字段 | 范围/枚举 | 默认 | 作用 |
|---|---|---:|---|
| `tempo_sync` | `off` / `auto` | `off` | 是否允许在节拍可信时进入 beat-sync |
| `tempo_confidence_min` | `[0,1]` | `0.0` | 节拍同步最低 tempo confidence |
| `beat_regularity_min` | `[0,1]` | `0.0` | 节拍同步最低规律度 |
| `beats_per_cycle` | `> 0` 或省略 | 省略时按 4 拍 | 一个 effect 运动周期对应多少拍 |
| `beat_subdivision` | `0.25`, `0.5`, `1`, `2`, `4` | `1.0` | 将每周期拍数按该粒度量化 |
| `speed_smoothing_seconds` | `>= 0` | `0.0` | beat/envelope 产生的 Adaptive speed 平滑时间 |
| `state_confirmation_seconds` | `>= 0` | `0.0` | 新音乐状态必须持续多久才确认切换 |
| `min_effect_hold` | `>= 0` | `0.0` | effect 切换后的最短保持时间 |
| `switch_cooldown` | `>= 0` | `0.0` | 两次 effect 切换之间的冷却时间 |

```yaml
# [YAML FRAGMENT]
- id: adaptive_music_scene
  start: 0.0
  end: 60.0
  target:
    type: digital_strip
    id: strip_12
  effect:
    mode: adaptive
    allowed:
      silence: calm
      calm: breath
      flowing: color_wave
      rhythmic: chase
      energetic: chase
      impact: onset_ripple
      transition: color_wave
      ambient: calm
    fallback: breath
  audio_control:
    tempo_sync: auto
    tempo_confidence_min: 0.75
    beat_regularity_min: 0.70
    beats_per_cycle: 4.0
    beat_subdivision: 1.0
    speed_smoothing_seconds: 0.5
    state_confirmation_seconds: 1.0
    min_effect_hold: 5.0
    switch_cooldown: 2.0
```

> `transition.min_effect_hold` / `transition.switch_cooldown` 也可以提供默认门限；当 `audio_control` 中对应值 **大于 0** 时，以 `audio_control` 的值优先。它们控制的是 Adaptive 切换稳定性，不是 `parameter_modulation`。

---

# 第 4 章：时间、叠加与运动时钟

### 4.1 时间与混合 (Blend & Transition)
- **`start` / `end`**：定义 Cue 在时间轴上的区间。多个 Cue 可以完全重叠运行。
- **`priority`**：多个 Cue 命中同一目标时，按 `(priority, 声明顺序)` 从低到高进入合成；因此高 priority 会**更晚**参与合成。`blend: replace` 时它通常覆盖/插值到低 priority 结果之上，`blend: add` 时则继续叠加，而不是简单“高者永远覆盖低者”。
- **`blend: replace`**：淡入淡出时与底色做插值渐变（$\text{底色} \times (1 - w) + \text{新色} \times w$）。
- **`blend: add`**：将新色按权重线性叠加到底色上（亮光叠加效果，上限截断为 1.0）。

### 4.2 运动时钟 (Integrated Motion Clock)
LIGHT-BELT 采用**积分运动时钟**驱动所有动态效果：
- **`speed` 代表运动流速**，而不是相位跳变：
  - `speed: 1.0` $\to$ 正常速度流动。
  - `speed: 0.0` $\to$ **运动瞬间冻结在原地**。
  - `speed: 2.0` $\to$ 以双倍流速从冻结位置继续向前推进。
- **`motion_time` vs `wall_time`**：
  - 几何运动、波浪前进、流星位移等运动相位遵循 `motion_time`（受 composed common speed 缩放与冻结影响）。
  - `color_timeline`、淡入淡出、Brightness Track 等仍按 Show/Cue 的挂钟时间推进。
  - Branch 的 `after` 释放使用 **`(show_time - cue.start) / cue_duration` 的归一化 Cue 进度** 与虚拟路径累计长度比较，因此不会因为你把 `effect.speed` 调快/调慢就把 release 点改成“可见光头正好经过某像素”的时刻。

### 4.3 目标明暗轨迹 (Target Brightness Tracks)
在无需修改 Cue 的前提下，可通过 Show 顶层的 `brightness_tracks` 独立控制目标的明暗曲线：

```yaml
# [YAML FRAGMENT]
brightness_tracks:
  - id: right_wall_accent
    target:
      type: digital_strip
      id: strip_44
    interpolation: linear       # linear (线性插值) | step (阶梯突变)
    start: 5.0
    end: 25.0
    keyframes:
      - { time: 5.0, value: 0.2 }
      - { time: 15.0, value: 1.0 }
      - { time: 25.0, value: 0.2 }
```

> [!IMPORTANT]
> - **轨迹不自发光**：Brightness Track 只是明暗衰减乘数；如果当前 Cue 输出全黑，`全黑 * 1.0` 依然是全黑。
> - **时间段互斥**：同一物理灯带若配置多条 Track，它们的时间区间 `[start, end)` 严禁重叠。

---

# 第 5 章：空间控制：方向、虚拟路径与分支

### 5.1 四个 Origin（逻辑空间原点变换）
`origin` 在 effect 完成一帧逻辑渲染后做坐标重映射。它描述的是 **Show 的逻辑路径方向**；物理灯带是否在 profile 中配置 `direction: reverse` 是另一层 mapping 语义。

- **`origin: start`**（逻辑起点向终点）：
  ```
  [逻辑 0 / start] ──>──>──>──>──>──> [逻辑 N-1 / end]
  ```
- **`origin: end`**（逻辑终点向起点）：
  ```
  [逻辑 0 / start] <──<──<──<──<──<── [逻辑 N-1 / end]
  ```
- **`origin: center`**（逻辑中心向两端对称扩散）：
  ```
  [start] <──<── [ Center ] ──>──> [end]
  ```
- **`origin: edges`**（逻辑两端向中心对称聚拢）：
  ```
  [start] ──>──> [ Center ] <──<── [end]
  ```

当 Cue target 是 `virtual_path` 且 Cue 自己没有写 `origin` 时，它继承该 path 的 `origin`；显式 Cue `origin` 会覆盖 path origin。非 path Cue 缺省按 `start` 处理。

---

### 5.2 虚拟路径 (Virtual Path)
`virtual_path` 允许你把多个逻辑 target 组织成**一条连续坐标路径**。这不是电气串联：各 ESP32 仍独立接收自己的 DDP 帧，只是 RK3588 在渲染阶段先把它们视为一条长路径。

- 引擎先按整条逻辑长度渲染，再按 member 长度拆回各实体 target。
- 对 `chase`、`comet`、`color_wipe`、`theater_phase`、`flowing_bands`、`coherent_noise_field` 等依赖逻辑位置的效果，跨成员接缝不会重新从 0 起算。
- **输入原生 effect 有例外**：作者自定义 `virtual_path` 在 renderer 侧表现为一条合成逻辑 strip，当前合成 `video_zone` 为 `center`。因此 `video_ambient` / `video_audio_fusion` 不会在同一 virtual path 内保留每个 member 原本的 `top/left/right/bottom` 取色语义；`spectrum` 也不适合靠 virtual path member ID 做三频区分。需要保留 member 输入语义时，优先对真实 strip / `digital_set` 分别编 Cue。

```yaml
# [YAML FRAGMENT]
virtual_paths:
  - id: top_ceiling_run
    origin: start
    targets:
      - { type: digital_strip, id: strip_11 }  # 10 组
      - { type: digital_strip, id: strip_12 }  # 40 组 (整条虚拟路径共 50 组)
```

---

### 5.3 有界分支 (Bounded Branching)
Branch 是**“同一个 fixed Cue 的另一份 effect instance，在一个确定的路径进度后变为可见”**，不是独立子 Cue。

关键规则：

- **`after.virtual_path` + `after.target`**：指定一个 Show v2 authored path 及其中的某个 member。引擎按 member 的累计逻辑长度计算 release progress，再与 Cue 的归一化时间进度比较。
- **不是波前检测**：它不会读取 `chase` 的头、`comet` 的彗星位置，也不会因为 `effect.speed` 改变而重新判断“光跑到哪了”。
- **Branch 不能另写自己的 effect**：它继承父 Cue 的 fixed effect、effect params、Cue color、ColorSource、audio/parameter modulation 和同一 motion clock；Branch 只额外声明 release 条件、`digital_set` target、`origin` 和 lifecycle。
- **`start_on_release`**：隐藏期间不 render；release frame 是该 Branch effect instance 的第一帧。
- **`pre_roll`**：从父 Cue 激活起就使用真实的 cue time、motion interval、audio/video 输入后台 render，但隐藏贡献会被丢弃；release 时继续同一个实例，不重置、不双算。
- Branch target 当前必须是 `digital_set`。这不是通用 DAG/任意树图 API。

```yaml
# [YAML FRAGMENT]
branches:
  - after:
      virtual_path: top_ceiling_run
      target: strip_11           # 这里表示 strip_11 这一 member 的累计路径完成比例
    target:
      type: digital_set
      ids: [strip_43, strip_44]
    origin: start
    lifecycle: pre_roll
```

例如 `top_ceiling_run = strip_11(10) + strip_12(40)` 且 `origin: start` 时，`after: strip_11` 的 release progress 是 `10/50 = 0.2`。30 秒 Cue 会约在 Cue 局部时间 6 秒释放；这与父 effect 的可见光头实际是否在该位置无关。

---

### 5.4 跨灯带分叉实战技巧：共享前缀并行虚拟路径
由于分支系统不支持通用 DAG 复杂树状分支，若需实现“光点流动到某一分叉点后同时兵分两路”，最佳实战做法是**定义两条共享前缀的虚拟路径**：

```yaml
# [YAML FRAGMENT]
virtual_paths:
  - id: fork_branch_a
    origin: start
    targets:
      - { type: digital_strip, id: strip_11 }  # 共同前缀
      - { type: digital_strip, id: strip_12 }  # 路线 A
  - id: fork_branch_b
    origin: start
    targets:
      - { type: digital_strip, id: strip_11 }  # 共同前缀
      - { type: digital_strip, id: strip_43 }  # 路线 B
```

用**两个时间、priority、origin、effect 参数与颜色完全相同的 fixed Cue**，分别 target 这两条 path，即可让共享前缀上的逻辑坐标一致，并在前缀结束后各自进入不同目的地。一个 Cue 本身只能有一个 `target`，所以不是“一个 Cue 同时 target 两条 path”。

这种做法适合“我真的要让一个 `chase` 在共享前缀后同步分叉”的视觉；不要把 bounded `branch.after` 当成 wavefront detector 来替代它。

---

# 第 6 章：颜色系统与动态采样

### 6.1 基础色彩 (Legacy `ColorSpec`)
在 Cue 的 `color` 模块中配置：
- **单色**：`color: { mode: solid, color: [1.0, 0.2, 0.0] }`
- **默认色**：`color: { mode: effect_default }`
- **循环调色板**：`color: { mode: palette, colors: [[1,0,0], [0,1,0], [0,0,1]] }`

---

### 6.2 六种高级动态色彩源 (`ColorSource`)

在 Cue 级别声明 `color_source` 模块可实现高级色彩流动：

| ColorSource 类型 | 视觉效果 | 依赖输入 | 采样机制 | 适用效果类别 |
|---|---|---|---|---|
| **`timeline`** | 随时间流逝平滑变色 | Cue 局部时间 | 全局时间插值 | `GLOBAL` / `POSITIONAL` |
| **`spatial_palette`** | 彩虹渐变固定铺满整条灯带 | 空间坐标 | 沿路径百分比采样 | `POSITIONAL` |
| **`video_average`** | 实时跟随视频全屏平均色 | 视频输入 | 需指定 `fallback` | `GLOBAL` / `POSITIONAL` |
| **`video_dominant`** | 实时跟随视频画面主色调 | 视频输入 | 需指定 `fallback` | `GLOBAL` / `POSITIONAL` |
| **`audio_spectrum_palette`** | 16段频谱能量决定空间色彩 | 音频频谱 | 低频端对应低音，高频端对应高音 | `POSITIONAL` |
| **`dominant_frequency_palette`** | 声音主音高决定全局色彩 | 主音高 (Hz) | `frequency_min/max_hz` 映射调色板 | `GLOBAL` / `POSITIONAL` |

#### 空间渐变示例 (`spatial_palette`)
```yaml
# [YAML FRAGMENT]
color_source:
  type: spatial_palette
  palette:
    - [0.1, 0.2, 0.9]   # 路径起点偏蓝
    - [0.8, 0.1, 0.6]   # 路径中段偏紫
    - [1.0, 0.8, 0.2]   # 路径末端偏金
```

#### 音高映射示例 (`dominant_frequency_palette`)
```yaml
# [YAML FRAGMENT]
color_source:
  type: dominant_frequency_palette
  frequency_min_hz: 100.0   # 低频基准 (100 Hz)
  frequency_max_hz: 2000.0  # 高频基准 (2000 Hz)
  palette:
    - [1.0, 0.2, 0.1]       # 低音偏红暖色
    - [0.1, 0.8, 1.0]       # 高音偏蓝冷色
  fallback: [0.2, 0.2, 0.2] # 无音频时的保底色
```

> [!CAUTION]
> **色彩铁律：Brightness Envelope 保护机制**：
> `ColorSource` **只替换色彩（RGB 色相）**，**绝不破坏灯效本身的明暗轮廓（亮度包络）**。
> 例如：当使用 `comet`（彗星）时，即便 `ColorSource` 输出满亮白光 `[1, 1, 1]`，彗星尾部的像素依然会按指数衰减变暗；使用 `breath` 时，全白色彩依然会随呼吸节律忽明忽暗。


### 6.3 六种 ColorSource 的必填项与 fallback

| 类型 | 关键字段 | 缺输入时 |
|---|---|---|
| `timeline` | `interpolation: rgb_linear` + 至少 2 个严格递增 `keyframes` | 不依赖外部输入；超出关键帧区间时钳到首/尾色 |
| `spatial_palette` | 非空 `palette` | 不依赖外部输入 |
| `video_average` | `fallback` | 无 `VideoFeatures` 时使用 authored fallback |
| `video_dominant` | `fallback` | 无 `VideoFeatures` 时使用 authored fallback |
| `audio_spectrum_palette` | 非空 `palette` + `fallback` | 整个 `AudioFeatures` 缺失时用 fallback；若 AudioFeatures 存在但 spectrum 未单独供应，模型提供 16 个零能量 bin，因此采 palette 起点 |
| `dominant_frequency_palette` | `frequency_min_hz < frequency_max_hz` + 非空 `palette` + `fallback` | 无 AudioFeatures 时用 fallback；频率超范围时钳到 palette 两端 |

`timeline` 示例：

```yaml
# [YAML FRAGMENT]
color_source:
  type: timeline
  interpolation: rgb_linear
  keyframes:
    - { time: 0.0, color: [1.0, 0.0, 0.0] }
    - { time: 4.0, color: [0.0, 0.0, 1.0] }
```

> [!IMPORTANT]
> Cue 级 `color_source.type: timeline` 与 effect 参数中的 `params.color_timeline` 是两套独立合同；前者是 Phase 39 的统一 ColorSource，后者是部分旧 renderer 保留的 effect-local 时间线参数。同样，`chase` / `twinkle` 的 `params.color_source` 也是旧 effect-local 枚举，不是 Cue 级 `color_source`。

---

# 第 7 章：声音与视频如何参与灯效

### 7.1 `AudioFeatures`：当前帧的音频测量数据

`AudioFeatures` 是 effect / ColorSource / modulation 能读取的“这一帧声音事实”。它不是视觉规则。

| 字段 | 范围/类型 | 含义 |
|---|---|---|
| `rms` / `loudness` | `[0,1]` | 归一化总体响度；当前模型在提供 `loudness` 时会同步 legacy `rms` |
| `bass` | `[0,1]` | 低频能量（约 20–200 Hz） |
| `mid` | `[0,1]` | 中频能量（约 200–2000 Hz） |
| `treble` | `[0,1]` | 高频能量（约 2000–12000 Hz） |
| `spectral_flux` | `[0,1]` | 频谱变化/瞬态强度 |
| `onset` | `[0,1]` | 起音冲击强度 |
| `peak` / legacy `beat` | bool | 峰值/拍点标记；当前模型会保持两者兼容 |
| `spectrum[0..15]` | 16 个 `[0,1]` bin | 16 段归一化频谱；bass/mid/treble 可由这些区间聚合 |
| `raw_level` | `>= 0` 原始域 | 未归一化的原始输入 level；不能直接假设是 `[0,1]` |
| `dominant_frequency` | `>= 0` Hz | 当前主导频率事实 |
| `dominant_magnitude` | `>= 0` 原始域 | 主导频率幅值 |
| `silence` | bool | 当前输入是否处于静音状态 |

> [!NOTE]
> **数据与艺术意义解耦**：系统没有全局“bass=红、treble=蓝”的作者规则。`spectrum` effect 自己为了保持既有视觉定义，内部固定使用 bass 红 / mid 绿 / treble 蓝；这只是这个 effect 的局部算法。`ColorSource`、`parameter_modulation` 和你自己的 Show 映射仍由作者决定颜色意义。

### 7.2 `MusicControlState`：Adaptive 与 legacy `audio_modulation` 的音乐控制状态

除了 `AudioFeatures`，分析层还维护更慢、更结构化的 `MusicControlState`：

`tempo_bpm`, `tempo_confidence`, `beat_phase`, `beat_strength`, `beat_regularity`, `energy`, `energy_trend`, `transient`, `bass_ambient`, `bass_pulse`, `spectral_motion`。

它主要被两处消费：

1. Adaptive selector：判断 `silence/calm/flowing/rhythmic/energetic/impact/transition/ambient`，并通过 `audio_control` 做 tempo sync、state confirmation、hold/cooldown；
2. `audio_modulation` 的 `music.*` sources。

### 7.3 三种“信号接入方式”不要混为一谈

- **Audio/video-native effect**：例如 `audio_pulse`, `bass_pulse`, `spectrum`, `video_ambient`, `video_audio_fusion`, `onset_ripple`，effect 自己定义输入如何影响视觉。
- **ScalarSource**：少数 effect 参数直接读取一个**自然归一化**信号，如 `color_wipe.progress_source`、`twinkle.event_gate_source`、`history_stream.sample_gain_source`。
- **Cue modulation**：
  - `audio_modulation` 只改 common `brightness/speed/intensity`；
  - `parameter_modulation` 只改 live registry 明确标记为可安全调制的 effect-local float。

---

# 第 8 章：Modulation：人工参数与声音控制怎么叠加

为了让灯光跟随音乐而不破坏人工设计，先用三种直觉理解：

- **MANUAL**：只写 authored base；声音不介入。
- **MODULATED**：人工 base 仍是设计中心，实时信号只乘上一个受限 multiplier。
- **DRIVEN**：实时信号直接把某个安全参数驱动到作者给定的 `[output_min, output_max]` 区间。

```
                              ┌──> audio_modulation (common: brightness / speed / intensity)
[音乐/音频/进度输入信号] ─────┤
                              └──> parameter_modulation (11 个 live white-list effect float)
```

### 8.1 `audio_modulation`（通用控件调制）

`audio_modulation` 每个 channel 都必须写 `source`, `amount`, `min_multiplier`, `max_multiplier`, `smoothing_seconds`。`amount` 在 `[0,1]`；min/max multiplier 在 `[0,10]` 且 `min <= max`。

对于普通 `[0,1]` source，内部先转成 `[-1,1]` 的 signed signal，再计算并钳制 `1 + amount * signal`。`music.energy_trend` 本身已经是 `[-1,1]`。source 缺失时该 channel 返回中性 `1.0`，并清除该 channel 的 smoothing history。

**当前可用 source 恰好是以下 15 个：**

- `AudioFeatures`：`audio.rms`, `audio.bass`, `audio.mid`, `audio.treble`, `audio.spectral_flux`, `audio.onset`
- `MusicControlState`：`music.energy`, `music.energy_trend`, `music.beat_strength`, `music.bass_pulse`, `music.bass_ambient`, `music.transient`, `music.spectral_motion`, `music.tempo_confidence`, `music.beat_regularity`

注意：`audio.loudness`, `audio.peak`, `audio.spectrum[i]`, `audio.dominant_frequency` **不是 legacy `audio_modulation` source**；它们可以在 ScalarSource 或 `parameter_modulation` 的相应合同中使用。

```yaml
# [YAML FRAGMENT]
audio_modulation:
  brightness:
    source: audio.rms
    amount: 0.6
    min_multiplier: 0.2
    max_multiplier: 1.5
    smoothing_seconds: 0.1
  speed:
    source: music.beat_strength
    amount: 0.8
    min_multiplier: 0.5
    max_multiplier: 2.0
    smoothing_seconds: 0.15
```

这里的 `brightness` 是**该 Cue effect 输出之后、进入 transition/blend composition 之前**的额外帧亮度乘数；它不是 APP 的最终全局 master brightness。`intensity` 则会作为 common effect 强度进入 renderer。两者都还会在更后面受到全局输出变换影响。

---

### 8.2 `parameter_modulation`（灯效专有参数调制）
仅支持对 11 个经过安全认证的浮点参数进行实时控制。

#### 白名单 11 个 Modulatable 参数表
| 所属 Effect ID | 参数名 (`target`) | 允许取值范围 | 物理/视觉含义 |
|---|---|:---:|---|
| `breath` | `min_brightness` | `[0.0, 1.0]` | 呼吸波谷最低亮度 |
| `color_wave` | `hue_span_degrees` | `[0.0, 360.0]` | 彩虹波跨越的色相角度跨度 |
| `color_wipe` | `edge_softness_px` | `[0.0, 10000.0]` | 擦除边缘柔化像素宽度 |
| `flowing_bands` | `base_gain` | `[0.0, 1.0]` | 非高亮暗色带亮度增益 |
| `flowing_bands` | `highlight_gain` | `[0.0, 1.0]` | 高亮巡游色带亮度增益 |
| `onset_ripple` | `floor_gain` | `[0.0, 1.0]` | 涟漪扩散背景底亮 |
| `coherent_noise_field` | `contrast` | `[0.0, 4.0]` | 噪声云雾对比度 |
| `video_audio_fusion` | `video_weight` | `[0.0, 1.0]` | 视频色彩占比权重 |
| `video_audio_fusion` | `audio_weight` | `[0.0, 1.0]` | 音频亮度占比权重 |
| `video_audio_fusion` | `bass_boost` | `[0.0, 10.0]` | 低音扩散脉冲增强倍数 |
| `video_audio_fusion` | `treble_limit` | `[0.0, 1.0]` | 高频微光闪烁上限 |

#### 两种调制模式对比
1. **`mode: modulate`（基准倍数缩放）**：
   - 必须在 `params` 中显式书写基准参数（如 `contrast: 1.0`）。
   - 音频信号作为乘数放大或缩小该基准值：$\text{最终值} = \text{基准值} \times \text{调制乘数}$。
   ```yaml
   # [YAML FRAGMENT]
   parameter_modulation:
     - target: contrast
       source: audio.treble
       mode: modulate
       output_min: 0.5          # 乘数下限 0.5 倍
       output_max: 2.0          # 乘数上限 2.0 倍
       fallback: 1.0
       smoothing_seconds: 0.1
   ```

2. **`mode: drive`（绝对数值范围直接驱动）**：
   - 音频信号在 `[output_min, output_max]` 区间内直接线性映射输出。
   ```yaml
   # [YAML FRAGMENT]
   parameter_modulation:
     - target: edge_softness_px
       source: audio.loudness
       mode: drive
       output_min: 0.0          # 音量为 0 时硬边缘 (0 px)
       output_max: 8.0          # 音量最大时柔化边缘 (8 px)
       fallback: 0.0
       smoothing_seconds: 0.08
   ```

### 8.3 `parameter_modulation` 的 source、fallback 与 raw-domain 归一化

**自然归一化 sources**：

- `cue_progress`
- `audio.rms`, `audio.loudness`, `audio.bass`, `audio.mid`, `audio.treble`, `audio.spectral_flux`, `audio.onset`, `audio.peak`
- `audio.spectrum[0]` ... `audio.spectrum[15]`

这些 source 自然位于 `[0,1]`。`audio.peak` 是布尔量，采样时映射为 `0/1`。

**原始域 sources**：

- `audio.raw_level`
- `audio.dominant_frequency`
- `audio.dominant_magnitude`

原始域没有全局统一的 `[0,1]` 定义，因此必须显式写有限的 `input_min` / `input_max`，且 `input_max > input_min`：

```yaml
# [YAML FRAGMENT]
parameter_modulation:
  - target: contrast
    mode: drive
    source: audio.dominant_frequency
    input_min: 80.0
    input_max: 1200.0
    output_min: 0.5
    output_max: 2.0
    fallback: 1.0
    smoothing_seconds: 0.1
```

- `drive`：如果 source 是可能缺失的 audio source，必须提供 `fallback`；`cue_progress` 永远存在，因此不要求 fallback。
- `modulate`：如果 source 缺失且没有显式 fallback，立即恢复 authored base，并清掉该 binding 的 smoothing history；显式 fallback 则属于 multiplier 输出域并参与 smoothing。
- 所有映射后的 endpoint/fallback 组合都还会重新进入 effect 的 live validator。例如 `flowing_bands.highlight_gain` 不能被调到小于 `base_gain` 的非法组合。

### 8.4 ScalarSource：effect 参数里的轻量 source selector

ScalarSource 只接受**自然归一化**输入，不接受 raw-domain 三项。当前 10 个 source family / 25 个具体可写 source 为：

- `cue_progress`
- `audio.rms`
- `audio.loudness`
- `audio.bass`
- `audio.mid`
- `audio.treble`
- `audio.spectral_flux`
- `audio.onset`
- `audio.peak`
- `audio.spectrum[0]` ... `audio.spectrum[15]`

它当前被少数 effect-local 参数使用，例如：

- `color_wipe.progress_source`
- `twinkle.event_gate_source`
- `twinkle.birth_gain_source`
- `history_stream.sample_gain_source`

当运行时 audio 输入不存在时，effect 内普通 `ScalarSource.sample()` 会得到 `0.0`；而 `parameter_modulation` 使用可感知“输入缺失”的 optional sampling，因此能执行前述 fallback 合同。两者不要混为一套错误处理规则。

---

# 第 9 章：22 个 Native Effect 完整图鉴

---

### Category A: 基础与环境氛围 (Basic / Ambient)

#### 1. `static` — 静态常亮
- **你会看到什么**：整条灯带或目标区域恒定点亮为指定单色，无任何动态闪烁或运动。
- **适合什么时候**：基础照明、静态底色铺陈、场景转场间歇。
- **主要驱动力**：静态时间配置。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 配置文件默认值 | 静态发光色彩 | 否 |
  | `color_timeline` | `color_timeline` | 线性关键帧列表 | 省略则使用固定色 | 随时间渐变的色彩序列 | 否 |
- **Common Controls**：`intensity` 线性缩放整体亮度。
- **色彩与音视频**：支持 Legacy ColorSpec，`ColorSourceSupport: GLOBAL`。无原生音视频依赖。
- **Virtual Path 表现**：全路径均匀单色点亮。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: static
    intensity: 1.0
    params:
      color: [0.2, 0.4, 0.8]
  ```

---

#### 2. `breath` — 呼吸渐变
- **你会看到什么**：灯光整体同步忽明忽暗，宛如平稳呼吸。
- **适合什么时候**：舒缓等待界面、冥想引导、背景氛围律动。
- **主要驱动力**：周期波形振荡。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `period` | `float` | `> 0.001` 秒 | `4.0` 秒 | 完整呼吸一次的总周期 | 否 |
  | `min_brightness` | `float` | `[0.0, 1.0]` | `0.01` | 呼气波谷时的最低残留亮度 | **是** |
  | `waveform` | `enum` | `sine`, `triangle`, `smoothstep` | `sine` | 呼吸明暗起伏的波形曲线 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 配置文件默认值 | 呼吸灯光基准色彩 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 随时间演进的色彩序列 | 否 |
- **Common Controls**：`intensity` 缩放最大输出亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: GLOBAL`（色彩乘以呼吸波形包络）。`min_brightness` 支持音频调制。
- **Virtual Path 表现**：整条路径全局同步呼吸。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: breath
    intensity: 1.0
    params:
      period: 3.5
      min_brightness: 0.05
      color: [0.8, 0.3, 0.1]
  ```

---

#### 3. `calm` — 平静微光
- **你会看到什么**：极低饱和度、极低亮度的微光缓慢呼吸，伴随极其细微的色相温和漂移（±10°）。
- **适合什么时候**：夜间休眠模式、低刺激放松、极暗环境点缀。
- **主要驱动力**：慢周期时间振荡。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `period` | `float` | `> 0.001` 秒 | `12.0` 秒 | 慢速微光漂移周期 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 配置文件默认值 | 中心基准色彩（内部自动压低饱和度） | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 慢速变色序列 | 否 |
- **Common Controls**：`intensity` 控制最大亮度（内部最大亮度被限制在 0.35）。
- **色彩与音视频**：支持 `ColorSourceSupport: GLOBAL`。无原生音视频依赖。
- **Virtual Path 表现**：整条路径均匀呈现微光。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: calm
    intensity: 0.6
    params:
      period: 8.0
      color: [0.2, 0.3, 0.6]
  ```

---

#### 4. `step_pulse` — 方波跳变脉冲
- **你会看到什么**：灯光在低电平基准色（`low_color`）与高电平脉冲色（`high_color`）之间进行无过渡的离散硬切跳变。
- **适合什么时候**：机械节拍卡点、警报指示、硬派电子乐节奏闪烁。
- **主要驱动力**：周期方波与占空比。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `period` | `float` | `> 0.001` 秒 | `4.0` 秒 | 脉冲完整周期 | 否 |
  | `duty_cycle` | `float` | `[0.0, 1.0]` | `0.5` | 高电平状态所占周期比例 | 否 |
  | `low_color` | `rgb` | 各通道 `[0.0, 1.0]` | 偏暗暖色 | 低电平暗态颜色 | 否 |
  | `high_color` | `rgb` | 各通道 `[0.0, 1.0]` | 偏亮暖色 | 高电平亮态颜色 | 否 |
- **Common Controls**：`intensity` 缩放输出亮度。
- **色彩与音视频**：由 `low_color` 与 `high_color` 直接定义；`ColorSourceSupport: NOT_APPLICABLE`。
- **Virtual Path 表现**：全路径同步跳变。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: step_pulse
    intensity: 1.0
    params:
      period: 1.0
      duty_cycle: 0.2
      low_color: [0.0, 0.0, 0.0]
      high_color: [1.0, 0.0, 0.0]
  ```

---

### Category B: 运动、几何与流动 (Motion / Geometry)

#### 5. `color_wave` — 彩虹波浪
- **你会看到什么**：一抹连续流动的绚丽彩虹波浪沿着灯带向前推进，空间上色彩平滑渐变，整体色相随时间持续旋转。
- **适合什么时候**：动感科技流动、空间引导、色彩丰富的高潮段落。
- **主要驱动力**：空间波形与色相积分推进。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | 浮点数 | `1.0` 周期/秒 | 波浪空间推进速率 | 否 |
  | `width` | `float` | `> 0.001` | `0.3` | 波浪特征宽度占总长度比例 | 否 |
  | `hue_cycle_rate` | `float` | 浮点数 | `0.1` 周期/秒 | 基准色相旋转漂移速率 | 否 |
  | `waveform` | `enum` | `linear`, `sine`, `triangle`, `saw` | `linear` | 空间色相渐变波形曲线 | 否 |
  | `hue_span_degrees` | `float` | `[0.0, 360.0]` 度 | `120.0` 度 | 整个波形跨越的色相角宽度 | **是** |
- **Common Controls**：`speed` 乘以推进速率；`intensity` 缩放亮度。
- **色彩与音视频**：原生 HSV 彩虹生成器；`ColorSourceSupport: NOT_APPLICABLE`。`hue_span_degrees` 支持音频调制。
- **Virtual Path 表现**：跨物理灯带连续计算波形，接缝处色彩无缝衔接。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: color_wave
    speed: 1.5
    intensity: 1.0
    params:
      speed: 1.0
      width: 0.4
      hue_span_degrees: 180.0
  ```

---

#### 6. `chase` — 流水跑灯
- **你会看到什么**：指定长度的明亮光块沿着灯带匀速奔跑，后方伴随可调节的拖尾衰减，支持正向、反向或端点反弹。
- **适合什么时候**：能量传输、方向引导、速度感营造。
- **主要驱动力**：运动时钟位移推进。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | 像素/秒 | `2.0` | 光块奔跑速度 | 否 |
  | `width` | `integer` | `>= 0` 像素 | `5` | 亮光块的核心像素长度 | 否 |
  | `gap` | `integer` | `>= 0` 像素 | `10` | 两个光块之间的暗区像素间隙 | 否 |
  | `direction` | `enum` | `forward`, `reverse`, `bounce` | `forward` | 运动方向（正向/反向/两端反弹） | 否 |
  | `trail` | `float` | 浮点数 | `0.3` | 光块尾部残余亮度比例 | 否 |
  | `color_source` | `enum` | `rainbow`, `video`, `static` | `rainbow` | 内部色彩源策略 | 否 |
  | `beat_boost` | `float` | 浮点数 | `2.0` | 检测到音乐节拍时的瞬时加速倍数 | 否 |
- **Common Controls**：`speed` 缩放像素流速；`intensity` 缩放亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。若音频节拍触发且 `beat_boost > 1.0` 则瞬间加速。
- **Virtual Path 表现**：在整条连续虚拟路径上奔跑，跨灯带绝不断位。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: chase
    speed: 1.0
    intensity: 1.0
    params:
      speed: 20.0
      width: 6
      gap: 14
      trail: 0.5
      direction: forward
      color_source: static
  ```

---

#### 7. `comet` — 彗星拖尾
- **你会看到什么**：一颗或多颗明亮的彗星头部划过夜空，身后拖着长长渐暗的彗尾。支持循环穿越、反弹以及正弦往复运动轨迹。
- **适合什么时候**：流星划过、高雅穿梭感、多粒子同向/对向追逐。
- **主要驱动力**：运动时钟位置与指数拖尾衰减。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | `>= 0.0` 像素/秒 | `1.5` | 彗星移动速度 | 否 |
  | `tail_length` | `float` | `>= 0.0` 路径比例 | `0.4` | 彗尾长度占灯带总长的比例 | 否 |
  | `decay` | `float` | `[0.0, 1.0]` | `0.85` | 彗尾每帧衰减系数（越小尾巴越短） | 否 |
  | `count` | `integer` | `[1, 64]` | `1` | 并行彗星发射源数量 | 否 |
  | `phase_spacing` | `float` | `[0.0, 1.0]` 周期比例 | `1.0 / count` | 多个彗星之间的相位间隔 | 否 |
  | `trajectory` | `enum` | `wrap`, `bounce`, `sine` | `wrap` | 运动轨迹（循环穿透/端点反弹/正弦往复） | 否 |
- **Common Controls**：`speed` 控制位移速度；`intensity` 控制彗星整体光芒强度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`（彗星头部与拖尾沿路径染色，同时保持头部最亮、尾部变暗的自然包络）。
- **Virtual Path 表现**：彗尾长度自动适应整条虚拟路径总长，流畅穿梭。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: comet
    speed: 1.0
    intensity: 1.0
    params:
      speed: 12.0
      tail_length: 0.35
      count: 2
      trajectory: wrap
  ```

---

#### 8. `color_wipe` — 颜色擦除铺满
- **你会看到什么**：光线从一端出发，像刷漆一样逐步将整条灯带点亮，走过的像素保持常亮直至全线铺满。
- **适合什么时候**：进度加载、仪式感开启、舞台充能铺满。
- **主要驱动力**：运动积分时间或音频能量驱动进度。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | `[0.0, 1000.0]` 像素/秒 | `20.0` | 擦除点亮速率 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 亮蓝色 | 铺满颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 擦除过程中的色彩演进 | 否 |
  | `progress_source` | `scalar_source` | 标量源选择器 | `None` (时间驱动) | 改由声音能量（如 `audio.rms`）驱动进度 | 否 |
  | `slew_seconds` | `float` | `>= 0.0` 秒 | `0.0` | 进度变化平滑滤波时间 | 否 |
  | `edge_softness_px` | `float` | `[0.0, 10000.0]` 像素 | `0.0` | 推进边缘的柔化过渡宽度 | **是** |
  | `progress_curve` | `enum` | `linear`, `smoothstep` | `linear` | 推进过程的速度曲线 | 否 |
- **Common Controls**：`speed` 缩放时间擦除速度；`intensity` 缩放亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。`edge_softness_px` 支持音频调制。
- **Virtual Path 表现**：沿虚拟路径连续铺满，尊重 `origin` 空间原点设置。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: color_wipe
    speed: 1.0
    intensity: 1.0
    params:
      speed: 25.0
      edge_softness_px: 2.0
      color: [0.1, 0.7, 1.0]
  ```

---

#### 9. `single_dot` — 孤立单点游走
- **你会看到什么**：整条灯带上仅有**孤立的一个像素点**在整洁游走，没有任何拖尾或扩散。
- **适合什么时候**：精密寻迹、雷达扫描点、极简主义空间定位。
- **主要驱动力**：离散整数像素索引推进。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | 像素/秒 | `5.0` | 单点游走速度 | 否 |
  | `direction` | `enum` | `forward`, `reverse`, `bounce` | `forward` | 游走方向 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 极暗蓝 | 点的颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 点游走过程中的变色序列 | 否 |
- **Common Controls**：`speed` 改变游走速度；`intensity` 缩放点亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。
- **Virtual Path 表现**：在整条连续虚拟路径上精准游走。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: single_dot
    speed: 1.0
    intensity: 1.0
    params:
      speed: 10.0
      direction: bounce
      color: [1.0, 1.0, 0.0]
  ```

---

#### 10. `theater_phase` — 剧场追光 (跑马灯)
- **你会看到什么**：经典剧院跑马灯效果：每隔 2 个暗像素亮 1 个像素（`index % 3 == phase`），以三相步进方式离散跳变推进，无任何平滑模糊。
- **适合什么时候**：复古舞台追光、狂欢庆典、经典跑马灯边界。
- **主要驱动力**：三相离散步进时钟。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `speed` | `float` | 相位步/秒 | `2.5` | 步进切换频率 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 极暗蓝 | 点亮像素颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 跑马灯变色序列 | 否 |
- **Common Controls**：`speed` 缩放跳变频率；`intensity` 缩放亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。
- **Virtual Path 表现**：`index % 3` 跨物理接缝严格保持模 3 连续。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: theater_phase
    speed: 1.0
    intensity: 1.0
    params:
      speed: 6.0
      color: [1.0, 0.8, 0.0]
  ```

---

#### 11. `flowing_bands` — 空间交替流动色带
- **你会看到什么**：灯带上排列着固定宽度的亮暗条纹网格（A B A B A B）。随着时间推移，一道醒目的高亮脉冲（C）沿着条纹依次点亮各个 A 带，但底层的条纹网格本身并不平移。
- **适合什么时候**：科技通道巡检、阵列信号传输、秩序感强烈的流动。
- **主要驱动力**：固定空间网格 + 离散步进状态巡游。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `band_width_px` | `integer` | `[1, 10000]` 像素 | `1` | A 亮带的像素宽度 | 否 |
  | `gap_width_px` | `integer` | `[1, 10000]` 像素 | `1` | B 暗隙的像素宽度 | 否 |
  | `base_gain` | `float` | `[0.0, 1.0]` | `0.125` | 未被高亮时的普通 A 带亮度 | **是** |
  | `highlight_gain`| `float` | `[0.0, 1.0]` | `0.625` | 被 C 状态扫过时的高亮亮度 | **是** |
  | `steps_per_second` | `float` | `[0.0, 1000.0]` 步/秒 | `1.0` | 高亮状态在各条带间转移的速率 | 否 |
  | `direction` | `enum` | `forward`, `reverse` | `forward` | 高亮转移方向 | 否 |
  | `phase_offset_steps` | `integer` | `[0, 10000]` | `0` | 初始高亮步进偏移 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 白色 | 条带基准颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 条带变色序列 | 否 |
- **Common Controls**：`speed` 改变步进转移速率；`intensity` 整体缩放。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。`base_gain` 与 `highlight_gain` 支持音频调制。
- **Virtual Path 表现**：条纹网格跨灯带无缝拼接。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: flowing_bands
    speed: 1.0
    intensity: 1.0
    params:
      band_width_px: 2
      gap_width_px: 2
      base_gain: 0.1
      highlight_gain: 0.9
      steps_per_second: 4.0
      color: [0.0, 0.9, 0.7]
  ```

---

### Category C: 事件、随机与物理模拟 (Event / Random / State)

#### 12. `twinkle` — 随机星光闪烁
- **你会看到什么**：像素点在灯带上随机诞生并像星星般闪烁，随后以指数规律柔和衰减熄灭。
- **适合什么时候**：星空顶、梦幻夜景、静谧氛围衬托。
- **主要驱动力**：随机泊松过程与指数衰减。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `density` | `float` | `[0.0, 100.0]` 事件/像素秒 | `0.12` | 星光诞生的空间密度 | 否 |
  | `fade_time` | `float` | `[0.01, 60.0]` 秒 | `0.7` | 星光闪烁后的衰减半衰期 | 否 |
  | `color_source` | `enum` | `solid`, `palette`, `random` | `random` | 内部星星色彩模式 | 否 |
  | `event_width_px`| `float` | `[0.01, 10000.0]` 像素 | `1.0` | 星星光斑的核心宽度 | 否 |
  | `blur_radius_px` | `float` | `[0.0, 10000.0]` 像素 | `0.0` | 星星光斑的边缘羽化半径 | 否 |
  | `event_gate_source` | `scalar_source` | 标量源 | `None` | 音频门控（无声时不产生星星） | 否 |
  | `birth_gain_source` | `scalar_source` | 标量源 | `None` | 音频强度决定新星星的诞生亮度 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 白色 | 单色模式下的星光颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 随时间演变的星光色彩 | 否 |
- **Common Controls**：`intensity` 缩放星光亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: EVENT`（星星诞生时刻确定颜色并终身锁定）。支持通过 `event_gate_source` 绑定音频。
- **Virtual Path 表现**：全路径自然散落分布。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: twinkle
    intensity: 1.0
    params:
      density: 0.25
      fade_time: 1.2
      color_source: solid
      color: [1.0, 0.9, 0.7]
  ```

---

#### 13. `onset_ripple` — 冲击波扩散涟漪
- **你会看到什么**：当音乐出现鼓击、重音瞬态冲击（Onset）时，从固定起点或随机位置瞬间激发出三角形波浪，以恒定速度向外扩散并逐渐衰减消散。
- **适合什么时候**：鼓点打击实时反馈、踩点动效、声光强烈互动。
- **主要驱动力**：实时音频打击检测 + 物理波动扩散模拟。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `onset_threshold` | `float` | `[0.0, 1.0]` | `0.35` | 触发涟漪诞生的声音冲击阈值 | 否 |
  | `wave_speed_pps` | `float` | `[0.0, 1000.0]` 像素/秒 | `18.0` | 涟漪波浪向前传播的速度 | 否 |
  | `wave_width_px` | `float` | `[0.1, 1000.0]` 像素 | `2.0` | 三角形扩散波峰的宽度 | 否 |
  | `decay_seconds` | `float` | `[0.01, 60.0]` 秒 | `1.5` | 涟漪在传播过程中的消散时间 | 否 |
  | `floor_gain` | `float` | `[0.0, 1.0]` | `0.0` | 无涟漪时的背景底色亮度 | **是** |
  | `event_origin` | `enum` | `fixed`, `random` | `fixed` | 涟漪发源地（固定起点 / 随机爆发） | 否 |
  | `propagation` | `enum` | `one_way`, `bidirectional` | `one_way` | 传播方向（单向推进 / 双向扩散） | 否 |
  | `wrap` | `boolean` | `true`, `false` | `false` | 波浪到达末端是否循环绕回 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 橙暖色 | 涟漪波峰颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 涟漪颜色序列 | 否 |
- **Common Controls**：`speed` 改变波浪传播速度；`intensity` 改变波峰亮度。
- **色彩与音视频**：原生强依赖音频瞬态（`audio.onset`, `peak`）；`ColorSourceSupport: EVENT`。`floor_gain` 支持音频调制。
- **Virtual Path 表现**：涟漪沿虚拟路径自然扩散，跨灯带连续传播。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: onset_ripple
    speed: 1.0
    intensity: 1.0
    params:
      onset_threshold: 0.3
      wave_speed_pps: 25.0
      decay_seconds: 1.0
      event_origin: fixed
      propagation: bidirectional
      color: [1.0, 0.4, 0.1]
  ```

---

#### 14. `heat_fire` — 一维模拟火焰
- **你会看到什么**：真实的 60Hz 物理火焰燃烧效果：底部不断爆发随机火星，热量向上扩散蔓延，同时空气持续冷却，呈现逼真的火焰摇曳感。
- **适合什么时候**：温暖壁炉、营火燃烧、能量喷射。
- **主要驱动力**：一维热传导方程 + 随机火星注入。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `cooling_per_second` | `float` | `[0.0, 60.0]` /秒 | `0.8` | 热量向上散逸的冷却速率 | 否 |
  | `spark_rate` | `float` | `[0.0, 60.0]` /秒 | `8.0` | 底部产生新火星的概率频率 | 否 |
  | `spark_strength` | `float` | `[0.0, 1.0]` | `0.9` | 爆发火星的热量初始强度 | 否 |
  | `diffusion` | `float` | `[0.0, 1.0]` | `0.35` | 相邻像素间的热量扩散系数 | 否 |
  | `spark_zone_px` | `integer` | `[1, 10000]` 像素 | `3` | 底部允许产生火星的像素范围 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 火焰金橙色 | 火焰热量映射的基准色彩 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 火焰变色序列 | 否 |
- **Common Controls**：`speed` 改变火焰燃烧与蔓延的模拟流速；`intensity` 缩放火焰光晕。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`（单色热量按亮度比例自然显色）。
- **Virtual Path 表现**：整条虚拟路径作为单根虚拟热管统一模拟向上燃烧。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: heat_fire
    speed: 1.0
    intensity: 1.0
    params:
      cooling_per_second: 1.2
      spark_rate: 10.0
      spark_strength: 0.95
      diffusion: 0.3
      spark_zone_px: 4
      color: [1.0, 0.3, 0.05]
  ```

---

#### 15. `history_stream` — 历史光流 (时间映射到空间)
- **你会看到什么**：时空转换光流：在灯带起点以固定步频持续采样当前输入色彩与音量增益，并像传送带一样将历史数据向后推移，形成一条记录了过去声音/色彩轨迹的“时间河流”。
- **适合什么时候**：音乐旋律记录留痕、心电图/波形记录仪、连续光流记录。
- **主要驱动力**：先进先出（FIFO）时间采样移位寄存器。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `steps_per_second` | `float` | `[0.001, 1000.0]` 步/秒 | `10.0` | 历史采样与空间推移步频 | 否 |
  | `direction` | `enum` | `forward`, `reverse` | `forward` | 推移方向（起点向后 / 末端向前） | 否 |
  | `sample_gain_source`| `scalar_source` | 标量源 | `None` | 采样时刻的亮度增益源（如 `audio.rms`） | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 白色 | 采样基准颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 随时间渐变的采样颜色 | 否 |
- **Common Controls**：`speed` 改变传送带流速；`intensity` 缩放整体亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`。可绑定 `sample_gain_source` 记录音乐起伏。
- **Virtual Path 表现**：历史队列容量自动匹配虚拟路径全长。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: history_stream
    speed: 1.0
    intensity: 1.0
    params:
      steps_per_second: 15.0
      direction: forward
      sample_gain_source: audio.bass
      color: [0.3, 0.8, 1.0]
  ```

---

#### 16. `coherent_noise_field` — 相干噪声场 (云雾漫游)
- **你会看到什么**：空间上平滑连续、随时间缓慢漂移的柔和云雾明暗纹理。相邻像素亮度渐变自然，绝无孤立像素的杂乱闪烁。
- **适合什么时候**：深海极光、流动星云、有机生物质感呼吸、高级环境光。
- **主要驱动力**：二维相干晶格噪声数学模拟。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `feature_size_px` | `float` | `[0.01, 10000.0]` 像素 | `8.0` | 噪声云雾斑块的空间尺度（越大越平缓） | 否 |
  | `drift_rate` | `float` | `[0.0, 1000.0]` /秒 | `0.25` | 纹理随时间自然漂移的流速 | 否 |
  | `contrast` | `float` | `[0.0, 4.0]` | `1.0` | 云雾明暗对比度（越大明暗越悬殊） | **是** |
  | `floor_gain` | `float` | `[0.0, 1.0]` | `0.10` | 噪声暗部的最低保底亮度 | 否 |
  | `ceiling_gain` | `float` | `[0.0, 1.0]` | `0.85` | 噪声亮部的最高峰值亮度 | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 天蓝色 | 云雾基准色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 云雾渐变颜色序列 | 否 |
- **Common Controls**：`speed` 改变时间漂移流速；`intensity` 缩放输出亮度。
- **色彩与音视频**：支持 `ColorSourceSupport: POSITIONAL`（极为推荐搭配 `spatial_palette` 呈现丰富极光色）。`contrast` 支持音频调制。
- **Virtual Path 表现**：按连续空间坐标采样，跨灯带无缝平滑过渡。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: coherent_noise_field
    speed: 1.0
    intensity: 1.0
    params:
      feature_size_px: 10.0
      drift_rate: 0.4
      contrast: 1.5
      floor_gain: 0.05
      ceiling_gain: 0.95
      color: [0.1, 0.5, 0.9]
  ```

---

### Category D: 音视频原生驱动 (Audio / Video Native)

#### 17. `audio_pulse` — 全频音量脉冲
- **你会看到什么**：整条灯带随着全频段总音量（RMS）的起伏进行灵敏的脉冲跳动，具备专业的 Attack/Release 动态包络。
- **适合什么时候**：通用音乐整体卡点、全场跟随音量闪耀。
- **主要驱动力**：实时全频音频 RMS 能量。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `attack` | `float` | `> 0.001`（runtime 速率系数） | `0.4` | 上升跟随速率；**数值越大越快** | 否 |
  | `release` | `float` | `> 0.001`（runtime 速率系数） | `0.15` | 下降跟随速率；**数值越大越快** | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 橙金色 | 脉冲颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 脉冲变色序列 | 否 |
- **Common Controls**：`intensity` 缩放最大脉冲亮度。
- **色彩与音视频**：原生依赖音频信号。支持 `ColorSourceSupport: GLOBAL`。无声音时平滑归零至黑色。
- **Virtual Path 表现**：全局同步跳动。
- **参数语义注意**：当前 Registry metadata 仍把 `attack/release` 的 unit 标为 `seconds`，但实际 `AttackReleaseEnvelope` runtime 按“每秒跟随速率系数”使用；节目调参应遵循本节的 **越大越快** 语义。这是 metadata 表述债务，不改变 YAML 字段。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: audio_pulse
    intensity: 1.0
    params:
      attack: 0.2
      release: 0.3
      color: [1.0, 0.6, 0.1]
  ```

---

#### 18. `bass_pulse` — 重低音律动
- **你会看到什么**：专门捕捉 20–200 Hz 重低音（底鼓、贝斯）能量，产生力量感强烈的低音冲击律动，内部带有 1.5 倍低音增益。
- **适合什么时候**：电子乐蹦迪、重低音节奏卡点、力量感震撼爆发。
- **主要驱动力**：实时低频能量（Bass）。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `attack` | `float` | `> 0.001`（runtime 速率系数） | `0.6` | 低音上升跟随速率；**数值越大越快** | 否 |
  | `release` | `float` | `> 0.001`（runtime 速率系数） | `0.2` | 低音下降跟随速率；**数值越大越快** | 否 |
  | `color` | `rgb` | 各通道 `[0.0, 1.0]` | 冰蓝色 | 律动颜色 | 否 |
  | `color_timeline` | `color_timeline` | 关键帧列表 | 省略则固定色 | 变色序列 | 否 |
- **Common Controls**：`intensity` 缩放冲击力度。
- **色彩与音视频**：原生依赖低频信号。支持 `ColorSourceSupport: GLOBAL`。
- **Virtual Path 表现**：全局同步响应低音。
- **参数语义注意**：当前 Registry metadata 仍把 `attack/release` 的 unit 标为 `seconds`，但实际 `AttackReleaseEnvelope` runtime 按“每秒跟随速率系数”使用；节目调参应遵循本节的 **越大越快** 语义。这是 metadata 表述债务，不改变 YAML 字段。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: bass_pulse
    intensity: 1.2
    params:
      attack: 0.1
      release: 0.25
      color: [0.1, 0.4, 1.0]
  ```

---

#### 19. `spectrum` — 三频段空间均衡器
- **你会看到什么**：三频段音乐均衡器：低音驱动红色、中音驱动绿色、高音驱动蓝色，分别输出到各自指定的灯带区域列表。
- **适合什么时候**：音乐频谱可视化、空间分区域声学映射。
- **主要驱动力**：实时 16 段频谱分频聚合。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `bass_zones` | `id_list` | 目标 ID 字符串列表 | `[]` | 响应重低音（红光）的目标灯带 ID 列表 | 否 |
  | `mid_zones` | `id_list` | 目标 ID 字符串列表 | `[]` | 响应中音（绿光）的目标灯带 ID 列表 | 否 |
  | `treble_zones` | `id_list` | 目标 ID 字符串列表 | `[]` | 响应高音（蓝光）的目标灯带 ID 列表 | 否 |
- **Common Controls**：`intensity` 缩放整体亮度。
- **色彩与音视频**：这个 effect **内部固定** bass=暖红、mid=绿色、treble=蓝色，`ColorSourceSupport: NOT_APPLICABLE`。这只是 `spectrum` 自身视觉定义，不是整个系统的频率→颜色规则。
- **Virtual Path 表现**：建议直接作用于真实 strip / `digital_set`，并在 `bass_zones/mid_zones/treble_zones` 中写当前 strip ID。作者自定义 `virtual_path` 在 renderer 中会合成为一个 synthetic strip ID，因此不会自动按 path member ID 继续三频分区。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: spectrum
    intensity: 1.0
    params:
      bass_zones: [strip_21, strip_22]
      mid_zones: [strip_31, strip_32]
      treble_zones: [strip_11, strip_12]
  ```

---

#### 20. `video_ambient` — 实时视频环境流光 (Ambilight)
- **你会看到什么**：当直接作用于真实 strip 时，灯带读取该 strip 配置的 `video_zone`（上/下/左/右/中心等）对应色彩，并配合 EMA 平滑后整条输出，实现画面色调向舱体灯光延伸。
- **适合什么时候**：观影模式、大屏视频联动、随电影画面自适应环境光。
- **主要驱动力**：实时视频帧图像分析。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `smoothing` | `float` | `[0.0, 1.0]` | `0.15` | EMA 平滑因子；`0` 近似即时响应，数值越大越保留上一帧、响应越慢；`1` 不再跟随新输入 | 否 |
- **Common Controls**：`intensity` 缩放环境光亮度。
- **色彩与音视频**：原生依赖视频流；`ColorSourceSupport: NOT_APPLICABLE`。没有 `VideoFeatures` 时使用安全暗色 `(0.02, 0.02, 0.05)`，不是纯黑。
- **Virtual Path 表现**：直接 target 真实 strip / `digital_set` 时，各 strip 使用自己的 `video_zone`。作者自定义 `virtual_path` 会在 renderer 侧合成为一条 `video_zone: center` 的逻辑 strip，因此**不会保留每个 path member 原来的 top/left/right/bottom 取色**；需要 Ambilight 分区时不要把这些 strip 合成一个 author-defined virtual path。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: video_ambient
    intensity: 1.0
    params:
      smoothing: 0.2
  ```

---

#### 21. `video_audio_fusion` — 视音频多维深度融合
- **你会看到什么**：视频提供环境底色，音频 RMS 控制整体亮度，重低音激发从中心向外的漫射波，中音提升色彩饱和度，高音在像素间激发微光闪烁，节拍点产生瞬态高亮闪烁。
- **适合什么时候**：顶级旗舰演示、高潮大片播放、全感官多模态融合体验。
- **主要驱动力**：视频图像流 + 实时多维音频特征深度融合。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `video_weight` | `float` | `[0.0, 1.0]` | `0.65` | 视频画面对亮度的权重占比 | **是** |
  | `audio_weight` | `float` | `[0.0, 1.0]` | `0.35` | 音频音量对亮度的权重占比 | **是** |
  | `bass_boost` | `float` | `[0.0, 10.0]` | `1.5` | 低音中心扩散波的爆发强度乘数 | **是** |
  | `treble_limit` | `float` | `[0.0, 1.0]` | `0.4` | 高音微光闪烁的最大幅度限制 | **是** |
- **Common Controls**：`intensity` 缩放总输出。
- **色彩与音视频**：原生强依赖视频与音频。4 个核心参数均支持 `parameter_modulation`。
- **Virtual Path 表现**：直接 target 真实 strip 时，低音扩散和高频 shimmer 在各 strip 内按其长度运行，并使用该 strip 的 `video_zone`。作者自定义 `virtual_path` 会变成一条 synthetic `center` strip：它仍能产生融合视觉，但会丢失各 member 原来的 video-zone 取色语义。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: video_audio_fusion
    intensity: 1.0
    params:
      video_weight: 0.7
      audio_weight: 0.3
      bass_boost: 2.0
      treble_limit: 0.3
  ```

---

### Category E: 巡检与工具 (Utility)

#### 22. `demo` — 效果巡检轮播
- **你会看到什么**：自动按固定间隔（如每 10 秒）依次轮播切换展示列表中的各个注册灯效。
- **适合什么时候**：展厅自运行巡检、新硬件上电能力演示。
- **专有参数表**：
  | 参数名 | 类型 | 取值范围 | 默认/省略行为 | 视觉含义 | 能否 parameter_modulation |
  |---|---|---|---|---|:---:|
  | `cycle_interval` | `float` | `> 0.001` 秒 | `10.0` 秒 | 切换到下一个效果的轮播间隔 | 否 |
  | `effects` | `id_list` | 效果 ID 列表 | 默认 6 个基础效果 | 参与轮播展示的效果名称列表 | 否 |
- **Common Controls**：直接继承自当前活跃的子效果。
- **色彩与音视频**：由当前轮播到的子效果决定；`ColorSourceSupport: NOT_APPLICABLE`。
- **最小 YAML 片段**：
  ```yaml
  # [YAML FRAGMENT]
  effect:
    mode: fixed
    id: demo
    params:
      cycle_interval: 8.0
      effects: [breath, color_wave, chase]
  ```

---

# 第 10 章：实战配方与典型组合

---

### 配方 A：最简单的固定氛围灯
单灯带 + 纯色 + 呼吸效果：
```yaml
# [YAML FRAGMENT]
- id: recipe_a_breath
  start: 0.0
  end: 15.0
  target:
    type: digital_strip
    id: strip_11
  effect:
    mode: fixed
    id: breath
    params:
      period: 4.0
      min_brightness: 0.1
      color: [1.0, 0.5, 0.2]
```

---

### 配方 B：一条光束跨多条物理灯带连续奔跑
利用 `virtual_path` 将 4 条灯带串联成 90 组像素的长跑道：
```yaml
# [YAML FRAGMENT]
virtual_paths:
  - id: perimeter_track
    origin: start
    targets:
      - { type: digital_strip, id: strip_11 }  # 10 组
      - { type: digital_strip, id: strip_12 }  # 40 组
      - { type: digital_strip, id: strip_43 }  # 20 组
      - { type: digital_strip, id: strip_44 }  # 20 组
cues:
  - id: recipe_b_continuous_chase
    start: 0.0
    end: 30.0
    target:
      type: virtual_path
      id: perimeter_track
    color:
      mode: solid
      color: [0.1, 0.8, 1.0]
    effect:
      mode: fixed
      id: chase
      speed: 1.0
      params:
        speed: 25.0
        width: 8
        gap: 20
        trail: 0.4
        color_source: static
```

---

### 配方 C：同一 Cue 同时作用于多条独立灯带
使用 `digital_set` 让一个 Cue 同时覆盖多条 strip。它们**不会被拼成一条连续坐标**；renderer 仍能按各 strip ID/长度维护自己的局部状态。需要光点真正跨接缝连续移动时，应改用 `virtual_path`。
```yaml
# [YAML FRAGMENT]
- id: recipe_c_synchronized_twinkle
  start: 0.0
  end: 20.0
  target:
    type: digital_set
    ids: [strip_31, strip_41]
  effect:
    mode: fixed
    id: twinkle
    params:
      density: 0.3
      fade_time: 0.8
      color_source: solid
      color: [0.9, 0.9, 1.0]
```

---

### 配方 D：音乐只调节运动流速与整体亮度
保持人工设定的灯效参数不变，仅通过 `audio_modulation` 随音乐能量调节速度与亮度：
```yaml
# [YAML FRAGMENT]
- id: recipe_d_audio_speed_boost
  start: 0.0
  end: 40.0
  target:
    type: digital_strip
    id: strip_12
  effect:
    mode: fixed
    id: flowing_bands
    params:
      band_width_px: 3
      gap_width_px: 3
      steps_per_second: 4.0
      color: [0.2, 0.6, 1.0]
  audio_modulation:
    brightness:
      source: audio.rms
      amount: 0.5
      min_multiplier: 0.3
      max_multiplier: 1.6
      smoothing_seconds: 0.1
    speed:
      source: audio.bass
      amount: 0.9
      min_multiplier: 0.5
      max_multiplier: 2.5
      smoothing_seconds: 0.1
```

---

### 配方 E：音乐直接驱动专有安全参数
使用 `parameter_modulation` 的 `drive` 模式，用音频瞬态响度直接驱动擦除边缘的柔化宽度：
```yaml
# [YAML FRAGMENT]
- id: recipe_e_dynamic_softness
  start: 0.0
  end: 30.0
  target:
    type: digital_strip
    id: strip_22
  effect:
    mode: fixed
    id: color_wipe
    params:
      speed: 15.0
      edge_softness_px: 0.0
      color: [1.0, 0.2, 0.5]
  parameter_modulation:
    - target: edge_softness_px
      source: audio.loudness
      mode: drive
      output_min: 0.0
      output_max: 6.0
      fallback: 0.0
      smoothing_seconds: 0.08
```

---

### 配方 F：极光空间渐变调色板
使用 `spatial_palette` 配合 `coherent_noise_field`，在整条灯带上铺设永不重复的漫游极光：
```yaml
# [YAML FRAGMENT]
- id: recipe_f_aurora_stream
  start: 0.0
  end: 45.0
  target:
    type: digital_strip
    id: strip_32
  effect:
    mode: fixed
    id: coherent_noise_field
    params:
      feature_size_px: 12.0
      drift_rate: 0.3
      contrast: 1.2
  color_source:
    type: spatial_palette
    palette:
      - [0.05, 0.1, 0.8]   # 湛蓝
      - [0.0, 0.8, 0.6]    # 极光青绿
      - [0.7, 0.1, 0.8]    # 梦幻紫
```

---

### 配方 G：音频频谱决定空间色彩
低音聚集在灯带起点，高音分布在灯带末端，根据实时频谱能量动态点亮颜色：
```yaml
# [YAML FRAGMENT]
- id: recipe_g_spectrum_color_flow
  start: 0.0
  end: 30.0
  target:
    type: digital_strip
    id: strip_12
  effect:
    mode: fixed
    id: chase
    params:
      speed: 15.0
      width: 6
      gap: 12
  color_source:
    type: audio_spectrum_palette
    palette:
      - [1.0, 0.1, 0.0]    # 低音偏红
      - [1.0, 0.8, 0.0]    # 中低音偏金
      - [0.1, 0.4, 1.0]    # 高音偏蓝
    fallback: [0.2, 0.2, 0.2]
```

---

### 配方 H：作者自定义主频→全局色彩
下面只是一个**作者选择的映射示例**：在 150–1800 Hz 内把较低主频映射到 palette 前端、较高主频映射到后端。反转 palette 就会反转颜色倾向，系统没有固定“低频红/高频青”规则：
```yaml
# [YAML FRAGMENT]
- id: recipe_h_pitch_color_mapping
  start: 0.0
  end: 30.0
  target:
    type: digital_strip
    id: strip_22
  effect:
    mode: fixed
    id: breath
    params:
      period: 3.0
  color_source:
    type: dominant_frequency_palette
    frequency_min_hz: 150.0   # 男低音区
    frequency_max_hz: 1800.0  # 女高音区
    palette:
      - [1.0, 0.2, 0.1]       # 低频红
      - [0.1, 0.9, 0.8]       # 高频青
    fallback: [0.3, 0.3, 0.3]
```

---

### 配方 I：后台预热并在路径进度点揭示 (Pre-roll Reveal)
这个示例故意使用**有状态的 `heat_fire`**：父 Cue 和 Branch 都运行同一个 effect。Branch 从 0 秒起后台模拟火焰，但在 `corridor_run` 的归一化 release progress 到达 `strip_11` 完成比例之前不可见；release 时显示已经演化到当前时刻的独立火焰状态。

```yaml
# [YAML FRAGMENT]
virtual_paths:
  - id: corridor_run
    origin: start
    targets:
      - { type: digital_strip, id: strip_11 }  # 10 / 50
      - { type: digital_strip, id: strip_12 }  # 40 / 50
cues:
  - id: recipe_i_fire_reveal
    start: 0.0
    end: 30.0
    target:
      type: virtual_path
      id: corridor_run
    effect:
      mode: fixed
      id: heat_fire
      params:
        cooling_per_second: 1.0
        spark_rate: 8.0
        spark_strength: 0.9
        diffusion: 0.35
        spark_zone_px: 3
        color: [1.0, 0.32, 0.04]
    branches:
      - after:
          virtual_path: corridor_run
          target: strip_11          # release progress = 10/50 = 0.2
        target:
          type: digital_set
          ids: [strip_43, strip_44]
        origin: start
        lifecycle: pre_roll
```

在这个 30 秒 Cue 中，`origin: start` 下约在 Cue 局部时间 6 秒释放。**这不表示 heat/fire 或任何可见波前“刚好走完 strip_11”**；release 只由 Cue 归一化时间进度和 path member 长度决定。

---

### 配方 J：独立明暗轨迹 (Brightness Tracks)
在灯效保持播放的同时，平滑压暗某一特定区域：
```yaml
# [YAML FRAGMENT]
brightness_tracks:
  - id: dim_front_area
    target:
      type: digital_strip
      id: strip_21
    interpolation: linear
    start: 10.0
    end: 25.0
    keyframes:
      - { time: 10.0, value: 1.0 }
      - { time: 15.0, value: 0.1 }   # 5秒内压暗至 10%
      - { time: 20.0, value: 0.1 }   # 保持暗态
      - { time: 25.0, value: 1.0 }   # 恢复原亮
```

---

# 第 11 章：3 个进阶完整可直接运行的 Show 示例

---

### Example 1：30 秒基础氛围 Show (基础照明与舒缓转场)
严格使用当前 production profile 的 Target，涵盖呼吸、平静与淡入淡出：

```yaml
# [COMPLETE RUNNABLE SHOW]
# created_at: 2026-08-23
# purpose: 30秒基础氛围与舒缓转场演示节目
# status: approved
# source: independent
# hardware_verified: false

schema_version: 2
show:
  id: example_01_basic_ambient
  duration: 30.0
  defaults:
    fade_in: 1.0
    fade_out: 1.0
    blend: replace
  cues:
    - id: cue_warm_welcome
      start: 0.0
      end: 16.0
      priority: 10
      target:
        type: digital_strip
        id: strip_11
      effect:
        mode: fixed
        id: breath
        intensity: 1.0
        params:
          period: 4.0
          min_brightness: 0.15
          color: [1.0, 0.55, 0.15]
    - id: cue_cool_relaxation
      start: 14.0
      end: 30.0
      priority: 20
      target:
        type: digital_strip
        id: strip_11
      effect:
        mode: fixed
        id: calm
        intensity: 0.8
        params:
          period: 6.0
          color: [0.15, 0.45, 0.95]
```

---

### Example 2：45 秒跨灯带连续空间 Show (虚拟路径流动与明暗轨迹)
通过 `virtual_path` 串联 `video_zone=top` 与 `video_zone=right` 中的 4 条 strip，共 90 组像素，并叠加明暗轨迹衰减：

```yaml
# [COMPLETE RUNNABLE SHOW]
# created_at: 2026-08-23
# purpose: 45秒跨灯带空间流动与明暗轨迹演示节目
# status: approved
# source: independent
# hardware_verified: false

schema_version: 2
show:
  id: example_02_spatial_motion
  duration: 45.0
  defaults:
    fade_in: 0.5
    fade_out: 0.5
    blend: replace
  virtual_paths:
    - id: ceiling_to_right_wall
      origin: start
      targets:
        - { type: digital_strip, id: strip_11 }  # 10 组
        - { type: digital_strip, id: strip_12 }  # 40 组
        - { type: digital_strip, id: strip_43 }  # 20 组
        - { type: digital_strip, id: strip_44 }  # 20 组
  brightness_tracks:
    - id: right_wall_accent_dimmer
      target:
        type: digital_strip
        id: strip_44
      interpolation: linear
      keyframes:
        - { time: 0.0, value: 0.4 }
        - { time: 22.5, value: 1.0 }
        - { time: 45.0, value: 0.4 }
  cues:
    - id: cue_space_chase
      start: 0.0
      end: 45.0
      priority: 10
      target:
        type: virtual_path
        id: ceiling_to_right_wall
      origin: start
      effect:
        mode: fixed
        id: chase
        speed: 1.2
        intensity: 1.0
        params:
          speed: 16.0
          width: 8
          gap: 20
          trail: 0.4
          direction: forward
          color_source: rainbow
```

---

### Example 3：60 秒音乐与色彩联动高级 Show
涵盖相干噪声云雾、空间色彩映射、通用音量调制与低音对比度调制：

```yaml
# [COMPLETE RUNNABLE SHOW]
# created_at: 2026-08-23
# purpose: 60秒音乐联动与空间色彩映射高级演示节目
# status: approved
# source: independent
# hardware_verified: false

schema_version: 2
show:
  id: example_03_audio_advanced
  duration: 60.0
  defaults:
    fade_in: 1.0
    fade_out: 1.0
    blend: replace
  virtual_paths:
    - id: cabin_ambient_loop
      origin: start
      targets:
        - { type: digital_strip, id: strip_21 }  # 10 组
        - { type: digital_strip, id: strip_22 }  # 40 组
        - { type: digital_strip, id: strip_31 }  # 10 组
        - { type: digital_strip, id: strip_32 }  # 40 组
  cues:
    - id: cue_aurora_audio_reactive
      start: 0.0
      end: 60.0
      priority: 10
      target:
        type: virtual_path
        id: cabin_ambient_loop
      effect:
        mode: fixed
        id: coherent_noise_field
        speed: 1.0
        intensity: 1.0
        params:
          feature_size_px: 12.0
          drift_rate: 0.4
          contrast: 1.2
          floor_gain: 0.1
          ceiling_gain: 0.9
      color_source:
        type: spatial_palette
        palette:
          - [0.05, 0.15, 0.85]  # 湛蓝
          - [0.85, 0.10, 0.65]  # 品红
          - [0.95, 0.75, 0.15]  # 暖金
      audio_modulation:
        brightness:
          source: audio.rms
          amount: 0.5
          min_multiplier: 0.3
          max_multiplier: 1.5
          smoothing_seconds: 0.1
        speed:
          source: audio.bass
          amount: 0.8
          min_multiplier: 0.5
          max_multiplier: 2.0
          smoothing_seconds: 0.15
      parameter_modulation:
        - target: contrast
          source: audio.treble
          mode: modulate
          output_min: 0.5
          output_max: 2.0
          fallback: 1.0
          smoothing_seconds: 0.1
```

---

# 第 12 章：新 Show 入库规范与生命周期

### 12.1 标准文件头注释 (Comment Header)
按当前仓库的 **Show admission / governance rules**，新 Show YAML **必须**以以下注释头开头。注释本身不会进入 YAML loader；之所以必须写成 `# ...`，是因为如果把 `created_at`、`status`、`hardware_verified` 等当成真正 YAML 顶层字段，严格 schema 会以 unknown field 拒绝。**单纯省略这些注释未必触发 parser error，但不符合当前入库规则。**

```yaml
# created_at: YYYY-MM-DD
# purpose: 一句话描述节目的视觉体验与应用场景
# status: draft | approved | production
# source: assets/energy-wakeup/energy-wakeup.yaml | independent
# hardware_verified: false
```

- **`status` 状态流转**：
  - `draft`：正在编辑构思中。
  - `approved`：通过团队代码评审与软件加载校验。
  - `production`：经项目的部署/验收流程确认后，可作为正式节目使用；若同时声称硬件已验证，仍需独立的真实硬件证据。
- **`hardware_verified: false`**：所有新编写的 Show 必须显式标记为 `false`，只有在真实物理设备上实测通过后方可由部署人员改为 `true`。

### 12.2 参考源原则
- **唯一兼容性基准**：`config/shows/energy-wakeup.yaml` 是当前唯一步调一致的兼容性基线。
- **严禁抄袭历史老 Show**：`config/shows/archive/` 下保留的 32 个历史 Show 仅用于回归测试，严禁从中抄录已废弃的 Target 名称或参数结构。

---

# 第 13 章：常见错误与避坑指南

### 13.1 常见校验错误排查

1. **使用当前 profile 不存在的 Target**
   - ❌ `wall_left`, `zone_32`, `strip_91`
   - ✅ 只使用第 2 章明确列出的 9 个 current target，或在 Show 内先定义并合法引用 `virtual_path`。

2. **Unknown effect / unknown parameter**
   - ❌ `effect.id: sparkle_magic`，或给 `chase.params` 填 `color`
   - ✅ effect ID 与 effect-local 参数必须来自第 9 章 / live registry；`chase` 的静态颜色放 Cue `color.mode: solid`，`params.color_source: static` 只负责选择 renderer 的旧色彩模式。

3. **参数范围或 enum 错误**
   - ❌ `origin: backwards`、`breath.waveform: square`、`min_brightness: 1.5`
   - ✅ 使用文档枚举与允许范围；loader 会给出精确 YAML path。

4. **把 common control 当 effect-local modulation target**
   - ❌ `parameter_modulation.target: speed`
   - ✅ common `brightness/speed/intensity` 归 `audio_modulation`；`parameter_modulation` 只允许 11 个 live modulatable float。

5. **同一 `parameter_modulation.target` 重复绑定**
   - ❌ 一个 Cue 对 `contrast` 写两条 binding
   - ✅ 每个 target 在同一 Cue 最多出现一次。

6. **Raw-domain source 没有输入边界**
   - ❌ `source: audio.dominant_frequency` 但不写 `input_min/input_max`
   - ✅ raw_level / dominant_frequency / dominant_magnitude 必须显式写有限且递增的输入范围。

7. **`drive` 缺少 audio fallback**
   - ❌ audio source + `mode: drive` 但没有 `fallback`
   - ✅ 除 `cue_progress` 外，可能缺失的 audio source 在 drive 模式必须写 final-value fallback。

8. **ColorSource 缺 fallback / 频率范围非法**
   - ❌ `video_average` 没 fallback；或 `frequency_min_hz >= frequency_max_hz`
   - ✅ input-driven ColorSource 按第 6.3 节补齐 fallback；dominant-frequency 范围必须严格递增。

9. **Adaptive 与 Fixed 字段混用**
   - ❌ `mode: adaptive` 同时写 `id` / `params` / Cue `color_source` / `parameter_modulation` / `branches`
   - ✅ Adaptive 写 `allowed` + `fallback`，需要稳定性时加 `audio_control`；高级 ColorSource/parameter modulation/branch 使用 fixed cue。

10. **Branch trigger 引用无效 path/member，或 Branch target 不是 `digital_set`**
    - ❌ `after.virtual_path` 不属于本 Show v2 authored paths；`after.target` 不是该 path member；Branch target 写 `digital_strip`
    - ✅ `after` 必须引用本 Show 定义的 path + 其中 member；release target 用 `digital_set`。

11. **把 Branch 当 wavefront detector**
    - ❌ 期望“chase 头真正到达 strip_11 的那一帧”才 release
    - ✅ `after` 是 cue progress × path cumulative length；真要做可见 chase 分叉，使用共享前缀的平行 virtual paths。

12. **Brightness Tracks 时间重叠**
    - ❌ 同一 concrete target 配 0–10s 和 5–15s 两个 Track
    - ✅ 同一实际 target 的 active interval `[start,end)` 不得重叠；每条 track 至少 2 个严格递增 keyframe。

13. **把 compatibility/example target 当 current production**
    - ❌ 从旧例子抄 `ceiling_left`, `wall_right`, `strip_92`
    - ✅ 当前 runnable Show 以 `config/profiles/rk3588-host-service.yaml` 的 9 个 strip 为准。

---

### 13.2 最容易搞混的 11 件事

1. **`effect.speed` vs `effect.params.speed`**：
   - `effect.speed` 是外部通用速率乘数（`1.0` 为基准）。
   - `effect.params.speed` 是效果内部的具体物理速度（单位如 `pixels_per_second`）。两者相乘得到最终流速。
2. **`intensity` vs `audio_modulation.brightness` vs 全局 master brightness**：
   - `effect.intensity` 是 Cue common effect 强度乘数，会进入 renderer。
   - `audio_modulation.brightness` 是 renderer 输出后的 Cue-local frame 亮度乘数，在 transition/blend 前应用。
   - APP / OutputTransform 的 master brightness 是更后面的全局输出层；它不是前两者的同一个字段。
3. **`ColorSpec.palette` vs `spatial_palette`**：
   - Legacy `ColorSpec.palette` 是随时间跳变颜色的离散调色板。
   - `spatial_palette` 是将多种颜色按空间比例平滑涂抹在整条长灯带上的空间渐变色。
4. **Cue 级 `color_source` vs `effect.params.color_source`**：
   - Cue 级 `color_source: {...}` 是 Show v2 的高级动态色彩引擎。
   - `effect.params.color_source: rainbow` 是 `chase` 等老效果的内部枚举参数。两者互不冲突。
5. **`audio_modulation` vs `parameter_modulation`**：
   - `audio_modulation` 专管 `brightness`、`speed`、`intensity`。
   - `parameter_modulation` 专管 11 个特定灯效内部参数。
6. **`ScalarSource` vs `parameter_modulation source`**：
   - `ScalarSource` 是写在 `effect.params` 内部的归一化信号选择器（如 `color_wipe.progress_source`）。
   - `parameter_modulation` 是外层 Cue 对效果参数施加的动态控制通道。
7. **`virtual_path` vs `digital_set`**：
   - `virtual_path` 把成员变成一个连续逻辑坐标，再拆回实体灯带，适合跨接缝连续运动。
   - `digital_set` 让同一个 Cue 同时覆盖多条真实 strip，但不会把它们拼成一个长坐标；stateful renderer 可按各 strip ID/长度维护局部状态。
8. **`virtual_path` vs `branch`**：
   - `virtual_path` 定义连续逻辑坐标。
   - `branch` 是父 fixed Cue 的独立 effect instance，在一个 authored path 的累计进度点后才对 `digital_set` 可见；它不拥有另一套 effect 配置。
9. **`after` vs `pre_roll`**：
   - `after` 决定**按 cue normalized progress + path member 累计长度何时释放**，不是波前位置。
   - `pre_roll` 决定**释放前是否已经后台计算父 Cue 同款 effect**。
10. **APP 控制 vs Show 编写**：
    - APP 负责现场选歌播控与全局拉杆。
    - Show YAML 决定灯光艺术细节与所有空间轨迹。
11. **当前生产 Target vs 教学/兼容 Target**：
    - 教程里的 `wall_left`、`strip_91` 是语法占位符。
    - 当前 profile 中可直接作为实体数字目标使用的是这 9 条 `strip_*`；它们还可以合法组成 `digital_set` 或 Show v2 `virtual_path`。

---

# 第 14 章：验证与排错工作流

请遵循以下 5 步工作流程：

```
[1. 编写 Show YAML]
       │
       ▼
[2. 核对 Target (必须属于当前 9 条之一)]
       │
       ▼
[3. 核对 Effect 参数与 Modulation 白名单]
       │
       ▼
[4. 本地命令行执行 Python 校验]
       │
       ▼
[5. 提交评审并部署测试]
```

### 真实可复制的 Python 校验命令

在 Windows PowerShell 下直接运行：

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/shows/your_new_show.yaml
```

成功时当前 CLI 输出形如：

```text
Show valid: your_show_id (N cues, duration=...s)
```

这表示 Show 已通过**软件 schema、effect/parameter 与当前 profile target catalog** 校验；它不等于真实灯带、网络时序或现场效果已经完成硬件验收。

---

## Coverage checklist

本手册经过自动化脚本针对当前仓库代码与 live EffectRegistry 的完整提取核对：

- **Effects**: 22 / 22（完整收录并逐一详解）
- **Authorable Effect Parameters**: 111 / 111（与 live EffectRegistry/exporter 参数名覆盖一致）
- **Modulatable Parameters**: 11 / 11
- **Adaptive `audio_control` fields**: 9 / 9
- **Legacy `audio_modulation` sources**: 15 / 15
- **Spatial Origins**: 4 / 4 (`start`, `end`, `center`, `edges`)
- **ColorSource Types**: 6 / 6 (`timeline`, `spatial_palette`, `video_average`, `video_dominant`, `audio_spectrum_palette`, `dominant_frequency_palette`)
- **ScalarSource families**: 10 / 10；**concrete accepted names**: 25（含 `audio.spectrum[0..15]`）
- **Parameter-modulation source families**: 13 / 13；**concrete accepted names**: 28（ScalarSource 25 + 3 个 raw-domain source）
- **Branch Lifecycle Modes**: 2 / 2 (`start_on_release`, `pre_roll`)
- **Current Production Targets**: 9 / 9 (`strip_11`, `strip_12`, `strip_21`, `strip_22`, `strip_31`, `strip_32`, `strip_41`, `strip_43`, `strip_44`)
- **Complete Runnable Shows**: 4 / 4（第 0 章 1 个 + 第 11 章 3 个；当前 profile 下 loader validated）

> **免责声明与边界确认**：
> - **APP Effect Authoring**: NOT PART OF APP V1（APP V1 为冻结播控门面，不提供灯效编辑）。
> - **Hardware Verification**: NOT CLAIMED BY THIS MANUAL（物理硬件部署与时序指标保持 NOT HARDWARE VERIFIED）。
