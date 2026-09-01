# strip_43 单灯带视觉 Showcase v2

**READY FOR HARDWARE VIEWING / NOT HARDWARE VERIFIED**。指定软件门禁已通过；没有真实硬件观看记录，现场观察栏仍须由人填写。此状态不代表下方尚未解析的 runtime 已可直接输出。

这是独立实物观看编排：**356.8 秒、30 FPS、10,704 帧、11 个 family、44 个 Variant、49 个核心 cue、74 个总 cue**。唯一编排来源是本目录 [show.yaml](show.yaml)，只目标 `strip_43` 的 20 个控制 groups。不启动新产品 Phase，不依赖音视频文件、媒体触发、音视频效果、media ColorSource 或 audio modulation。

## 运行前检查与命令

从当前 worktree 根目录运行。Windows 只用仓库捆绑解释器，第一次使用前执行以下验证；失败立即停止，不换解释器：

```powershell
.\.python\Scripts\python.exe -c "import sys, pathlib, light_engine; cwd=pathlib.Path.cwd().resolve(); exe=pathlib.Path(sys.executable).resolve(); pkg=pathlib.Path(light_engine.__file__).resolve(); candidates=[cwd/'.python'/'Scripts'/'python.exe', cwd/'.python'/'python.exe']; existing=[c for c in candidates if c.exists()]; assert existing, 'No bundled Python found'; assert any(c.resolve()==exe for c in existing), 'Executable mismatch'; assert exe.name.lower()=='python.exe'; assert str(pkg).startswith(str(cwd)); print('executable=', exe); print('package=', pkg); print('PROJECT_PYTHON_OK')"
```

生产源模板为 `config/profiles/rk3588-host-service.yaml`；它冻结九节点逻辑拓扑与 group 数量。现有解析器 `scripts/resolve_nodes.py` 在目标 Host 通过 Avahi 解析唯一名 `wled-strip-<label>.local`，生成忽略跟踪的 `config/runtime/wled-ddp-mdns.yaml`。源模板不代表现场已解析，不能直接把源模板当作完成现场解析的 runtime 使用。现场按现有部署流程生成 runtime，本任务不修改或自动重新生成它；无解析结果就禁用该节点，不用旧 IP、缓存 IP、HTTP 探测或网段扫描回退。

**本次只读快照（2026-08-31）：** 源模板与现有 runtime 均定义 `strip_43 = 20 groups`，对应 node 7 / output 1；现有 runtime 的 node 7 仍为 `enabled: false`、host 为未解析的 mDNS 名（九节点均禁用）。因此当前文件不能直接用于观看：必须在现场完成现有 mDNS 解析流程并通过下述检查。本任务没有连接硬件或宣称解析成功。

先停止其它 Host、APP 控制的播放、旧 CLI、演示/测试输出等进程，确保**只有一个输出进程**拥有这些灯带。不要与 systemd Host 或另一个 worktree 的输出同时运行。读取生成结果的强制检查如下；不通过就停止，不能删掉断言：

```powershell
.\.python\Scripts\python.exe -c "from pathlib import Path; import ipaddress, yaml; p=yaml.safe_load(Path('config/runtime/wled-ddp-mdns.yaml').read_text(encoding='utf-8')); l=p['layout']; s=next(x for x in l['strips'] if x['id']=='strip_43'); o=next(x for x in l['digital_outputs'] if x['strip_id']=='strip_43'); n=next(x for x in l['digital_nodes'] if x['node_id']==o['node_id']); assert s['pixel_count']==20; assert n.get('enabled',True) is True, 'strip_43 mDNS unresolved/disabled: STOP'; assert isinstance(ipaddress.ip_address(n['host']),ipaddress.IPv4Address), 'Expected resolved IPv4'; assert p['system']['output_fps']==30; print(s); print(o); print(n)"
```

离线语法/registry 校验不会打开硬件，允许用生产源模板。现场 runtime 也应校验：

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-visual-showcase-v2/show.yaml
.\.python\Scripts\python.exe -m light_engine --config config/runtime/wled-ddp-mdns.yaml validate-show --show config/acceptance/single-strip-visual-showcase-v2/show.yaml
```

完成独占和解析检查后，使用现有 Host 引擎 CLI 开始实物观看（本任务未执行此硬件命令）：

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/runtime/wled-ddp-mdns.yaml run --show config/acceptance/single-strip-visual-showcase-v2/show.yaml --clock internal --duration 356.8 --max-frames 10704
```

