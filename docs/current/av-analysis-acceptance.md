# 音视频分析与灯光输出验收

## 九条灯带如何延伸屏幕

九带逐组演示使用 `config/examples/regional-av-preview.yaml`。在有效画面上，上、下各取约六分之一画面高度，左、右各取约八分之一宽度。每条边最多保留 64 个有序 RGB 样本，在**同一局部**给较亮像素更高权重，以保留占地较小的太阳和反光。横向边缘从左到右、纵向边缘从上到下重采样到各自灯组数，再应用配置方向。

| 边缘 | 屏幕周边 | 舱内对应灯带 |
|---|---|---|
| 上 | 11，10 组 | 12，顶棚边缘，17 组 |
| 下 | 21，10 组 | 22，地面与墙面交界，20 组 |
| 左 | 31，10 组 | 32，左舱门或圆窗，10 组 |
| 右 | 41，10 组 | 43、44，右墙波浪带，各 10 组 |

同一侧的多条灯带各自延伸整条边，目前部署配置提供方向和所属边缘，未提供墙面各安装段覆盖屏幕的起止坐标。原融合路径用 70% 区域均色混合 30% 平滑全屏色，RMS 决定基础亮度，低频和节拍增强脉冲，中频微调饱和度，高频产生微弱波动。原始节目还可用固定 cue 覆盖实时输入。逐组演示以局部原色为基底，基础增益为 1，RMS 权重为 0.85，低频倍率为 1.15，高频波动关闭。增亮时锁定灯组 RGB 比例，纯黑保持黑色；最终仍经过生产亮度上限 0.65 与 gamma 1.3。

原片 35–55 秒的预览可用下面的命令复现。屏幕四周显示四条环屏带；右侧同时列出所有九条灯带的输入色条和物理映射结果。

```powershell
.\.python\Scripts\python.exe -m scripts.acceptance.render_media_show --video assets/energy-wakeup/energy-wakeup.mp4 --audio assets/energy-wakeup/energy-wakeup.flac --show config/examples/regional-av-preview.yaml --profile config/profiles/rk3588-host-service.yaml --output tmp/sunrise.png --preview 35 55 --screen-edges
```

在预览第 9 秒，11 的第 6 组、12 的第 9 组最亮。11 的第 6 组输入 RGB 为 (190, 165, 109)，生产配置下输出 (146, 121, 70)，HSV 色相从 41.5° 变为 40.3°。左侧 31 从上到下的加权 RGB 码值约为 76、53、40、37、12、15、3、1、1、1，右侧 41 为 54、51、31、26、19、12、7、1、2、4。

第 13–15 秒保持相同画面和媒体时钟，仅将音频特征切为静音。原始 Show 的 60 帧、107 组输出完全相同。逐组节目缩短亮度包络的响应时间后，有声时每帧平均 RGB 码值为静音时的 1.95–2.43 倍；较慢包络为 2.04–2.42 倍。音频 RMS 与逐帧增益的相关系数由 0.384 升至 0.515。这 60 帧中，每个灯组至少一个通道增加，所有通道均未减小。码值不等同于实测照度。输出上限和 gamma 始终作用于最终映射。

逐组回归入口为 `tests/test_screen_extension.py`，定向媒体、灯效和映射测试共 133 项通过。实际预览为本地运行证据目录 `artifacts/runs/av-analysis-20261122/screen-extension-final.mp4`。在下列命令中分别使用逐组节目及原始节目，即可复算有声、静音对照与逐帧增益。

```powershell
.\.python\Scripts\python.exe -m scripts.acceptance.measure_mapped_audio --video assets/energy-wakeup/energy-wakeup.mp4 --audio assets/energy-wakeup/energy-wakeup.flac --profile config/profiles/rk3588-host-service.yaml --show config/examples/regional-av-preview.yaml --start 48 --end 50 --output tmp/sunrise-audio-response.json
```

## 输入与时间轴

Host 从 `assets/<show>/` 发现媒体与节目。mpv 播放主媒体并提供播放位置，独立的 Light Engine 进程用同一位置采样。视频由 OpenCV 解码为 BGR，分析器缩至 160×90，以默认 10 Hz 更新。区域 RGB、平均色和主色进入 Show 色源、`video_ambient` 或融合效果。配置决定画面区域与灯带的对应关系。

