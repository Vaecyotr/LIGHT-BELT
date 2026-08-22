# LIGHT-BELT 灯效与参数手册

本文列出当前 registry 注册的全部 21 个灯效。名称必须使用代码 ID，例如
`color_wipe`，不能使用中文名称代替。

## 通用编排控制

以下字段属于 Show/compositor，而不是某一个 renderer。Show v2 schema 接受这些字段；某个 renderer
是否实际消费 color、speed 或 intensity，以 registry capability 和下文的实现说明为准。

- `start` / `end`：cue 在节目时间轴上的开始和结束时间，单位为秒。它们不是像素位置。
- `origin`：空间起点。取值为 `start`、`end`、`center`、`edges`，分别表示从路径起点、路径末端、中间向外、两端向内。它特别适合配合 `color_wipe` 和 `chase`。
- `color.mode`：Show v2 颜色策略。`effect_default` 使用效果默认颜色；`solid` 使用一个 RGB 颜色；`palette` 使用 RGB 调色板。
- `audio_modulation.brightness`：按音乐分析结果调制 cue 亮度。最终全局亮度仍只在 `OutputTransform` 应用一次。
- `audio_modulation.speed`：按音乐分析结果乘算效果速度；最终上下文速度范围为 `0.0` 到 `10.0`。
- `audio_modulation.intensity`：按音乐分析结果乘算音频响应强度；最终上下文强度范围为 `0.0` 到 `10.0`。
- `global_brightness`：全局输出亮度，范围 `0.0` 到 `1.0`。`0.0` 为全黑，`1.0` 为不做亮度衰减。

Show v2 中 `effect.speed` 与 `effect.intensity` 是通用乘数，默认均为 `1.0`；它们会与运行时基础值和
`audio_modulation.speed/intensity` 相乘，最后钳在 `EffectContext` 的 `0.0..10.0` 范围。它们不是
`effect.params` 的成员。相反，`effect.params.speed` 是少数旧效果自己的命名参数，例如
`chase.params.speed`、`single_dot.params.speed` 和 `theater_phase.params.speed`。效果自己的速度参数先由
renderer 读取，再乘以通用 `effect.speed`。`flowing_bands` 使用离散推进参数
`params.steps_per_second`，`onset_ripple` 使用连续波前参数 `params.wave_speed_pps`；不要把这些字段
互相替换。

Phase 34 起，`effect.speed`、adaptive selector speed 和 `audio_modulation.speed` 的最终组合值是
**瞬时运动速率倍数**，不是 `cue 时间 × 当前 speed` 公式里的绝对相位倍数。Show runtime 为每个 cue
维护一个内部积分运动时钟；降速或升速只改变后续斜率，`speed=0` 冻结，恢复后从冻结相位继续。
同一 cue 的 released branches 共享该相位，adaptive effect 切换不会重置它。常量 speed `S` 仍与
`cue_local_time × S` 完全兼容。该时钟不是 authored 参数，Show v2 语法没有变化；向后 seek 仍须
reset 并从头 replay，也不会为缺失的 live audio 补造历史样本。

Phase 33 的 `ScalarSource` 是少量效果可选使用的通用 `[0,1]` 输入选择器。V1 只接受
`cue_progress`、`audio.rms`、`audio.loudness`、`audio.bass`、`audio.mid`、`audio.treble`、
`audio.spectral_flux`、`audio.onset`、`audio.peak` 和 `audio.spectrum[0]` 到
`audio.spectrum[15]`。缺失音频返回 `0`；已有输入若越界或为 NaN/Inf 则显式失败。
`audio.raw_level`、dominant frequency/magnitude、表达式、Python/eval 和 WLED 字段名都不是 V1
source。尤其 dominant frequency 没有全局颜色含义。

Registry 是效果 ID、renderer、参数白名单/validator 和 common capability 的唯一运行时权威。当前 ID 为：

`static`, `breath`, `color_wave`, `chase`, `comet`, `audio_pulse`, `bass_pulse`, `spectrum`,
`video_ambient`, `video_audio_fusion`, `calm`, `color_wipe`, `twinkle`, `demo`, `step_pulse`,
`single_dot`, `theater_phase`, `flowing_bands`, `onset_ripple`, `heat_fire`, `history_stream`。

文中“安全创作范围”表示在当前 RGB `[0,1]` 输出模型内建议使用的范围。部分旧效果的
Show 参数校验目前只拒绝非有限数值，因此超出安全范围的值未必会在加载时立即失败，但可能
产生无效帧或不直观行为。

