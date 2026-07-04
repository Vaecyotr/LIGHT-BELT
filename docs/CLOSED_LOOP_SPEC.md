# LIGHT-BELT 六区域实体闭环改造任务书

> 本文件用于交给 Claude Code。它定义系统目标、架构边界、协议、约束和验收条件，不规定逐行实现方式。请在 LIGHT-BELT 仓库根目录使用 Plan Mode 阅读本文件。

## 1. 任务使命

将现有 LIGHT-BELT 从“视频/音频分析与模拟输出原型”改造为可部署到 RK3588 ARM64 Linux 的灯光主脑，并形成以下实体闭环：

```text
视频/音乐播放与统一时钟
        ↓
RK3588 上的 LIGHT-BELT
├─ 视频五区域分析
├─ 音频 RMS / Bass / Mid / Treble / Flux / Beat
├─ 六区域效果生成
├─ RGB → RGB+CCT 五通道转换
├─ 六节点 RS-485 帧生成
└─ WS2811 完整物理帧生成
        │
        ├─ RS-485 → 6个 STM32 → 6块 YYNMOS-8 → 6个 RGB+CCT COB 区域
        └─ UDP → ESP32-S3 → RMT → 24V WS2811
```

RK3588 是唯一在线主脑。RK3568 只作为备用、调试或降级主机，本任务不构建 RK3588/RK3568 分布式计算。

## 2. 已确认的硬件事实

### 2.1 模拟 COB

真实灯带不是 RGBW 四通道，而是：

```text
24V、六根线、共阳极、五个受控通道
+24V / R / G / B / WW / CW
```

系统名称统一为：

```text
RGB+CCT
```

代码字段统一为：

```text
r
g
b
warm_white
cool_white
```

六个逻辑区域：

```text
1 ceiling_left
2 ceiling_right
3 wall_left
4 wall_right
5 front
6 rear
```

最终硬件架构为每个区域一个 STM32 节点和一块 YYNMOS-8，每个 STM32 输出五路 PWM。

### 2.2 数字灯带

数字灯带为 24V WS2811 RGB COB。当前共有约 15 米，最终安装长度未确定。

当前演示应支持：

```text
一个 ESP32-S3 节点
一条物理 WS2811 链
六个连续逻辑区段
```

未来应通过配置扩展为多个 ESP32-S3 节点，不得要求修改灯效算法。

### 2.3 电源和长度

当前拥有：

```text
RGB+CCT COB：15米
WS2811：15米
明纬 LRS-150-24：1台
明纬 LRS-350-24：2台
```

最终灯带长度和最终电源分配未确定。软件不得硬编码 15 米、5 米、100 像素或固定功率。

## 3. 当前仓库基线

开始工作前必须自行审计仓库并验证以下基线，不要只相信本任务书：

```text
python -m pytest -q
```

当前预期基线约为：

```text
220 passed
```

当前已知结构：

```text
light_engine/analysis
light_engine/media
light_engine/effects
light_engine/mapping
light_engine/engine
light_engine/outputs
light_engine/cli
config
tests
```

当前已知缺口：

1. `RGBWColor`、`ZoneOutput`、效果和 JSON 输出仍以 RGBW 为核心。
2. `layout.yaml` 的模拟区域类型仍为 `rgbw`。
3. `SerialOutput` 是单端口、11 字节 RGBW v1 协议，没有 Node ID、Sequence 或 CRC16。
4. `SerialOutput` 在真实串口打开失败时会静默回退到内存传输，可能造成虚假成功。
5. 当前串口输出可能对亮度重复缩放。
6. 当前串口后台队列保存多个独立区域包，不能保证六节点属于同一逻辑帧。
7. 当前 `UdpOutput` 按逻辑 strip 分包，Sequence 由输出端自行生成，ESP32 可能收到局部新旧帧。
8. 当前 UDP 校验为简单 XOR，不是目标协议。
9. 串口和 UDP 真实发送路径存在 `_health()` 被当作函数调用的问题，现有测试没有覆盖。
10. `send_all()` 与具体输出后端可能重复统计发送帧。
11. `pyserial` 未列入正式或硬件可选依赖。
12. Engine 当前主要通过内部固定步长推进时间，尚未以实际媒体播放位置作为主时钟。
13. 仓库中目前没有可验证的 STM32 和 ESP32-S3 固件工程。

