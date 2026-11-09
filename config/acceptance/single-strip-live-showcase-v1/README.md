# Single-strip live showcase v1

面向公司现场演示的单灯带节目：`strip_31`，10 个 WS2811 控制组，30 FPS，138 秒（4140 帧）。Show 只含当前 Registry 已实现的固定效果；不声明媒体颜色源、音视频调制或媒体效果，也不需要音频、视频或麦克风输入。除 Demo 的 `effect.speed=1.5` 外，其余 cue 的通用速度均为 1；所有 cue 的 `effect.intensity` 均为 1。亮度仍由现有 `OutputTransform` 统一处理。

## 时间表、参数与预期

RGB 是归一化 `[0,1]` 值。下表中的速度明确标出对应参数和单位；控制速度与局部速度不可混为一谈。

| 时间（秒） | 效果及 cue | 参数与速度单位 | 视觉预期 |
|---|---|---|---|
| 0–2 | 黑场 `BLACK_start` | RGB `[0,0,0]` | 演示准备黑场。 |
| 2–3.5、3.5–5、5–6.5、6.5–8 | Static：红、绿、蓝、冷白 | 固定颜色分别 `[1,0,0]`、`[0,1,0]`、`[0,0,1]`、`[0.85,0.9,1]` | 全带四种单色依次切换。 |
| 8–8.4 | 黑场 | RGB `[0,0,0]` | Static 与 Breath 间隔。 |
| 8.4–11.4 | Breath A | `period=2s`、sine、`min_brightness=0.05`；青蓝 `[0.05,0.7,0.85]` | 每秒 0.5 个完整呼吸周期。 |
| 11.4–14.4 | Breath B | `period=1s`、smoothstep、`min_brightness=0.05`；橙金 `[0.95,0.32,0.03]` | 每秒 1 个完整呼吸周期。 |
| 14.4–14.8 | 黑场 | RGB `[0,0,0]` | Breath 与 Calm 间隔。 |
| 14.8–19.8 | Calm | `period=2.5s`；基色 `[0.3,0.12,0.7]` | 保留原生低刺激、低饱和度缓慢漂色。 |
| 19.8–20.2 | 黑场 | RGB `[0,0,0]` | Calm 与 Color Wipe 间隔。 |
| 20.2–22.2 | Wipe 起点 | `params.speed=5` groups/s，硬边，青蓝 | 从 start 向前铺展，约 1.8 秒覆盖 10 组。 |
| 22.2–24.2 | Wipe 终点 | `params.speed=5` groups/s，硬边，橙金 | 从 end 反向铺展；独立 cue 重新开始。 |
| 24.2–26.2 | Wipe 中心 | `params.speed=5` groups/s，`edge_softness_px=1`、smoothstep，紫色 | 从中心向两侧铺开。 |
| 26.2–28.2 | Wipe 双端 | `params.speed=5` groups/s，`edge_softness_px=1`、smoothstep，青紫 | 两端向中心铺开。 |
| 28.2–28.6 | 黑场 | RGB `[0,0,0]` | Wipe 与 Single Dot 间隔。 |
| 28.6–32.6 | Single Dot A | `params.speed=6` groups/s，forward，冷白 | 单点正向循环；10 组路径约 1.67 秒一圈。 |
| 32.6–36.6 | Single Dot B | `params.speed=10` groups/s，bounce，金色 | 单点往返，端点反射周期约 1.8 秒。 |
| 36.6–37 | 黑场 | RGB `[0,0,0]` | Single Dot 与 Chase 间隔。 |
| 37–41 | Chase A | `params.speed=6` groups/s，forward，`width=2`、`gap=3`、`trail=0.35`、static color，橙金 | 5 组图案周期约 0.83 秒，保持明显暗隙。 |
| 41–45 | Chase B | `params.speed=9` groups/s，bounce，其余几何同 A，rainbow | 图案推进周期约 0.56 秒，反射运动并保留间隙。 |
| 45–45.4 | 黑场 | RGB `[0,0,0]` | Chase 与 Theater Phase 间隔。 |
| 45.4–48.4 | Theater Phase A | `params.speed=4` 相位步/s，青色 | 三相循环约 0.75 秒。 |
| 48.4–51.4 | Theater Phase B | `params.speed=7.5` 相位步/s，品红 | 三相循环约 0.4 秒。 |
| 51.4–51.8 | 黑场 | RGB `[0,0,0]` | Theater Phase 与 Flowing Bands 间隔。 |
| 51.8–55.8 | Flowing Bands A | 带宽/间隙各 1 组，`base_gain=0.12`、`highlight_gain=0.95`，`steps_per_second=3`，forward，青蓝 | 5 个亮带位置循环约 1.67 秒；速度单位是亮带步/s。 |
| 55.8–59.8 | Flowing Bands B | 相同宽度与增益，`steps_per_second=4.5`，reverse，紫红 | 反向循环约 1.11 秒。 |
| 59.8–60.2 | 黑场 | RGB `[0,0,0]` | Flowing Bands 与 Demo 间隔。 |
| 60.2–68.2 | Demo | `cycle_interval=2s`；`single_dot`、`theater_phase`、`color_wave`、`breath`；通用 `effect.speed=1.5` | 每约 2 秒自动切换一个内置效果；公共速度乘数为 1.5。 |
| 68.2–68.6 | 黑场 | RGB `[0,0,0]` | Demo 与 Color Wave 间隔。 |
| 68.6–71.6 | Color Wave A | `params.speed=0.45` 相位/s，`width=0.85`、hue span 140°、sine、`hue_cycle_rate=0.08` | 柔和色带推进。 |
| 71.6–74.6 | Color Wave B | `params.speed=0.70` 相位/s，`width=0.80`、hue span 240°、triangle、`hue_cycle_rate=0.10` | 更锐利、更宽色域的色带。 |
| 74.6–77.6 | Color Wave C | `params.speed=-0.85` 相位/s，`width=0.75`、hue span 360°、saw、`hue_cycle_rate=0.12` | 反向完整色环推进。 |
| 77.6–78 | 黑场 | RGB `[0,0,0]` | Color Wave 与 History Stream 间隔。 |
| 78–82 | History Stream A | `steps_per_second=6`，forward；局部时间 0/2/4s 的 RGB 为红/青/金，RGB 线性插值 | 约 1.5 秒填满 10 组后持续推进颜色。 |
| 82–86 | History Stream B | `steps_per_second=6`，reverse；同一局部红/青/金时间线 | 反向写入并持续替换历史颜色。 |
| 86–86.4 | 黑场 | RGB `[0,0,0]` | History Stream 与 Heat Fire 间隔。 |
| 86.4–96.4 | Heat Fire | `spark_rate=10/s`、`spark_strength=0.85`、`cooling_per_second=0.9`、`diffusion=0.50`、`spark_zone_px=2`；基色 `[1,0.32,0.04]` | 原生 60 Hz 热场持续产生暖色火种并向远端传播。 |
| 96.4–96.8 | 黑场 | RGB `[0,0,0]` | Heat Fire 与 Noise Field 间隔。 |
| 96.8–100.8 | Noise Field A | `feature_size_px=2.5`、`drift_rate=0.85` 噪声时间/s、`contrast=1.5`、gain 0.06–0.95；蓝青空间 palette | 10 组上可辨的蓝青空间亮暗纹理缓慢演变。 |
| 100.8–104.8 | Noise Field B | `feature_size_px=1.7`、`drift_rate=1.5` 噪声时间/s、`contrast=1.6`、gain 0.06–0.95；蓝紫空间 palette | 更细、更快的蓝紫纹理。 |
| 104.8–105.2 | 黑场 | RGB `[0,0,0]` | Noise Field 与 Step Pulse 间隔。 |
| 105.2–108.2 | Step Pulse A | `period=0.8s`、`duty_cycle=0.4`；低亮深紫 `[0.08,0.01,0.16]`、高亮品红 `[1,0.02,0.65]` | 离散明暗切换，每秒 1.25 周期。 |
| 108.2–111.2 | Step Pulse B | `period=0.6s`、`duty_cycle=0.55`；低亮深蓝 `[0.01,0.03,0.18]`、高亮青 `[0,0.9,1]` | 更快节奏，每秒约 1.67 周期。 |
| 111.2–111.6 | 黑场 | RGB `[0,0,0]` | Step Pulse 与 Twinkle 间隔。 |
| 111.6–115.6 | Twinkle A | `density=0.6` event/(group·s)，`fade_time=0.35s`，金色，事件宽 1 组、blur 0.6 组 | 约 6 次/秒暖金局部闪点。 |
| 115.6–119.6 | Twinkle B | `density=1.0`，`fade_time=0.25s`，红/蓝/紫/青 palette，宽 1、blur 0.6 | 约 10 次/秒高对比彩色闪点。 |
| 119.6–123.6 | Twinkle C | `density=1.4`，`fade_time=0.18s`，随机色，宽 1、blur 0.6 | 约 14 次/秒快速随机闪点。 |
| 123.6–124 | 黑场 | RGB `[0,0,0]` | Twinkle 与压轴 Comet 间隔。 |
| 124–128 | Comet A | `params.speed=9` groups/s，wrap，单头，`tail_length=0.55`、`decay=0.92`，冰蓝 | 快速循环彗星及长尾。wrap 单头使用原生兼容尾迹算法。 |
| 128–132 | Comet B | `params.speed=18` groups/s，bounce，单头，`tail_length=0.60`、`decay=0.92`，金橙 | 往返彗星，单程路径约 9 组，运动速率约 2 次反射/s。 |
| 132–136 | Comet C | `params.speed=27` groups/s，wrap，单头，`tail_length=0.65`、`decay=0.92`，青紫 | 每帧理论位移 0.9 组的高速压轴；通过现场观察确认相机下仍可辨头尾。 |
| 136–138 | 最终黑场 | RGB `[0,0,0]` | 两秒全黑安全保持。 |

