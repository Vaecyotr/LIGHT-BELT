# RK3588 一键部署

适用目标为 NanoPC-T6 / RK3588、Ubuntu 22.04、aarch64、用户 `pi`、GNOME Wayland，仓库位于 `/home/pi/LIGHT-BELT`。

## 目标

默认部署执行以下独立步骤。

- SSH / Avahi / `iw` / mpv / 基础工具
- 固定 `uv 0.9.5` 和可下载的 CPython `3.11.14`，已有有效 Python 3.11 环境继续复用
- 独立关闭 APT 自动更新及更新、升级、Apport 提示，安全禁用 `jammy-proposed`
- 只安装缺少的系统依赖，使用 `--no-upgrade`，不执行系统 upgrade/dist-upgrade
- mDNS 动态生成 `config/runtime/wled-ddp-mdns.yaml`
- 安装 Host 用户服务和 user linger，GNOME 登录时自动导入实际 Wayland 会话
- 安装 BlueZ/PulseAudio、无人值守配对、公共可发现模式和 RT5616 默认输出
- 安装 `systemd --user` Bluetooth/local-media priority service
- mpv 使用原生 Wayland/EGL，在图形会话建立后立即创建全屏黑窗口
- 自动验收 8443、Host API、mpv socket、runtime、监管域等

## 前置条件

1. 厂家镜像应优先固化正确 RK3588 BSP、Wi-Fi/Bluetooth 驱动、SSH、Avahi、`iw` 和销售地区 regulatory domain。
2. 仓库已经 clone 到 `/home/pi/LIGHT-BELT`。
3. 已安装 GNOME Wayland。图形登录策略保持现有配置，黑幕在 `pi` 图形会话建立后显示。
4. 不要用 `sudo` 启动整个 bootstrap；脚本会在必要步骤自行请求 sudo。

## 使用

```bash
cd /home/pi/LIGHT-BELT && bash scripts/bootstrap-rk3588.sh
```

默认不修改桌面背景、全局通知、锁屏、休眠或 GDM 自动登录。需要原有 Kiosk 设置时显式执行 `bash scripts/bootstrap-rk3588.sh --configure-kiosk`。独立更新策略在两种模式下都先于包安装执行。

部署不需要临时 `export` Python 版本、显示编号或认证信息。JWT 和配对码首次生成后保存在 `~/.config/light-belt/host.env`，权限为 `0600`。若旧 `/etc/light-belt/host.env` 已存在且有效，先迁移其内容并保留原文件。无效的已有凭据会明确报错，不静默轮换。配对码可由 `pi` 运行 `grep '^LIGHT_BELT_PAIRING_CODE=' ~/.config/light-belt/host.env` 查看。

成功结尾：

```text
LIGHT-BELT RK3588 DEPLOYMENT: PASS
LIGHT-BELT RK3588 BOOTSTRAP: PASS
```

## 设计边界

### Python 安装前检查

平台检查和 `setup-python.sh --check` 在系统策略或软件安装前运行。固定组合来自 uv 0.9.5 的下载索引，其中包含 Linux aarch64 GNU 的 CPython 3.11.14。已有相同 uv 会实际列出并核对构建，缺少或不同版本的 uv 在正式安装时收敛到固定版本。已有 `.venv` 必须属于 Python 3.11，禁止自动重建或降级它。声明与 `uv.lock` 不一致时停止。