这些是审计入口，不是要求你机械地逐项打补丁。请识别根因并形成一致架构。

## 4. 强制架构边界

内部类名和文件拆分可由你决定，但以下边界必须成立。

### 4.1 分层

系统必须清晰分为：

```text
媒体时钟与媒体控制
分析
逻辑效果
逻辑到物理映射
协议编码
传输
控制器固件
```

约束：

- 分析模块不得知道 RS-485、UDP、STM32、ESP32 或具体端口。
- 效果模块不得直接编码通信包。
- 协议编码必须是纯逻辑，可在无硬件环境下测试。
- 传输层必须可注入 fake/memory transport，不得靠串口打开失败自动进入测试模式。
- 物理像素数量、节点地址、区段偏移和方向全部来自配置。
- 同一个逻辑灯光帧必须具有唯一 Sequence 和时间戳，并同时用于 RS-485 与 UDP 输出。
- 输出后端不得各自生成互不相关的 Sequence。

### 4.2 逻辑帧

逻辑帧必须能够表达：

```text
sequence
timestamp / media_position
六个 RGB+CCT 模拟区域
若干数字逻辑灯带
metadata / diagnostics
```

可保留 `PixelFrame` 名称，也可引入新模型；若重构公共模型，应提供清晰迁移路径，并更新全部效果、输出和测试。

### 4.3 物理映射

逻辑区域与物理设备分离：

- 模拟区域映射到 RS-485 `node_id`。
- 数字逻辑灯带映射到 `digital_node_id + pixel_offset + pixel_count`。
- 一个 ESP32 节点可以包含多个逻辑区段。
- 多个逻辑区段不得重叠或越界。
- 数字物理帧必须按节点合并后发送，而不是由各效果直接发送多个 strip 包。

## 5. RGB+CCT 数据模型与色彩效果

### 5.1 数据模型

新增或迁移到五通道颜色模型：

```text
RGBCCTColor
r
g
b
warm_white
cool_white
brightness 或等效的单一亮度语义
```

约束：

- 所有通道内部范围为 `[0,1]`。
- NaN、Inf 和越界值必须拒绝或有明确、统一的钳位策略。
- 亮度只应用一次。
- `to_uint8()` 或最终量化步骤必须明确唯一。
- `all_pixels_valid()` 等验证逻辑必须覆盖 WW/CW。
- JSON、模拟器、诊断和导出必须展示 WW/CW。

### 5.2 RGB 到 RGB+CCT 转换

实现可配置、可测试的 RGB→RGB+CCT 转换。实现算法可自主选择，但必须满足：

- 黑色输出五通道全零。
- 高饱和纯红、纯绿、纯蓝主要使用 RGB，WW/CW 接近零。
- 中性白场同时使用 WW 和 CW，RGB 残余受配置控制。
- 暖白输入满足 `WW > CW`。
- 冷白输入满足 `CW > WW`。
- 转换前后感知亮度不应出现明显非单调行为。
- 有全局及每区域功率/通道限制，防止 RGB、WW、CW 同时满载造成不必要功耗。
- 暖白/冷白偏置、白光提取强度、总输出限制均可配置。
- 不假装从普通 RGB 视频精确恢复真实色温；这是视觉映射策略，文档中必须如实说明。

### 5.3 效果兼容

现有主要效果必须继续工作：

```text
static
video_ambient
audio_pulse
bass_pulse
spectrum
breath
color_wave
chase
comet
calm
demo
video_audio_fusion
```

目标效果：

- `video_ambient`：视频区域决定基础颜色和冷暖白倾向。
- `spectrum`：低频驱动顶部，中频驱动左右墙，高频驱动前后。
- `video_audio_fusion`：视频决定基础颜色，音频决定亮度、脉冲、饱和度和动态幅度。
- 数字 WS2811 保持 RGB 像素，不扩展为 CCT。
- 现有五区域视频映射继续成立：
  - top → ceiling_left / ceiling_right
  - left → wall_left
  - right → wall_right
  - center → front / rear
  - bottom → 暂未分配

不得为了 RGB+CCT 重写已验证的视频/音频分析算法，除非测试证明存在必要缺陷。

## 6. RS-485 v2 协议

### 6.1 物理模型

```text
RK3588 / Windows PC
→ 一个 USB-RS485 适配器
→ 一条半双工 RS-485 总线
→ 六个带唯一地址的 STM32 节点
```

