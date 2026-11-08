# Single-strip PPT showcase v1

这是一个只驱动 `strip_31` 的软件演示节目：当前生产源模板中该 WS2811 输出有 10 个控制组。节目总长 116.0 秒，30 FPS，共 3480 帧；时钟必须使用 `internal`。Show 不声明或读取音频、视频、麦克风输入，也不修改全局亮度；亮度仍由 `OutputTransform` 统一处理。当前节目和下文的离线证据均为 **NOT HARDWARE VERIFIED**。

## 本机验证与运行

在仓库根目录执行：

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-ppt-showcase-v1/show.yaml
.\.python\Scripts\python.exe -m pytest -q tests/test_single_strip_ppt_showcase.py
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml run --show config/acceptance/single-strip-ppt-showcase-v1/show.yaml --clock internal --duration 116.0 --max-frames 3480
```

`run` 会使用当前配置的真实输出通道；现场运行前应确认 `strip_31` 的节点已解析并且输出区域安全。没有 `--audio`、`--video` 或麦克风参数时，所有帧只由内部时钟和 Show cue 决定。正常结束仍由现有 Engine 安全黑帧路径处理；114.0–116.0 秒的 `BLACK_end` 另行保持全黑。

## 时间表与视觉预期

| 绝对时间（秒） | Cue / Registry effect | 实际参数 | 视觉预期 |
|---|---|---|---|
| 0–2 | `BLACK_start` / `static` | RGB `[0,0,0]` | 黑场，建立拍摄前基线。 |
| 2–8 | `COMET_cool_single_wrap` / `comet` | `params.speed=2.5`; `count=1`; `trajectory=wrap`; `tail_length=0.25`; `decay=0.8`; 冷白 `[0.85,0.9,1]` | 单头沿 10 组循环移动，短尾可辨认。 |
| 8–15 | `COMET_blue_double_bounce` / `comet` | `params.speed=3.0`; `count=2`; `trajectory=bounce`; `phase_spacing=0.5`; `tail_length=0.20`; `decay=0.8`; 蓝 `[0.03,0.2,1]` | 两个蓝色发射器往返，交汇后重新分离。 |
| 15–22 | `COMET_purple_double_wrap` / `comet` | `params.speed=4.5`; `count=2`; `trajectory=wrap`; `phase_spacing=0.5`; `tail_length=0.15`; `decay=0.8`; 紫 `[0.55,0.05,0.9]` | 双头循环更快，仍保留头尾层次。 |
| 22–22.5 | `BLACK_after_comet` / `static` | RGB `[0,0,0]` | 显式转场黑场。 |
| 22.5–29 | `WAVE_sine` / `color_wave` | `params.speed=0.35`; `width=0.9`; `waveform=sine`; `hue_span_degrees=140` | 慢速正弦彩色波，适合拍摄连续色带。 |
| 29–35.5 | `WAVE_triangle` / `color_wave` | `params.speed=0.75`; `width=0.8`; `waveform=triangle`; `hue_span_degrees=240` | 三角波色域更宽，推进轮廓清楚。 |
| 35.5–42.5 | `WAVE_saw` / `color_wave` | `params.speed=-0.8`; `width=0.75`; `waveform=saw`; `hue_span_degrees=360` | 反向锯齿推进，覆盖完整色环。 |
| 42.5–43 | `BLACK_after_wave` / `static` | RGB `[0,0,0]` | 显式转场黑场。 |
| 43–49 | `TWINKLE_low` / `twinkle` | `density=0.12`; `fade_time=0.9`; `color_source=palette`; `event_width_px=1`; `blur_radius_px=0`; 金/蓝/紫 palette | 稀疏、长衰减的局部星光。 |
| 49–56 | `TWINKLE_mid` / `twinkle` | `density=0.35`; `fade_time=0.7`; 同上 palette 与宽度 | 中等出生率，局部事件仍保持间隔。 |
| 56–63 | `TWINKLE_high` / `twinkle` | `density=0.6`; `fade_time=0.5`; 同上 palette 与宽度 | 高出生率、短衰减，避免持续全亮。 |
| 63–63.5 | `BLACK_after_twinkle` / `static` | RGB `[0,0,0]` | 显式转场黑场。 |
| 63.5–70.5 | `FIRE_low` / `heat_fire` | `spark_rate=4`; `spark_strength=0.7`; `cooling_per_second=1.2`; `diffusion=0.3`; `spark_zone_px=2`; 橙红 `[1,0.18,0.02]` | 低速火种从起始区域扩散，保留空间暗部。 |
| 70.5–77.5 | `FIRE_mid` / `heat_fire` | `spark_rate=8`; `spark_strength=0.9`; `cooling_per_second=0.8`; `diffusion=0.35`; `spark_zone_px=2` | 更密集的热量传播，橙红原生强度变化。 |
| 77.5–83.5 | `FIRE_high` / `heat_fire` | `spark_rate=12`; `spark_strength=0.95`; `cooling_per_second=0.65`; `diffusion=0.45`; `spark_zone_px=2` | 高能火焰段，仍由热量强度乘橙红 RGB 渲染。 |
| 83.5–84 | `BLACK_after_fire` / `static` | RGB `[0,0,0]` | 显式转场黑场。 |
| 84–114 | `FINALE_noise` / `coherent_noise_field` | `feature_size_px=3.2`; `drift_rate=0.3`; `contrast=1.15`; `floor_gain=0.08`; `ceiling_gain=0.65`; `intensity=0.25`; `blend=replace`; 蓝—青—紫 `spatial_palette`; `fade_out=4` | 连续、可拍摄的低亮度冷色空间底。 |
| 90–114 | `FINALE_twinkle` / `twinkle` | `density=0.25`; `fade_time=0.8`; `intensity=0.20`; `event_width_px=1`; `blur_radius_px=0`; 金白；`blend=add`; `fade_out=4` | 金白星光叠加在噪声底上，事件保持局部可见。 |
| 98–114 | `FINALE_comet` / `comet` | `params.speed=3.5`; `count=2`; `trajectory=bounce`; `phase_spacing=0.5`; `tail_length=0.15`; `decay=0.8`; `intensity=0.40`; 金白；`blend=add`; `fade_out=4` | 双发射器在底层上往返；110–114 秒三层共同按已有 `transition.fade_out` 淡出。 |
| 114–116 | `BLACK_end` / `static` | RGB `[0,0,0]` | 明确的两秒全黑安全保持。 |

`effect.speed` 是通用 motion multiplier，本节目保持为 `1`；表中 `params.speed` 是 `comet` 或 `color_wave` 的 effect-specific 速度。每个 cue 都可以重置 state；本节目不依赖平滑变速、碰撞检测或跨 cue 状态继承。

## NanoPC-T6 更新与单命令运行

以下命令在开发机执行，假设 NanoPC-T6 的仓库是 `/home/pi/LIGHT-BELT`，SSH 用户为 `pi`。只同步本任务目录，不覆盖生产配置：

```bash
scp -r config/acceptance/single-strip-ppt-showcase-v1 pi@<nanopc-host>:/home/pi/LIGHT-BELT/config/acceptance/
ssh pi@<nanopc-host> 'cd /home/pi/LIGHT-BELT && ./.venv/bin/python -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-ppt-showcase-v1/show.yaml && ./.venv/bin/python -m light_engine --config config/profiles/rk3588-host-service.yaml run --show config/acceptance/single-strip-ppt-showcase-v1/show.yaml --clock internal --duration 116.0 --max-frames 3480'
```

运行前先确认 `wled-strip-31.local` 已由现有 resolver 解析；不要把 `config/profiles/rk3588-host-service.yaml` 改成临时 fake/memory 输出，也不要附加媒体参数。

## 证据边界

专项测试会验证 YAML Schema/Registry/目标拓扑、3480 帧离线渲染、确定性复播、无媒体输入不变、章节黑场、末尾 60 帧全黑，以及 Finale 三层 contribution 的实际非零贡献。离线渲染不打开网络输出；NanoPC-T6 的 WLED/mDNS、真实亮度、摄像机拍摄效果、掉电和进程强杀后的物理状态仍未进行实机验证。