固定构建依据为 [uv 0.9.5 下载元数据](https://github.com/astral-sh/uv/blob/0.9.5/crates/uv-python/download-metadata.json)。播放器的立即窗口和原生 Wayland 选项按 [mpv 0.34.1 手册](https://github.com/mpv-player/mpv/blob/v0.34.1/DOCS/man/options.rst) 核对，实际显示验收使用 [`vo-configured` 属性](https://github.com/mpv-player/mpv/blob/v0.34.1/DOCS/man/input.rst)。

### 独立系统更新策略

`setup-update-policy.sh` 管理 APT periodic 配置、APT 定时器、发行版升级和 Apport 提示，以及针对更新/崩溃通知的 autostart 覆盖。它不依赖 Kiosk 模块，不全局关闭 GNOME 通知。`--check` 只读核对文件、定时器和实际生效的 `apt-config` 值。

APT/dpkg 事务运行时会拒绝部署，不杀进程。正常的 `unattended-upgrades.service` 关机等待进程不算活动更新事务。源配置支持传统 `.list` 和 deb822 `.sources`，只移除或禁用 `jammy-proposed`，保留其他 suite、仓库选项和注释，并添加负优先级 pin。已安装的 proposed 包保留，需按设备软件清单人工核查其来源。手动 `sudo apt-get update` 和受控安装能力保留。

修改前对已有文件做一次 `.light-belt.bak` 备份，重复执行不重复创建备份。APT 源、更新策略和 BlueZ 配置采用同目录原子替换。未知源格式或配置链接会报错，避免覆盖到其他位置。

### Host 与图形会话

当前 Host 为 `systemd/user/light-belt-host.service`。user linger 让 API 随开机启动，GNOME autostart 的 `start-host-session.sh` 在登录时导入真实的 `WAYLAND_DISPLAY` 并重启 Host。不会固定 `wayland-0`、`DISPLAY=:0`、UID 1000 或 Xauthority。mpv IPC 位于 `/run/user/<pi-uid>/light-belt/mpv.sock`，由用户服务的 `RuntimeDirectory` 管理。

旧系统 Host 和旧系统 default-sink 服务会停用，原 unit 文件保留。Host、RT5616 默认音频和优先级服务在用户作用域运行，BlueZ 配对及公共发现服务在系统作用域运行。原生 PulseAudio 是已批准的音频路线，检测到活动 `pipewire-pulse` 时会停止并保留已有音频栈。

没有图形会话时，API 可以启动，黑幕等待 GNOME 登录。存在图形会话时，验收还要求 mpv IPC 应答、`vo-configured=true`、`fullscreen=true` 和 Wayland context。显示器上的黑幕、GPU 驱动与重启生命周期仍需实机验收，不能由 API ready 代替。

### 不固化 runtime IP

`config/runtime/wled-ddp-mdns.yaml` 每次由 `scripts/runtime/resolve_nodes.py` 根据现场 mDNS 生成。未解析节点会被 disabled，而不是把旧 IP 带到新设备。

### 不自动开启后台 Git 更新

bootstrap 会安装并启用 Host、Bluetooth 配对/公共模式、RT5616 默认输出等必要服务。

以下默认不 enable：

- `lb-update.timer`
- `lb-backup-data.timer` 和 `hdmi-setup.service` 保持原策略，不随部署开启

`lb-update.timer` 即使曾被开启也会在默认部署中停止并禁用。手动 LIGHT-BELT 更新器控制当前用户 Host，并在图形会话存在时核对实际 mpv 输出就绪状态。

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
- **NOT HARDWARE VERIFIED：** 当前实现、0.20 秒恢复体验，以及 Host/音频用户服务的 reboot/no-SSH 生命周期，必须在当前 NanoPC-T6 重新验收。

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

bootstrap 在修改 Python 环境前停止运行中的 Host，失败时尝试恢复之前的运行及启用状态，避免迁移失败后开机启动两个 Host。单独运行 Python 安装器时仍拒绝修改活跃 Host 的环境。安装与更新共用环境锁。缺少旧依赖缓存且网络不可用时，恢复可能失败，日志会明确报告。系统包和已经应用的独立更新策略不做自动降级回滚。

以上新增安装与恢复分支完成本地软件验证后，仍须在当前设备验收：**NOT HARDWARE VERIFIED**。Windows 开发环境使用 `scripts/dev/bootstrap_python.ps1`；共享 `.python` 连接只验证，不同步、不重建。

## NanoPC-T6 实机验收

以下步骤需在目标设备上执行。当前 RT5616 profile、真实 A2DP 音频、可见黑幕与冷启动均为 **NOT HARDWARE VERIFIED**。

**首次部署。** 在 `pi` 的 GNOME Wayland 会话内运行默认部署。RT5616 服务从 PulseAudio 查询本机声卡、profile 和 sink。已有可用输出时沿用当前 profile。仅有输入时选择同一卡的可用输出 profile，优先保留输入能力。服务等待输出出现后设置默认 sink，只显式迁移已有的 A2DP 策略流。A2DP loopback 由 PulseAudio 蓝牙策略创建。

若服务报错，先用这些只读命令区分 ALSA 未枚举、PulseAudio 未发布输出 profile，以及输出 profile 已启用但 sink 未出现。只有输入能力的声卡无法靠设置默认 sink 变成可播放设备，需根据 ALSA 清单核对 BSP、声卡驱动和 UCM 配置。

```bash
cat /proc/asound/cards
command -v aplay >/dev/null && aplay -l
pactl --format=json list cards
pactl --format=json list sinks
pactl get-default-sink
journalctl --user -u light-belt-audio-default-sink.service -b --no-pager -n 100
```

首次部署后运行完整检查。 `--require-wayland` 用于验收，图形会话缺失会返回失败。默认安装检查允许等待图形登录。

```bash
cd /home/pi/LIGHT-BELT
bash scripts/deploy/rk3588/verify-install.sh --require-wayland
cat /proc/sys/kernel/random/boot_id
sha256sum ~/.config/light-belt/host.env
uname -m
printf '%s\n' "$XDG_SESSION_TYPE" "$WAYLAND_DISPLAY"
./.venv/bin/python -V
~/.local/bin/uv --version
bash scripts/deploy/rk3588/setup-python.sh --check
bash scripts/deploy/rk3588/setup-update-policy.sh --check
systemctl list-timers --all apt-daily.timer apt-daily-upgrade.timer lb-update.timer
apt-cache policy libc6
loginctl show-user pi -p Linger
systemctl --user is-enabled light-belt-host.service light-belt-audio-default-sink.service light-belt-bluetooth-priority.service
systemctl --user is-active light-belt-host.service light-belt-audio-default-sink.service light-belt-bluetooth-priority.service
curl --fail http://127.0.0.1:8443/api/v1/status
./.venv/bin/python -m host_services.runtime_health --mpv-socket "/run/user/$(id -u)/light-belt/mpv.sock"
bluetoothctl show
pactl info
pactl get-default-sink
pactl list short modules
bash scripts/deploy/rk3588/set-default-audio-sink.sh --check
journalctl --user -u light-belt-host -u light-belt-audio-default-sink -u light-belt-bluetooth-priority -b --no-pager -n 100
```

目视确认登录后是全屏黑幕。手机配对并持续播放时，运行以下命令，确认 A2DP source、策略 loopback 与 RT5616 目标 sink，并听测实际声音。再启动本地媒体，确认蓝牙播放期间本地媒体被抑制，断开后恢复。

```bash
pactl list short sources
pactl list short source-outputs
pactl list short sink-inputs
pactl list short sinks
bash scripts/deploy/rk3588/set-default-audio-sink.sh --check
```

**重复部署。** 记录凭据文件摘要、更新策略和当前桌面设置，重复执行默认部署后核对记录。音频 oneshot 每次部署会重新执行，已正确的 profile 不会被重复切换。

可在重复部署前后各运行 `gsettings get org.gnome.desktop.session idle-delay`、
`gsettings get org.gnome.desktop.screensaver lock-enabled` 和
`gsettings get org.gnome.desktop.notifications show-banners`，核对值保持一致。
若设备使用 `/etc/gdm3/custom.conf`，可同时比对 `sudo sha256sum /etc/gdm3/custom.conf`。

```bash
cd /home/pi/LIGHT-BELT
credentials_before=$(sha256sum ~/.config/light-belt/host.env)
bash scripts/bootstrap-rk3588.sh &&
test "$credentials_before" = "$(sha256sum ~/.config/light-belt/host.env)" &&
bash scripts/deploy/rk3588/verify-install.sh --require-wayland
```

**重启验收。** 记录 `cat /proc/sys/kernel/random/boot_id` 的输出，再执行 `sudo reboot`。按设备现有 GDM 登录策略进入 `pi` 图形会话，在没有 SSH 会话帮助的情况下先目视确认黑幕，然后从本机终端运行 `verify-install.sh --require-wayland`，确认 boot ID 已变化、三个用户服务在当前启动中成功运行，并重新做手机播放检查。默认部署保留原有 Kiosk/GDM 设置。
