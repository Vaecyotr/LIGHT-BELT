# 单灯带现场演示

Show ID 为 `single-strip-live-showcase-v1`，目标是 `strip_31` 的 10 个控制组；总长 60 秒、30 FPS、1800 帧。使用 internal clock，Show 不依赖音视频或媒体调制；全局亮度由 `OutputTransform` 处理。现场输出和拍摄效果为 **NOT HARDWARE VERIFIED**。

| 秒 | 效果与实际参数 | 视觉预期 |
|---|---|---|
| 0–0.5 | 黑场 | 准备 |
| 0.5–4.5 | Chase：12 正向、18 往返组/秒；width 2、gap 2、trail 0.18 | 橙金、虹色亮段快速移动 |
| 4.5–8.5 | Color Wave：1.6/2.2/-2.6 相位/秒；sine/triangle/saw；width 0.8/0.72/0.65、色域 300/300/360 度、hue rate 0.20/0.22/0.25 | 三种快速色波 |
| 8.5–12.5 | Twinkle：density 1.7/2.4/3，fade 0.22/0.17/0.13 秒，宽 1、blur 0.3 | 单色、palette、随机闪点；约 17/24/30 次出生/秒 |
| 12.5–16 | Single Dot：15 正向、23 往返组/秒 | 无尾迹单点 |
| 16–19 | Theater Phase：8/10 相位步/秒 | 青色、品红三相切换 |
| 19–22 | Flowing Bands：10 正向、14 反向亮带步/秒；带宽/间隔 1、base 0.03、highlight 1 | 五个亮带位置快速轮转 |
| 22–25.5 | History Stream：14 正向、22 反向步/秒；红→青→金→紫 | 多色历史持续推进 |
| 25.5–29.5 | Color Wipe：start 12、end 16、center/edges 12 组/秒；四个独立 cue | 四种方向重启铺展 |
| 29.5–33 | Coherent Noise Field：drift 2.5/4 噪声时间/秒、feature 1.8/1.5 组、contrast 2.5/2.6、gain 0.03–1 | 蓝青、蓝紫亮暗纹理 |
| 33–37 | Heat Fire：spark 22/秒、strength 0.95、cooling 2.4/秒、diffusion 0.7、spark zone 2 | 原生 60 Hz 暖色热场 |
| 37–41 | Demo：cycle 0.8 秒、common speed 3.5；single_dot、theater_phase、color_wave、chase | 自动切换四种效果 |
| 41–43 | Static：红、绿、蓝、冷白各 0.5 秒 | 四色切换 |
| 43–44.5 | Calm：period 0.7 秒，基色 [0.25,0.12,0.65] | 柔和低亮漂色 |
| 44.5–47 | Breath：sine 0.75 秒、smoothstep 0.55 秒，最小亮度 0.02 | 青蓝、橙金快速呼吸 |
| 47–50 | Step Pulse：period 0.45/0.35 秒、duty 0.45 | 深紫/品红、深蓝/青色阶跃 |
| 50–58.5 | Comet：24 wrap、27 bounce、29 wrap 组/秒；单头、tail 0.6、decay 0.82 | 不同颜色高速头尾 |
| 58.5–60 | 黑场 | 最终安全保持 |

局部 `params.speed` 与通用 `effect.speed` 相乘；仅 Demo 的通用速度为 3.5，其余为 1。Demo 切换采用实际时间，不受该乘数改变。Comet 单头 wrap 使用逐帧衰减的兼容分支；bounce 使用距离形状的发射器分支。29 组/秒在 30 FPS 下约 0.967 组/帧，量化后可能重复一组。

Windows 仓库根目录的验证命令：

```powershell
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml validate-show --show config/acceptance/single-strip-live-showcase-v1/show.yaml
.\.python\Scripts\python.exe -m light_engine --config config/profiles/rk3588-host-service.yaml inspect-topology --show config/acceptance/single-strip-live-showcase-v1/show.yaml
.\.python\Scripts\python.exe -m pytest -q tests/test_single_strip_live_showcase.py
```

NanoPC-T6 上使用现有 resolver 生成的 `config/runtime/wled-ddp-mdns.yaml`，确认 `strip_31` 已解析并独占输出，停止 `light-belt-host.service` 后用 `.venv/bin/python -m light_engine --config config/runtime/wled-ddp-mdns.yaml run --show config/acceptance/single-strip-live-showcase-v1/show.yaml --clock internal --duration 60 --max-frames 1800`；结束后恢复原 Host 服务。其他启用灯带可能收到黑帧。CLI 可能创建合成特征源或启动配置的 WLED 音频接收，但此 Show 不消费这些特征。