## 1. `static`：单色常亮

**用途与效果：** 将目标数字灯带的全部实际像素段设为同一颜色；模拟 RGB+CCT 区域也显示
对应颜色。适合基础照明、固定氛围、测试颜色和作为其他 cue 的底色。

### `color`

- **含义：** RGB 基础颜色，顺序为 `[r, g, b]`。
- **范围：** 每个通道 `0.0` 到 `1.0`。
- **如何使用：** `[1, 0, 0]` 是红色，`[0, 1, 0]` 是绿色，`[0, 0, 1]` 是蓝色。Show v2 推荐通过 cue 的 `color.mode: solid` 设置。

### `color_timeline`

- **含义：** 按 cue 本地时间在多个 RGB 关键帧之间做线性插值。
- **范围：** `interpolation` 当前只能为 `rgb_linear`；至少 2 个关键帧；首个 `time >= 0`，后续时间必须严格递增；颜色通道均为 `0.0` 到 `1.0`。
- **如何使用：** 可让常亮灯在 5 秒内由红色平滑变成蓝色，而不需要切换效果。

## 2. `breath`：呼吸灯

**用途与效果：** 所有目标像素以正弦曲线同步变亮和变暗。适合平静氛围、待机状态和慢节奏段落。

### `period`

- **含义：** 一次完整“变亮再变暗”的周期，单位为秒。
- **范围：** 有效下限为 `0.001` 秒；当前无硬性上限。安全创作范围建议 `0.2` 到 `120` 秒。
- **如何使用：** `2.0` 是较快呼吸，`4.0` 是默认柔和呼吸，`10.0` 以上会非常缓慢。

### `min_brightness`

- **含义：** 呼吸波谷时相对于基础颜色保留的最低亮度。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** `0.0` 会降到全黑；`0.05` 保留微光；`0.5` 只在半亮到全亮之间呼吸。

### `color`

- **含义：** 呼吸灯的 RGB 基础颜色。
- **范围：** 每个通道 `0.0` 到 `1.0`。
- **如何使用：** 设置呼吸的色调，亮度波形会乘在这个颜色上。

### `color_timeline`

- **含义：** 呼吸过程中随时间改变基础颜色。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 可让一次长呼吸段从冷蓝逐渐过渡到暖红，同时保留呼吸明暗变化。

## 3. `color_wave`：彩色流动波

**用途与效果：** 沿每条数字灯带生成连续 HSV 彩虹波，并随时间流动；模拟区域显示同一算法的动态颜色。

### `speed`

- **含义：** 空间波相位的推进速度，并继续乘以通用 `speed`。
- **范围：** 当前接受任意有限数；`0` 停止空间推进，负数反向。建议 `-10.0` 到 `10.0`。
- **如何使用：** `0.2` 缓慢流动，`1.0` 为默认速度，`3.0` 更活跃，负值可反向流动。

### `width`

- **含义：** 色彩波相对于灯带长度的空间宽度，不是固定像素数。
- **范围：** 算法将小于 `0.001` 的值钳为 `0.001`；建议 `0.05` 到 `2.0`。
- **如何使用：** 小值会在同一灯带上出现更多、更密的颜色变化；大值形成更宽、更平缓的色带。

### `hue_cycle_rate`

- **含义：** 随相位旋转整体色相的速率。
- **范围：** 当前接受任意有限数；`0` 不额外旋转色相，负数反向旋转。建议 `-2.0` 到 `2.0`。
- **如何使用：** `0.1` 是默认缓慢变色；提高后整条波的颜色轮换会更快。

## 4. `chase`：追逐灯

**用途与效果：** 生成重复的移动亮块，可做剧院追逐、流水点、彩虹追逐以及往返扫描。它不会像
`color_wipe` 一样保留所有经过位置。

### `speed`

- **含义：** 基础移动速度，单位约为实际 WS2811 像素段/秒，并乘以通用 `speed`。
- **范围：** 安全范围 `0.0` 到 `1000.0`；`0` 停止移动。建议常用 `0.2` 到 `50.0`。
- **如何使用：** 长灯带与短灯带使用相同值时，每秒跨过相同数量的实际像素段。

### `width`

- **含义：** 每个移动亮块的宽度，单位为像素段。
- **范围：** 非负整数；`0` 不产生亮块。建议不超过目标灯带的实际 `pixel_count`。
- **如何使用：** `1` 接近单点扫描，`3` 到 `5` 是明显亮块，更大值形成宽带。