## NanoPC-T6 SSH 更新、运行与恢复

仓库部署事实：用户服务为 `light-belt-host.service`，工作目录 `/home/pi/LIGHT-BELT`，服务使用 `.venv/bin/python`，生产 profile 是 `config/runtime/wled-ddp-mdns.yaml`。先从开发机推送后更新目标机；以下命令假设远端分支 `1108` 可正常快进：

```bash
ssh pi@<nanopc-host> 'cd /home/pi/LIGHT-BELT && git fetch origin 1108 && git switch 1108 && git pull --ff-only origin 1108'
```

以下整段在 NanoPC-T6 SSH shell 执行。它先记录 Host 原服务状态，再停止 Host，安装 `EXIT` 恢复钩子；校验独占条件、重新运行仓库自带 resolver 生成 runtime、确认 `strip_31` 已解析且恰为 10 组、校验 Show，然后运行 4140 帧。无论验证失败、运行失败或正常结束，退出钩子都会按原状态恢复 Host 服务。运行前必须结束任何其它 CLI/演示程序；检查命令若发现其他 `light_engine` 进程会退出并恢复 Host，不会擅自杀掉进程。

```bash
ssh pi@<nanopc-host>
cd /home/pi/LIGHT-BELT
(
set -Eeuo pipefail
host_was_active=0
systemctl --user is-active --quiet light-belt-host.service && host_was_active=1 || true
restore_host() {
  rc=$?
  trap - EXIT
  if [ "$host_was_active" -eq 1 ]; then
    systemctl --user start light-belt-host.service || echo 'ERROR: failed to restore light-belt-host.service' >&2
  fi
  exit "$rc"
}
trap restore_host EXIT
systemctl --user stop light-belt-host.service

pgrep -af '[l]ight_engine|[h]ost_services' || true
if pgrep -f '[l]ight_engine|[h]ost_services' >/dev/null; then
  echo 'Another LIGHT-BELT output process is active; stop it cleanly before retrying.' >&2
  exit 1
fi

./.venv/bin/python scripts/runtime/resolve_nodes.py
./.venv/bin/python -c 'from pathlib import Path; import ipaddress,yaml; p=yaml.safe_load(Path("config/runtime/wled-ddp-mdns.yaml").read_text()); l=p["layout"]; s=next(x for x in l["strips"] if x["id"]=="strip_31"); o=next(x for x in l["digital_outputs"] if x["strip_id"]=="strip_31"); n=next(x for x in l["digital_nodes"] if x["node_id"]==o["node_id"]); assert s["pixel_count"]==10, s; assert n.get("enabled") is True, n; ipaddress.IPv4Address(n["host"]); assert p["system"]["output_fps"]==30; print("strip_31 runtime ready:",s,o,n)'
./.venv/bin/python -m light_engine --config config/runtime/wled-ddp-mdns.yaml validate-show --show config/acceptance/single-strip-live-showcase-v1/show.yaml
./.venv/bin/python -m light_engine --config config/runtime/wled-ddp-mdns.yaml run --show config/acceptance/single-strip-live-showcase-v1/show.yaml --clock internal --duration 138 --max-frames 4140
)
```