显式 `--clock internal` 覆盖 profile 的 mpv 时钟，不传 `--audio`、`--video` 或静音媒体文件。现有 CLI 无媒体参数时会创建 synthetic feature source；production profile 还配置了 WLED 音频接收器，Host 启动时仍可能绑定接收 socket。这不构成本 Show 的输入依赖，Show 没有引用这些特征；专项测试用无特征与变化音视频特征重放验证量化输出一致。接收 socket 出错仍须按现有 Host 错误处理，不静默绕过或改 profile。

复用九节点 profile 时，未被此 Show 点亮的其它**启用**灯带会收到黑场；DDP 跳过禁用节点。这里是单灯带视觉目标，**不是仅向一个节点发包**。生产亮度仅在 `OutputTransform` 施加一次：源模板 `max_brightness=0.65`、`gamma=1.3`，其它 transform 参数取现有合并配置。普通展示 `intensity=1.0`，Show 不再乘 0.65。

## 颜色合同与速度单位

RGB 均是归一化通道值。以下为冻结颜色，不是温度或硬件校准数据：

| 名称 | RGB / palette |
|---|---|
| C1 | `[0.05,0.7,0.85]` |
| C2 | `[0.9,0.32,0.03]` |
| C3 | `[[0.9,0.15,0.02],[0.95,0.6,0.08],[0.5,0.05,0.85],[0,0.72,0.9]]` |
| C4 | `[[0.02,0.06,0.45],[0,0.7,0.85],[0.4,0.08,0.8]]` |
| C5 | 0% `[0.02,0.08,0.6]` → 50% `[0.75,0.05,0.6]` → 100% `[0.95,0.55,0.05]` |
| high_contrast_palette | `[[0.95,0.12,0.02],[0.05,0.85,0.95],[0.85,0.05,0.65],[0.95,0.9,0.65]]` |
| warm_white_gold | `[0.95,0.82,0.55]` |
| cool_near_white | `[0.85,0.9,1]` |

C3/C4/high_contrast_palette 均为 **positional spatial_palette**，沿完整逻辑路径按位置 RGB 线性插值。C5 是 `rgb_linear` 时间插值，通常关键帧为 0、T/2、T，越界保持端点颜色。需要外部重新着色的 cue 显式提供白色原生底色，以保留 renderer 亮度包络；Chase/Comet 用 cue solid 白色由现有 compositor 注入，不写 registry 不接受的 `params.color`。

九个适用 common speed 的 family 用 A/B/C/D = **2.5/5/7.5/9.5**。Breath/Twinkle common speed 固定 **1.0**，由自身周期和事件参数控制节奏。

- `single_dot` 的 groups/s 表示离散亮点位移；端点距离为 **19**，单程约 **4.75/2.375/1.583/1.25s**。wrap 周期还包括末端回绕一步，不能用端点距离冒充完整 wrap 周期。
- `chase/comet` 是 groups/s 位移；Comet A 保留既有单头 wrap 状态尾迹，B/C/D 走多发射器轨迹语义，不能拿 A 的尾长去套其它档公式。
- `color_wipe` 标注的是推进基准；曲线和 origin 映射改变实际可见边缘推进。首 group 在 cue 局部零时刻已亮（输出仍受淡入影响）。
- 一个 `flowing_bands` band step 跨过一个亮带和一个 gap，本方案共 **两个 groups**，不能把 step/s 直接写成 groups/s。
- `history_stream` 是 samples/s；零时刻已有第一份样本，20 groups 首次填满约 **9.5/4.75/3.167/2.5s**，不是 20/rate。颜色按采样时刻的 cue wall time 写入。
- `color_wave` 是 phase units/s，**不直接等于可见波形周期**；原生 linear 返回未取模位置，hue_span 参数不保证整条灯带实际 hue 范围恰好等于该角度。
- `coherent_noise_field` 是 noise-time/s；`heat_fire` 是模拟时间倍数，均不换算成 groups/s。
- Twinkle 的 `density×20` 是 events/s；`fade_time` 是指数衰减时间常数，**不是事件寿命**。四档均固定 `event_width_px=1.0`、`blur_radius_px=0`，尽量形成局部、清晰的离散事件核心，不强行要求任何浮点状态永远只有一个非零 group。多个旧事件可以同时存活。

## 绝对时间与观看记录

以下按 YAML 编排整理。时间区间为左闭右开，所有 cue 边界落在 30 FPS 帧网格；表中循环小数只为阅读而取六位，帧数才是重播边界的精确表达。普通校准/展示各 **0.1s 淡入、0.1s 淡出**，均包含在时长内；Variant 紧邻不另加黑场。