### `gap`

- **含义：** 相邻亮块之间的暗区长度，单位为像素段；重复周期约为 `width + gap`。
- **范围：** 非负整数。建议不超过目标灯带实际长度的数倍。
- **如何使用：** `width: 1, gap: 2` 接近旧版每 3 段亮 1 段的剧院追逐。

### `direction`

- **含义：** 移动方向。
- **范围：** `forward`、`reverse`、`bounce`。
- **如何使用：** `forward` 正向，`reverse` 反向，`bounce` 在两端往返，可近似旧版 `scanner`。

### `trail`

- **含义：** 亮块尾端相对于头部保留的强度。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** `0` 形成明显衰减尾部，`0.3` 为默认，`1.0` 让整个亮块等亮。

### `color_source`

- **含义：** 追逐亮块的颜色来源。
- **范围：** `rainbow`、`video`、`static`；Show 中也常将 `solid` 颜色策略与 `static` 来源配合使用。
- **如何使用：** `rainbow` 沿灯带变化；`video` 读取视频平均色；`static` 使用 cue 的 `color`。

### `beat_boost`

- **含义：** 检测到节拍时的速度倍数；值为 `0` 时关闭节拍加速。
- **范围：** 安全范围 `0.0` 到 `10.0`，默认 `2.0`。
- **如何使用：** `1.0` 不额外加速，`2.0` 在 beat 帧上加倍，过高会产生突跳。

## 5. `comet`：流星

**用途与效果：** 一个或多个彩色 emitter 沿逻辑路径运动并留下可选尾迹。默认单 emitter 的
wrap 行为保持原有 comet 状态机；多 emitter 与新轨迹由 cue 级积分 motion time 计算，可确定性
reset/replay，并在动态通用 speed 变化时保持连续。

### `speed`

- **含义：** 流星头的移动速度，单位约为像素段/秒，并乘以通用 `speed`。
- **范围：** 安全范围 `0.0` 到 `1000.0`；建议 `0.2` 到 `50.0`。
- **如何使用：** 增大可得到快速流星；当前效果没有独立反向参数。

### `tail_length`

- **含义：** 尾巴长度占当前灯带实际 `pixel_count` 的比例。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** `0` 只显示头部；`0.25` 表示尾巴约占四分之一灯带，`0.75` 表示长尾；因此不同长度灯带会得到成比例的尾巴。

### `decay`

- **含义：** 每帧保留的历史尾迹比例。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** 越接近 `0` 消失越快；`0.85` 为默认；`1.0` 不做逐帧衰减，但仍受尾巴空间渐变影响。

### `count` / `phase_spacing` / `trajectory`

- **含义：** `count` 是 emitter 数量；`phase_spacing` 是相邻 emitter 占完整轨迹周期的归一化偏移；
  `trajectory` 选择 `wrap`、`bounce` 或 `sine`。
- **范围：** `count` 为整数 `1..64`；`phase_spacing` 为 finite `0..1`，省略时使用 `1/count`；
  `trajectory` 默认 `wrap`。
- **如何使用：** 多 emitter、往返扫描和正弦缓动都属于同一个 comet family，不产生 WLED alias。

## 6. `audio_pulse`：全频音量脉冲

**用途与效果：** 使用音频 RMS 总能量控制整条灯带亮度。适合随整体响度起伏的灯光。

### `attack`

- **含义：** 音量上升时追随目标亮度的速率系数，数值越大反应越快。
- **范围：** 有效下限 `0.001`；建议 `0.01` 到 `1.0`。
- **如何使用：** `0.1` 较柔和，`0.4` 为默认，`1.0` 对声音起音反应很快。

### `release`

- **含义：** 音量下降时亮度回落的速率系数，数值越大下降越快。
- **范围：** 有效下限 `0.001`；建议 `0.01` 到 `1.0`。
- **如何使用：** 小值产生长拖尾，大值让灯光迅速跟随安静段落。

### `color`

- **含义：** 音量脉冲的 RGB 基础颜色。
- **范围：** 每个通道 `0.0` 到 `1.0`。
- **如何使用：** 声音包络只改变亮度，不改变指定色相。

### `color_timeline`

- **含义：** 在音量脉冲持续期间改变基础颜色。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 可在同一音乐段中让音量响应灯从暖色平滑转为冷色。

## 7. `bass_pulse`：低频脉冲