初始版本是主机单向下发灯光数据，不要求每帧 ACK。可以预留诊断命令，但不能让 ACK 阻塞 30 FPS 灯光输出。

### 6.2 固定帧

协议 v2 固定为 16 字节：

```text
Byte 0   0xA5
Byte 1   0x5A
Byte 2   Version = 0x02
Byte 3   Command
Byte 4   Node ID
Byte 5   Sequence
Byte 6   R
Byte 7   G
Byte 8   B
Byte 9   WW
Byte 10  CW
Byte 11  Fade High
Byte 12  Fade Low
Byte 13  Flags
Byte 14  CRC16 High
Byte 15  CRC16 Low
```

协议约束：

- `Node ID`：1～6；可预留广播地址，但必须文档化。
- `Sequence`：uint8，允许自然回卷。
- `Fade`：uint16，大端，单位毫秒。
- CRC：CRC-16/CCITT-FALSE。
- CRC 覆盖 Byte 0～13。
- 解析器搜索双字节同步头，固定长度读取，再验证 CRC。
- STM32 接收端字节间超时目标 5 ms；超时重置解析状态。
- 错包、未知版本、未知命令、错误节点不得改变当前灯光状态。
- 必须生成并文档化至少一个主机与固件共享的 Golden Vector。

### 6.3 主机输出语义

每个逻辑帧包含六个节点命令：

```text
同一 sequence
同一逻辑 timestamp
按 node_id 1～6 编码
```

主机输出队列必须保存“最新完整逻辑帧”，而不是保存大量旧包：

- 队列容量语义为最新帧覆盖。
- 一帧的六个节点包不能与下一帧交错。
- 串口不可用时，生产模式必须明确失败并标记 unhealthy。
- memory/fake transport 只能通过配置或依赖注入显式启用。
- 不允许静默回退并继续宣称硬件输出成功。
- 统计必须区分 logical frames、wire packets、drops、errors。
- 统计必须线程安全且只计数一次。

## 7. UDP v2 与 WS2811 物理帧

### 7.1 原子帧原则

每个 ESP32-S3 物理节点每个灯光帧只接收一个完整 UDP 数据报：

```text
一个 node_id
一个 sequence
一个完整物理像素数组
一次校验
```

初始 v2 不做应用层分片。若某节点像素数超出配置的单数据报上限，应在配置阶段失败并要求增加 ESP32 节点，而不是运行时发送局部帧。

### 7.2 建议协议

可在保持以下字段和语义的前提下优化布局：

```text
Magic
Version = 2
Message Type
Digital Node ID
Flags
Sequence（至少uint32）
Pixel Count
Payload Length
RGB payload
CRC32
```

强制要求：

- 明确定义字节序。
- CRC 覆盖头部和 payload。
- 长度与 Pixel Count 必须交叉校验。
- 拒绝重复、陈旧、损坏或尺寸不匹配的帧。
- 生成并文档化 Golden Vector。
- 当前 15 米或最终长度不能硬编码。
- 配置必须校验每个物理节点是否能放入一个安全 UDP 数据报。
- 现有六个数字逻辑区域可映射到一个物理节点的连续区段。
- 未来可增加多个数字节点而不修改效果层。

### 7.3 ESP32-S3 固件

若仓库没有固件工程，在 `firmware/` 下新增可独立编译的 PlatformIO 工程，或采用同等可复现结构。

固件架构必须实现：

```text
Core 0
├─ Wi-Fi
├─ UDP接收
├─ 长度/版本/CRC/Sequence校验
└─ 最新完整帧写入长度1队列

Core 1
├─ 读取最新帧
├─ 双缓冲交换
├─ RMT/可靠硬件后端输出
└─ 一帧只刷新一次
```

约束：

- 使用 `xTaskCreatePinnedToCore()` 或等效机制明确任务核心。
- 队列长度为1，使用覆盖语义，不积压旧帧。
- UDP回调/接收任务不得直接调用灯带刷新。
- GPIO、node_id、pixel_count、色序、亮度上限、超时均可配置。
- 当前默认数据 GPIO 可保持 GPIO4，但不能散落硬编码。
- 超时后进入可配置安全状态，桌面默认全黑。
- 串口诊断至少输出收包数、CRC错误、序号间隙、刷新数、超时数。
- 固件必须能在无实体灯带时编译。
- 不得声称已通过实体硬件验收，除非提供真实测试证据。