0–12s 校准各 2 秒：0–2 红、2–4 绿、4–6 蓝、6–8 冷近白、8–10 group 0、10–12 group 19。端点均为 local speed=0 的 single_dot，origin 分别 start/end。

| 明确黑场 cue | 绝对区间（秒） | 时长/帧 |
|---|---|---|
| SEP_01 | 12–12.4 | 0.4s / 12 |
| SEP_02 | 42.4–42.8 | 0.4s / 12 |
| SEP_03 | 70.8–71.2 | 0.4s / 12 |
| SEP_04 | 95.2–95.6 | 0.4s / 12 |
| SEP_05 | 119.6–120 | 0.4s / 12 |
| SEP_06 | 148–148.4 | 0.4s / 12 |
| SEP_07 | 176.4–176.8 | 0.4s / 12 |
| SEP_08 | 200.8–201.2 | 0.4s / 12 |
| SEP_09 | 229.2–229.6 | 0.4s / 12 |
| SEP_10 | 261.6–262 | 0.4s / 12 |
| SEP_11 | 294–294.4 | 0.4s / 12 |
| SEP_12 | 326.4–326.8 | 0.4s / 12 |

核心 family 累计 310 秒。表中每个 Variant 都有 `通过 / 不清楚 / 退化 / 备注` 记录栏；不能用软件通过替代肉眼填写。cue ID 均为 `FX_<family>_<A|B|C|D>`，额外 Wipe 重播才追加 `_r1`、`_r2`；辅助 cue 不计入 44 Variant。

### Breath 呼吸

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 12.4–21.4 | 1 | period=8s → 0.125 cycles/s | C1 solid | waveform=sine; min_brightness=0.05 | 慢呼吸含完整 8s 周期 | □通过 □不清楚 □退化；备注：____ |
| B / 21.4–28.4 | 1 | period=4s → 0.250 cycles/s | C2 solid | waveform=sine; min_brightness=0.05 | 4s 周期 | □通过 □不清楚 □退化；备注：____ |
| C / 28.4–35.4 | 1 | period=2s → 0.500 cycles/s | C5 GLOBAL timeline | waveform=sine; min_brightness=0.05 | 2s 周期且颜色随时间变化 | □通过 □不清楚 □退化；备注：____ |
| D / 35.4–42.4 | 1 | period=1.2s → 0.833 cycles/s | cool_near_white solid | waveform=sine; min_brightness=0.05 | 1.2s 快呼吸 | □通过 □不清楚 □退化；备注：____ |

### Color wave 色波

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 42.8–49.8 | 2.5 | speed=0.08 → 0.2 phase units/s | 原生 hue 60° / sine | width=0.75; hue_cycle_rate=0.1; hue_span_degrees=60; waveform=sine | 窄色域正弦起伏 | □通过 □不清楚 □退化；备注：____ |
| B / 49.8–56.8 | 5 | speed=0.08 → 0.4 phase units/s | 原生 hue 140° / triangle | width=0.75; hue_cycle_rate=0.1; hue_span_degrees=140; waveform=triangle | 扩大色域、三角色波 | □通过 □不清楚 □退化；备注：____ |
| C / 56.8–63.8 | 7.5 | speed=0.08 → 0.6 phase units/s | 原生 hue 240° / linear | width=0.75; hue_cycle_rate=0.1; hue_span_degrees=240; waveform=linear | 240° 参数、linear 未取模斜坡 | □通过 □不清楚 □退化；备注：____ |
| D / 63.8–70.8 | 9.5 | speed=0.08 → 0.76 phase units/s | 原生 hue 360° / saw | width=0.75; hue_cycle_rate=0.1; hue_span_degrees=360; waveform=saw | 完整色轮与 saw 回绕 | □通过 □不清楚 □退化；备注：____ |

### Single dot 单亮点

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 71.2–77.2 | 2.5 | speed=1.6 → 4 groups/s | C1 solid | direction=forward | 正向单点走满 20 groups | □通过 □不清楚 □退化；备注：____ |
| B / 77.2–83.2 | 5 | speed=1.6 → 8 groups/s | C2 solid | direction=reverse | 反向单点、无尾巴 | □通过 □不清楚 □退化；备注：____ |
| C / 83.2–89.2 | 7.5 | speed=1.6 → 12 groups/s | C3 positional | direction=bounce | 单点往返、两端转向 | □通过 □不清楚 □退化；备注：____ |
| D / 89.2–95.2 | 9.5 | speed=1.6 → 15.2 groups/s | C4 positional | direction=forward | 最快正向单点仍可追踪 | □通过 □不清楚 □退化；备注：____ |