**用途与效果：** 使用 `20-200 Hz` 低频能量控制亮度，并带有 `1.5` 倍内部低频增益。适合鼓点、低音和冲击段落。

### `attack`

- **含义：** 低频增强时亮度上升速率，越大越快。
- **范围：** 有效下限 `0.001`；建议 `0.01` 到 `1.0`。
- **如何使用：** 默认 `0.6`，比 `audio_pulse` 更快地响应低频冲击。

### `release`

- **含义：** 低频减弱后亮度下降速率，越大越快。
- **范围：** 有效下限 `0.001`；建议 `0.01` 到 `1.0`。
- **如何使用：** 默认 `0.2`；减小可留下更长的低频余辉。

### `color`

- **含义：** 低频脉冲的 RGB 基础颜色。
- **范围：** 每个通道 `0.0` 到 `1.0`。
- **如何使用：** 默认冷蓝，也可改成红色或其他固定颜色。

### `color_timeline`

- **含义：** 随 cue 时间改变低频脉冲的基础颜色。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 可让低频响应在不同乐段间连续换色，而包络仍由低频驱动。

## 8. `spectrum`：频段分区

**用途与效果：** 将低频、中频和高频能量分别分配给指定逻辑灯带或模拟区域。低频为红色，
中频为绿色，高频为蓝色；没有列入任何分组的目标保持黑色。

### `bass_zones`

- **含义：** 由低频 `20-200 Hz` 驱动的逻辑目标 ID 列表。
- **范围：** 字符串列表；每个 ID 应是本 cue 范围内存在的灯带或区域。
- **如何使用：** 可把地面或低位灯带放入该列表，让它们随低音显示红色。

### `mid_zones`

- **含义：** 由中频 `200-2000 Hz` 驱动的逻辑目标 ID 列表。
- **范围：** 字符串列表；ID 应存在于当前布局和目标范围。
- **如何使用：** 可将墙面灯带放入该列表，随人声和主要乐器显示绿色。

### `treble_zones`

- **含义：** 由高频 `2000-12000 Hz` 驱动的逻辑目标 ID 列表。
- **范围：** 字符串列表；ID 应存在于当前布局和目标范围。
- **如何使用：** 可将顶部或装饰灯带放入该列表，随高频细节显示蓝色。

## 9. `video_ambient`：视频环境色

**用途与效果：** 每个目标读取其 `video_zone` 对应的视频区域颜色，并做时间平滑。灯带实际长度
只决定复制多少个相同颜色的像素段。

### `smoothing`

- **含义：** 指数移动平均的新输入权重。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** `0.0` 在当前实现中直接跟随新颜色；接近 `1.0` 时更多保留上一帧、变化更慢。默认 `0.15`。

## 10. `video_audio_fusion`：视频音频融合

**用途与效果：** 视频决定基础色和区域色，音频 RMS 控制亮度，低频增加中心扩散脉冲，高频增加
微弱闪烁，beat 增加瞬时冲击。

### `video_weight`

- **含义：** 视频亮度在目标亮度混合中的权重。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** 提高后灯光更忠实于画面亮暗；默认 `0.65`。

### `audio_weight`

- **含义：** 音频 RMS 在目标亮度混合中的权重。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** 提高后整体亮度更明显地随声音变化；默认 `0.35`。通常与 `video_weight` 的和保持约 `1.0`。

### `bass_boost`

- **含义：** 低频能量进入扩散脉冲前的倍率。
- **范围：** 安全范围 `0.0` 到 `10.0`。
- **如何使用：** `0` 关闭低频扩散，`1.0` 原强度，默认 `1.5`，过高会频繁达到亮度上限。

### `treble_limit`

- **含义：** 高频闪烁强度的上限。
- **范围：** 安全范围 `0.0` 到 `1.0`。
- **如何使用：** `0` 关闭高频闪烁；默认 `0.4`，但算法还会将高频乘以 `0.15`，所以实际闪烁保持克制。

## 11. `calm`：平静漂色

**用途与效果：** 以低饱和度、低亮度缓慢漂移色相，适合长时间观看和安静环境。

### `period`

- **含义：** 色相轻微摆动的主周期，单位为秒。
- **范围：** 有效下限 `0.001` 秒；建议 `2.0` 到 `300.0` 秒。
- **如何使用：** 默认 `12.0`；增大后变化更平缓，减小后更容易察觉颜色摆动。

### `color`

