# WLED Audio Sync V2 输入合同

本文记录 LIGHT-BELT 当前已经落地的只读 UDP 音频输入适配器。它不是 WLED runtime、效果兼容层、Host API
或固件实现。线缆、组播网络、丢包率、时钟抖动和灯带观感均 **NOT HARDWARE VERIFIED**。

## 44-byte wire layout

唯一上游布局依据固定为 WLED `v16.0.1`、commit
[`29b389df1c1aaec6ff53aea742d17063b985906c`](https://github.com/wled/WLED/commit/29b389df1c1aaec6ff53aea742d17063b985906c)
源码中的 packed `audioSyncPacket`：
[audio_reactive.cpp](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp#L799-L811)。
LIGHT-BELT 使用显式 little-endian `struct` 格式 `<6s2sffBB16sHff`，只接受恰好 44 bytes：

| Offset | Size | LIGHT-BELT 解码名 | 合同 |
| ---: | ---: | --- | --- |
| 0 | 6 | header | 必须逐 byte 等于 `00002\0` |
| 6 | 2 | reserved | 接受并忽略，避免把扩展位误当错误 |
| 8 | 4 | sample raw | finite、非负 float；原值成为 generic `raw_level`，不假定已 normalized |
| 12 | 4 | smoothed sample | finite、非负 float；`min(value / 255, 1)` 成为 normalized loudness |
| 16 | 1 | peak | 非零映射为 generic boolean peak |
| 17 | 1 | reserved | 接受并忽略 |
| 18 | 16 | FFT bands | `transmitAudioData()` 将内部值 clamp 到 `0..254`；wire byte 严格除以 `254.0`，成为 immutable `[0,1]` 16-tuple；`255` 非 canonical，decoder 拒绝 |
| 34 | 2 | reserved | 接受并忽略 |
| 36 | 4 | FFT magnitude | finite、非负 `dominant_magnitude` |
| 40 | 4 | FFT major peak | finite、非负 Hz `dominant_frequency` |

长度、header 或任一 float 合法性不满足时，整个 datagram 无效；适配器跳过它并增加 invalid 诊断计数。
任一 FFT band 为 `255` 时同样无效。WLED 内部 `fftResult` 即使可到 255，固定 v16.0.1 的
[`transmitAudioData()`](https://github.com/wled/WLED/blob/29b389df1c1aaec6ff53aea742d17063b985906c/usermods/audioreactive/audio_reactive.cpp)
在写入 V2 packet 前会将 band clamp 到 254；因此 254 才是 live wire 的 normalized full scale。
这不是 WLED 效果值或参数槽的数值兼容合同。

## Generic 16-band adapter

`AudioFeatures` 保存非 normalized `raw_level`、normalized `loudness`、immutable 16-band
`spectrum`、`peak`、`dominant_frequency` 与 `dominant_magnitude`。它继续向旧效果派生兼容字段：
`rms = loudness`，`bass = mean(bins 0..2)`，`mid = mean(3..9)`，
`treble = mean(10..15)`，`beat = peak`。`spectral_flux` 和 `onset` 都在 source drain 中由相邻合法
spectrum 的 positive-only 差计算；`silence` 由 loudness 与 spectrum 阈值计算。适配器和效果不读取
WLED C++ 字段名。

`dominant_frequency` 只记录声音测量事实。LIGHT-BELT 没有“低频=红、高频=蓝”之类的全局视觉映射；
频率如何影响颜色、速度或位置必须由具体 Effect 自己定义。

## 明确不可用的 `fftBin`

WLED 本地 Audio Reactive 实现可以拥有 wire 之外的分析器状态或控件，但 44-byte Audio Sync V2
packet **不广播 `fftBin`**。因此当前 LIGHT-BELT 不拥有该数据，也不从 16-band spectrum 虚构一个同名值。
本阶段不修改协议；需要该输入的未来迁移必须先按 inventory 分类为近似或输入扩展需求。

旧文件分析和合成输入仍可构造 `rms/bass/mid/treble/beat`；模型会提供 generic loudness/peak alias。
当前文件分析器不制造虚假的 16-band 数据，未提供时 spectrum 为 16 个零。

## Drain、fresh 与 stale

一次 `poll(show_timestamp)` 会以 nonblocking `recvfrom` 排空当前 socket：

- 连续值取 drain 中最后一个合法 packet；无效 packet 不覆盖合法状态。
- peak 对 drain 中全部合法 packet 做 OR，避免短 peak 在排空时丢失。
- flux 严格按合法 packet 的实际接收顺序逐一比较，返回该 drain 中最大的 positive transition。
- 没有新 packet 但 packet age 尚未达到 stale threshold 时，保留连续值，同时清零
  peak/beat/spectral_flux/onset。
- `packet_age >= stale_after` 时返回全零特征，并且每次 fresh→stale 只清除一次 spectrum history。
- stale 后第一个恢复 packet 不与 stale 前 spectrum 比较；同一恢复 drain 的后续合法 packet 仍按顺序比较。
- `reset()` 清除 retained values、age 和 flux history，但不关闭 socket；`close()` 离开 multicast 并关闭。

诊断包含 open/stale、packet age、received/valid/invalid、stale transitions、reset count、最后错误和 sender。

## Source priority 与 Engine 生命周期

当前 Engine 音频优先级是：已加载音频文件 > 配置的 live WLED Audio Sync V2 > synthetic source > `None`。
文件音频存在时 live source 不打开。live 已配置但 stale 时返回零特征，不偷偷降级到 synthetic。Engine 在
fresh→stale 时重置 music-control history；媒体时间线 reset/seek 同时 reset live source 和效果状态。
live source 的 bind/join 失败会让 Engine 启动显式失败，不会制造成功。

## RK3588 Profile 语义

`config/profiles/rk3588-host-service.yaml` 只覆盖：

```yaml
system:
  audio:
    source: {kind: wled_audio_sync_v2}
```

其余值由 `config/system.yaml` 合并提供：multicast `239.0.0.1`、UDP port `11988`、interface
`0.0.0.0`、`stale_after_ms: 250`，audio update rate 为 60 Hz。`interface_ipv4: 0.0.0.0` 表示默认
IPv4 interface，不是远端 sender 地址。Windows development 默认 `kind: disabled`；fake/memory 输入仍需显式选择。

该 Profile 同时配置 RK3588 主机向九个 ESP32 节点发送 DDP，但 DDP 输出与 Audio Sync V2 输入是两个独立 UDP
合同。本文不声称运行上游 WLED 的 ESP32 节点已启用 audio-reactive usermod、已发送 multicast，或 RK3588 网络已放行组播；
以上均 **NOT HARDWARE VERIFIED**。