### Chase 追逐

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 95.6–101.6 | 2.5 | speed=1 → 2.5 groups/s | C1 solid | width=2; gap=4; trail=0.15; color_source=static; beat_boost=1; direction=forward | 亮段之间留间隔 | □通过 □不清楚 □退化；备注：____ |
| B / 101.6–107.6 | 5 | speed=1 → 5 groups/s | C2 solid | width=2; gap=4; trail=0.15; color_source=static; beat_boost=1; direction=reverse | 反向追逐、间隔保留 | □通过 □不清楚 □退化；备注：____ |
| C / 107.6–113.6 | 7.5 | speed=1 → 7.5 groups/s | C3 positional | width=2; gap=4; trail=0.15; color_source=static; beat_boost=1; direction=bounce | 往返追逐 | □通过 □不清楚 □退化；备注：____ |
| D / 113.6–119.6 | 9.5 | speed=1 → 9.5 groups/s | C4 positional | width=2; gap=4; trail=0.15; color_source=static; beat_boost=1; direction=forward | 最快档不退化为全亮 | □通过 □不清楚 □退化；备注：____ |

### Comet 彗星

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 120–127 | 2.5 | speed=1.2 → 3 groups/s | C1 solid | decay=0.8; count=1; trajectory=wrap; tail_length=0.15; phase_spacing=1 | 单头 wrap、有衰减尾迹 | □通过 □不清楚 □退化；备注：____ |
| B / 127–134 | 5 | speed=1.2 → 6 groups/s | C2 solid | decay=0.8; count=1; trajectory=bounce; tail_length=0.2; phase_spacing=1 | 单头 bounce、有头尾 | □通过 □不清楚 □退化；备注：____ |
| C / 134–141 | 7.5 | speed=1.2 → 9 groups/s | C3 positional | decay=0.8; count=2; trajectory=bounce; tail_length=0.15; phase_spacing=0.5 | 双头短暂交汇后重新分离 | □通过 □不清楚 □退化；备注：____ |
| D / 141–148 | 9.5 | speed=1.2 → 11.4 groups/s | high_contrast_palette positional | decay=0.8; count=3; trajectory=wrap; tail_length=0.1; phase_spacing=0.333333 | 三头 wrap、空间不过度覆盖 | □通过 □不清楚 □退化；备注：____ |

### Color wipe 铺展

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 148.4–155.4 | 2.5 | speed=1.4 → 3.5 groups/s 推进基准 | C1 solid | edge_softness_px=0; progress_curve=linear; origin=start | 从 group 0 铺满 | □通过 □不清楚 □退化；备注：____ |
| B / 155.4–162.4 | 5 | speed=1.4 → 7 groups/s 推进基准 | C2 solid | edge_softness_px=1; progress_curve=linear; origin=end | 从 group 19 铺满，每次均可停看 | □通过 □不清楚 □退化；备注：____ |
| C / 162.4–169.4 | 7.5 | speed=1.4 → 10.5 groups/s 推进基准 | C5 POSITIONAL timeline | edge_softness_px=1; progress_curve=smoothstep; origin=center | 从中心向两端；重播不重置 C5 | □通过 □不清楚 □退化；备注：____ |
| D / 169.4–176.4 | 9.5 | speed=1.4 → 13.3 groups/s 推进基准 | C4 positional | edge_softness_px=1; progress_curve=smoothstep; origin=edges | 从两端向中心，铺满并停看 | □通过 □不清楚 □退化；备注：____ |

### Flowing bands 流动亮带

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 176.8–182.8 | 2.5 | steps_per_second=0.8 → 2 band steps/s | C1 solid | band_width_px=1; gap_width_px=1; base_gain=0.2; highlight_gain=0.85; phase_offset_steps=0; direction=forward | 黑 gap 保留，高亮沿亮带前进 | □通过 □不清楚 □退化；备注：____ |
| B / 182.8–188.8 | 5 | steps_per_second=0.8 → 4 band steps/s | C2 solid | band_width_px=1; gap_width_px=1; base_gain=0.2; highlight_gain=0.85; phase_offset_steps=0; direction=reverse | 高亮反向推进 | □通过 □不清楚 □退化；备注：____ |
| C / 188.8–194.8 | 7.5 | steps_per_second=0.8 → 6 band steps/s | C3 positional | band_width_px=1; gap_width_px=1; base_gain=0.2; highlight_gain=0.85; phase_offset_steps=0; direction=forward | 亮带高亮更快推进 | □通过 □不清楚 □退化；备注：____ |
| D / 194.8–200.8 | 9.5 | steps_per_second=0.8 → 7.6 band steps/s | C4 positional | band_width_px=1; gap_width_px=1; base_gain=0.2; highlight_gain=0.85; phase_offset_steps=0; direction=reverse | 最快反向推进仍能辨认 gap | □通过 □不清楚 □退化；备注：____ |