- **含义：** 用来确定平静漂色中心色相的 RGB 颜色。
- **范围：** 每个通道 `0.0` 到 `1.0`。
- **如何使用：** 它决定中心色相；效果会自行降低饱和度和亮度，因此最终输出不会等于原始 RGB 强度。

### `color_timeline`

- **含义：** 随 cue 时间移动平静漂色的中心颜色。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 可让长时间环境光从一个平静色系逐步过渡到另一个色系。

## 12. `color_wipe`：逐步填充

**用途与效果：** 从空间起点开始逐个点亮像素段；已经点亮的位置保持亮着，直到每条目标灯带按
自己的实际 `pixel_count` 填满。它对应旧 Arduino 测试代码中的 `colorWipe`。模拟 RGB+CCT 区域
没有像素长度，因此在 cue 生效时直接显示目标颜色。

### `speed`

- **含义：** 每秒新增点亮的实际 WS2811 像素段数量。
- **范围：** 硬校验范围 `0.0` 到 `1000.0`。
- **如何使用：** `0` 只点亮起始像素并暂停；`5` 每秒推进约 5 段；`25` 每秒推进约 25 段。10 段和 40 段灯带使用同一速度时，分别约需 `10/speed` 和 `40/speed` 秒填满。

### `color`

- **含义：** 新点亮及已保持点亮像素的 RGB 颜色。
- **范围：** 硬校验为 3 个通道，每个通道 `0.0` 到 `1.0`。
- **如何使用：** 可通过 cue 的 `solid` 颜色指定单色；与 `origin` 组合可实现正向、反向、中间向外和两端向内填充。

### `color_timeline`

- **含义：** 随 cue 时间改变当前所有已点亮像素的颜色。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 填充推进期间可以同时从一种颜色平滑变为另一种颜色；变化作用于全部已亮区域。

### `progress_source` / `slew_seconds`

- **含义：** `progress_source` 可用一个 `ScalarSource` 直接控制填充比例；省略时使用 cue 级积分
  motion time 推进。`slew_seconds` 是标量从 0 到 1 满量程变化所需时间。
- **范围：** source 必须属于上文 V1 列表；`slew_seconds` 为 finite `>=0`，默认 `0` 表示直接跟随。
- **如何使用：** 外部 progress 的 `0/0.5/1` 分别点亮 `0/50%/100%` 路径。reset、source 切换或
  向后 seek 会直接重基准；空间方向仍只由公共 `origin` 控制。

## 13. `twinkle`：随机星光

**用途与效果：** 在每条数字灯带的有效像素范围内随机生成星点，并按时间淡出。生成量使用
`density * pixel_count * delta_time` 计算，因此 40 段灯带的平均新星数量是同参数 10 段灯带的
4 倍；位置始终限制在各自 `0 .. pixel_count-1` 内。模拟 RGB+CCT 区域没有离散位置，保持黑色。

### `density`

- **含义：** 每个实际像素段、每秒期望生成的新星数量。
- **范围：** 硬校验范围 `0.0` 到 `100.0`。
- **如何使用：** `0` 不生成新星；`0.05` 很稀疏；默认 `0.12`；`1.0` 表示平均每个像素每秒生成一次。随机位置碰撞会使肉眼可见的新星数略低于期望值。

### `fade_time`

- **含义：** 星点指数淡出的时间常数，单位为秒。
- **范围：** 硬校验范围 `0.01` 到 `60.0` 秒。
- **如何使用：** `0.1` 很快闪灭；默认 `0.7` 有清晰余辉；`2.0` 以上会积累较多重叠星点。

### `color_source`

- **含义：** 每颗新星的颜色来源。
- **范围：** 硬校验为 `solid`、`palette`、`random`。
- **如何使用：** `solid` 使用 `color`；`palette` 从 cue 的调色板中随机挑选；`random` 为每颗星随机生成高亮 HSV 色彩。

### `color`

- **含义：** `color_source: solid` 时使用的 RGB 星点颜色，也是调色板缺失时的后备颜色。
- **范围：** 硬校验为 3 个通道，每个通道 `0.0` 到 `1.0`。
- **如何使用：** `[1,1,1]` 是白色星光；也可使用蓝色、金色或 cue 的 `solid` 颜色。随机位置与固定颜色彼此独立。

### `color_timeline`