## 8. STM32 RGB+CCT 节点固件

若仓库没有固件工程，在 `firmware/` 下新增可独立编译的 PlatformIO 工程，或采用同等可复现结构。

功能要求：

- STM32F103C8T6 BluePill。
- 每块板一个可配置 Node ID。
- 五路硬件 PWM：R/G/B/WW/CW。
- UART/RS-485 接收 v2 固定帧。
- CRC16、版本、命令、Node ID、长度验证。
- 5 ms 字节间超时。
- 目标值与当前值分离。
- 按 Fade 毫秒进行非阻塞插值。
- 通信超时进入可配置安全状态，桌面默认全黑。
- 主循环不得使用会阻塞接收和 PWM 更新的长延时。
- 记录 valid frames、CRC errors、address misses、timeouts 和 sequence gaps。
- PWM、UART、可选 DE/RE 引脚通过集中配置定义。
- 自动收发 RS-485 模块不需要 DE 引脚时应支持该模式。
- 固件必须能编译并包含协议 Golden Vector 测试或宿主侧等效验证。

可以选择 Arduino STM32、HAL 或其他合理实现，但必须说明选择理由，并保持 PlatformIO 可复现编译。

## 9. 媒体时钟与 RK3588 主脑

### 9.1 时钟抽象

保留确定性内部时钟用于测试和离线导出，同时新增媒体播放时钟适配层。

LIGHT-BELT 必须支持：

```text
internal/deterministic clock
mpv IPC media clock
```

要求：

- 正式播放时，灯光位置以播放器实际媒体位置为准，而不是独立累加固定帧周期。
- 支持开始、暂停、继续和媒体结束。
- Seek 或时间跳变时，分析器和效果状态必须有明确重置/恢复策略。
- 测试使用 fake clock，不依赖 CI 中真正启动 mpv。
- mpv 不存在、IPC不可用或播放器退出时必须明确报错或进入安全状态。
- 不实现完整图形界面。
- 提供一个面向 RK3588 的命令或 supervisor 入口，可启动/连接 mpv、运行灯光引擎并在结束时发送安全帧。

### 9.2 平台要求

- 保持 Windows 开发/模拟模式可用。
- 支持 RK3588 ARM64 Linux。
- 不提交 Windows 私有 Python 解释器作为 Linux 依赖。
- 修正 `pyproject.toml` 的串口依赖策略。
- Linux 设备路径来自配置，不硬编码 `/dev/ttyUSB0`。
- 文档说明可通过 udev 规则建立稳定名称，但不要要求测试环境拥有 root。
- 提供 RK3588 安装、依赖、运行和 benchmark 文档。
- 可提供 systemd 示例，但不得把设备路径、用户名和媒体目录写死。

## 10. 配置体系

配置必须覆盖：

### 模拟区域

```text
zone_id
node_id
video_zone
channel order
brightness/power limit
warm/cool bias
safe state
```

### 数字物理节点

```text
node_id
host
port
pixel_count
color_order
brightness limit
timeout
max_udp_payload
```

### 数字逻辑区段

```text
logical strip id
physical node id
offset
pixel_count
direction
video_zone
```

### 输出

```text
strict production mode
explicit memory/fake mode
RS-485 port/baudrate
UDP nodes
diagnostics
```

验证要求：

- Node ID 唯一。
- 六个模拟区域都有合法 Node ID。
- 数字区段不重叠、不越界。
- 单节点完整帧不超过 UDP 上限。
- 非法配置在启动时失败，错误信息指出配置路径和具体字段。
- 提供至少两个配置 profile：
  - Windows/无硬件开发与模拟
  - RK3588/RS-485+UDP 实体闭环

## 11. 诊断、错误语义与安全状态

必须修复和统一输出健康状态。

至少提供：

```text
healthy
last_error
logical_frames_submitted
logical_frames_sent
packets_sent
frames_dropped
packets_dropped
crc_errors
sequence_gaps
reconnects
last_success_time
```

要求：

- 线程安全。
- 不重复计数。
- 后端失败相互隔离，但生产模式可配置为关键输出失败即退出。
- 严禁把 memory fallback 计为实体发送成功。
- CLI结束时打印各输出健康摘要。
- JSONL记录 sequence、timestamp、RGB+CCT、数字节点帧摘要及输出状态。
- 程序退出、媒体结束或严重错误时尽力发送安全帧并关闭资源。