### Twinkle 火花

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 201.2–208.2 | 1 | density=0.1, fade_time=1.2s → 2 events/s | warm_white_gold solid | event_width_px=1; blur_radius_px=0; color_source=solid | 低出生率、长衰减 | □通过 □不清楚 □退化；备注：____ |
| B / 208.2–215.2 | 1 | density=0.25, fade_time=0.8s → 5 events/s | C1 solid | event_width_px=1; blur_radius_px=0; color_source=solid | 中出生率、明显出生/衰减 | □通过 □不清楚 □退化；备注：____ |
| C / 215.2–222.2 | 1 | density=0.5, fade_time=0.5s → 10 events/s | C5 EVENT timeline | event_width_px=1; blur_radius_px=0; color_source=solid | 出生记住当时 C5；避开重叠后观察 | □通过 □不清楚 □退化；备注：____ |
| D / 222.2–229.2 | 1 | density=0.8, fade_time=0.3s → 16 events/s | effect-local random | event_width_px=1; blur_radius_px=0; color_source=random | 随机色、高出生率和短衰减，避免长期全亮 | □通过 □不清楚 □退化；备注：____ |

### Heat fire 热场

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 229.6–237.6 | 2.5 | 无 local 速度；spark_rate=8/simulation-s → 2.5× simulation time | C2 solid | cooling_per_second=0.8; spark_rate=8; spark_strength=0.9; diffusion=0.35; spark_zone_px=3 | 慢模拟、由火种区传播 | □通过 □不清楚 □退化；备注：____ |
| B / 237.6–245.6 | 5 | 无 local 速度；spark_rate=8/simulation-s → 5× simulation time | C3 positional | cooling_per_second=0.8; spark_rate=8; spark_strength=0.9; diffusion=0.35; spark_zone_px=3 | 更快暖/紫/青位置着色 | □通过 □不清楚 □退化；备注：____ |
| C / 245.6–253.6 | 7.5 | 无 local 速度；spark_rate=8/simulation-s → 7.5× simulation time | C4 positional | cooling_per_second=0.8; spark_rate=8; spark_strength=0.9; diffusion=0.35; spark_zone_px=3 | 更快冷色位置着色 | □通过 □不清楚 □退化；备注：____ |
| D / 253.6–261.6 | 9.5 | 无 local 速度；spark_rate=8/simulation-s → 9.5× simulation time | high_contrast_palette positional | cooling_per_second=0.8; spark_rate=8; spark_strength=0.9; diffusion=0.35; spark_zone_px=3 | 最快热场仍有空间与时间变化 | □通过 □不清楚 □退化；备注：____ |

### History stream 历史颜色

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 262–273 | 2.5 | steps_per_second=0.8 → 2 samples/s | warm-history 原生 timeline | direction=forward | 深红→橙→金，缓慢写入 | □通过 □不清楚 □退化；备注：____ |
| B / 273–280 | 5 | steps_per_second=0.8 → 4 samples/s | cool-history 原生 timeline | direction=reverse | 深蓝→青→紫，反向历史 | □通过 □不清楚 □退化；备注：____ |
| C / 280–287 | 7.5 | steps_per_second=0.8 → 6 samples/s | RGB-history 原生 timeline | direction=forward | 红→绿→蓝，可分辨采样区段 | □通过 □不清楚 □退化；备注：____ |
| D / 287–294 | 9.5 | steps_per_second=0.8 → 7.6 samples/s | high-contrast-history 原生 timeline | direction=reverse | 金→洋红→青→冷近白，快速反向写入 | □通过 □不清楚 □退化；备注：____ |

### Coherent noise field 连续噪声