- **含义：** 随 cue 时间改变之后新生成的 `solid` 星点颜色；已经生成的星点保留其生成时颜色并继续淡出。
- **范围：** `rgb_linear`；至少 2 个严格递增时间的关键帧；时间 `>= 0`；RGB 通道 `0.0` 到 `1.0`。
- **如何使用：** 可让随机位置的星点在节目进程中逐渐从冷色转为暖色，而不是每颗都随机色。

### `event_width_px` / `blur_radius_px`

- **含义：** 将单像素 event 扩成对称实心宽度，并在外侧增加线性软化半径。
- **范围：** width 为 finite `0.01..10000`，默认 `1`；blur 为 finite `0..10000`，默认 `0`。
- **如何使用：** 默认值保持原有单点替换行为；非默认值启用可确定性重放的连续 logical-path
  event field，跨 virtual-path 接缝后再拆分。

### `event_gate_source` / `birth_gain_source`

- **含义：** 两者均使用同一 `ScalarSource` V1；gate 缩放 event 出生预算，birth gain 缩放新 event
  的生成颜色，不改变已出生 event 的保存颜色。
- **范围：** 可省略；source 必须属于上文 V1 列表。
- **如何使用：** 可用 loudness/onset/peak 等明确驱动出生或亮度，但颜色仍来自 authored
  `solid`/`palette`/`random`，本阶段没有 audio palette framework。

## 14. `demo`：自动轮播

**用途与效果：** 按固定时间间隔循环运行一组已注册效果，主要用于演示和快速巡检，不适合需要
精确 cue 控制的正式节目。

### `cycle_interval`

- **含义：** 每个子效果持续时间，单位为秒。
- **范围：** 有效下限 `0.001` 秒；当前无硬性上限。建议 `1.0` 到 `300.0` 秒。
- **如何使用：** 默认 `10.0`；缩短可快速预览，延长可观察单个效果。一次大 `delta_time` 只前进一个子效果。

### `effects`

- **含义：** 参与轮播的效果 ID 列表，按列表顺序循环。
- **范围：** 非空字符串列表；应只包含已注册效果 ID，并避免把 `demo` 自身加入列表。
- **如何使用：** 例如 `[static, breath, color_wipe, twinkle, chase]`。未知 ID 会被跳过；若全部无效则回退到 `static`。

## 15. `step_pulse`：两级阶跃脉冲

在 cue 本地时间的前半周期输出 `low_color`，后半周期输出 `high_color`，不做插值。`period` 默认
`4.0` 秒且运行时最小按 `0.001` 秒处理；`low_color` 和 `high_color` 都是三个有限 `0..1` RGB
通道。通用 `effect.intensity` 在 renderer 输出后按 cue 局部效果强度缩放并钳制 RGB；默认 `1.0`
仍保留两组 authored RGB 的精确值，且不会替代全局 `OutputTransform` brightness。

## 16. `single_dot`：离散单点

每条逻辑路径只点亮一个像素且没有尾迹。`params.speed` 默认 `5.0` 像素/秒，
`direction` 为 `forward`、`reverse` 或 `bounce`，`color` 为 RGB。位置由 cue 级积分 motion time 计算。
最终位置速率为 `params.speed ×` 最终通用 speed；两者可同时存在。通用 `effect.intensity` 缩放最终
authored RGB，但不修改位置或 `params.speed`。

## 17. `theater_phase`：三相剧院遮罩

按 `index % 3` 选择一个离散相位。`params.speed` 默认 `2.5` 相位/秒，`color` 默认为低亮蓝色；
相位按 cue 级积分 motion time 确定，推进速率为 `params.speed ×` 最终通用 speed。通用 `effect.intensity` 缩放
最终 authored RGB，不改变离散三相遮罩。

## 18. `flowing_bands`：固定间隔、离散高亮

基础 pattern 固定为 `A B A B A B`：A 是 authored color 的低亮段，B 是严格的全黑段，C 是与
A 同色但 gain 更高的状态。空间 pattern 本身不平移；离散步进只改变“当前哪个 A 变成 C”。当
`band_width_px=1`、`gap_width_px=1` 且没有 phase offset 时，黄金序列为
`ABABAB → CBABAB → ABCBAB → ABABCB`，随后从第一个 A 循环。`direction` 只改变高亮遍历顺序，
不会反转或移动 A/B 底纹。

效果自身不保存独立相位积分器：步数由 cue 级积分 motion time、`steps_per_second` 和
`phase_offset_steps` 确定，因此同一输入可直接重放。`virtual_path` 会先作为一条完整逻辑路径渲染，
再拆回成员 strip；A/B pattern 和 C 的移动都不会在实体 strip 接缝处重启。`origin` 仍由 compositor
统一处理。

