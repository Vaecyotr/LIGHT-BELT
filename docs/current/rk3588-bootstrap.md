# RK3588 一键部署

适用目标：NanoPC-T6 / RK3588、Ubuntu 22.04、正式用户 `pi`、仓库 `/home/pi/LIGHT-BELT`。

## 目标

把已经在实机验证过的系统配置和项目部署收敛成一次执行：

- SSH / Avahi / `iw` / mpv / 基础工具
- `uv` + Python 3.11.16 + `.venv` + Host 依赖
- GNOME kiosk 设置：黑底、禁通知、禁锁屏/休眠、禁止发行版升级弹窗
- mDNS 动态生成 `config/runtime/wled-ddp-mdns.yaml`
- 安装并 enable `light-belt-host.service`
- 安装 BlueZ/PulseAudio、无人值守配对、公共可发现模式和 RT5616 默认输出
- 安装 `systemd --user` Bluetooth/local-media priority service
- Host 启动后 mpv 永久全屏黑幕；播放器源码不再强制 `--vo=xv`
- 自动验收 8443、Host API、mpv socket、runtime、监管域等

## 前置条件

1. 厂家镜像应优先固化正确 RK3588 BSP、Wi-Fi/Bluetooth 驱动、SSH、Avahi、`iw` 和销售地区 regulatory domain。
2. 仓库已经 clone 到 `/home/pi/LIGHT-BELT`。
3. 当前仓库必须包含 `systemd/light-belt-host.service`，且不能再有旧 `topeet` 路径。
4. 不要用 `sudo` 启动整个 bootstrap；脚本会在必要步骤自行请求 sudo。

## 使用

```bash
cd ~/LIGHT-BELT
bash scripts/bootstrap-rk3588.sh
```

成功结尾：

```text
LIGHT-BELT RK3588 DEPLOYMENT: PASS
LIGHT-BELT RK3588 BOOTSTRAP: PASS
```

## 设计边界

### 不固化 runtime IP

`config/runtime/wled-ddp-mdns.yaml` 每次由 `scripts/runtime/resolve_nodes.py` 根据现场 mDNS 生成。未解析节点会被 disabled，而不是把旧 IP 带到新设备。

### 不自动开启后台 Git 更新

bootstrap 会安装并启用 Host、Bluetooth 配对/公共模式、RT5616 默认输出等必要服务。

以下默认不 enable：

- `lb-update.timer`
- `lb-backup-data.timer`
- `hdmi-setup.service`

原因是它们仍需要单独的产品级验收，避免调试期间后台改变代码或显示模式。

### Bluetooth 路由所有权

NanoPC-T6 历史实机已经冻结以下路线：

```text
phone/tablet A2DP
  -> bluez_source
  -> PulseAudio module-bluetooth-policy
  -> one policy-managed module-loopback
  -> alsa_output.platform-rt5616-sound.stereo-fallback
```

PulseAudio Bluetooth policy 是 A2DP 路由的唯一所有者。LIGHT-BELT 不创建
`module-loopback`。部署会幂等删除旧的
`bluetooth-audio-loopback.service`/helper，并且只卸载含
`latency_msec=80` 的已知旧 loopback，不会删除 policy 管理的有效路线。

`bluetooth-auto-agent` 以 `NoInputNoOutput` 提供无人值守配对；
`bluetooth-public-mode` 保持设备 powered、pairable、discoverable。该公共配对策略
允许附近设备请求配对，属于产品安全风险，现场部署需要在物理访问策略中考虑。

### Bluetooth/local-media 音频优先级

Host 启动 mpv 时设置 PulseAudio application identity：

```text
LIGHT-BELT-LocalMedia
```

`light-belt-bluetooth-priority.service` 是 `pi` 的 `systemd --user` unit，直接使用
该用户的 PulseAudio session，不注入手工 `PULSE_SERVER`/XDG/DBus 环境。它监听
`pactl subscribe`：任意匹配 `bluez_source.*.a2dp_source` 的 source 进入
`RUNNING` 时，立即临时 mute 当前 `LIGHT-BELT-LocalMedia` sink-input；视频、时间线、
灯光分析和同步继续运行。Bluetooth 持续 inactive 约 `0.20 s` 后才释放本服务拥有
的 suppression；短暂切歌/缓冲恢复为 `RUNNING` 时不会漏出本地音频。普通用户/app
mute 仍由现有 mpv 控制，二者不是同一个状态。

优先级服务仅对它在原本未 mute 的 stream 上施加的 suppression
标记所有权，重启后也可依据该标记恢复；启动前已存在的外部 mute 不会被解除。
PulseAudio 只暴露单一 mute 位：如果外部控制在 stream 已被本服务 mute
期间再次写入同样的 mute 值，它不会提供可靠的第二个所有权信号。
产品的普通用户/app mute 因此仍应通过独立的 mpv 状态表达。

### 验证状态

- **历史实机验证：** native PulseAudio policy 的唯一 A2DP 路线、RT5616 默认 sink、
  清除重复 `latency_msec=80` 路线后无重音、断开重连和整机重启后重连。
- **历史 prototype/user-observed：** 以 A2DP source `RUNNING` 判断优先级、
  `LIGHT-BELT-LocalMedia` 身份、sink-input mute 保持视频运行、事件驱动订阅。
- **当前软件验证目标：** ownership-safe suppression、动态 stream discovery、
  0.20 秒 transition-only debounce 及部署静态不变量。
- **NOT HARDWARE VERIFIED：** 当前合并实现、0.20 秒恢复体验，以及 provisional
  `systemd --user` unit 的 reboot/no-SSH 生命周期，必须在当前 NanoPC-T6 重新验收。

### Wi-Fi regulatory domain

bootstrap 会：

- 安装 `iw`
- 写 `/etc/modprobe.d/regdom.conf`
- 尝试 `iw reg set CN`
- 在最终验收读取 `/sys/module/cfg80211/parameters/ieee80211_regdom`

但不会盲目修改 bootloader。若内核仍显示 `00`，应由厂家镜像/bootloader 固化 `CN` 后再验收。

## 重复执行

apt、服务安装、Bluetooth cleanup、runtime 生成和 GNOME 设置按幂等思路设计；重复安装不会创建第二套服务或第二条 Bluetooth loopback。

Python 安装与更新共用固定版本 `uv 0.9.5` 的锁定同步逻辑，以 `pyproject.toml` 和 `uv.lock` 为依据，生产安装只选 Host 依赖。现有兼容 `.venv` 不自动重建或切换解释器；声明与锁不一致时失败。系统蓝牙服务仍使用系统 Python，不能混入 Host 环境。

重新运行 bootstrap 前先明确停止 Host，或使用已完成本地验证的事务式更新入口；安装器在 Host 运行时拒绝修改依赖。安装与更新共用同一环境锁，不能并发执行。更新器不自动启用原先禁用的定时器；同步、启动或健康检查失败时尝试恢复旧版本与旧锁对应环境。缺少旧依赖缓存且网络不可用时恢复仍可能失败，失败状态及恢复文件会明确保留。

以上新增安装与恢复分支完成本地软件验证后，仍须在当前设备验收：**NOT HARDWARE VERIFIED**。Windows 开发环境使用 `scripts/dev/bootstrap_python.ps1`；共享 `.python` 连接只验证，不同步、不重建。