确认节点解析通过后再继续。其它灯带若在 runtime 中启用，Show 只绘制 `strip_31`，但共享 production profile 的输出引擎仍可能向其它已启用目标发送黑帧；这是九节点配置下的单灯带视觉节目，并不表示只向 node 6 发包。不要同时运行 Host 与独立 CLI。退出钩子会在正常退出、错误和 Ctrl+C 路径尝试恢复原先 active 的 Host；若 Host 原先 inactive，则保持停止。恢复失败会在终端明确报错。

## 软件证据与实机边界

Show 是无媒体依赖编排；`run` 显式使用 internal clock，未传 `--audio`、`--video` 或麦克风设备。现有 CLI 会创建合成特征源，生产 profile 还可能启动 WLED 音频接收；本 Show 的 cue 不读取这些特征。接收器初始化错误仍由引擎报告。Show intensity 不覆盖生产亮度上限，最终全局亮度仍由 `OutputTransform` 处理。

Schema 校验、离线帧回放和软件测试不能证明 NanoPC-T6 的 mDNS、DDP、WS2811 接线、颜色/亮度观感或摄像机采样已通过。`strip_31` 实际输出、不同速度下的拍摄连贯性、火焰观感、随机星点布局、散热/供电和中断时物理安全状态仍需现场观察；硬件状态为 **NOT HARDWARE VERIFIED**。