| 参数 | 范围与默认值 | 语义 |
| --- | --- | --- |
| `band_width_px` | integer `1..10000`，默认 `1` | 每个 A 段的宽度；被选中时整段变为 C |
| `gap_width_px` | integer `1..10000`，默认 `1` | 每个 B 段的宽度；输出始终为 `(0, 0, 0)` |
| `base_gain` | finite `0..1`，默认 `0.125` | A 的低亮 gain |
| `highlight_gain` | finite `base_gain..1`，默认 `0.625` | C 的高亮 gain |
| `steps_per_second` | finite `0..1000`，默认 `1` | 每秒跨过的 A 段数；再乘通用 `effect.speed` |
| `direction` | `forward` / `reverse`，默认 `forward` | C 遍历 A 段的方向 |
| `phase_offset_steps` | integer `0..10000`，默认 `0` | 在 cue 时间步数上增加的离散偏移 |
| `color` | 三个 finite `0..1` RGB 通道，默认白色 | A 与 C 共享的 authored color |
| `color_timeline` | Show v2 `rgb_linear` 时间线 | compositor 按 cue 本地时间解析为当前 authored color |

最终 RGB 还乘以通用 `effect.intensity`；这不是设备 brightness，`OutputTransform` 仍是全局亮度的
唯一应用点。

## 19. `onset_ripple`：起音涟漪

该效果只读取通用 `AudioFeatures`，不读取 WLED 字段名。peak 的上升沿或 onset 从阈值下方越过阈值
时出生一条波；持续高值不会逐帧重触发。每条波保存真实 cue 出生时间、motion 出生时间、强度、低频、高频和响度，最多保留
16 条，超限淘汰最旧波。silence 或 stale 音频不产生新 wave，但不会隐藏已经出生的 wave；已有 wave
按 motion age 计算传播距离，按真实 cue age 计算指数 decay，直至自然衰减并在真实年龄超过
`decay_seconds × 8` 后淘汰。改变通用 speed 不会缩短或延长 `decay_seconds`。
效果从逻辑 start 坐标向外渲染；center/edges/end 仍由 compositor 做确定性重映射。

| 参数 | 范围与默认值 | 语义 |
| --- | --- | --- |
| `onset_threshold` | finite `0..1`，默认 `0.35` | onset 上升沿门槛 |
| `wave_speed_pps` | finite `0..1000`，默认 `18` | 波前像素/秒；再乘通用 speed |
| `wave_width_px` | finite `0.1..1000`，默认 `2` | 三角形软波前宽度 |
| `decay_seconds` | finite `0.01..60`，默认 `1.5` | 指数衰减时间常数 |
| `floor_gain` | finite `0..1`，默认 `0` | 无波位置底光 |
| `event_origin` | `fixed` / `random`，默认 `fixed` | 每个事件从逻辑起点或 cue-local seeded 归一化随机相对坐标出生 |
| `propagation` | `one_way` / `bidirectional`，默认 `one_way` | 单向或同时向两侧传播 |
| `wrap` | boolean，默认 `false` | 波前是否在有限逻辑路径首尾环绕 |
| `color` / `color_timeline` | RGB / Show v2 时间线 | 波形基础颜色 |

低频来自 16-band 的 0..2 bins 与 legacy `bass` 的较大值，高频来自 10..15 bins 与 legacy
`treble` 的较大值；因此文件/合成旧特征与 16-band live adapter 都能驱动效果。通用 intensity 作用于
最终 RGB。一次调用命中多条独立逻辑路径时，同一 random event 保存一个 `[0,1)` 相对位置，再按每条
路径自己的 `pixel_count` 映射，因此不同长度路径的起点始终有效；等长路径保持同位置。`virtual_path`
仍先作为一条连续逻辑路径映射一次，不会在成员 strip 接缝重启。

## 20. `heat_fire`：固定步进热火焰

每条逻辑 strip 持有独立 heat 数组，以私有 60 Hz 步长执行冷却、向上扩散和底部火花注入。
随机数由 cue 创建时捕获的 seed、strip ID 和 tick 共同确定，不依赖输出帧率；目标 tick 来自 cue 级
积分 motion time，相同 seed 和 motion schedule 下 30/60 fps 得到相同状态。向后时间仍要求 reset/replay；显式 `reset()` 产生相同重放。
长度变化时按新长度从 tick 0 重建，且不包含节点、GPIO 或传输知识。