| Variant / 绝对秒 | common speed | local speed/rate → effective rate | 色彩策略 | 形态参数（源自 YAML） | 肉眼观察目标 | 记录 |
|---|---:|---|---|---|---|---|
| A / 294.4–302.4 | 2.5 | drift_rate=0.12 → 0.3 noise-time/s | C1 solid | feature_size_px=8; contrast=1.2; floor_gain=0.1; ceiling_gain=0.85 | 大尺度慢变包络 | □通过 □不清楚 □退化；备注：____ |
| B / 302.4–310.4 | 5 | drift_rate=0.12 → 0.6 noise-time/s | C4 positional | feature_size_px=6; contrast=1.2; floor_gain=0.1; ceiling_gain=0.85 | 中尺度、冷色位置着色 | □通过 □不清楚 □退化；备注：____ |
| C / 310.4–318.4 | 7.5 | drift_rate=0.12 → 0.9 noise-time/s | C3 positional | feature_size_px=4; contrast=1.2; floor_gain=0.1; ceiling_gain=0.85 | 更细尺度、较快漂移 | □通过 □不清楚 □退化；备注：____ |
| D / 318.4–326.4 | 9.5 | drift_rate=0.12 → 1.14 noise-time/s | high_contrast_palette positional | feature_size_px=3; contrast=1.2; floor_gain=0.1; ceiling_gain=0.85 | 最细尺度、快速漂移仍保留连续性 | □通过 □不清楚 □退化；备注：____ |

Color wave 冻结组合再次列明，速度与色域/形态的验证相互独立：

```text
A  speed=2.5  hue_span=60   sine
B  speed=5.0  hue_span=140  triangle
C  speed=7.5  hue_span=240  linear
D  speed=9.5  hue_span=360  saw
```

History 四套均是 **effect-local `params.color_timeline`**，不配置 cue-level ColorSource，不统一套 C5。关键帧如下（D 是精确 33%、66%，不是三等分）：

| Variant | 原生颜色时间线（局部秒 : RGB） |
|---|---|
| A — warm-history | 0s: `[0.8,0.04,0.01]` → 5.5s: `[0.95,0.28,0.02]` → 11s: `[0.95,0.7,0.08]` |
| B — cool-history | 0s: `[0.02,0.04,0.35]` → 3.5s: `[0,0.72,0.85]` → 7s: `[0.45,0.05,0.75]` |
| C — RGB-history | 0s: `[0.9,0.03,0.02]` → 3.5s: `[0.03,0.85,0.08]` → 7s: `[0.02,0.1,0.9]` |
| D — high-contrast-history | 0s: `[0.95,0.6,0.04]` → 2.31s: `[0.85,0.04,0.65]` → 4.62s: `[0.03,0.85,0.95]` → 7s: `[0.85,0.9,1]` |

同帧观察新旧采样颜色及方向顺序；高速 D 只保留约 2.5s 历史，不能要求四个关键帧锚点在同一帧共存。Twinkle C 则在**事件出生**时保存 C5 颜色，衰减中不跟随当前 timeline 重着色；新事件重叠同 group 会混色，不把它误判成出生记忆失效。Heat fire 的 spatial palette 仅表示位置着色，**不是温度色表**。双彗星可短暂交汇，交汇前后应能辨认两头，不要求始终分离。

## Wipe 重播和 C5 连续性

| Variant | 次数 × 每次帧数 | 每次 cue 时长 | 铺满理论局部秒 | 铺满至淡出前理论窗口 |
|---|---|---|---|---|
| A | 1 × 210 | 7s | 19/3.5 ≈ 5.428571s | ≈ 1.471429s |
| B | 2 × 105 | 3.5s | 19/7 ≈ 2.714286s | ≈ 0.685714s |
| C | 3 × 70 | 70/30s | 19/10.5 ≈ 1.809524s | ≈ 0.423810s |
| D | 3 × 70 | 70/30s | 19/13.3 ≈ 1.428571s | ≈ 0.804762s |

每次须在量化后铺满，并在淡出前完整保持至少 0.3s。以下精确帧边界覆盖所有 Wipe 子 cue：

| cue ID | 起始帧–结束帧（不含） | 绝对秒 |
|---|---|---|
| FX_color_wipe_A | 4452–4662 | 148.4–155.4 |
| FX_color_wipe_B | 4662–4767 | 155.4–158.9 |
| FX_color_wipe_B_r1 | 4767–4872 | 158.9–162.4 |
| FX_color_wipe_C | 4872–4942 | 162.4–164.733333 |
| FX_color_wipe_C_r1 | 4942–5012 | 164.733333–167.066667 |
| FX_color_wipe_C_r2 | 5012–5082 | 167.066667–169.4 |
| FX_color_wipe_D | 5082–5152 | 169.4–171.733333 |
| FX_color_wipe_D_r1 | 5152–5222 | 171.733333–174.066667 |
| FX_color_wipe_D_r2 | 5222–5292 | 174.066667–176.4 |