有外部音轨时，Host 用 mpv 的 `audio-add … select` 指定实际播放轨，并给 Engine 传入同一文件。纯音频媒体直接供文件分析器读取。仅传 `--video` 时，OpenCV 提供画面；配置启用 WLED Audio Sync V2 时，声音特征来自麦克风。生产九带配置启用该输入。文件音频的优先级更高，空窗和文件结束均不会切换到麦克风。

对只有内嵌音轨的节目，在**素材准备机**上执行以下命令。目标目录应含一个 Host 支持的 MP4、MKV 或 MOV。参数是从零开始的音频轨序号。工具保留采样率与声道数，通过 FFmpeg 将选定轨道写成同目录的 FLAC。已有外部播放音轨时会报错。换片、换音轨时应重新核对或更新素材包；运行时不会检查外部音轨与视频的版本关系。

```powershell
.\.python\Scripts\python.exe scripts/authoring/prepare_show_audio.py assets/my-show/film.mp4 --track 0
```

音轨时间以容器起点为零，延迟开始的轨道在 FLAC 中保留前导静音。600 ms 延迟轨回归覆盖了提取、Host 发现、文件特征、暂停回拖和物理映射像素。FFmpeg 仅用于素材准备及预览编码。[FFmpeg 时间戳与流选择说明](https://ffmpeg.org/ffmpeg.html)

文件音频使用源采样率、单声道混合以及默认 50 ms Hann 窗，窗中心对齐媒体位置。文件开头裁定窗起点为零。频带默认为 20–200、200–2000、2000–12000 Hz，并受 Nyquist 频率约束。配置中的 25 ms hop 参与历史容量和部分阈值计时；生产 Engine 每个输出 tick 最多更新一次。默认输出 30 FPS，配置的音频更新上限 60 Hz 在此路径上实际最多 30 Hz。PCM 可向前读半窗。WLED 路径只消费已收到的报文，以最新连续量、当次峰值与超时状态更新；默认配置过期时间为 250 ms。

短时频谱通量提供起音候选。音乐控制器以事件间隔估计 60–180 BPM 和相位，将节奏规律性、低频脉冲和中期能量趋势分别交给效果或 Show 调制。文件路径用减去直流后的原始 RMS 识别真实电平变化；WLED 有自己的原始量纲。趋势使用前后两段均值，15% 死区抑制稳定鼓点在统计窗边缘的数量波动；低于 PCM RMS 0.0001 时不报告趋势。分析历史以 60 Hz 为容量基准并设上限，实际涵盖的媒体秒数取决于输入频率。四秒无新节奏事件后 BPM 和置信度清零，以容纳最低支持速度下的四拍间歇。

融合效果在区域 RGB 上调节亮度，低频起音与节拍相位共用包络，高频形成随媒体时间移动的同色亮度波。画面全黑时仍保留黑场。Show 也可通过 `music.energy_trend` 调制参数。效果结果依次通过 `OutputTransform` 与物理映射；实机生产路径再发送 DDP，每个节点仅接收自己的灯组。暂停在相同媒体时间重复发出相同像素，序号继续递增。Host API 拖动会重启 Engine 后对齐 mpv；直接使用 mpv 时钟的 Engine 也能处理回拖和循环回绕。两条路径都应分别检查。

## 可复现比较

在仓库根目录执行。以下示例使用新的输出目录。旧实现仅从 Git 取出源码和配置，不需要切换工作树。

```powershell
$lab = 'tmp/av-reproduction'
New-Item -ItemType Directory -Path $lab
git archive --format=zip --output="$lab/baseline.zip" e6e19059b735e90bd47920c41668a31eca8fc8f3 light_engine config
Expand-Archive -LiteralPath "$lab/baseline.zip" -DestinationPath "$lab/baseline"
.\.python\Scripts\python.exe tests/audio_ab_probe.py --root "$lab/baseline" --window-anchor forward
.\.python\Scripts\python.exe tests/audio_ab_probe.py --root . --window-anchor center
.\.python\Scripts\python.exe -m scripts.acceptance.av_quality_ab fixture --folder $lab
.\.python\Scripts\python.exe -m scripts.acceptance.av_quality_ab capture --folder $lab --root "$lab/baseline" --label baseline
.\.python\Scripts\python.exe -m scripts.acceptance.av_quality_ab capture --folder $lab --label working
.\.python\Scripts\python.exe -m scripts.acceptance.av_quality_ab compare --folder $lab
```

`comparison.mp4` 含原始合成声音、画面与同步的 A/B 灯带预览。旧实现对应 A，新实现对应 B。`trajectory.png` 显示共同量程下的映射输出均值。`*-trace.json` 保存 RMS、频带、起音、BPM、相位、置信度、代表色、分区、亮度与帧差；同名 NPZ 保存时间戳和物理像素。默认开发配置比较 179 帧、每帧 632 个像素。全黑比例按逐通道四舍五入到 8-bit 后计算，结束安全帧排除在外。

| 试验输入与指标 | 原实现 | 逐组映射前的融合版本 |
|---|---:|---:|
| 15 个连续 PCM 鼓点，强鼓与弱鼓分别计数 | 每组命中 1，误检 1 | 每组命中 15，误检 0，平均绝对误差 2.22 ms |
| 12 个非等间隔起音 | 命中 1 | 命中 12，误检 0，平均绝对误差 13.06 ms |
| 旋律叠加弱鼓，15 个标注 | 命中 15，误检 2，BPM 未锁定 | 命中 15，误检 1，120 BPM，平均置信度 0.766 |
| 持续低音降到原振幅 20%，观察滚动归一化后期的最大瞬态 | 1.000 | 0.043 |
| 合成线性渐强，暖机后平均趋势 | 0.000069 | 0.729 |
| 半红半黑，红色通道平均值，参考 100/255 | 0.7843 | 0.3922 |
| 六秒预览的暗场鼓点段，8-bit 全黑像素比例 | 40.67% | 0.10% |
| 同一预览的亮场鼓点段，映射通道均值 | 0.03384 | 0.10036 |

起音匹配采用 ±50 ms、一对一配对；这个容差对应一个分析窗。起音不等同于稳定节拍，文件测得的时间误差也不包含扬声器、网络和灯带延迟。项目的 120 BPM WAV 在两版均得到 120 BPM 和约 0.970 平均置信度。切分样例在新版命中全部起音，但估得 163.6 BPM、平均置信度仅 0.293。连续噪声各有一次误检，均未形成 BPM 锁定。带颤音和共振峰变化的合成持续元音在两版均产生一个候选起音，均未锁拍。人声主导、弱鼓的真实录音仍需独立标注。

在持续旋律覆盖弱鼓的样例上，把所有频谱起音直接送进速度估计器可得到 120 BPM，但会使不规则钢琴的平均置信度从 0.014 升到 0.026。保留方案仅在最近四个 PCM 起音的三个间隔全部落入支持速度范围、且间隔之差不超过一个 50 ms 窗时纳入弱起音。钢琴置信度维持 0.014，代价是弱鼓需要多个重复周期才能建立节奏。强起音仍直接参与跟踪。

第一次去除随机白色高频闪动后，暗场鼓点段有 95.86% 的像素量化为全黑。根因是带有明暗信息的区域 RGB 又乘了一遍全画面亮度。保留方案去掉这次重复衰减。亮场均值随之上升，样例亮场的 255 饱和通道比例仍为零。一名观看者在同音量的 A/B 屏幕对照中选择了 B。复评时隐藏版本名称、交换 A/B 顺序，分别记录鼓点是否拖拍、暗色能否分辨、字幕是否抢色、切镜是否突兀及连续高频是否刺眼，并记下具体时间点。

启用逐组边缘采样后，同一暗场素材还暴露出暗蓝画面与黑边的亮度过于接近。改为检查黑边候选像素的三个颜色通道后，该样例的暗场鼓点段全黑比例为 0%，亮场鼓点段平均 RGB 码值为 0.09153，亮场通道饱和比例为 0%。有真正黑色区域的定位测试仍要求这些灯组在有声时保持黑色。新版六秒对照保存在运行证据的 `edge-ab/` 子目录。

## 节目和设备验收

完整节目可用真实 Show、媒体、准备好的轨道以及部署源配置离线渲染。此命令将已映射的帧送入内存记录器。输出 PNG 横轴为节目时间，纵轴按节点与输出顺序排列，每行对应一个物理灯组。

```powershell
.\.python\Scripts\python.exe -m scripts.acceptance.render_media_show --video assets/energy-wakeup/energy-wakeup.mp4 --audio assets/energy-wakeup/energy-wakeup.flac --show assets/energy-wakeup/energy-wakeup.yaml --profile config/profiles/rk3588-host-service.yaml --output tmp/energy-wakeup-timeline.png --preview 35 50
```

可选的 `--preview 35 50` 在同目录生成 MP4，将 35–50 秒的源画面、选定声音与逐输出帧的九带像素并排放置。PNG 时间图按约四分之一秒取样，适合查看整段节目的空间分布。MP4 使用完整输出帧率，适合听看节拍。两者均编码屏幕预览。

在 Windows 开发机上，305 秒的原始节目与同源音轨产生 9,149 帧、9 个节点、107 个灯组。解码器根据已解码的 PTS 处理顺序采样，对等间隔中间帧省去 BGR 转换，随机定位后按 PTS 校正。用 1080p60 原视频在 100–104.9 秒每 100 ms 采样一次，50 张缩略帧的摘要与旧实现一致。开发机上的解码 P95 从 286.5 ms 降至 22.8 ms；该数值包含当时开发机负载。可变帧率样例的前半段每 200 ms 一帧、后半段每 100 ms 一帧，测试覆盖帧间保持、回拖和最后一帧。

五分钟 44.1 kHz 双声道 FLAC 的独立读取试验中，Python/NumPy 可追踪峰值由 151.4 MiB 降至 0.82 MiB，代价是 1,800 次取窗总耗时由 37 ms 增至 297 ms。该指标不含全部进程和解码器驻留内存。Engine 处理容量按整段计算，耗时百分位使用最近 3,600 个输出帧；现场应在同机运行 mpv、解码和实际输出时采集端到端数据。

画面分析能区分整体色相突变与保持全局配色的平移，并保留内部暗像素。相邻帧差仍是变化强度指标；同色调切镜、全屏闪光、摇镜和物体运动无法普遍分开。对称的暗画面边缘也可能被识别为黑边。当前结果未建立镜头语义、歌词、主观情绪或音乐段落识别的验收证据。

最后的现场门槛是同一片源在 NanoPC-T6-LTS 上通过 mpv 实播，分别检查安静段、切镜、暂停回拖、切歌和循环；记录单带与九带的画面、出声与发光时间差。另用扬声器与 WLED 麦克风检查实时输入延迟及断包恢复。以目标亮度复看深蓝暗场和亮场鼓点，决定是否调整部署配置的 gamma 与亮度上限。**NOT HARDWARE VERIFIED**。

## 验证记录

九带逐组映射集成后的全量命令为 `.\.python\Scripts\python.exe -m pytest -q --suite full --basetemp=tmp/av-screen-extension-full --tb=short -rs`，1,697 项通过、1 项因目录符号链接不可用跳过，耗时 573.89 秒。随后缩短边缘亮度包络并修正暗蓝画面黑边判别，相关测试 133 项通过（46.05 秒），快速集 386 项通过（13.57 秒），单带软件证据复算 2 项通过（29.89 秒），退出码均为 0。最终原始节目离线复跑渲染 9,149 帧，用时 161.61 秒；最近 3,600 帧处理耗时 P95 为 36.93 ms，P99 为 44.46 ms。开发机同时有其他验收负载，不能据此断言每帧稳定达到 30 FPS。

原版代码取自 `e6e19059b735e90bd47920c41668a31eca8fc8f3`。Windows 工作区的全量回归为 1,696 项通过、1 项跳过，用时 605.44 秒。跳过项是安装包材料测试中的目录符号链接用例。部署相关测试需要能创建 Windows Junction 并运行 Git Bash 的环境。快速集 386 项通过。音频控制与 WLED 定向回归 46 项通过，音视频时间轴、VFR、读窗、EOF 与映射定向回归 20 项通过。

在其他验收进程退出后，用相同随机种子、默认六带配置和 NullOutput 连续运行两版的 1,800 帧合成融合基准。取消等待帧周期后，旧版与保留版的处理容量分别为 179.8 和 195.4 FPS，帧处理 P95 分别为 7.48 和 7.17 ms。真实节目包含视频解码、文件音频和 Show 合成；在并行回归负载下，无预览录制的完整 305 秒渲染耗时 177.98 秒，最近 3,600 帧的 P95 为 42.64 ms，P99 为 50.58 ms，超过 30 FPS 的 33.3 ms 单帧预算。

六秒 A/B、原始节目 35–50 秒的九带音画预览、全片灯组时间图、旧版和保留版的特征与像素、被放弃暗场方案的量化结果，均保存在本地运行证据目录 `artifacts/runs/av-analysis-20261122/`。跟踪的单带软件基线中，融合 cue 的像素摘要、亮度统计和 source-weight 对照距离随算法改变。回归继续核查这些行为指标和复算的一致性。