## 12. 测试与验收

### 12.1 不得回退

现有测试必须全部通过，或在数据模型迁移时被等价、合理地更新。不得删除测试以获得绿色结果。

### 12.2 必需新增测试

至少覆盖：

1. RGBCCTColor 验证、量化和亮度只应用一次。
2. RGB→RGB+CCT 的黑、RGB原色、中性白、暖白、冷白和单调性。
3. 功率限制。
4. 六区域现有效果的输出合法性。
5. RS-485 v2 encode/decode、Golden Vector、CRC损坏、噪声、拆包、错地址、Sequence回卷。
6. 一逻辑帧六节点同 Sequence，且包不跨帧交错。
7. latest-frame 覆盖语义。
8. 严格生产模式不静默回退。
9. UDP v2 roundtrip、Golden Vector、CRC/长度/旧Sequence/超尺寸拒绝。
10. 六逻辑区段合并为一个物理节点完整帧。
11. 多数字节点映射。
12. 相同逻辑帧的 RS-485 与 UDP 使用相同 Sequence。
13. 输出健康统计不重复。
14. fake media clock 的运行、暂停、结束和 seek/reset。
15. CLI/config smoke tests。
16. 固件协议常量与主机协议一致，或通过共享生成物/Golden Vector防止漂移。

### 12.3 端到端软件验收

提供一个可重复执行的无硬件验收命令或测试：

```text
输入：10秒视频 + 10秒音频
效果：video_audio_fusion
输出：fake RS-485 + fake UDP + JSON
```

验证：

- 约 300～301 个逻辑帧。
- 每帧六个模拟节点命令。
- 每个数字物理节点每帧一个完整数据报。
- 同帧 Sequence 完全一致。
- 无 NaN/Inf。
- 无协议解码失败。
- 队列无旧帧积压。
- 结束后安全关闭。
- 输出一份机器可读和人类可读的验收摘要。

### 12.4 编译与运行证据

最终必须实际运行并报告：

```text
python -m pytest -q
python -m light_engine benchmark --effect video_audio_fusion --frames 1800
```

若新增 PlatformIO 固件：

```text
pio run -d firmware/stm32_rgbcct_node
pio run -d firmware/esp32_ws2811_node
```

报告必须包含：

- 实际命令。
- 返回码。
- 测试数量。
- 失败项。
- benchmark P50/P95/P99 和 processing capacity。
- 修改文件清单。
- 仍需真实硬件验证的项目。

不要只说“应该通过”。

## 13. 非目标

本任务不包括：

- 安卓平板 App。
- 最终舱体施工和商业配电设计。
- 确定最终 COB/WS2811 米数。
- 自动选择电源和线径。
- RK3588 与 RK3568 分布式计算。
- NPU/GPU优化。
- 云服务。
- 摄像头实时输入。
- 完整Web管理后台。
- 声称完成真实硬件验收。
- 为保持 v1 二进制协议而牺牲新架构；如保留 v1，只能是显式 legacy 模式。

## 14. 实施原则

- 先审计，再计划，再实现。
- 优先复用已经通过验证的视频、音频、效果和映射代码。
- 解决根因，不添加临时旁路。
- 不以巨大重写代替必要迁移。
- 每个阶段保持测试可运行。
- 对协议、配置和安全行为写文档。
- 对无法在当前环境验证的硬件行为明确标记 `NOT HARDWARE VERIFIED`。
- 内部文件和类结构由你根据现有代码选择；如偏离本架构边界，必须在计划中说明理由和权衡。

## 15. Claude Code 的第一阶段输出要求

第一次运行请处于 Plan Mode，禁止编辑文件。完成以下内容：

1. 运行或检查基线测试。
2. 阅读相关模型、效果、映射、引擎、输出、CLI、配置和测试。
3. 列出真实调用链与状态所有权。
4. 确认上述已知缺口，补充遗漏问题。
5. 提出分阶段实施计划。
6. 指出每阶段修改的接口和受影响模块。
7. 指出迁移兼容策略。
8. 指出风险、回滚点和验证命令。
9. 只在存在会改变硬件线序、协议字节布局或安全状态的阻塞歧义时提问。
10. 不要在计划获批前修改代码。

计划获批后，在新的干净会话中实施，并持续运行验证。