C 的整个 7s 展示块为 162.4–169.4s，C5 中点在绝对 165.9s。三个子 cue 从整个块采样边界颜色，再将关键帧时间转换为自身局部时间，中间子 cue 保留 50% 转折。它们的 timeline 端点与下一个起点颜色相同；不会重播回深蓝。重播仍有正常淡出/淡入和铺展重启，**色度连续不意味着跨 cue 原始 RGB 亮度连续**。

## Finale：326.8–354.8s

六个 cue 的绝对时序如下。Noise replace 优先级 10 / intensity 0.30；Twinkle add 优先级 20 / intensity 0.20；Comet add 优先级 30 / intensity 0.40。S1/S2/S3/S4 分别为 common speed 2.5/5/7.5/9.5；Twinkle 始终为 1.0。

| cue ID | 绝对秒 | common speed | fade_in / fade_out | 色彩与形态 |
|---|---|---:|---|---|
| FIN_noise_S1 | 326.8–333.8 | 2.5 | 0.1s / 0s | C4 positional; feature_size_px=6; drift_rate=0.12; contrast=1.2; floor_gain=0.10; ceiling_gain=0.85 |
| FIN_noise_S2 | 333.8–347.8 | 5 | 0s / 0s | C4 positional; feature_size_px=6; drift_rate=0.12; contrast=1.2; floor_gain=0.10; ceiling_gain=0.85 |
| FIN_twinkle | 333.8–354.8 | 1 | 0.1s / 3s | warm_white_gold; density=0.25; fade_time=0.8; event_width_px=1.0; blur_radius_px=0 |
| FIN_comet_S3 | 340.8–347.8 | 7.5 | 0.1s / 0s | C2; local speed=1.2; count=2; phase_spacing=0.5; bounce; tail_length=0.10; decay=0.8 |
| FIN_noise_S3 | 347.8–354.8 | 7.5 | 0s / 3s | C4 positional; feature_size_px=6; drift_rate=0.12; contrast=1.2; floor_gain=0.10; ceiling_gain=0.85 |
| FIN_comet_S4 | 347.8–354.8 | 9.5 | 0s / 3s | C2; local speed=1.2; count=2; phase_spacing=0.5; bounce; tail_length=0.10; decay=0.8 |

相对 0–7s 仅 Noise S1；7–14s Noise S2 加入 Twinkle；14–21s 再加入 Comet S3；21–25s Noise 换 S3、Comet 换 S4；25–28s 三层共同淡出。首次加入淡入 0.1s，换档为相邻新 cue（零切换 fade），**不宣称模拟状态连续**。最后存续三层共同在绝对 **351.8–354.8s** 以 fade_out=3s 结束，动态像素无需逐帧单调变暗。验收要求软件测试检查实际贡献与合成中间值，证明量化后各层均有可见贡献且没有非预期截断；实际结果见文末执行记录。

Finale 记录：□通过 / □不清楚 / □退化 / 备注：____

## 结束与安全边界

- `SAFE_black` 显式覆盖 **354.8–356.8s**，零 fade，最后 **60 帧全黑**；不是只有最后一帧黑。
- 正常结束和 Ctrl+C 均由现有 Engine 的 finally 关闭路径尝试发送安全黑帧并关闭输出（production `exit_safe_state: true`）。只运行上述既有 CLI，不用强杀进程代替正常关闭；注意输出 health 与关闭错误日志。
- 末尾黑场与 Ctrl+C 只代表软件发送意图，**不能保证断电、网络中断、接收故障或进程被强制终止后的物理状态**。异常时按现场安全流程处置，不假定灯带已经熄灭。

## 软件证据、限制与复现

两份测试直接读取正式 YAML。已通过的检查覆盖：结构合同、live registry 校验；全 10,704 帧真实 ShowRuntime 离线推进，经 production OutputTransform 与现有 `to_uint8()`；同颜色/形态/seed/cue identity 的独立速度/节奏对照；无特征与变化音视频特征全 Show 重放；确定性与 Finale 分层证据。Finale 使用实际捕获贡献检查全部 840 帧、最后 90 帧共同淡出及随后 60 帧安全黑场，不重复调用运行中的 stateful effect。离线测试不打开输出、不实时等待六分钟。

