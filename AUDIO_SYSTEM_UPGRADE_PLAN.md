# LIGHT-BELT 康养舱音频系统升级方案

## 1. 执行摘要

**视频由 mpv 播放，手机通过蓝牙播放，Host 只在二者共用扬声器时选择声音。** 灯带有独立的输出所有者。用户可以看视频、听手机 A 的音乐，同时让灯光跟随 WLED 环境麦克风。视频暂停后，节目时间轴停在原处，手机及独立音乐灯效可以继续；视频退出也不结束手机播放。

| 产品规则 | 工程落点 |
|---|---|
| 两台手机可同时连接，扬声器一次播放一台；配对历史可超过两台 | BlueZ 提供连接与传输事实，Host 管理两个连接名额和一条可听回放路。先播者保持，释放后从仍在播放者中接替，右屏可主动交接。 |
| 视频原声可恢复 | Host 保存节目音量及主动静音；接管期间临时抑制原声，释放后在当前视频位置按最新偏好恢复。手机音量由手机调节。 |
| 灯光从哪里取声音 | 右屏只提供「设备音频（自动跟随）」和「环境麦克风」。前者是首次安装默认值，自动跟随获选手机或节目音轨；有效静音、无数字媒体、采集故障分开显示。数字故障保留基础灯效并重试。 |
| 如何切灯光、如何找回节目灯光 | 一个受管 Engine 持有 DDP，在帧边界选择节目、独立音乐或手动画面。正常换角色持续出帧；显式关灯优先进入安全状态。右屏首页与播放中的控制页常驻显示灯光意图，手动或关闭时可一键「恢复随播放」，亮度与分析偏好单独保存。 |
| 独立右屏通过控制局域网使用 Host | 每台舱一次授权一台控制终端，任何使用右屏的人都能管理蓝牙。复用网页、HTTP 查询和现有播放器 API；配对走真实 BlueZ Agent 回调。顾客手机只需蓝牙。 |

源码与媒体核查基点为 `1121-video-shock` 的 `039c00b02f3a5aceeb12eb762ac8ce22a69d0bbf`。第 2 节描述已有系统与软件证据；第 3–8 节是实施合同。生产路由切换以 H2、H3 通过为前提，配对及网络右屏上线另须 H4 通过。开发前先完成第 8 节的设计审查；未关闭的设计反例与待实测的设备能力分别登记。阶段授权、实现验证和生产放行分别判断。[项目事实](CLAUDE.md) · [闭环规格](docs/CLOSED_LOOP_SPEC.md) · [现行实施计划](docs/IMPLEMENTATION_PLAN.md)

## 2. 现状审计

### 2.1 节目音轨同时有播放端和分析端