| 参数 | 范围与默认值 | 语义 |
| --- | --- | --- |
| `cooling_per_second` | finite `0..60`，默认 `0.8` | 每秒随机冷却上界 |
| `spark_rate` | finite `0..60`，默认 `8` | 每秒火花概率率 |
| `spark_strength` | finite `0..1`，默认 `0.9` | 火花热量增量 |
| `diffusion` | finite `0..1`，默认 `0.35` | 每 tick 向上混合比例 |
| `spark_zone_px` | integer `1..10000`，默认 `3` | 允许注入火花的底部像素数 |
| `color` | 三个 finite `0..1` RGB 通道，默认 `[1.0, 0.32, 0.04]` | heat 强度缩放的 authored color |
| `color_timeline` | Show v2 `rgb_linear` 时间线 | compositor 按 cue 本地时间解析为当前 authored color |

以上七个 authored keys 与 registry 白名单完全一致；五个模拟参数及 `color` 的 validator 范围与表中
一致，`color_timeline` 由 Show loader/compositor 校验和解析。renderer 读取五个模拟参数和解析后的
color，每个像素输出 `authored color × min(1, heat × effect.intensity)`；当 intensity 为默认 `1.0` 时
就是 authored color × heat。当前实现没有 thermal palette、热度到多段颜色梯度或 WLED palette ID
语义，不应把单色 heat 缩放描述成调色板取色。

通用 speed 改变固定 60 Hz 模拟 tick 的未来推进速率，通用 intensity 缩放最终 RGB。该实现是 RK3588-native clean-room 算法，
不是 WLED Fire2012 数值兼容实现。

## 21. `history_stream`：时间样本空间历史

每个固定 sampling step 把当前 authored RGB 样本插入一条有界 logical-path history，旧样本向空间
内部推进。t=0 立即插入 step 0；forward 的最新样本在逻辑首端，reverse 的最新样本在末端。
它是通用 time-to-space primitive，不是 comet 尾迹、ripple 历史、WLED Stream compatibility 或
ESP32 缓冲区。`virtual_path` 始终先作为一条连续路径推进，再拆回成员 strip。

| 参数 | 范围与默认值 | 语义 |
| --- | --- | --- |
| `steps_per_second` | finite `0.001..1000`，默认 `10` | 固定采样步率；再乘通用 `effect.speed` |
| `direction` | `forward` / `reverse`，默认 `forward` | 新样本进入路径的端点与旧样本推进方向 |
| `sample_gain_source` | 可选 ScalarSource V1 | 当前 sample RGB 的 gain；缺失音频为 0 |
| `color` | 三个 finite `0..1` RGB 通道，默认白色 | 当前 authored sample color |
| `color_timeline` | Show v2 `rgb_linear` 时间线 | 在每个精确 fixed-step 时间取色并保存为空间历史 |

跨过多个未渲染 motion step 时，renderer 从 motion 区间插值每个边界实际跨越的 cue 墙钟时间，并在
该时间采 authored color timeline；只计算路径容量内仍可见的末尾样本。实时 audio gain 只使用当前
可观察值，不伪造过去音频。向后 seek 仍须 reset 并从头 replay；常量 sample 与 authored timeline
均有 30/60 FPS 等价覆盖。最终 RGB 再乘通用
`effect.intensity`，全局 brightness 仍只属于 `OutputTransform`。

## 长度与位置规则

- 实际数字灯带长度来自布局中的 `pixel_count`，当前舱体灯带分别为 10、20 或 40 个 WS2811 像素段，均为 `NOT HARDWARE VERIFIED` 且保持可配置。
- 所有 21 个效果都使用运行时逻辑 `pixel_count`；新效果没有固定 60-pixel 假设。
- `color_wipe` 的完成时间随实际长度变化；`twinkle` 的生成量按实际长度成比例变化；`comet.tail_length` 按实际长度的比例变化；`history_stream` 的 buffer 容量严格等于当前逻辑路径长度。
- `origin` 改变逻辑效果的空间展开方式；物理接线方向仍由布局/映射层处理，效果代码不包含 GPIO、节点 ID 或物理端口。
- 本文描述的软件行为已经由自动化测试覆盖，但灯带长度、方向、颜色顺序、跨板接缝、功耗和视觉观感仍为 `NOT HARDWARE VERIFIED`。