确定性限定为**相同完整随机初态下的离线重放**：Twinkle A/B/D/Finale 在冻结参数下走 legacy 模块 `random`，测试保存、显式设种并在结束恢复模块随机状态，同时固定 ShowRuntime seed。C 的 EVENT timeline 走私有事件流。**只固定 ShowRuntime seed 不足以保证 legacy Twinkle 的每次实物布局相同**，本 Show 不承诺现场每次随机火花落点一致，也不增加 scalar gate、改宽度或给 D 添加外部 ColorSource 来掩盖此限制。

新增测试和直接相关回归均串行运行。全量 pytest（含全量基线）、benchmark、固件原生测试与构建均为 **USER-WAIVED**，不是通过；旧 acceptance fixture 不修改、不顺带修复。没有新的 registry effect ID、schema、公共 API、硬件拓扑或引擎改动。

本次唯一修改前相关基线（不重复执行）：

```powershell
.\.python\Scripts\python.exe -m pytest -q tests/test_common_motion_clock_phase34.py tests/test_phase39_color_source.py tests/test_show_common_effect_controls.py tests/test_comet_moving_emitters.py tests/test_history_stream_phase33.py tests/test_twinkle_event_fields_phase33.py tests/test_phase35_coherent_noise_field.py tests/test_phase33_scalar_color_wipe.py
```

结果：**176 passed in 1.38s，退出码 0**。后续的同命令运行是修改后回归，不是再次基线。实现后专项命令：

```powershell
.\.python\Scripts\python.exe -m pytest -q tests/test_single_strip_visual_showcase.py tests/test_single_strip_visual_showcase_observability.py
```

执行记录（2026-08-31 至 2026-09-01；专项各轮均使用上方两文件命令）：

| 检查 / 轮次 | 实际结果 | 退出码 |
|---|---|---:|
| 捆绑解释器验证 | `PROJECT_PYTHON_OK` | 0 |
| 唯一修改前相关基线 | 176 passed in 1.38s | 0 |
| 初始源模板 validate-show，两次尝试 | 先发现 Chase/Comet 不接受 params.color，再发现 Twinkle 原生枚举应为 solid；已修正 Show 作者参数 | 各 1 |
| 专项第 1 轮 | 1 failed, 8 passed in 44.09s；测试将 History timeline mapping 错当作列表 | 1 |
| 专项第 2 轮 | 2 failed, 9 passed in 37.57s；测试误用 Breath 单绿色通道和 Comet 覆盖上限 | 1 |
| 专项第 3 轮 | 1 failed, 13 passed in 38.49s；测试把 uint8 门槛用于原始浮点值 | 1 |
| 专项第 4 轮（最终） | **25 passed in 40.36s** | **0** |
| 修改后八模块相关回归 | **176 passed in 1.33s**；命令与唯一相关基线相同 | **0** |
| 最终源模板 validate-show | 74 cues, duration=356.8s | 0 |
| 最终现有 runtime validate-show | 74 cues, duration=356.8s；仅验证，不打开输出 | 0 |

指定软件门禁通过，最终两次 pytest 合计 **201 项通过**。D 已完成独立静态复审；上述失败没有被隐藏、跳过或改为预期失败，后续修正测试判据和诊断，未修改引擎或降低冻结的视觉合同。现场 mDNS 未解析、软件证据不等于实物可观察性、未执行豁免测试，均保留为限制。硬件运行命令仅供现场使用，**本次未执行**。

本轮边界：只新增本目录 show.yaml、README.md 和上述两份测试。开工/收尾比较现有 tracked 文件、两套旧 acceptance（含 (1)）、两份 Energy Wakeup、生产/runtime profile 的 SHA-256 与实际 Git 变更清单；不把 Git HEAD 写成测试 golden，不纳入运行缓存。未暂存、未提交、未推送、未创建 PR。

收尾结果：开工已记录的 **627 个路径项（612 个独立文件）SHA-256 全部一致**，没有删除或改写。另有 6 个中文路径的既有 tracked 文件未进入开工 SHA 清单；收尾改用 `git -c core.quotepath=false ls-files` 后补查，它们的 `git hash-object -- <path>` 与 `git ls-files --stage -- <path>` 索引内容逐项一致，退出码 0。没有将这些既有文件误报成新增文件。

最终范围检查命令：

```powershell
git status --short --branch
git ls-files --others --exclude-standard
git diff --check
git diff --stat
```

以上退出码均为 **0**；实际新增清单仅四个交付文件。`git diff --stat` **为空**，因为四个文件仍为 untracked、未暂存，且没有任何 tracked 文件差异；空输出不表示没有新增交付。受保护文件指纹通过 PowerShell `Get-FileHash -Algorithm SHA256` 只读复核。