1. `shows_loader._discover_assets` 枚举 `assets/<show>/`，按排序选视频、独立音频和 YAML。视频加音频会生成 `media_path + audio_path`；只有音频时由 `media_path` 承载。可选的 `data/shows_manifest.json` 覆盖发现结果。本工作树现有 `energy-wakeup.mp4` 和原始 YAML，无覆盖清单和独立音轨。实际调用发现结果为 `show_id=energy-wakeup, duration_ms=305620, audio_path=None`；使用收录的 RK3588 模板调用真实内容预检通过。设备专用的 mDNS 运行配置需要在部署时生成。测试用 `config/shows/energy-wakeup.yaml` 不参与生产选择。[发现规则](host_services/shows_loader.py) · [播放前校验](host_services/engine_adapter.py) · [生产 Show](assets/energy-wakeup/energy-wakeup.yaml)
2. Host 用户服务在 Wayland 会话使用 `%t/light-belt/mpv.sock`，启动或接入 idle mpv。播放时串行化会话命令，启动带 generation 的事件观察器，暂停、`loadfile replace`、等 `file-loaded`。如有 `audio_path`，`MpvClient.add_audio_track` 用 `audio-add … select` 选择该轨；按需 seek 并确认位置。节目引擎就绪后才解除暂停。mpv 的应用名为 `LIGHT-BELT-LocalMedia`，依赖音频服务器的实际输出选择。仅设置默认 sink 并不能证明已存在的 mpv 流在该 sink 上。[用户服务](systemd/user/light-belt-host.service) · [MpvClient、playback_play、_ensure_mpv](host_services/engine_adapter.py) · [mpv 命令合同](https://mpv.io/manual/stable/)
3. `RealEngineAdapter.on_playback_start` 启动独立的 `python -m light_engine … run --show … --clock mpv --mpv-socket … --ready-stdout`，依后缀传 `--video` 和外部/纯音频的 `--audio`。stdout 就绪标记、持续排空日志、存活检测分别处理。单独 MP4 可由 mpv 播放内嵌声音，Engine 的视频参数只供画面分析。已有离线 `prepare_show_audio` 能用 FFmpeg 选择流、保留时间偏移并发布单个 FLAC，播放与分析共同使用该音轨。不要在点击播放时重复转码。[子进程构造](host_services/real_engine_adapter.py) · [离线音轨制作](scripts/authoring/prepare_show_audio.py) · [CLI 入口](light_engine/cli/__init__.py)
4. 普通暂停/继续只改 mpv；Host seek 会暂停原播放、停止渲染器/辅助触发线程、请求精确 seek、确认位置，再以同一 Show 重建引擎并恢复原播放状态。手动灯光命令也可能用 internal-clock 子进程替换节目引擎，reset 恢复 YAML。停止、自然结束、进程异常各自有回收或错误路径，watchdog 会核对会话代际。**切换分析源若借用 seek、reset 或手动灯光命令，就会丢失效果历史，触及安全熄灯，甚至改变暂停状态。** [RealEngineAdapter 生命周期](host_services/real_engine_adapter.py) · [Host 会话与 watchdog](host_services/engine_adapter.py) · [回归断言](tests/test_host_playback_contracts.py)

#### 当前节目素材的离线核查

| 对象 | 实测结果 | 对升级实施的影响 |
|---|---|---|
| 本地 MP4 | 文件 356,213,314 字节。默认视频流 H.264 High 10、1920×1080、yuv420p10le、60 fps，共 18,336 帧、305.600 s。唯一音轨为默认 AAC-LC、44,100 Hz、双声道、305.620998 s。两条流的 start_time 均为 0。FFmpeg 从头至尾解码音视频成功。 | 可以直接使用本文件验收；H.264 10-bit / 1080p60 的 mpv 解码方式、掉帧、舱内扬声器输出和与灯光分析同时运行的负载须在目标机测。 |
| Host 与文件分析入口 | 在拦截子进程启动时检查 `RealEngineAdapter.on_playback_start` 实际组装的命令：当前目录传 `--video energy-wakeup.mp4`，无 `--audio`。在系统临时副本中，用项目原有 `prepare_show_audio(video, track=0)` 生成同名 FLAC 后再次发现、校验，命令同时传 `--video` 和 `--audio`。 | 当前节目素材可向 mpv 提供内嵌原声；现有 Engine 会按生产配置取 WLED。建议制作/部署阶段生成一次同轨 FLAC 作为可复现的文件分析基线。永久放入外轨也会使 Host 明确选择它播放，不能当作仅分析用途的缓存。 |
| 音轨一致性 | 临时 FLAC 为 47,432,015 字节，双声道共 13,477,888 个采样帧。用同一个 FFmpeg 将 MP4 选中音轨和 FLAC 各自解码为相同格式的交错 s24le，整段 PCM 的 SHA-256 均为 `e26ee4a3bb7c95b41d2f8e2a2dcbc84fe99eefd9296b522cdd976dc72c3b090a`。 | 覆盖本素材的选轨、片头、声道顺序、长度及片尾采样；以后更换媒体或选择其它语言轨时重新验证。 |
| 节目尾段 | 原始 YAML 时长 305.000 s，媒体比 Show 长约 621 ms。305 s 后的解码音轨还有 27,388 个采样帧，峰值约 0.00511 FS，RMS 约 0.00185 FS。 | 现有离线基线和受管模式无接班内容时，灯光到 Show 终点发安全帧；受管模式已有独立音乐接班时改按 第 4.2 节 的帧边界连续交接。mpv 继续到媒体 EOF。Host 按媒体时长显示进度；退出状态要等对应会话结束。另测从暂停状态 seek 到 304.9、305.0 和 305.3 s，再继续或重播；尾段不应被当作失源、假节拍或新手机接管。 |

复核输入文件可用 SHA-256 `79ed7c04f7670bf80bed3d4ff827a0153d2e3d834516546a23a5a33e14aaed2c`。仓库按 `*.mp4` 忽略视频，单独部署媒体时据此识别本次验收素材。相同输入的验证命令为 `ffprobe -v error -show_streams -show_format -of json assets/energy-wakeup/energy-wakeup.mp4` 和 `ffmpeg -nostdin -v error -xerror -i assets/energy-wakeup/energy-wakeup.mp4 -map 0:v:0 -map 0:a:0 -f null -`。PCM 对比对两个输入分别执行 `ffmpeg -v error -i INPUT -map 0:a:0 -c:a pcm_s24le -f hash -`。[素材](assets/energy-wakeup/energy-wakeup.mp4) · [制作工具](scripts/authoring/prepare_show_audio.py) · [真实适配器](host_services/real_engine_adapter.py)

**真实素材的灯光对照。** 取节目 112.000 至 128.000 s（右端不含），固定同一 MP4、生产 YAML、九节点模板、随机种子与 30 fps 媒体位置。分别输入临时同轨 FLAC、相同原声重放、同采样规格的全零音轨。走 `Engine.run → ShowRuntime → OutputTransform → PhysicalMapping`，在发送端以 DDP 同一舍入规则读取 `DigitalNodeFrame.outputs[].pixels`，每帧 107 个 RGB 像素。两次原声输出 480 帧逐值一致；与静音输入相比，479 帧有变化，单帧最多 107 个像素发生变化，8 位单通道最大差值 29。这里的“静音输入”用于改变分析信号；仅操作 mpv 静音并不会改变文件分析输入。该片段可直接复用于验收用例 2。实验使用模拟 mpv 位置和内存观察端，未发出网络包。

**全片与暂停/跳转。** 在同一生产模板、临时同轨 FLAC 和原始 Show 下，以模拟 mpv 时钟从 0 s 每次推进 1/30 s。完整渲染产生 9,150 个节目帧，覆盖九个节点、每帧 107 个 RGB 像素，其中 9,079 帧有非零通道；逻辑序号连续，305.000 s 另产生全黑安全帧。单独注入暂停、继续、前跳到 200 s、暂停回退到 88 s、继续、跳到 304.9 s 再到 305.0 s，两次暂停的重复时间均保持同样像素，末帧为安全黑。这些观测来自软件输出端。[运行循环与结束路径](light_engine/engine/__init__.py) · [DDP 像素转换](light_engine/outputs/ddp_output.py)

**末尾 seek 需要单列处理。** 从 305.0 或 305.3 s 的暂停位置启动渲染器，离线复现实例均在 ready 后只输出安全黑帧并正常结束。此时视频仍可有合法的媒体位置。Host 的 `process_failure` 容许接近 YAML 结束时子进程正常退出，但 `on_playback_start/on_playback_resume_yaml` 在 ready 后立即读到已退出时会抛错，存在与进程调度顺序相关的边界。E 阶段保留旧入口 ready 前后退出的回归；受管模式在 `[show_duration, media_duration)` 只将节目上下文标为已结束，由第 4.2 节确定接班内容或安全结束。Host 不等待一个不可能产生的节目首帧，mpv 保持播放/暂停意图，seek 回 Show 范围再恢复节目上下文。保留中途崩溃和非零退出错误。现有证据尚未覆盖实际 mpv 与 Host 子进程在 NanoPC 上的竞态。[Host 播放会话](host_services/engine_adapter.py) · [子进程就绪与故障判定](host_services/real_engine_adapter.py)

### 2.2 蓝牙可以回放，当前优先级不足以实现产品仲裁

Ubuntu 22.04 部署要求原生 PulseAudio；检测到活动的 pipewire-pulse 会阻止按此路径安装。历史部署记录为手机 A2DP Source → 本机 BlueZ/A2DP Sink → pi 用户会话的 `bluez_source.*.a2dp_source` → `module-bluetooth-policy` 自动创建 `module-loopback` → RT5616 ALSA sink → 扬声器。`audio_output.py` 通过 card 和 owner module 查找可用输出，支持显式 sink；必要时选可用输出 profile、设置默认、移动已识别的策略流。`--check-playback` 检查 RUNNING 和路由；实际插线、放大器与声压仍要测。安装脚本专门清理了旧重复 loopback。仓库记载旧机单路线、无重音和重连的验证，当前镜像、手机组合及版本须复验。[部署记录与证据边界](docs/current/rk3588-bootstrap.md) · [输出检查](scripts/deploy/rk3588/audio_output.py) · [蓝牙部署](scripts/deploy/rk3588/setup-bluetooth.sh)

现在由用户级 `BluetoothAudioPriority` 先枚举，再订阅 `pactl subscribe`。任一匹配 source 为 RUNNING 即查找上述 mpv sink-input，在原先未静音的流上写所有权属性并静音；转 inactive 时同步等待 0.20 s，复查后仅解除拥有的 mute。启动时能识别已标记的流。Host 的 `audio_set` 另写 mpv 的 volume/mute，在内存保留意图和待应用状态；API 接受值或 `audio_output_available=True` 都无法证明实际路由、设备音量或有声。现有两个写入作用于不同层；PulseAudio 的单个流静音位自身不能表达多个控制者的意图。[优先级实现](scripts/deploy/rk3588/bluetooth_audio_priority.py) · [优先级用例](tests/test_bluetooth_audio_priority.py) · [音量 API](host_services/routers/audio.py)

可定位的缺口包括先快照后订阅的事件窗口、循环在恢复等待和 pactl 调用期间不能即时处理新流、路由已建立之后才抑制 mpv、超过防抖窗的缓冲没有独立证据，以及多个 source 被压成一个布尔值。没有设备级赢家、失败者输出门控、AVRCP 观测、蓝牙 PCM 送入 Engine 的路径或 Kiosk 状态。新增录音客户端还可能改变某些 source 的 RUNNING 状态。单凭该状态、连接标志或声能阈值都不足以判断用户按下了播放/暂停。

系统级默认 Agent 使用 `NoInputNoOutput`，自动同意 confirmation/authorization，固定 PIN/passkey；公共模式服务循环开启 discoverable、pairable，安装将相应超时置零。该组合与“在右屏确认配对”直接冲突。仅新建一个页面，旧代理仍可先答复。[默认 Agent](scripts/deploy/rk3588/bluetooth-auto-agent.py) · [公共模式](scripts/deploy/rk3588/bluetooth-public-mode.sh) · [安装所有者](scripts/deploy/rk3588/install-services.sh)

### 2.3 引擎、WLED 与实际消费

| 位置 | 已有行为 | 设计影响 |
|---|---|---|
| `Engine._begin_run_session / _get_audio_features` | 加载文件优先于 WLED，之后才是已配置的生成源/无输入；有文件时不打开 WLED，文件空窗不落到下一来源。独立 CLI 的无媒体分支另有生成源逻辑。 | 生产 Host 显式启用托管分析。旧 CLI、离线渲染及优先级测试保留既有语义。 |
| `AudioReader / AudioAnalyzer.analyze` | 按原采样率读取有界文件窗口，多声道求平均。Engine 在媒体位置附近取 50 ms 居中窗，起点夹到零。分析去 DC、计算 PCM RMS、滚动百分位响度、Hann FFT 三段功率占比、正向谱通量、onset、带冷却的 beat。全零/噪声底有专门处理。 | 文件可预读半窗；实时窗只使用已到的样本。PCM 目前没有真实 16 段和有效主频输出。 |
| `Engine.run / MpvIPCClock.tick` | IPC 读取播放位置、暂停及结束；以媒体时间调度，在输出循环每次最多更新一次音频。配置输出 30 fps、音频 60 Hz、窗 50 ms、hop 配置 25 ms，三者不能当作实测采样频率。暂停可复制上一逻辑帧并分配新 sequence；媒体跳变重置分析及效果。 | 手机和麦克风必须单独计时，否则暂停时积压、恢复时旧包看似刚到。 |
| `WledAudioSyncV2Source.poll` | 非阻塞 drain，44 字节、小端、头 `00002\0`；校验有限非负浮点、频段字节 0–254。取最后合法包的连续值、汇总本次 peak 和正谱差。无新包但仍新鲜时清事件；超龄归零并清谱历史；过期边沿 Engine 重置音乐分析。 | 用“最后合法数据”评估健康；当前以 drain 时刻记 age，无法识别排队很久的包，也没有发送时钟、序号或发端身份认证。多发端混收会污染通量。 |
| `AudioFeatures → MusicControlAnalyzer.update → EffectContext` | 文件与 WLED 在 Engine 汇合。已有 tempo_bpm、tempo_confidence、beat_phase、beat_strength、beat_regularity、energy、energy_trend、transient、bass_ambient、bass_pulse、spectral_motion。重复时间返回旧状态，时间回退须 reset；有界历史，节拍间隔筛选、缺证据/长停顿使估计失效。 | beat 是输入提示，beat_strength 是连续强度，BPM 是有范围的估计。效果、调制、选效器可同时消费原始特征与派生状态。 |

生产模板由 resolver 生成运行配置，默认 WLED Audio Sync V2 输入为 `239.0.0.1:11988`、超时 250 ms；另一路 DDP 输出端口为 4048。九个数字节点的模板没有模拟分区。麦克风汇入 Engine，不经扬声器；蓝牙回放和文件分析原本可能各自工作并跟随不同音乐。节目中只有使用音频的 cue 能体现切源，静态段没有可见变化是合理结果。[引擎调度](light_engine/engine/__init__.py) · [媒体读取](light_engine/media/__init__.py) · [分析器](light_engine/analysis/audio.py) · [派生状态](light_engine/analysis/music_control.py) · [接收器](light_engine/analysis/wled_audio_sync.py) · [项目协议说明](docs/reference/wled-audio-sync-v2.md) · [生产模板](config/profiles/rk3588-host-service.yaml)

### 2.4 Host、Kiosk 与本地证据

当前 Kiosk 直接调用 V1 REST，播放状态约 1 s 刷新，音量另约 3 s 读同一播放状态。`api.seek` 已存在，但 `PlaybackBar.vue` 只显示进度，未发出 seek。`App.vue` 的 HUD 也只有暂停/继续、退出。Host 提供已构建的 `kiosk/dist`；大屏上的 Wayland/mpv 会话属于主机，独立右屏在控制局域网打开网页；现有桌面脚本不负责右屏授权。V1 的 `require_auth` 是空操作，CORS 宽松，配对/token 兼容接口仍存在。旧 WS 需要一次性票据，但申请票据可以匿名，事件名与 REST 集合有冻结测试。不能把新配对请求、PIN 或设备信息塞进公开 V1 推送。[网页入口](kiosk/src/App.vue) · [播放组合函数](kiosk/src/composables/usePlayback.js) · [音量组合函数](kiosk/src/composables/useVolume.js) · [进度条](kiosk/src/components/PlaybackBar.vue) · [Host 依赖](host_services/deps.py) · [WS](host_services/ws.py) · [冻结测试](tests/test_app_host_api_v1_freeze.py)

**本机基线包含一个可重复失败。** 152 个蓝牙、分析、播放、授权、输出与冻结合同定向测试通过；另组 22 项有 21 项通过。失败的延迟内嵌音轨用例已成功制作带 600 ms 静音前缀的 FLAC 并发现 sidecar，接着在融合效果的模拟分区计算中，蓝色乘积为 1.0128523921568626，超过颜色转换允许的 1；单测独立复现相同值。该夹具未走完最终映射及暂停回退断言，不能援引它证明整链已通。生产 DDP 模板无该模拟分区，不能据此判定实机数字输出也会失败。[失败夹具](tests/test_media_fusion_quality.py) · [效果乘法](light_engine/effects/video_audio_fusion.py) · [颜色输入校验](light_engine/color/__init__.py)

## 3. 技术选型

| 决策 | 行为、取舍和采用条件 |
|---|---|
| 保留原生 PulseAudio 和 BlueZ | 当前部署已定位 RT5616，历史单路能播放。改用 PipeWire/WirePlumber 会连带改变对象命名、策略、依赖和安装验证。直接 Acquire BlueZ 的压缩 transport 会与声音服务器争用所有权，还要承担编解码。二者均无当前收益。 |
| 选中流的 monitor 作为实时数字输入 | PulseAudio 可在连接录音流之前指定一个 sink-input，只录该流。获选手机、仅有内嵌音轨的 mpv 都可用同一读法。通过模块、设备、目标 sink、服务器代际反查 index，采集只读。普通 RT5616 monitor 包含同 sink 的其它手机、系统声音与混音，留作验收真值。直接读单部手机的 bluez source 则更接近路由前、可独立于扬声器，但要单独处理 mpv，且可能因录音改变活动判据。默认用定向 monitor；实机证实该接口有缺陷时，才针对获选手机验证 source tap，保留相同隔离合同。 |
| PCM 工具与边界 | 首选 `parec --monitor-stream=…` 作为 Engine 拥有的可回收读流子进程，复用系统工具，先用到达时间和样本计数建时标。管道无每块硬件 PTS。若实测时延误差超界才把同一输入适配器替换为小型异步 libpulse 客户端，读取 timing/latency、hole、move、suspend 回调；不改上层合同。 |
| 手机回放实施“先静音、后开路” | 原生策略每部手机可先建一条可听路，再由外部监听器去静音，无法保证第一块音频或第二部手机不会混入。主方案在升级部署中**仅关闭原生策略的 A2DP 自动 loopback**（`a2dp_source=false`），保留发现、编解码和声卡管理；Host 仅为赢家创建一条具名、指定 source/sink 的 PA loopback，由服务器实时搬运声音。这改变现行唯一策略所有者约定，仅在隔离验证机 H2、H3 均通过后才可修改生产设备路由。避免手工和自动路由并存。 |
| 文件分析与制作 | 优先使用节目已选择的独立音频或经现有工具生成的同轨 FLAC。文件可 seek、复现且不受扬声器音量影响。纯视频有声且无 sidecar 时，设备音频模式可取所选 mpv sink-input，标示为实时采集。纯视频无音频流时刻意报不可用。 |
| 保留 WLED V2 和现有 NumPy/SciPy | 麦克风上送的是特征，无法恢复 PCM、精确拍点或绝对声压。继续使用当前解码器与 MusicControlAnalyzer；增加来源质量与频段描述。舱内无需增加回采硬件；实机同步测量可使用外部量具。 |

选型依据包括 PulseAudio 的定向录音调用、Jammy 自带的命令行接口与蓝牙策略参数。后两者能否同现场服务器、驱动和手机共同达到延迟/隔离要求，需要实测。[libpulse 录音流](https://www.freedesktop.org/software/pulseaudio/doxygen/stream_8h.html) · [Jammy parec 手册](https://manpages.ubuntu.com/manpages/jammy/man1/parec.1.html) · [PulseAudio 模块合同](https://www.freedesktop.org/projects/pulseaudio/Documentation/User/Modules/) · [BlueZ Media API](https://bluez.readthedocs.io/en/latest/media-api/)

Jammy 对应的上游 v15.99.1 实现在 source 创建钩子中读取 `enable_a2dp_source` 决定是否加载回放 loopback；`parec` 在连接 record stream 之前设置监视的 sink-input。启动顺序是**从 BlueZ transport 与 PA 解码 source 识别候选，建立获选者回放路，由该路解析 sink-input，最后连接只读采集**。数字采集成功与扬声器接管分别提交。[策略源码](https://github.com/pulseaudio/pulseaudio/blob/v15.99.1/src/modules/bluetooth/module-bluetooth-policy.c) · [parec 实现](https://github.com/pulseaudio/pulseaudio/blob/v15.99.1/src/utils/pacat.c)

现行手动入口会终止节目引擎，启动临时 Show 并丢弃 stdout；现行 Engine.run 到期后进入 finally，_shutdown 发送安全帧并关闭输出，_begin_run_session 会重置序号。让两个这样的 run 先后或同时打开生产输出，都无法给出连续交接合同。主方案仅对 Host 托管路径分开**画面内容的寿命**和**发送端的寿命**：原有 Engine 子进程维持一个发帧循环，节目、独立音乐和手动效果只向它提供逻辑像素。独立 CLI、离线重放及维护 profile 沿用各自原有的终止行为。[引擎生命周期](light_engine/engine/__init__.py) · [实际 DDP 输出](light_engine/outputs/ddp_output.py)

## 4. 总体架构

```text
独立右屏 ── HTTPS 命令/快照 ── Host ── mpv IPC ── 视频与节目原声
                                ├─ BlueZ system D-Bus：发现、配对、名额、活动观测
                                ├─ pi 用户 PulseAudio：选路、门控与回读
                                └─ 单一受管 Engine：期望画面与输入 →，实际角色、首帧与健康 ←
手机 A / B → BlueZ → PA 解码 source → 唯一获选 loopback ─┐
节目文件 → mpv → 节目 sink-input ─────────────────────────┴→ RT5616 → 音响

获选媒体的 PA 定向 monitor → PCM ──┐
节目同轨文件 → 按媒体时间取窗 ────┼→ 当前 Engine 的选择器 → 特征/音乐状态
指定 WLED → Audio Sync V2 ───────┘                      → 节目或独立效果 → 映射 → DDP
```

### 4.1 视频、蓝牙设备和扬声器

**状态分别归属。** mpv 与现有 Host 会话拥有节目、位置和暂停状态。BlueZ 拥有绑定、连接及媒体 transport/player 事实，PulseAudio 拥有实际声卡、流与路由。Host 在一个串行更新入口处理设备事件、用户选择、mpv 门控和路由回读。Engine 只报告它实际使用的输入。多页 Kiosk 共读 Host 的快照；同一事实不用前端变量或持久化的“上次正在播放”重建。

**两个连接名额。** 按同一手机的 BlueZ 身份计数，音频及控制 profile 共享名额。`Paired` 决定历史列表，`Device1.Connected` 计实际连接。每个未决的 Connect、主动 Pair 或入站接纳先原子预留名额（Pair 本身可能建链）；同一手机的连接和预留只计一次。断开在 BlueZ 确认后释放；超时先重读对象，再撤销预留。满额返回 `CONNECTION_LIMIT`，允许用户选择先断开谁；不得自动替换现有两部。扫描和忘记未连接的历史手机不占名额。

入站及自动重连也要在接纳层受限。满额时关闭新增配对，并在镜像试验中验证控制器可连接性/已知设备入站限制能否阻止第三条链路且保留既有 A、B；空出名额时恢复本服务施加的限制。不能用关闭 discoverable、关闭 Pairable 或 Agent 拒绝新配对代替已配对手机的入站准入。BlueZ 的 Blocked 是每设备属性，影响驱动及后续连接；若使用，必须只撤销自己施加的限制、处理服务重启和新设备并发，且以 HCI 轨迹实证。若出现第三条实际连接，即时隔离并断开新来者、不建回放路，记录违规峰值；事后断开只是恢复措施，严格上限验收仍失败。对账时保留可证明早已接纳的设备，不按事件到达顺序随意踢掉旧用户。H2 无法证实硬上限时升级控制器准入方案，不靠 UI 截断列表。[BlueZ Adapter1](https://bluez.readthedocs.io/en/latest/adapter-api/) · [BlueZ Device1](https://bluez.readthedocs.io/en/latest/device-api/)

**判断播放活动。** 按 transport 的 Device、A2DP 角色和 PA card/source 归属关联同一手机。逐台保留 `paired, connected, transport_state, player_status, activity, speaker_role`。pending 表示流在传输但尚未获取，active 表示已获取；Host 不与 PA 竞争 Acquire。只有播放证据与可用解码源相符才成为自动候选。AVRCP 明确 pause/stop 时短暂复核并抑制同一残余 active，直到新 playing 或已验证的传输停→起。资料缺失时显示未知；只有该手机/镜像经 H2 验证的边沿才可代替 AVRCP。安静、手机音量为零以及采集服务 EOF 均不代表用户停止。切歌和缓冲保留当前赢家，使用可取消的单调计时器和状态重读；既有 0.20 s 仅为旧服务参数。可试明确暂停 250 ms、无 player 的 idle 1.5 s，按误切换及实际释放延迟校准。无限缓冲与暂停若同迹，记录机型缺口，右屏可指定其它手机或断开。[BlueZ Media API](https://bluez.readthedocs.io/en/latest/media-api/)

| 事件 | 扬声器与媒体动作 | 成功判据 |
|---|---|---|
| 空闲、无活动手机；视频播放/暂停/退出 | 有播放中的节目音轨时按节目音量/主动静音输出；暂停或无视频时两路无声。 | 视频状态及音轨由 mpv 确认；界面区分无媒体、节目静音和路由异常。 |
| A 开始，或手机先播、随后启动视频 | 先合成有效静音、核对 mpv 已门控并考虑已提交尾缓冲，再只为 A 建具名路由到 RT5616。无 mpv 也能开手机路；有赢家时新 mpv 在 load/resume 前完成门控。 | PA 回读源、module、sink-input、目标 sink 和 transport 匹配，才显示手机 A 占用扬声器。采集失败独立处理。 |
| A 在播，B 也开始 | B 保持连接或传输，记“等待播放权”，A 持续占用。没有 B 的可听回放路。 | 实际 sink 图仅一部手机可听，连接与播放标签分别显示。 |
| A 停止、暂停或断开 | 关闭 A 并核对尾缓冲。B 仍活动则保持节目门控，接通 B；否则撤节目门控。A 再播放排在当前赢家 B 之后。 | 有节目则从**当前进度**恢复，受最新主动静音约束；无节目则两路无声。相同时刻开始以 Host 观察的首个有效活动沿排序，同批用稳定设备标识打破平局。 |
| 右屏指定已连接的 B | B 有活动时先关 A、验证旧路消失，再接通 B；不向任一手机发送远程暂停/播放。B 无活动时也释放 A，为 B 保留一次待播选择，允许节目按偏好出声，无节目则安静。A 可继续传输但不自动反抢。 | 分别显示“等待 B 开始播放”和真实扬声器来源。B 开播才建立其路由；这次选择在 B 首次接管后转为普通赢家，随后暂停即可交给 A。B 断开或用户点“恢复自动分配”取消等待，重算当前候选。手选目标只活在内存。 |
| 视频暂停、继续、seek、切换、停止、EOF；A 正在听 | 只操作视频及节目灯光时间线，A 的连接、活动和回放路继续；重建节目 mpv 时重新应用其有效 mute。 | 同一 A 路由保持，手机位置由手机掌控。反向的蓝牙事件也不调用 mpv 的 pause、resume、seek、loadfile 或 stop。 |
| 路由失败或 PA/Host 重启 | 先订阅再取全量快照并对账，匹配服务代际及完整路由归属。唯一且仍有效的自有路可续用，否则有序回收孤儿并重选。新 mpv 保守静音起步。 | 不能证实旧路已关时保持门控、报故障；能证实无手机可听时才按当前视频状态恢复。PA 索引、赢家 ID 和旧计时器均不跨服务实例使用。 |

Host 持久化节目 volume、user_muted。`effective_mute = user_muted OR route_gate`；蓝牙释放只清临时 gate。V1 音量接口、场景和右屏共用同一写入口，端口不可用要公开；核对的是数字输出通路，实际声音由 H2/H3 在音响端测量。固定获选 loopback 的 source、sink、归属标记和禁止迁移参数；开始、换人、断线、设备索引复用时均检查。旧事件不得覆盖更新后的选择。

收到 BlueZ/PA 事件时先保存事实，再派发受影响的路由事务；不得持有播放会话锁等待 D-Bus 回调，也不能让同步的 mpv 加载或 Engine ready 等待阻塞 FastAPI 事件循环。路由事务开始/提交均复核当前赢家与 mpv 实例。新 mpv 第一次解除启动静音前也复核门控，避免“启动时没有手机、放声时 A 已接管”的漏音。对 A→B 的直接交接保持节目门控，过程中短暂没有已确认的手机路由属于“切换中”，不能据此向引擎下发一帧节目音轨。

### 4.2 灯光分析、独立音乐效果和 DDP 所有权

| 右屏可选来源 | 正常取值 | 等待、故障和安静 |
|---|---|---|
| 设备音频（自动跟随，首次安装默认） | 已获准向扬声器播放的手机 → 该手机定向 PCM；否则有正在播放的节目 → 同轨文件，只有内嵌轨时取 mpv 定向流。文件按媒体时间分析，独立于节目音量和主动静音。 | 无数字目标显示「没有可分析的设备音频」；应有流而取不到窗显示「设备音频采集异常，正在重试」；合法全零窗显示「设备音频安静」。故障期间保持基础灯效。 |
| 环境麦克风 | 始终读取指定 WLED ESP32 的 Audio Sync V2。 | 合法零包显示「环境安静」；停发、持续坏包或发端不符显示「麦克风无数据」，只等待同一发端恢复。 |

前一版设计中，「自动」和「设备音频」面对视频、手机、无媒体、静音和采集故障的决策完全相同。界面合并为上表两项，「自动」描述数字媒体之间的选择规则。锁定某一部手机或强制分析被压制的节目会改变既定需求；手动指定扬声器播放者仍在蓝牙页完成。声音来源选择与「恢复随播放」两个控件独立。

Host 内部、持久化和新接口读回只用 `analysis_mode=auto/mic`。首次缺省为 auto。若旧偏好或旧调用传 device，在**输入边界**归一为 auto；已有 auto、mic 保留。读旧偏好即可正确运行，下一次成功保存原子写入规范值；同义设置幂等，不重开采集、不重置历史或触发第二次切源。未知请求值报 400，读到损坏配置显示偏好读取故障，不伪报成功。磁盘写失败保留先前有效设置。刷新、换节目、手机断连、Host/整机重启不改变所选来源。界面另列实际输入如「手机 A」「节目音轨」「环境安静」，等待或异常时列明原因。

Host 保存**灯光意图** `follow/music/manual/off`、手动目标和亮度。这是舱的设置，不识别上一位或下一位用户。首次安装为 follow；再次进舱、启动/退出视频、长时间闲置和冷启动均不清除覆盖。意图决定**当前画面角色**，所有需要输出的角色共用同一 Engine 发送端。关闭和亮度为零分别显示。

| 意图与现场情况 | 发送端采用的画面角色 |
|---|---|
| 随播放，视频在有效 Show 区间播放 | 选节目上下文，时间戳取 mpv 位置；手机取得扬声器只改分析输入。 |
| 随播放，视频暂停且手机在播，或无有效节目但手机仍播 | 选独立音乐上下文，按单调时钟工作。暂停的节目保留定格及位置；恢复视频时回到 mpv 当前进度，暂停时手机停止则回到该定格。换节目不得使用上个节目的定格。 |
| 随播放，视频暂停且无手机；或节目到终点 | 前者保持节目定格。已到 Show 末尾（含最后约 621 ms）时，若手机仍在播就接独立音乐；无接班内容才安全结束。 |
| 显式独立音乐 | 复用现有 `audio_pulse` 加低亮基础层。无视频也能用指定麦克风；数字采集失效保持基础效果，输入恢复后叠加响应。 |
| 显式手动 / 关闭 | 手动继续使用已选目标和效果；只有本身消费音频的效果响应输入。off 立即取消候选并安全关灯。两者均可由用户在主页面主动恢复随播放。 |

#### 正常换角色的帧合同

托管模式一次打开输出，一次初始化 OutputTransform、PhysicalMapping、帧序号和 DDP socket。新角色准备期间只有**旧角色具备供帧资格**；新角色只有媒体 reader、时钟、ShowRuntime/效果私有状态和一个预备逻辑帧槽，不持有输出句柄，无权分配输出序号、开关 WLED 或调用 Engine._shutdown。最多一个活动角色加一个候选，不创建第二个 Engine 或跨进程像素转发服务。维护/独立 CLI 如需接管同一物理布局，先停止生产服务；部署以同机同布局互斥锁围住打开到关闭输出的整个寿命，Host 重启后不能凭旧 PID 超时就另开 writer。

1. **准备。** Host 通过现有父子管道发带编号的最新意图、角色、节目代际、seek 代际与源引用。解析/解码、接 mpv、加载手动效果在发帧循环外进行。候选与活动角色共享唯读的带 epoch 特征快照；不并行 drain 同一 WLED socket/消费同一个节拍，不让候选改变活动效果、随机数或分析历史。若必须先试算效果，串行化使用共享随机状态的调用或隔离其状态。候选就绪条件是匹配当前时间位置与布局的**完整首个逻辑帧**（所有目标、长度、数值均有效）；合法的黑色首帧同样有效。输入未热时可先用合同允许的基础帧并标示等待。仅有对象、加载成功或进程 ready 都不能提交。
2. **持续发送。** Engine 在单调时钟的输出节拍上选一个完整画面；使用有界最新帧槽，发帧端不等待候选、媒体 I/O 或 Host。旧角色可继续则正常渲染；因 seek/EOF/换节目已不能推进且有接班意图，暂时重复上一个获准的完整逻辑画面，不重播其节拍。每个实际发送节拍只由 Engine 分配一个新逻辑序号，并携带所选画面的媒体或实时角色时间。暂停/重发保持该画面的时间；从单调域回到媒体域允许时间跳转，序号仍连续。输出变换与物理映射仍沿单一路径对每个发出帧各做一次，不把上次经亮度或 gamma 处理的像素再作为输入。
3. **提交。** 帧边界核对最新编号、角色、布局、媒体代际及位置（播放中校验与当前进度的容差，先试一个输出周期；过时则取更新帧）。选中候选帧，按原顺序发送该完整帧的全部节点数据后才处理下一帧。成功指这一逻辑帧向全部启用节点的**本机提交**完成。首帧成功后回报角色 applied 和逻辑序号，回收旧 reader/效果状态；其清理不发黑、不关 socket、不发 HTTP off。正常交接采用直接帧切换，不给所有效果额外加淡出到黑或交叉渐变。两个角色本就不同的亮度、创作中的暗场和用户关灯仍如实输出。
4. **撤销与失败。** 新请求替换旧候选；迟到首帧、取消回调、旧节目 EOF 和旧代际的 off 不得提交。过期或映射前校验失败且旧角色仍获准时，它继续输出，Host 显示角色切换失败。旧角色已失效时，自第一次只能重发旧画面起按单调时钟设**不可续期**的冻结上限（设计起测值 500 ms）；超过上限仍无有效接班帧，显示故障、发安全黑并回收。连续切换不得延长这个上限。已确认的正常暂停定格有自己的播放状态，不受故障冻结计时器影响。若首个新帧已部分发往节点后报错，进入输出故障处理，禁止宣称 applied 或以另一 writer 重发同序号。

**终止与安全。** Show 到 305 s、mpv EOF 或视频 STOP 只结束节目角色。Host 将当下灯光意图和无节目时的接班规则与播放会话一并下发，Engine 在处理终点前即可分辨「转音乐」和「无接班」；随后 Host 的同代通知幂等。受管 seek 先锁定当前画面并更新媒体代际，Host 确认 mpv seek，候选在新位置准备，期间不关闭输出；有独立/手动画面时只重置受影响的节目读取状态。恢复暂停或新播须支持先在已加载的暂停位置生成首帧，再允许 Host 恢复 mpv，避免互等。旧 CLI 保留一次 run 结束即安全收尾的语义。

显式 off、没有接班内容的真正终止、Host 控制管道丢失、不可恢复的输出故障及服务正常关机均走现有安全收尾。off 抢占准备及未提交帧，已开始的完整帧发完后下一帧安全黑，清除队列，再由唯一发送端关闭；Host 串行处理相关 WLED 本地 off 并回读可用状态。重新点亮需处理上一次 off 的完成/失败，同一节点不能让前一代异步 HTTP off 晚到新输出之后。发送者崩溃或断网时可能无法发安全黑：等旧进程确实退出并取得互斥锁后才恢复；设备超时的本地状态、节点熄灯与失联告警由 H5/H6 验证。UDP 部分发送不能撤回；无确认时界面报告「关闭已请求 / 输出状态未知」，不承诺物理已熄灭。[现有 DDP 队列与发送](light_engine/outputs/ddp_output.py) · [退出安全帧](light_engine/engine/__init__.py) · [WLED 本地状态](host_services/wled_brightness.py)

切源采用准备、帧边界提交、清理三步。等待新源时仅可短时保留当前仍允许且新鲜的连续量；旧手机或已被用户排除的源立即停用。新源失效使音频增量衰减至中性，保留节目或独立模式的基础效果、亮度和有效输出。连续量可先试 150–300 ms 过渡；节拍、BPM、相位与事件 ID 不插值。重置分析历史，丢弃旧窗和暂停时积压的事件；单纯换源不重置 Show、效果、视频或帧序号。快速反复点选仅最后请求可以提交。

节目与独立音乐分别使用媒体时钟和真实单调时钟。托管入口显式选择实时输入，绕开现行无媒体 CLI 自动 use_synthetic、internal 固定步长时钟和手动临时 Show 的 86,400 s 时限。辅助触发仍随节目代际，亮度沿原入口只应用一次，内部交接绝不调用会解除暂停的 V1 playback/reset。[现有适配器](host_services/real_engine_adapter.py) · [CLI 时钟与输入](light_engine/cli/__init__.py)

托管模式在**节目内容边界**捕获 `MpvIPCClock.tick()` 的 `MediaEnded`，Show 时长到期也走同一边界。两者均不能冒泡到一次性 CLI 的 `finally: _shutdown()`。开始该节目时已经带上同代 `role_on_video_end`；EOF 先到即可执行最近一次确认的接班规则。若正等待同代接班配置或候选首帧，只能使用上述有上限的 hold。已知没有接班角色则立即安全结束。重复 EOF 和晚到的旧配置都不能再关一次输出；冷启动的第一份配置不完整时不宣告角色就绪。真正丢失 Host 控制管道时终止受管输出。[mpv 时钟](light_engine/clock.py) · [现有 Engine 收尾](light_engine/engine/__init__.py)

**第 k 个节点写失败。** 该逻辑周期整体提交失败；故障前各节点可能已呈现不同画面。中止此帧剩余普通数据和所有未提交内容，不报 applied。由同一 writer 另分配一个安全帧序号，对故障时全部启用节点各尝试送完安全黑（含 k 及尚未处理的节点）；其中一个失败仍继续尝试其余节点。记录逐节点的普通帧最后本机提交、安全黑发送结果、HTTP off/本地状态回读或超时，清队列并关闭。Host 对仍可达节点执行有界的安全关灯，对失联节点保留「状态未知」直至重连复核；场景整体显示输出故障。恢复先核对唯一所有者、节点状态与当前意图，再以最新配置恢复或保持关闭，禁止回放故障前队列。安全请求使用有限次数和独立单调期限，一个失联节点不能卡住其余节点的收尾。

准备任务另设最长耗时（先以现有启动就绪期限 10 s 作为试验上限）。即使旧角色仍可正常出帧，超时也须释放候选、显示失败；停止或取消的解码任务不得无界堆积。若活动计算本身卡住，按最后一次获准的新内容计时并进入同一有限 hold，不允许靠反复发送旧像素掩盖故障。源合法静音、节目明确暂停及持续的手动静态色用其实际状态区别，不用“像素没有变化”判断卡死。部署互斥锁应在所有会打开生产 DDP 的 Host、CLI 和维护入口共用的稳定本机路径取得，由持有 socket 的进程持锁到最终关闭；服务重启不能靠删除锁文件来取得所有权。

### 4.3 五个时间点与数字采集

| 量 | 单位/取得方式 | 用途与限制 |
|---|---|---|
| 视频媒体位置 | mpv playback-time，秒；Host 进度面向用户用 ms | 定位 cue、视频和文件窗口；允许停顿和回退。 |
| 音频采集时间 | Host 同机 CLOCK_MONOTONIC 纳秒域；PCM 用样本序号和协商采样率重建窗起止，最初锚定到达并减去可测录音缓冲。 | 文件有对应媒体窗；实时输入的窗口中心/末端为估计值。WLED 无发端时戳，采样时刻留空。 |
| 到达时间 | 本机读入 PCM 块或收 UDP 的单调时间，单列 `received_ns` | 新鲜度、掉包和抖动。WLED 用持续排空的接收线程/预算和最晚有效到达时刻；进程调度长停顿时丢积压、开新代际，不将恢复后的 drain 冒充新的声音。 |
| 扬声器发声 | PA timing 的估计值，含 loopback、sink 缓冲；模拟输出、功放和声传播另测 | `estimated_present_ns` 可空，附误差。无权把蓝牙 Delay、录音到达或 mpv time-pos 直接当作现场声压时间。 |
| 灯光生成、发送、显光 | 记录 render、DDP send 前后单调时间和逻辑序号；实灯用光电/高速视频测 | 与输入事件对齐、统计帧间隔。DDP 无逐帧显示确认，不挪用维护用 UDP v3 的 scheduled apply。 |

实时采集建议从 48 kHz、双声道、s16le、10–20 ms 块开始（请求格式，记录服务器转换与实际协商值）。48 kHz 双声道每秒 192,000 B，200 ms 原始环缓冲约 38.4 kB，不含线程、FFT 及进程开销。处理奇数字节/半帧、整帧拼接、断流 EOF、积压和短读，采集线程与渲染分离。使用约 50 ms 窗、25 ms hop，按累计样本数切窗，旧 PCM 过载时丢整窗并置 discontinuity，禁止积压追赶。输入格式转 float 后先各声道去 DC；首版保留现有文件 mono 算法用于兼容，实时 stereo 在明显反相抵消时以双声道功率/能量较强声道估计频谱，记录策略并测试。解析 reader 时不要向 PA 创建播放流。

计算每窗中心、末端与接收时间，记录流启停、服务器移动和累计样本误差；有缺口就重锚，不能用系统日历时间拼接历史。在渲染单调截止点仅取已完成、同 epoch 且符合最大年龄的窗；有估计扬声器呈现时间时，从短有界队列挑最接近预期显光时刻的窗。离线文件继续用当前媒体位置直接索引。实测“灯早于声”才给定向分析增加有限等待；灯已迟则先减块长/链路缓冲，绝不倒退节目时钟。WLED 从麦克风听到声音到收到特征的延迟独立标定，来源和手机切换后旧标定不自动复用。[PulseAudio 时间与缓冲](https://www.freedesktop.org/software/pulseaudio/doxygen/streams.html)

## 5. 接口合同

### 5.1 一份特征进入引擎，一份派生音乐状态进入效果

引擎内部用一个带元数据的观测对象交付每个窗。保留现有 `AudioFeatures`、`MusicControlState` 和 `EffectContext` 调用入口；新字段用可选默认值。实时采样时钟用于派生分析，Show 渲染仍使用原媒体时间。不要通过替换 `ctx.timestamp` 来同步现场音乐。

| 合同组 | 字段、单位与有效性 | 实现和兼容 |
|---|---|---|
| 身份/时间 | `source_kind=file/phone_pcm/program_pcm/wled`，`source_id, source_epoch, sample_seq, clock_domain=media/monotonic, analysis_time_s, media_time_s?, captured_ns?, received_ns?, estimated_present_ns?, uncertainty_ms?`；媒体/单调时间不可直接相减。 | 每个窗/每次有效 drain 产生唯一序号，hold 不增。文件 timestamp 维持既有调用约定；实时音乐分析使用同源递增秒数，投影给旧效果的特征 timestamp 与当前效果时钟一致（节目取媒体时钟，独立模式取单调时钟）。 |
| 可用性 | `quality=fresh/held/stale/unavailable/warming, silent, discontinuity, age_ms?, capabilities` | 合法静音是 fresh。invalid 不更新 age；held 保连续量并清事件，stale/unavailable 停止更新历史。旧调用者的零值/None 另按原合同投影，新调用者显式区分未知与零。 |
| 幅度/分频 | `loudness[0,1], rms, bass, mid, treble, pcm_rms?, raw_level?, spectrum16?, band_layout, level_scale, dominant_hz?, dominant_strength?` | loudness 是相对灯效量，不是 LUFS/dB SPL。PCM 的 pcm_rms 是去 DC 的线性电平，可派生 dBFS；WLED raw/magnitude 保留传感器单位。PCM 三段先沿用原频率范围/总功率比；WLED 沿用组均值。跨源只承诺相对强弱和频序。 |
| 起音与事件 | `spectral_flux, onset_strength, peak_hint, beat_event, event_id?, beat_strength, beat_confidence?` | peak 是瞬态候选。由同一 MusicControlAnalyzer 已接纳的节拍分支发一次 beat_event，事件 ID 用 epoch 和事件序号。新加的逐拍置信度须有标注样本校准，未校准返回 null；已有 tempo_confidence 单独使用。首窗、恢复首窗、静音、hold、过期均屏蔽事件。 |
| 音乐派生 | `energy[0,1], energy_trend[-1,1], transient, bass_ambient, bass_pulse, spectral_motion, tempo_bpm?, tempo_confidence[0,1], beat_phase?[0,1), beat_regularity[0,1]` | 复用现有跟踪器的 60–180 BPM 区间及有界历史。无足够间隔、低可信或节拍超时，公开 BPM/phase=null；旧 MusicControlState 保留零哨兵。用低置信度驱动连续能量效果，避免假锁拍。 |

**16 段的实现约定。** 以仓库固定的 WLED v16.0.1 提交为参照。其 22,050 Hz、512 点、未启用带通的分支，按包含端点的 FFT bin 区间取均值。16 组依次为 `1–2, 2–3, 3–5, 5–7, 7–10, 10–13, 13–19, 19–26, 26–33, 33–44, 44–56, 56–70, 70–86, 86–104, 104–165, 165–215`，bin 中心间隔约 43.07 Hz，端点有重叠。带通分支替换最低四组与最高一组，上游另有增益、AGC、频带补偿、缩放及衰减。V2 wire 只携带 16 字节结果，接收器除以 254；无滤波模式、物理单位或 `fftBin`。默认把现场 WLED 标为 `wled_v2_native_unknown`，登记了固件/配置后才细化。[固定版本映射与缩放](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L490-L545) · [本地解析合同](docs/reference/wled-audio-sync-v2.md)

PCM 的新增 `spectrum16` 按上述对应 Hz 窗从已有 FFT 聚合幅度，按频率宽度对端点加权；低于当前分辨率或高于 Nyquist 的段标为无支持，不把缺测值算成静音。以窗增益修正后的幅度映射到固定 dBFS 显示范围（初始 −60 至 0 dBFS，静音门内归零），标 `pcm_wled16_ref, scale=dbfs_display`。同一纯音应落在对应段或交界邻段，无须与带 AGC 的麦克风逐字节一致。主频用门限以上的最强非 DC 谱峰估计 Hz，混频/低信噪比时允许缺省。PCM 的主频强度用明确归一化单位，不能和 WLED magnitude 做幅值比较。

兼容陷阱在 `AudioFeatures.__post_init__`：只要传入 spectrum 就会重算 bass/mid/treble，loudness 覆盖 rms，peak 覆盖 beat；缺省 spectrum 被填成 16 个零。应在适配层显式选择 legacy 三段来源，例如可选 `band_semantics=from_spectrum/native_pcm`，缺省维持旧构造行为；PCM 工厂一次构造完整对象，避免构造后改别名。旧灯效对不具备 16 段的输入仍读原值。新增 PCM 谱可能激活原来始终为零的颜色源，需以实际 cue 比对并在托管模式启用；原 CLI 离线输出保持可复现。切源只清对应 reader、谱差、阈值、节拍/趋势历史和未消费事件。平滑值仅供展示/渲染，不能送回节拍检测器制造第二次起音。[模型](light_engine/models.py) · [既有 PCM 边界测试](tests/test_audio_state_regressions.py) · [Show 音频调制](light_engine/show/audio_modulation.py)

### 5.2 Host 与当前 Engine 的运行时合同

托管路径只有一个 Engine 子进程句柄。沿用 stdin/stdout 管道、stdout 日志排空和启动就绪标记；Host 不另起节目/手动/音乐 writer。输出生命周期内更换内容不调用 _begin_run_session 或 _shutdown。Host 的 mpv 会话代际继续隔离播放事件。旧连接的回复不能用于新实例。

| 方向 | 最少数据 | 确认、取消和恢复 |
|---|---|---|
| Host → Engine，configure | `n, video_generation, seek_generation, role, role_on_video_end, role_args, mode, digital_target`。role 取 show/music/manual/none；role_args 是经 Host 校验的节目、手动目标或音乐配置。mode 只传 auto/mic。定向流引用带 PA 代际、sink 和身份指纹。 | 整份期望配置按序替换，同号幂等。仅源改变且角色和媒体代际相同，保留活动角色；只换角色且音源继续时不重开流。off 优先撤销在途配置；只有更新的显式允许点亮操作能解除 off。 |
| Engine → Host，status | `n, role_phase, effective_role, source_phase, effective_source, reason, quality, first_frame_seq?`；role_phase 取 preparing/applied/idle/fault，source_phase 取 waiting/preparing/applied/fault。 | 启动 ready、候选首帧可用、本机向全部启用节点提交完成与实灯显光分别记录。角色可用基础帧生效，音源仍在等待。节目定格时新源可准备，首个消费它的帧之后才报告来源 applied。没有启用节点或输出不健康时不可报告设备成功。 |
| 取消/故障 | Host 只采纳当前句柄、匹配请求与媒体代际的报告；超时先查实态，同号重送或显示故障。 | 角色交接不关闭控制管道。新进程只用于冷启动、实际停止后的启用或确认旧 writer 死亡后的恢复；跨进程死亡按故障验收。 |

独立音乐使用单调时钟产生灯帧。若用户让正在播的视频音轨驱动独立或手动效果，文件窗仍需 **mpv 的当前媒体位置**；复用只读 mpv IPC 取位置或复用确认过的 mpv 流，不能把音乐效果运行秒数当作文件位置。节目暂停后该数字目标失活，手机和麦克风仍按实时钟工作。生产时间线的 pause/seek/EOF、管道命令和输入准备回调要在帧边界排好顺序，先清废弃来源再交付事件。无 PCM、FFT 数组或整帧灯光经 Host/Kiosk 转发。

托管模式的 ready 表示基础渲染和输出已就绪。缺少 WLED、未获 PCM 首窗、还没有手机等情况单独报告输入等待/故障；不能沿用旧 CLI 将可恢复的输入错误升级为整场播放启动失败。候选 Show 或首帧校验失败时按第 4.2 节保留仍合法的旧内容；全局映射/输出初始化或发送故障才升级为输出端失败。

### 5.3 局域网右屏的最小控制接口

**一个 Host、一个网页、一个设备授权。** 每台 RK3588 为自己的独立右屏签发一个高熵随机设备会话。安装或更换时，在本机受信安装流程产生一次性短时登记码，右屏经同源 HTTPS 提交到 `POST /control/enroll`；Host 核验并原子保存设备会话散列，用 host-only、Secure、HttpOnly、SameSite=Strict 的持久 cookie 交付凭据。限制登记尝试、到期失效；更换右屏/撤销时使旧散列和未决确认失效。正常重启沿用本舱已授权设备；恢复出厂或独立初始化重新产生证书/配对材料，禁止复制有有效凭据的整机镜像。没有人员账户、员工密码、角色或跨舱后台。日常所有使用右屏的人都能执行下表全部操作；忘记设备需点一次二次确认。

新路由随现有 FastAPI 注册在静态挂载之前，采用窄前缀 `/control`，共用现有成功/错误 envelope 与前端请求封装。除受限登记外，**包括读取状态、发现列表和配对数字**在内都验证设备会话。变更用 POST/PUT/DELETE，校验精确 HTTPS Origin、同源请求及 CSRF 防护；不继承允许任意源的 CORS 配置。公开 JS/日志/URL 中不能出现登记码、会话秘密或 PIN。可复用 Host 的 TLS 能力，但现有配置默认关闭，须真实右屏验证证书链、主机名及浏览器 cookie。需兼容旧 HTTP 客户端时用部署侧 HTTPS 入口，后端限 loopback 或隔离的受信入口；不得接受客户端自报可信代理身份。

**兼容面与整机控制边界。** V1 的匿名 REST、匿名申请 WS ticket、冻结的事件目录和 APP 操作继续在受信的兼容接入路径工作。旧票据或 APP 配对码不能换取右屏权限。不能简单把原 `:8443` 匿名播放/灯光/场景端口同时暴露给任意局域网客户端，否则仍可绕开右屏操作灯带和节目。部署按实际网络设置入口：普通控制局域网只发布受信 HTTPS；在此入口，对既有 V1 控制、票据与 WS 也按右屏会话放行，保留其 URL、请求体和响应结构。确有旧 APP 的设备保留**网络隔离的兼容入口**（例如隔离网段与接入策略），只可访问原 V1/WS，不代理新管理接口；防火墙封住绕行的后端口。独立终端上仅信任 IP、页面可见性或局域网密码都不足以授予设备管理。逐条审查 scenes/apply、lights/effects、audio/set、playback/reset、认证/票据及静态页面：旧命令只改变各自原有控制对象，不能创建蓝牙连接、指定手机、改变分析偏好或答配对码。若站点无法提供隔离的旧入口，就不能在该网段开放匿名兼容服务；列为部署条件，不修改 V1 冻结定义。[Host 应用与 CORS](host_services/main.py) · [现有依赖](host_services/deps.py) · [V1 冻结断言](tests/test_app_host_api_v1_freeze.py)

**读实态，不建事件平台。** 主页面保留既有播放进度查询；整合音量读取，避免同页重复查询。新增 `GET /control/state` 返回同一份受保护快照；主页面可见时约 2 s，一次配对/连接或切源正在进行时约 1 s，提交后和页面重新可见时立即取一次，单飞请求，失联退避。这是对 Host 已缓存事实的读取，不按浏览器刷新率扫描 BlueZ 或逐次查询 PA。D-Bus、PA 和子进程 ACK 在后台异步改变这份快照。配对挑战一直保留到答复、取消或到期，切源和连接的结果保留到下一次同对象操作/合理时限，页面可恢复读取。失联时标“状态待刷新”，旧列表不能用来答挑战。V1 客户端仍可订阅原 WS；不向旧 WS 传设备清单或确认数字。

例如，A 占用扬声器、B 正在等待、灯光跟随环境时，主页面读取以下业务字段。设备 ID 是 Host 分配的本舱标识。

```json
{
  "video":{"state":"playing","volume":0.45,"user_muted":false},
  "speaker":{"kind":"phone","device":"a","status":"routed","waiting_for":null},
  "lighting":{"intent":"follow","intent_token":"l17","effective_role":"show","phase":"applied","brightness":0.6},
  "analysis":{"mode":"mic","target":"wled","effective":"wled","phase":"applied","quality":"fresh","reason":null},
  "bluetooth":{"available":true,"connected_count":2,"limit":2,"adding":false,
    "devices":[
      {"id":"a","name":"手机 A","paired":true,"connected":true,"activity":"transmitting","role":"speaker"},
      {"id":"b","name":"手机 B","paired":true,"connected":true,"activity":"transmitting","role":"waiting"}
    ],"pending":null,"challenge":null}
}
```

| 用户操作/可用条件 | 调用和动作 | 完成时页面显示什么 |
|---|---|---|
| 查看/刷新 | GET /control/state；失联重连重新核验 cookie。主页面及播放控制区显示扬声器、灯光状态和分析来源；设备页显示适配器、连接数、绑定和发现项。 | 开始播放按钮旁保留现行灯光提示，播放中亦可访问。失联标「状态待刷新」；普通页面不展示 PA 索引/PID 等工程字段。 |
| 选灯光分析来源 | PUT /control/analysis，`{"mode":"auto"}` 或 `{"mode":"mic"}`。旧 device 输入是 auto 的兼容别名。两枚来源按钮为「设备音频（自动跟随）」「环境麦克风」。 | 以规范 mode 标示选中值，另列实际手机名、节目音轨、麦克风或等待/异常。切换来源不会唤醒已关灯带、清除手动效果或把亮度调高。 |
| 选择独立音乐、关灯、恢复随播放 | PUT /control/lighting，例如 `{"intent":"follow","if_intent":"l17"}`，亦可 music/off。手动效果沿用原入口；Host 保存 manual 的逐灯带目标。if_intent 来自快照，校验会恢复/替换灯光意图的操作。 | 受理后显示「正在恢复」；有活动内容以角色首帧 applied 确认，idle 时确认「已随播放，等待节目或音乐」。失败展示实际状态及重试入口。 |
| 打开设备页、搜索、添加设备 | POST /control/bluetooth/scan 开启有期限的 discovery；POST /control/bluetooth/add 开一次限时窗（先试 60 s）并搜索；DELETE /control/bluetooth/add 提前结束。满额可查看/扫描，添加需先释放名额。 | 从 Adapter1 的属性和本客户端持有的发现会话更新名单。重复点击沿用当前窗口；到期收回自有可发现/可配对状态、释放扫描，不影响已绑定设备正常重连。 |
| 发起配对/取消 | POST /control/bluetooth/devices/{id}/pair，在窗内预留名额并异步 Device1.Pair；POST /control/bluetooth/pair/cancel 绑定当前配对尝试标识。 | 显示正在配对、待确认、手机取消、失败或已配对。成功要求配对事实 Paired=true；连接、传输、可听另行判断。 |
| 入站授权/六位比对/PIN | POST /control/bluetooth/answer，带当前 challenge、设备 id 和 accept/reject，真正需要输入时附 PIN/passkey。一次只处理一个配对交互。 | 显示真实蓝牙设备名称与请求类型，数字作为字符串保留前导零。答复后继续等待 BlueZ。过期挑战关闭，重复应答、不同设备或重启前的应答均不能生效。 |
| 连接/断开/忘记 | POST /control/bluetooth/devices/{id}/connect 或 /disconnect；DELETE /control/bluetooth/devices/{id}。先校验名额、设备及当前动作。忘记当前赢家先退路再断连并 RemoveDevice。 | 已连接按 Connected；断开待实际连接及路由均释放；忘记待绑定消失。部分失败如“已断开，忘记失败”保留可重试结果。满额显示“已连接 2 台，请先断开一台”。 |
| 指定播放者 | PUT /control/speaker，`{"device":"b"}`；null 取消待播保留、回自动。可指定**任何已接纳且仍连接**的手机，即使它还没有 PA source；不可指定历史离线项。 | 有活动待路由确认；无活动显示“等待手机 B 播放”，扬声器行继续显示真实节目或无声。另一部手机标示传输中/等待。 |
| 播放/暂停/继续/退出、拖进度、节目音量及总亮度 | 右屏开始用 POST /control/play（与旧 V1 play 共用播放核心，保留亮度和手动覆盖）；其余复用 V1 pause/resume/stop/seek、audio/set、brightness/set。拖动释放仅提交一次 seek。 | 用媒体位置及 Host 回读刷新。手机获选时展示“手机音量请在手机上调”，节目滑块标明只改变节目原声及恢复后的数值。日常操作无需人员登录。 |

**下一位使用者的恢复路径。** 主屏及播放控制区按 Host 的真实意图显示下表提示。右屏启动节目只发 /control/play，不附带 follow。提示常驻，不用阻塞播放的弹窗或定时消失的通知。

| Host 快照 | 使用者看到的状态和动作 | 点按之后 |
|---|---|---|
| off | 「灯光已关闭，播放节目仍保持关闭」　**恢复随播放** | 一次显式 follow，只改变灯光意图。正在播且未过 Show 末尾时在**当前进度**恢复，无视频但手机在播则选独立音乐，否则等待下次播放。 |
| manual 或 music | 「手动灯效：〈名称/手动设置〉」或「独立音乐灯效」　**恢复随播放** | 解除覆盖，按第 4.2 节优先表选画面。保留视频状态、手机赢家、节目音量、分析来源和亮度。 |
| 已随播放，或恢复后亮度仍为 0 | 「随播放 · 亮度为 0」　**调整亮度** | 打开已有亮度滑块，由用户明确设值。off 且亮度为 0 时先提供恢复，再提示调亮；修改 off 状态下的亮度不自动开灯。 |
| 正在恢复、关灯确认中、失联或输出异常 | 显示具体等待/故障，联网后重取快照 | 不重复投递缓存的“恢复”。关灯意图已保存但硬件状态未知时分别显示，不将网络故障描述为用户已关灯。 |

意图和手动目标原子保存。intent_token 只用于灯光意图的并发校验；真实意图变化、关灯重申或 Host 换代使旧 token 失效，普通轮询和选源不会改变它。右屏按快照提交恢复，Host 串行校验，过期返回 409 并刷新；须重新点按，不自动重试成一次开灯。重复同一已完成设置可返回实态。主动关灯优先，即使旧界面发起也可再次关灯；若保存失败，仍请求安全熄灯，显示「关闭已请求，设置保存失败」，不把跨重启保存报成成功。正常重启、闲置、重新配对、刷新和下一个影片均不复位。无需识别用户身份或新增访客会话。

**最少的异步标识。** 简单设置返回 200 和已保存的值；设备命令提交给 D-Bus 后返回 202 与当前动作，回调核查目标属性后才转为成功。Host 为单个配对尝试及每个互斥的设备操作保留一个短期 attempt 标识、目标、动作、状态、期限及错误；同目标同动作重试合并，冲突为 409。快照按设备展示当前或最近结果；无全局任务表。同次配对可能发生不同 Agent 回调，故每个**要求回答**的回调生成一次随机 challenge，绑定控制屏授权、attempt、设备、类型和到期时刻。Cancel、Release、设备断开、授权撤销或 BlueZ owner 改变，立即作废对应回调。Host 重启旧 attempt 失效，再读实际 Paired/Connected。模式和亮度不使用蓝牙 attempt；灯光意图专用 token 只保护显式意图变更；单一右屏顺序发送设置，最后一条意图由子进程配置编号确认。HTTP 401/403 表示设备授权失效/请求来源不符，404 表示设备消失，409 表示满额或冲突，410 表示过期确认，503 表示适配器/路由不可用；响应带稳定错误码、可读原因和已有 request_id。

**BlueZ Agent。** 主选在 Host 的长寿命 system-bus 连接上注册唯一 KeyboardDisplay Agent、请求默认 Agent，处理入站与主动 Pair。核实 A2DP/必要控制 profile UUID。分别实现 Request/DisplayPinCode、Request/DisplayPasskey、RequestConfirmation、RequestAuthorization、AuthorizeService、Cancel、Release；显示型回调只呈现，输入/确认型异步等待真实手指操作。Just Works 只呈现实际授权，不能补造比对码。无可拒绝授权回调的入站组合，只允许用户在右屏选中设备后发起配对；在这种组合上“添加设备”执行搜索和出站 Pair，保持入站 Pairable 关闭，界面说明需在右屏选择手机。异步 D-Bus 库以 Linux 条件依赖接入现有 3.11 锁文件；若系统限制默认 Agent 权限，优先最窄 D-Bus 策略，仍需特权则仅将回调交给已改造的系统代理转发，同一时刻只注册一个策略所有者。H4 必须覆盖特权、真实手机、认证超时以及旧自动同意服务关停。[Agent1](https://bluez.readthedocs.io/en/latest/agent-api/) · [现有配对服务](scripts/deploy/rk3588/bluetooth-auto-agent.py)

**删减取舍。** 使用现有 Host 路由组、设备 cookie 和受保护的状态查询，去掉独立 Kiosk 平台、全量 SSE、事件回放、全局 revision、通用幂等键、操作队列 API、细粒度人员权限与周期性凭据轮换系统。将重复配对、晚到确认和快速切源分别交给按设备互斥、一次性 challenge 和 Engine 配置编号处理。断流后查快照即可得到仍待处理的挑战和真实结果；H4、用例 5 和用例 6 证明页面刷新/两标签操作不会误确认或漏报完成。

## 6. 完整实施计划

### 6.1 阶段、依赖、文件与交付条件

#### A–G 实施状态（2026-11-25，本地工作树）

“已完成”仅标在有可复查结果的子项上。下表中的软件结果来自当前工作树或明确注明的既有基线。H1–H6 的现场记录仍为空，生产切换未执行。

| 工作包 | 已完成的子项与证据 | 阶段尚缺的证据或工作 |
|---|---|---|
| A · 部分完成 | **已完成：本地媒体基线、RGB+CCT 越界修复。** 已复现蓝色通道 1.0128523921568626；在进入颜色转换前按峰值限幅并保留色比，原媒体融合测试 6 项通过。真实素材核查见第 2.1 节。[修复](light_engine/effects/video_audio_fusion.py) · [回归](tests/test_media_fusion_quality.py) | 隔离镜像、控制器、真实声路和屏幕的 H1–H4 证据待采集。 |
| B · 软件基准已完成 | **已完成：托管 PCM 的 WLED 参考频段、主频、代际和事件门控；标注点击轨的 BPM、相位与事件匹配。** 纯音增益、双音分离、交界带、反相、静音/噪声和旧 CLI 的三段/空谱语义分别有断言。两种采样率的数值见表后。[频谱测试](tests/test_analysis.py) · [点击轨与事件测试](tests/test_managed_audio_input.py) · [弱鼓点与噪声回归](tests/test_audio_state_regressions.py) | 此标注仅覆盖软件信号基准。真实歌曲感知质量、WLED AGC 与手机时间延迟分别在 H3/H5/H6 评估，逐拍置信度继续以缺省表示尚未校准。 |
| C · 部分完成 | **已完成：模拟后端下的名额预留、先播者保持、暂停交接、空闲手机待播以及单路先关后开。** 已接入 Agent1、PA 模块与 sink-input 回读；回读失败不确认获选。[播放权回归](tests/test_audio_routing.py) · [配对回归](tests/test_bluez_pairing.py) · [Agent 合同](tests/test_bluez_agent_contract.py) | 目前观察超额连接并断开新来者属于恢复路径；**尚未证明第三条实际连接建立前便被拒绝**。H2 需在 Host 重启、历史手机自动回连与并发接入时记录 HCI 峰值。Agent 注册、上电重连和真实路由需 H2–H4。 |
| D · 部分完成 | **已完成：托管文件、定向 PCM 与指定发端 WLED 输入；更新编号、陈旧数据隔离、采集错误退避。** 50 ms 窗与 25 ms 步长、旧窗事件不重放已有针对性测试。[输入适配](light_engine/analysis/managed_audio_input.py) · [采集测试](tests/test_parec_capture.py) | H3/H5 需确认两个手机的数字流隔离、断连/移动时重新绑定、采集对播放判据的影响和端到端时延。 |
| E · 部分完成 | **已完成：同一发送循环的角色交接、模拟 mpv 时钟下的实际节目片尾回归、部分发送故障的逐节点安全尝试。** 原始 YAML 下测 304.9 s 已渲染后越过终点、从 305.0/305.3 s 或媒体 EOF 进入、无接班时安全黑。内存输出断言序号连续、正常换角色不发安全帧。Linux 生产 socket 使用内核互斥。[交接和片尾测试](tests/test_managed_renderer.py) · [DDP 发送端](light_engine/outputs/ddp_output.py) | 真 mpv 事件先后顺序、Linux 并发进程互斥、实灯最大暗隙、硬杀后的本地灯态及长稳仍需验证。 |
| F · 部分完成 | **已完成：设备登记/撤销、持久意图与过期恢复拒绝、快照超龄禁写、待播与路由实态分开、挑战逐项确认与前导零保留。** 本地无头 Edge 已用测试快照核对恢复随播放、选择 mic、展示 004281 和拒绝操作；新增前端状态规则另以 Node 测试验证。V1 冻结合同独立回归。[控制 API](tests/test_control_api.py) · [设备偏好](tests/test_control_terminal.py) · [右屏状态测试](kiosk/test/audio-controls.test.js) | H4 需验证真实右屏证书、控制网隔离、换屏、跨舱凭据、配对和普通使用者全流程。浏览器多标签并发与真实掉线恢复仍需联调。 |
| G · 待迁移 | **已完成：Linux 条件依赖锁定、旧安装入口防冲突检查、只读预检及隔离验证说明。** [预检](scripts/deploy/rk3588/check-managed-audio.sh) · [部署说明](docs/current/rk3588-bootstrap.md) | 幂等迁移、回滚演练、两次安装、冷启动、整机 H1–H6 **未完成**。现场通过并获得生产部署授权前，保留原生产策略。 |

**B 的数值证据。** 对 44.1 kHz、48 kHz 的文件各制作 60、90、120、180 BPM 标注点击轨，25 ms 取窗步长。原实现会从 180 BPM 剔除偏短的量化间隔，测得 171.43 BPM。受管估计器保留一个取样周期内的边界间隔，再对一致的间隔求均值。8 组回归均通过（10.49 s）；两种采样率下四档的稳态中位数分别为 60.00、90.08、120.00、180.00 BPM。暖机后匹配区间内无漏检或多检，最大事件误差 16.67 ms，锁定后的相位环形误差中位数最大 0.025 周期。1120 Hz 交界音在第 7、8 段（从 0 计）响应；83 Hz 与 3000 Hz 等幅混合时，原 PCM 低/高两段功率占比各约 0.50。这些是输入文件的算法观测，声光端到端时延需另测。

**分支 `1125-full-update` 的子项闭环。** 以下子项以 `1d84695` 上的增量验证为依据。H1–H6 仍待隔离机实测。

- **C 已完成 PA 恢复的软件回归。** PA 订阅中断后带退避重建。己方路由消失或归属不明时保持原声门控。策略恢复后先核对拥有者和有效流，再接管遗留路由或建立新路。已核对路由消失且手机明确暂停时解除临时门控，避免 PA 重启后节目长期无声。[路由与订阅测试](tests/test_audio_routing.py) · [协调器恢复测试](tests/test_bluez_pairing.py)
- **D 已完成热切源过渡的本地验证。** 新来源的连续渲染量在 150 ms 内渐入，原始观测继续供分析和诊断，首窗不重放旧节拍。源切换测试检查起点、中点、终点和实际静音标志。[热切源回归](tests/test_managed_audio_input.py)
- **E 已完成候选撤销、发送故障和真实父子管道的软件验证。** 过期候选不能覆盖已提交帧，注入 DDP 部分发送失败后不能发出成功确认。此前的 DDP 故障夹具缺少 `mpv_socket`，修正后确实走到了发送故障分支。真实 Host 父进程与 Engine 子进程经管道切换音乐／手动角色，使用内存 DDP 验证同一进程内的帧序号递进，最终正常退出。[交接测试](tests/test_managed_renderer.py) · [父子进程测试](tests/test_managed_adapter.py)
- **E/F 已完成播放器和灯光错误的状态分离。** 管道故障发生在 mpv 已暂停之后时，播放接口保留实际暂停结果，右屏另显示灯光故障。Host 恢复已保存的关灯意图时重新向已启用 WLED 节点写入并回读，失败后重试，确认后避免反复写入。相关软件行为采用替身验证。[Host 合同测试](tests/test_control_api.py)

最终定向组合覆盖上述 Host、Engine、蓝牙闭环和 V1 兼容面，共 104 项通过，30.86 秒，返回码 0。实机阶段需检查 PA 重启、HCI 第三台接入峰值、证书与触屏、DDP 断流及实灯交接。

完整软件回归共 1783 项通过，1 项因 Windows 目录符号链接不可用而跳过，523.85 秒，返回码 0。完整回归启动后补充了 PA 恢复时的显式停止、已验证模块接管和控制终端夹具校验。这些最终改动分别由上述 104 项定向组合和最后的 6 项控制终端／父子进程复跑覆盖。

A–G 是设计审查后的工作分解。第 8 节的设计反例未关闭时只修订方案，不启动开发。与实现无关的现场事实可在另行授权后先行取证。阶段获准后，Windows 用仓库解释器，开发阶段先做针对性测试及 fast，集成后跑 production，跨层发布前跑 full、Kiosk 测试与构建。软件测试注入 D-Bus/PA、媒体时钟和输出端。涉及接纳、实际路由、扬声器、DDP 和浏览器授权的验收还需要现场记录。

| 工作包 | 实施范围与接口 | 退出条件 |
|---|---|---|
| **A　冻结对照，先做风险实验** | 记录当前镜像、服务、影片 SHA 和初始声路。用第 2 节实际素材、原始 YAML、静音轨及已有 `scripts/authoring/prepare_show_audio.py` 建立对照。相同生产软件版本的隔离验证机做 H1–H4，批准前生产机只观测。 | 输出 HCI/BlueZ/PA 轨迹、两个活动手机与第三台自动重连记录、右屏证书与 Agent 可达性、单路与 PCM 隔离报告；失败项有复现和替代验证，不以历史硬件记录放行。颜色越界用 `tests/test_media_fusion_quality.py` 单列，获准后在 `light_engine/effects/video_audio_fusion.py` 修正分区增益边界并原样回归，保留颜色校验。 |
| **B　统一特征与时钟**，可与 C 并行 | 改 `light_engine/models.py`、`light_engine/analysis/audio.py`、`music_control.py`，完成第 5.1 节的能力标记、16 段映射、时间域、静音门及节拍去重。保留旧三段和离线优先级。 | `tests/test_audio_state_regressions.py`、`test_music_control.py`、`test_wled_audio_sync.py` 增加两种采样率、双音、反相 stereo、起音/交界带、渐强弱、重复窗、静音、噪声和标注点击轨。量化 BPM/相位及置信度；不跨源产生旧拍点。 |
| **C　连接准入、扬声器和配对**，在开发机可先做 | 新增 `host_services/bluetooth.py` 负责 ObjectManager、槽位、Agent 与设备待决动作，`host_services/audio_routing.py` 负责 PA 快照、候选及唯一可听路。复用 `scripts/deploy/rk3588/audio_output.py` 的 RT5616 识别；改 `host_services/engine_adapter.py` 的 audio_set、scene_apply、mpv 初始化和读回。Host 保存偏好，路由仲裁不等待 Engine。单调定时器、耗时 D-Bus/PA 操作异步化，快照读取不能堵塞 ASGI。 | 新增 `tests/test_audio_routing.py`、`test_bluez_pairing.py`。覆盖并发预留/去重/释放、历史三台、入站与自动重连、A→B 自动/手动交接、无活动手选、故障回滚、PA index 复用、断连与迟到回调、门控中改变主动静音。断言全过程 ≤1 条手机可听路；第三条物理连接的上限由 H2 验证。 |
| **D　同一个选择器和数字捕获**，依赖 B 与 C 的流引用合同 | 新增 `light_engine/analysis/source_selector.py`、`pulse_capture.py`，改 `engine/__init__.py`、`analysis/wled_audio_sync.py`、`cli/__init__.py`（均在 light_engine 下），必要的配置校验及 `config/system.yaml`、`config/profiles/rk3588-host-service.yaml`。开发受管模式、独立单调时钟、WLED 发端校验、非阻塞采集与 bounded buffer、APPLIED/health。旧文件 CLI 和原合成测试显式路径继续可用。 | `tests/test_engine_wled_audio_source.py`、`test_engine_music_control_state.py`、`test_clock_integration.py` 覆盖 no_media、stale、合法零包、同一音源恢复、仅错包、短读、快速切换、暂停定格与实时输入、合成默认隔离。数字故障即使有新鲜 mic 也不产生 WLED 特征。 |
| **E　托管 Engine 单一发送端与角色交接**，合入 C/D | 在 `light_engine/engine/__init__.py` 分开内容准备/释放与输出打开/关闭，在 `light_engine/cli/__init__.py` 接入托管入口。复用 `light_engine/outputs/__init__.py` 的最新完整帧队列、变换、映射和 `ddp_output.py`。改 `host_services/real_engine_adapter.py` 的 start/manual/resume/seek/stop/process_failure 和 `host_services/engine_adapter.py` 的 play/pause/EOF/watchdog/scene/brightness；`wled_brightness.py` 的收尾仅在安全终止路径执行并返回实际错误。Host 将角色、源及失去视频后的接班角色合并为一份配置。 | `tests/test_host_real_engine_adapter.py`、`test_host_playback_contracts.py`、`test_host_runtime_lifecycle.py` 及受管引擎测试实现第 6.3 节的全部交接反例。核对 PID、输出打开次数、每节点完整帧、单次变换与响应。304.9/305.0/305.3 s 分别测有接班、无接班、已过 Show 终点再进入；旧 CLI 退出安全黑及节目中途故障测试继续保留。 |
| **F　局域网右屏上线前的软件联调**，页面可先用样例快照，完成依赖 C–E | 在 `host_services/main.py` 注册 `host_services/routers/control.py`；在 `host_services/deps.py` 增加专用于受保护路由的设备校验；登记存储按实例复用用户配置目录。新增极薄的右屏 play 入口，复用已有播放核心。改 `kiosk/src/api.js`、`App.vue`、`composables/useVolume.js`、`usePlayback.js`、`components/VolumeSlider.vue`、`PlaybackBar.vue`；合并来源控件，增加常驻灯光状态、一键恢复和亮度为零提示；蓝牙面板和播放页共用状态快照。构建并检查 Host 真正提供的 `kiosk/dist`。 | 新增 `tests/test_control_api.py`、扩展 `kiosk/test/api.test.js` 及浏览器触摸测试；覆盖旧票据拒绝、设备替换、旧 device 归一为 auto、显式恢复与过期恢复被拒、上一位关灯后下一位开始播放、输入 PIN、满额、指定空闲设备、连续点击、异步拒绝、断网刷新、页面回前台。保留 `tests/test_app_host_api_v1_freeze.py`、`test_host_static_ui.py` 和 V1 play/reset 亮度断言。 |
| **G　迁移与整机验收**，依赖 H2/H3 的路由结论、H4 和 A–F | 改 `scripts/deploy/rk3588/setup-bluetooth.sh`、`install-services.sh`、`setup-system.sh`、`setup-python.sh`、`audio_output.py`、`verify-install.sh`、`systemd/user/light-belt-host.service`；补入设备 HTTPS 入口、实例化授权材料和隔离的兼容接入。核对 `pyproject.toml → uv.lock → host_services/requirements.txt` 在 aarch64 可安装。运行配置仍从原模板生成。 | 已通过的软硬件组合按下述互斥迁移。`tests/test_rk3588_bluetooth_deployment.py` 加旧配置升级、幂等、失败回滚，保留防重音回归；更新 `docs/current/rk3588-bootstrap.md` 和受保护控制接口说明。实机完成 H1–H6、六组验收、两次安装、冷启动与换屏。 |

**生产变更顺序。** H2/H3 在隔离的测试镜像上修改路由参数；生产设备在结果通过前保持已有优先级服务、PA 模块与初始化。迁移先备份实际启用状态、PA 配置和已绑定设备资料，停节目并关临时配对窗。观察者先只读比对；维护窗口停旧 writer、确认被标记的 mute 与有效 loopback 归属，再在原模块配置上设置 `a2dp_source=false`，确认自动路已退出，再启用新 writer。H4 通过后停旧公共模式和 NoInputNoOutput Agent，核对默认 Agent 唯一，再开放受保护管理。对照实际安装路径处理 `light-belt-bluetooth-priority.service`、`bluetooth-public-mode.service`、`bluetooth-auto-agent.service` 和旧启动链接；新所有者通过冷启动及回滚演练后才清退废弃实现。保留原 RT5616、默认 sink、图形会话、凭据、健康检查及历史配对。回滚时先隔离新管理入口、关闭新建路并确认已清，再恢复已记录的旧配置和服务；旧公开配对策略只在原部署边界内恢复。恢复后实际播放一部手机验证单路、原声恢复与无重音。不得在同一个可听 sink 上并行试跑两种策略。

### 6.2 最小实机实验与分支决策

实验均由后续获准的工程人员在目标 NanoPC-T6-LTS 上执行。命令中出现的设备、monitor 和 index 必须从当次快照取值。记录版本、手机型号/OS、profile、codec、音频材料、路由图和统一单调时间。验收结束后关闭临时发现、录音和测试路由。

| 实验 | 步骤与记录 | 预期观察 → 不满足时的决定 |
|---|---|---|
| **H1　硬件与镜像盘点** | pi 图形会话执行 `bluetoothctl list`、`bluetoothctl show`、`bluetoothctl --version`、`rfkill list`、`lsusb -t`、`pactl info`、`pactl list cards`、`pactl list sinks`、`pactl list short modules`；记录控制器/驱动/固件、是否 USB 或板载扩展、RT5616 profile、插口、默认 sink、mpv 实际 sink。用 `ffprobe -show_streams -show_format` 核对部署节目及边车。 | 识别真实硬件、A2DP 能力、原生 PA 和有声输出。板号不能推断实际蓝牙模块或并发数量。若环境实为 PipeWire、无适配器/输入专用 profile/未插线，则先修复或单列镜像适配，不能给出当前方案通过结论。[T6-LTS 厂商原理图](https://wiki.friendlyelec.com/wiki/images/4/44/NanoPC-T6_LTS_2310_SCH.pdf) |
| **H2　两个连接名额、赢家及独占回放** | 在隔离 NanoPC 上同步记录 `btmon` 的连接建立/断开、`busctl monitor org.bluez`、`pactl subscribe`、sources/modules/sink-inputs 及单调时钟。A、B 分别、同时连接并播不同音（交换先后）；测试 A 暂停/断连交给 B、A 恢复、手选活动 B 和空闲 B、切歌、静音段、长缓冲；第三部已配对 C 在满额时主动连接、自动重连、冷启动三机齐连、两台同时争最后一席。先保留旧镜像基线，再验证隔离镜像 `a2dp_source=false` 后候选 source/transport 可见且在开路前可判，杀 Host 核对孤儿路。 | A/B 均能同时连接，三台历史绑定保留，任意时刻接纳且实际连接 ≤2；满额不踢 A/B。记录 HCI 峰值、profile、每部手机的活动证据和可听赢家；不能用每秒轮询证明无瞬时第三链路。仅一台可听、B 不抢占、关路确认后才开路。验证两台稳定连接但仅一路 transport 时能否识别 B 的待播并自动交接；缺候选证据或双机连接不成立则验收失败。若必须先有消费者才暴露活动，试隔离至非物理 sink、仅赢家接 RT5616，证明流出生即隔离，再重跑 H2/H3。 |
| **H3　定向 PCM 和实际音量影响** | 令手机 A 播 440 Hz、B 播 880 Hz、节目播另一已知频率。分别短时录指定手机 source、其目标 sink-input 和 RT5616 总 monitor。示例 `timeout 8s parec --raw --format=s16le --rate=48000 --channels=2 --device="$MONITOR" --monitor-stream="$INPUT" > /tmp/lb-selected.s16`。对三路按频谱/互相关比较，逐项改变手机音量、mpv 音量/静音，插入系统提示音，暂停后分别开/关录音，换 sink、重建流再试。 | 定向流只含目标媒体，打开采集不创造额外播放路、不令手机假活跃；回读真实格式、延迟及音量前后关系。若索引失效，必须重新绑定；若定向 monitor 不可用，仅在单源 tap 的隔离、活动无反馈及延迟均通过后采用该 BT 替代；无可用节目 tap 时要求匹配 sidecar。总混音不能冒充设备音频。 |
| **H4　真实配对与独立 LAN 右屏** | 在测试设备上保存原代理状态，停旧自动同意/公共服务，验证唯一 KeyboardDisplay Agent 的权限。两类手机各试右屏/手机发起、比对、PIN、Just Works、拒绝、超时、取消、配对时网络中断、两标签答不同设备、无名额与窗外入站。用实际右屏浏览器通过 HTTPS 操作；另用未授权 LAN 终端核对新接口、旧 HTTP/WS 入口和代理边界。两台舱用同一软件独立初始化，撤销/换屏、重启、验证旧屏和另一舱 cookie 失效。 | 用户日常无需登录便可完成全部操作；状态吻合 BlueZ，窗外不产生新绑定，既有手机可在有名额时重连。未授权终端看不到名单/PIN、不能管理蓝牙或绕过旧入口发控制命令。真实证书信任、cookie 持久化、回调超时满足触屏流程。无拒绝能力的入站路径按 第 5.3 限定；特权不足时验证唯一窄代理。 |
| **H5　WLED 和实灯时序** | 核对麦克风板标识、固件版本、Audio Reactive 发送开关、组播接口；用 `tcpdump -ni "$IFACE" 'udp port 11988 or udp port 4048'` 对比输入输出。安静、拍手、扫频，保持 DDP 在线只停 Audio Sync，再发送错误包或第二发端。测输入/收包/出帧/灯光变化。 | 合法静音 fresh，最后合法包超龄一次 stale，坏包不续期，恢复不产生旧峰。若板卡帧处理/DDP 与音频发送相互影响，实测其同时工作条件；必要时将已有带麦克风的发送节点与受 DDP 控制的灯节点分开配置，并重新验证网络和负载。 |
| **H6　资源和长稳** | 同节目分别测文件、蓝牙定向和 WLED。记录 PA latency、PCM gaps、队列高水位、子进程数、FD、丢帧与 DDP 发送间隔；用 `pidstat -rud`、`/proc/<pid>/fd`、RSS、温度/降频计数取空载基线、切源高峰和稳态。重复断连、重启 PA/BlueZ、单杀采集与 Engine、Host 正常停启，最后冷启动。 | 测候选准备/释放与 High 10 视频争用下的最大帧间隔及高水位；每次正常换角色保持一个 Engine PID、一个 DDP 发送端、至多一个手机可听路；切换后 reader/FD 回落到对应基线。数据面故障不操作 mpv 播放。资源或抖动超出下述参考值时先定位采集、FFT、效果或传输，再调整窗口/队列。 |

**现场放行条件。** H2 必须在新路由策略下同时验证候选可见性、单路排他以及关掉 Host 后 PA 孤儿路线的恢复/回滚。H3 要在绑定采集后重启 PA、复用旧 index，检查无旧数据串入、无双路放声，并记录 parec 退出状态、协商格式和读入块间隔；首选设备 PCM 不能绑定时阻止新版上线，按 H3 试验替代采集点并重跑。H4 在旧默认 Agent 已停用后，分别尝试数字比较和无数字的配对：前者须有真实回调，后者须为右屏选中设备的一次性主动配对，或有可拒绝的入站授权回调。若系统直接创建新的入站绑定、在绑定前无法取得右屏同意，则对该组合禁用入站配对，只开放右屏选中设备后发起的配对，不得伪造比较码或事后补弹窗。

H2 还应覆盖 Host 缺席的时间窗：两部手机已经连接时重启 Host 或 BlueZ，并在重启前后持续让第三部历史手机尝试回连。受控接纳尚未就绪时不得开放不受限的新连接；仅在进程恢复后清理第三台仍属于上限失败。三台同时启动的试验单独记录接纳顺序和 HCI 连接峰值。

### 6.3 六组交付验收

各组两列都须留证。自动化测试通过只表示对应软件合同成立。右屏只显示业务状态；工程端同时采集 HCI、BlueZ、PA、mpv、Engine 和输出证据。

| 用例 | 软件验收 | 实机验收 |
|---|---|---|
| **1　节目、两部手机与单路扬声器** | 测 A 先播、B 传输等候，A 停→B 接管，A 重播不能抢回。手选 B、空闲 B 等待、取消保留、B 断线，分别断言先关后开、恢复原声或无声。对视频 pause/resume/seek/stop/EOF 断言未向蓝牙发播放/断连命令；反向也无 mpv 播放状态变更。测门控中主动静音、改音量和新 mpv。 | H2/H3 双音加节目音，录总 monitor、定向流及实际扬声器。两台手机同时连接仅一台可听。视频退出后继续听手机；手机随后停播时无节目原声。仅播放视频时音量/主动静音正确。 |
| **2　来源实时切换、停用与恢复** | 同 renderer 对数字→mic→数字、A→B、手机→节目做标记输入，查首帧、旧拍不重放、连续序号。数字策略在手机、节目、无目标、合法零窗和故障上的结果逐一测试；给旧 auto/device 偏好和请求输入同一轨迹，要求相同目标、同一规范读回和仅一个选中控件。即使 mic 健康，使 PCM 退出，断言不替代，恢复原数字源。分别验证源缺席、静音与故障。 | 用节目 112–128 s 段、手机窄带音及近麦拍手核对显光与实际源；保持视频和扬声器连续。让读取器退出、索引失效、再恢复，检查基础灯效、界面及 DDP 间隔，原音频赢家照常播放。 |
| **3　WLED 环境输入** | 注入零包、错包、错 sender、长间隔及恢复，验证 TTL、清历史与单次事件。在节目、独立音乐中都手选 mic，播放手机和切换视频不改变模式。 | H5：拍手、说话、安静，保持 DDP 在线仅停止音频发送。屏幕区分“环境安静”和“麦克风无数据”，蓝牙路由、视频进度不变。 |
| **4　无视频的独立音乐及输出所有权** | 模拟无 mpv 时 A 音乐从连接到发声和响应；暂停节目并保持独立时钟、退出节目音乐灯继续、恢复按原媒体位置。静态手动/亮度 0/显式关闭均不被开播覆盖。固定纯音、混频、点击、反相、噪声，检查第 5.1 节特征。跨 24 h 的模拟时钟无 86,400 s 或合成数据结束。 | 从 idle 冷启动，无视频时手机可带动灯；再开节目、暂停、seek、退出。按下方连续交接专项逐节点采 DDP，并同步测灯光；正常交接过程中持续有且只有一个发送端，旧 off/亮度命令不能清掉新灯光。调整手机音量与灯带亮度，记录真实响光、帧间隔和当前效果。 |
| **5　右屏设备操作、满额与实例隔离** | 为每个触摸动作测受理、状态确认与失败。超过两条历史记录；满额时 C 主动/入站/自动重连和并发 Connect/Pair；预留超时不漏名额。旧确认/旧 cookie、串设备和跨舱授权均拒绝。确认普通 V1 和受保护入口符合各自合同。 | H2/H4：两台同时连接，再让已绑定第三台申请/自动重连；没有强踢。普通使用者经独立 LAN 右屏搜索、配对、确认、连接、指定 A/B、断开、忘记。未登记 LAN 客户端不能读敏感状态/调用管理操作。两舱独立首次授权，换屏后旧凭据失效，无全局账户。 |
| **6　异常、持久化、片尾和长期运行** | 首装 auto→手选 mic→选回设备音频→换节目→手机启停/断开→退出→页面刷新→Host/整机重启；断言仅用户设置改变持久值。分别重启 Host、BlueZ、PA、Engine，重建实态并核对可听赢家及静音；掉线期间快速切源、迟到回调、源准备失败、两标签并发。重跑颜色边界和末尾 seek 的独立回归。 | H6：正常重启与突发掉电、Kiosk 断网刷新和子进程故障后，菜单偏好读回、真实连接数/赢家重新对账、用户 mute 生效，无旧拍点、孤儿路或凭据串舱。上一位关灯/手动后由另一人直接启动视频，灯光持续覆盖；两人均能看懂提示并在原播放进度显式恢复。用实际 MP4 分别测 305 s 有接班的连续帧、无接班的安全帧和媒体 EOF，全片重播及长稳留存资源曲线。 |

#### 连续交接专项

| 反例与取证 | 通过条件 |
|---|---|
| 软件对照：九节点各放可识别的非零哨兵图案 A、B，同固定物理布局。注入慢加载、候选产生首帧后取消、快速 A→B→A、延迟回调，以及候选图中本来就有黑色的区段；同时记录逻辑帧、每个节点 DDP payload、open/close 与 WLED HTTP 调用。 | 正常切换期间 DDP 只打开一次、关闭零次。每个逻辑周期发送全部 A 或全部 B；无无关全黑、无 SAFE_STATE、无 off、无新 socket。正常输入的 B 首帧成功前不报 applied，取消代际不出帧，作者有意设计的黑仍保留。逻辑序号跨切点唯一递进；抓包按每节点和时间窗关联 DDP 的 4 位线序号，允许其正常回绕。 |
| 并发/故障：候选卡住、首帧缺 strip/错误长度、seek 后旧 PTS、丢失 active、准备期间主动关灯、慢发送/第 k 个节点写失败、管道 EOF 或硬杀 writer。 | 活动内容仍合法则持续发送；无法继续且已确认有接班时仅在冻结预算内重发，超时安全结束并报故障。关灯抢占候选，黑后无迟到复亮。部分发送不报提交完成；旧进程未退出/锁未取得，不启动第二个发送端。单独检查安全黑、WLED off、错误提示、节点自身超时回落。 |
| H5/H6 实机：固定非零图案，在暂停↔音乐、手动↔节目、seek/换节目、305 s 有接班 EOF、连续夺回角色等路径各反复切换；另用第 2 节真实素材比对。采集每个启用节点的包、首个新帧、最大包间隔和同步光电/高速录像，记录传感器采样周期和噪声底。 | 每次带接班的正常切换都无额外全黑帧；非零哨兵测点无可分辨的灭灯间隔或非内容导致的亮度下陷。跨节点切换时差单列，DDP 没有跨节点呈现确认；以最差节点/最差一次判断。首次参考目标：30 fps 下正常交接每节点最大间隔 ≤2 帧（约 67 ms），同时低于实测该节点 realtime timeout 并留余量；超界需定位，不能只报 p95。另做无接班 EOF、off、故障黑的阳性对照。 |

分别令首节点、中间节点、末节点写失败，验证普通帧在失败处停止，随后每个启用节点都有独立安全尝试及结果、全局不报 applied。再交换 MediaEnded、Host EOF、配置与首帧到达顺序，覆盖已有接班规则、候选迟到、无接班和同时 off 四条分支；正常接班不得经过 CLI 的关闭路径。

#### 灯光意图与来源的触屏专项

覆盖 off、manual、music、follow × 亮度 0/非零，逐项测试换人后右屏进首页、启动/退出节目、暂停、重播、换手机、切分析源、刷新及重启。保持原意图和亮度，首页及播放控制页均有正确提示；只点「恢复随播放」时对照 Host 命令轨迹，确认没有播放/seek/reset、解除静音或调整亮度请求。有节目在当前位置恢复，有手机无节目则转独立音乐，两者皆无则显示等待；亮度 0 时继续为零。用两页模拟过期恢复/较新 off、保存失败、设备掉线和重连，结果以快照和 writer 实态确认。V1 显式 play/reset 分别按第 7.3 节回归。

**测量先于定标。** 以下是待实测和产品确认的参考目标。统一保存设备版本、原始轨迹及 p50/p95/max，不把这些数作为已获批指标。

- 接管/释放从已确认 transport/player 边沿到实际声道切换计时；总 monitor 对两条标记音做短窗功率比较，给出阈值、窗宽和噪声底（可先用 10 ms 窗和 −40 dBFS 检查重叠）。再用声卡/功放后的录音复核可听漏音。初测明确播放后 300 ms 内接管、明确暂停后 1 s 内恢复；缓冲与无元数据设备单列，不以缩短静音间隙换双音。
- 已就绪来源切换到首个 applied 帧先看 p95 ≤300 ms；30 fps 对应约 33.3 ms/帧，比较相同 cue 基线，切源期 DDP 发送间隔 p95 先看 ≤2 帧，无新增安全黑帧或序号重启。至少重复 100 次；来源切换与角色交接分别记录最差值，交接验收按上述逐节点和光电专项判断。
- 滴答/拍手与实灯时间差用同一采集系统的音频+光电信号，或带音轨的高速摄像校准通道偏差；分别报告数字 tap→灯、扬声器→灯、麦克风→灯，正负号定义为灯晚于声为正。初始观察目标为数字声光绝对差 p95 ≤100 ms，WLED ≤150 ms。测试重点包括时延漂移和最慢手机。
- 在干净标注点击轨的稳态区间先试 BPM 中位误差 ≤3、逐拍匹配容差 ±80 ms，报告 precision/recall 和相位环形误差。静音和纯持音另计假节拍，启动/恢复暖机单列；噪声中输出低置信度比锁定错误 BPM 更符合合同。纯音频段按中心/交界评估，标注带宽和有效信噪比。
- 至少覆盖一次完整节目与重播，再做建议 8 h 稳定性试验。用相同 cue 对比新增 CPU、RSS 和温度，初查稳态增量 CPU < 单核 15%、RSS < 64 MiB（含采集子进程），FD 和环缓冲无持续增长；最终以同机并行渲染的帧预算及实测调整。

## 7. 风险、异常恢复与兼容边界

### 7.1 观察点和恢复动作

| 状况 | 保留什么，如何恢复 | 用户可见的结果 |
|---|---|---|
| 无数字媒体、合法静音、数字捕获停止 | 无活动媒体清数字目标。新鲜零窗保持当前来源。应有数字流而无窗则清过期事件、保持基础灯效，带上限退避重开 reader（如 0.25–5 s），重绑前重读 PA 对象；不操作手机或 mpv。 | 分别显示“没有可分析的设备音频”“设备音频安静”“设备音频采集异常，正在重试”。没有一种情况会自动写入 mic。 |
| WLED 停发、只发错包、第二发端、合法包长期不变 | 用指定发端最后合法包判断 age；非法数据不续期。stale 后清历史，第一恢复窗不与旧谱比较。相同数据可能就是安静或稳定声音，V2 缺发端时钟/序号，诊断可提示拍手验证；重复 peak 受边沿和抑制期约束。 | mic 模式显示等待/无数据或安静，恢复后仍跟 mic。扬声器不变。 |
| 断连、缓冲、两手机竞争 | 明确断连先退旧路再接仍活动的候补；缓冲用可取消 timer 和新快照，合法静音不触发换人。手选设备掉线取消保留；迟到回调按尝试和对象所属服务丢弃。 | 正在播放、传输中等待、等待指定手机开播可区分。证据矛盾显示待确认。 |
| 蓝牙名额错误、蓝牙服务掉线 | 停止新的入站/出站接纳和配对确认。服务恢复时重新订阅、枚举真实绑定/连接，而非从历史列表或落盘赢家恢复名额。核对入站策略后恢复配对/连接。 | 标明适配器不可用、满额或重连中；违规第三条连接独立记为故障，不把 UI 的 2/2 当作合规证据。 |
| PA 崩溃、RT5616 不可用、路由回收失败 | PA server 变化使所有旧 stream/module index 失效。重查音响、source 与实际路，关闭可确认归属的孤儿。未排除双音时保持 mpv 临时门控，不改投 HDMI；确认安全后重选或按偏好恢复节目。 | “音响不可用 / 正在恢复”，避免把数字录音成功当作已出声。 |
| 暂停、seek、自然结束、准备失败或真正发送端故障 | 媒体事件只改变相关内容角色。候选不可用而活动内容有效时继续旧内容；已失去旧内容按冻结上限处理。正常转角色不触发安全终止。关灯、真正无接班或不可恢复输出故障才进入安全收尾。 | 分别展示定格、切换中、切换失败、明确关闭或输出故障；正常交接有额外黑帧即失败。进程恢复前核对互斥锁和旧所有者，不因灯光故障改变手机播放。 |
| Host、Kiosk 或相关服务重启 | Host 恢复偏好、按现有合同进入视频 idle；先查 BlueZ/PA 和存活进程，再接管可证实的唯一手机路或重建。没有可靠赢家时按当前活动重新裁决。页面刷新重新取状态，Host/BlueZ 重启使旧挑战失效；换屏还会撤销旧设备授权。 | 保留节目音量、主动静音、分析及灯光意图；实际输入显示等待直到确认。独立音乐按恢复后的事实重启，不自动续播视频。 |

### 7.2 必须通过实测解决的技术问题

1. **连接容量与第三条链路。** 先分清控制器无法建立两条 ACL、BlueZ 只启用一个 A2DP profile、PA 未发布第二 source，以及 Host 无法观察 B 仍在播。保留双手机型号、镜像/固件、HCI 峰值、D-Bus 与 PA 记录。优先改控制器准入配置或修复驱动/BlueZ 策略（镜像成本，回归现有绑定、断电重连）；硬件容量确实不足时，试经实测支持双手机的替换蓝牙模块/USB 适配器（物料、驱动、射频、绑定迁移及新旧控制器切换成本）。在样机重做 H1–H4 和 H6；能配对多台或只支持一台实际连接均不能通过双机验收。
2. **回放因果顺序与数字隔离。** 在未创建可听路由时要能判断 A、B 活动，且采集不能维持假活动；H2/H3 任一失败，保留生产基线，在隔离镜像验证新实现。遇到暂停与无限缓冲观测完全相同的机型，记录自动切换能力缺口并测试真实 player/transport 组合；手动指定仅提供恢复操作。
3. **现场授权与配对。** HTTPS 证书名称、浏览器信任/持久存储、实例密钥隔离、默认 Agent 权限、匿名 V1 的受信接入路径一并验收。旧自动 Agent 仍在应答、代理后端可被普通网络直接访问、过期挑战可被回答，任一项均阻止上线。
4. **连续输出的实机余量。** H5/H6 测候选解码与常规渲染同时工作时的最坏间隔、切点的实际光强和节点 realtime timeout；分别验证正常连续、创作黑帧与故障黑。记录 High 10 1080p60 的 CPU/内存高水位、候选过期率、控制链路延迟。进程硬杀、板卡或网络失联时软件可能无法把安全黑送达，须核对节点断流回落配置为安全态并实测；不满足则不能标记安全恢复通过。保留 112–128 s、143–159 s 的真实 cue 对照。实灯结果均为 **NOT HARDWARE VERIFIED**。

三项修订中尚需现场给出数值或事实的是：① RK3588 在解码与候选准备同时进行时的最坏帧间隔以及冻结预算；② 各 WLED 节点的实际断流回落、从 off 启用时的命令顺序和跨节点可见偏差；③ 下一位使用者能否在独立右屏找到「恢复随播放」并区分亮度为零。分别用第 6.3 节的输出专项与换人触屏专项记录结果。若实测出现正常换角色闪黑、未授权复亮或使用者反复误判已经开灯，保留为设计审查问题，重审对应合同。

### 7.3 已发现的产品语义交界

现有 WLED `_post_bri` 在更新亮度时一并发 `on:true`。持久 off 期间，调整亮度及旧 V1 play 的亮度复位只更新可读的**亮度设定值**；统一的硬件写入入口必须阻止所有隐式 on，包括场景初始化、延迟任务和重启重放。显式恢复后才按保存的亮度与新角色发出相应硬件命令。正常角色交接不发送电源开关命令。从 off 恢复时，要协调 WLED 本地关灯与首个有效 DDP 画面；H5 需实测目标固件的 realtime 与本地 on/off 顺序，不能因一个裸 on 先闪出旧本地颜色。V1 与右屏命令走同一串行化边界，验收交错的 V1 play、右屏 play/stop、旧 follow 与新 off；检查设定亮度、实际帧和 WLED HTTP payload 三者。[现有亮度写入](host_services/wled_brightness.py)

- **旧 APP 的开始播放会重设亮度。** 已发布 V1 明确每次 `/api/v1/playback/play` 将 brightness_scale 置为默认 0.5，测试直接断言它；V1 reset 会清除手动覆盖且可恢复暂停，应用场景还有显式停止节目的行为。这些均保留。右屏只给“启动节目”加一个保护入口 `POST /control/play`，与 V1 共用内容校验、mpv 加载、seek、ready、出错回收，仅将亮度/手动覆盖的初始化策略作为入口参数。右屏调用保留当前意图，自动交接也不重设亮度；旧 APP 用户显式 play/reset 属于有原合同语义的操作。可读的亮度始终是同一个现行值，显式关灯锁由灯光意图守住；不能先写 0.5 再补写原值。V1 与右屏各有行为测试。若将来还要更改旧 APP play 的明订语义，应另行版本化。[V1 说明](docs/reference/host-api-v1.md) · [亮度与 reset 回归](tests/test_host_service_api.py)
- **手选未活动的手机**按一次待播选择处理。释放旧手机，空档期间可听正在播放的节目；页面同时报告实际声音与等待目标。当前设备开始后才成为赢家，释放后恢复自动排队。此默认消除了“选择设备”等于“强迫手机播放”或“等待期间一定全舱无声”的歧义。
- **暂停视频时的两种灯光意图**由第 4.2 节的优先表决定。没有独立接管条件时保持节目定格，有手机并处于随播放时让独立音乐灯接手；手动/关灯继续优先。用户主动选择环境麦克风只改变分析输入，并不自动开灯或改变手机播放权。

## 8. 最终方案自审

| 核对问题 | 取舍与可证伪的检查 |
|---|---|
| 视频、手机、灯光是否被连成一台播放器？ | 各自有事实来源；只在扬声器、DDP 两处仲裁。分别测试“无视频手机独播”和“静音/关灯手机仍播”。切源期间检查 mpv 位置、渲染 PID、序号及扬声器路。 |
| 是否有多套状态或进程竞争？ | 单一可听 loopback、单一 DDP writer、单一默认 Agent。候选只提交逻辑内容，旧角色的析构没有输出权限。测旧 off 迟到、writer 退出后孤儿、就绪但首帧未提交、连续 hold 与序号边界。 |
| 精简 Kiosk 是否漏掉必要授权/异步动作？ | 单舱设备会话、一个状态查询、仅为实际设备异步操作和 Agent 回调使用短期标识。用未授权客户端、两页同时确认、换屏、重启与跨舱 cookie 验证。既有 WS 仍供原订阅使用，无第二套 SSE、重放日志、通用任务系统或角色平台。 |
| 旧节目与效果是否会被改写？ | 保留生产 YAML、物理映射、DDP、OutputTransform 与文件 CLI。新特征通过可选字段及兼容投影接入。第 2 节的 PCM 散列、480 帧对照和全片记录继续作为软件对照，独立模式额外测单调时间与空输入。 |
| 生产迁移是否有实际先决条件？ | H2/H3 给出硬件并发、准入、单路和采集隔离证据后才能动生产音路；H4 先验证真实屏与真实 Agent；H5/H6 交付声光与长稳证据。下列历史测试记录描述已有分支，尚未执行本设计的开发、部署或实机验收。 |

**设计审查的退出条件。** 逐项走查“输入改变 → 配置编号 → 帧选择 → 输出结果 → 页面读回”，包括有/无接班的 EOF、准备失败叠加 off、双页旧恢复、亮度为零，以及旧 APP 兼容入口。任何能造成非预期熄灯/复亮、双 writer 或把采集故障显示成静音的反例均是设计阻断项，须先改本方案再评审。第 7.2 节集中记录依赖现场证据的条件；H2/H3 的准入与路由、H4 的真实控制屏授权、H5/H6 的时序、断流回落及资源余量都不能由文字审查代替。基线中已有的片尾 seek 竞态和颜色越界在 A/E 有单列闭环；历史通过数不能抵销已知失败。此文档是待按上述标准核验的设计，不构成开发或生产变更授权。

**既有软件与素材核查记录。** 解释器验证返回 `PROJECT_PYTHON_OK`；通过仓库的 `.python/Scripts/python.exe` 调用，解释器解析到共享仓库 venv，导入包位于本工作树。下表中的 pytest 均用 `.\.python\Scripts\python.exe -B -m pytest -q -p no:cacheprovider`；分组中的文件均在 `tests/`。未执行完整生产套件、硬件命令或部署。前两组 pytest 使用了项目配置的忽略目录 `tmp/pytest` 存放临时夹具；最后单例以 `-o addopts=` 使用系统临时目录。

| 实际运行 | 返回码 | 结果 |
|---|---:|---|
| DDP/时钟/旧入口基线：`test_phase32_topology_ddp.py test_clock_integration.py test_host_real_engine_adapter.py test_app_host_api_v1_freeze.py`，加 `test_host_service_api.py` 中 play 复位亮度、paused reset 恢复播放、brightness_set 仅推送已启用 WLED 三项，使用 `-o addopts=` | 0 | 58 passed，17.08 s；覆盖现有行为。第 6.3 节新增的交接与换人专项尚待实现后执行。 |
| V1 专项复核：`test_app_host_api_v1_freeze.py` 和 `test_host_service_api.py` 的 `test_playback_play_resets_brightness_scale`、`test_playback_reset_from_paused_resumes_playback`，加 `-o addopts=` | 0 | 8 passed，7.04 s；确认旧 APP 接口、开始播放的亮度复位、暂停时显式 reset 的语义。 |
| pytest：`test_bluetooth_audio_priority.py test_engine_wled_audio_source.py test_wled_audio_sync.py test_audio_state_regressions.py test_engine_music_control_state.py test_host_playback_contracts.py test_app_host_api_v1_freeze.py test_host_auth_contracts.py test_deployment_audio_output.py` | 0 | 152 passed，34.98 s；禁用 cacheprovider 的 cache_dir 提示、Starlette TestClient 依赖弃用提示。 |
| pytest：`test_media_fusion_quality.py test_host_video_input.py test_rk3588_bluetooth_deployment.py` | 1 | 21 passed，1 failed，19.27 s；失败位置见第 2.4 节。 |
| pytest 单例，加 `-o addopts= --tb=line`：`test_media_fusion_quality.py::test_delayed_embedded_soundtrack_drives_mapped_frames_across_paused_rewind` | 1 | 同一失败，6.37 s。 |
| `node --test kiosk/test/api.test.js` | 0 | 3 passed，0.456 s。覆盖旧 API 请求与错误反馈。 |
| 实际 MP4 的 ffprobe 流信息查询、FFmpeg 全片音视频解码、MP4/临时 FLAC 两次 24 位 PCM 散列 | 0 | 容器、时间轴及音轨一致性见第 2.1 节。 |
| 新增视频后的 pytest：加 `-o addopts=`，运行 `test_host_shows_loader.py test_host_real_engine_adapter.py test_host_video_input.py test_host_playback_contracts.py` | 0 | 88 passed，22.27 s；使用系统临时目录。 |
| `.\.python\Scripts\python.exe -B -u -`，临时素材制作、Host 预检/启动参数观测、112–128 s 原声重放与静音对照、305 s 全长及末段离线渲染 | 0 | 163.73 s；全片帧数和对照结果见第 2.1 节。 |
| `.\.python\Scripts\python.exe -B -u -`，真实素材、模拟 mpv 暂停/跳转及 305.0、305.3 s 两个末段入口 | 0 | 7.34 s；两个入口均只产生安全帧。 |
| `git rev-parse HEAD`、`git status --short --branch`、`git diff --stat` | 0 | 基点见第 1 节；新增方案为未跟踪文件，普通 diff 统计不包含它。 |
