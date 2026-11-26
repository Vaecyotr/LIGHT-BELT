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
- 保留 BlueZ A2DP 发现、原生 PulseAudio、声卡和 RT5616 默认输出；Host 管理配对及可听路由
- mpv 使用原生 Wayland/EGL，在图形会话建立后立即创建全屏黑窗口
- 自动验收 8443、Host API、mpv socket、runtime、监管域等

## 前置条件

1. 厂家镜像应优先固化正确 RK3588 BSP、Wi-Fi/Bluetooth 驱动、SSH、Avahi、`iw` 和销售地区 regulatory domain。
2. 统一版本源码位于 `/home/pi/LIGHT-BELT`。
3. 已安装 GNOME Wayland。图形登录策略保持现有配置，黑幕在 `pi` 图形会话建立后显示。
4. 不要用 `sudo` 启动整个 bootstrap；脚本会在必要步骤自行请求 sudo。

## 使用

```bash
cd /home/pi/LIGHT-BELT && bash scripts/bootstrap-rk3588.sh
```

默认不修改桌面背景、全局通知、锁屏、休眠或 GDM 自动登录。需要原有 Kiosk 设置时显式执行 `bash scripts/bootstrap-rk3588.sh --configure-kiosk`。独立更新策略在两种模式下都先于包安装执行。

部署保留已有 TLS 证书、环境文件和用户数据。退役的 JWT、配对码及网页登记凭据不再读取或生成。

### 设备进入统一部署的三种路径

以下使用 `1125-full-update` 作为统一版本的分支示例。执行前将 `UnifiedBranch` 改为现场批准的实际发布分支，并与发布清单核对提交。

新设备直接克隆并安装：

```bash
(
  set -e
  UnifiedBranch=1125-full-update
  cd /home/pi
  git clone --branch "$UnifiedBranch" --single-branch https://github.com/zxlzzz/LIGHT-BELT.git LIGHT-BELT
  cd /home/pi/LIGHT-BELT
  git rev-parse HEAD
  bash scripts/bootstrap-rk3588.sh
)
```

旧系统先用 Git 获取新版，再运行新版安装器（不依赖旧更新器的分支设置）：

```bash
(
  set -e
  UnifiedBranch=1125-full-update
  cd /home/pi/LIGHT-BELT
  git status --short --branch
  test -z "$(git status --porcelain)" || { echo '工作树有更改，停止安装' >&2; exit 1; }
  PreviousBranch=$(git branch --show-current)
  PreviousCommit=$(git rev-parse HEAD)
  git remote set-branches --add origin "$UnifiedBranch"
  git fetch origin "refs/heads/$UnifiedBranch:refs/remotes/origin/$UnifiedBranch"
  if git show-ref --verify --quiet "refs/heads/$UnifiedBranch"; then
    git switch "$UnifiedBranch"
    git merge --ff-only "origin/$UnifiedBranch"
    git branch --set-upstream-to="origin/$UnifiedBranch"
  else
    git switch --track -c "$UnifiedBranch" "origin/$UnifiedBranch"
  fi
  test "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$UnifiedBranch")"
  git rev-parse HEAD
  LIGHT_BELT_PREVIOUS_BRANCH="$PreviousBranch" LIGHT_BELT_PREVIOUS_COMMIT="$PreviousCommit" \
    bash scripts/bootstrap-rk3588.sh
)
```

已运行统一版本的系统，确认工作树干净及 upstream 后使用事务更新器：

```bash
cd /home/pi/LIGHT-BELT
git status --short
git branch -vv
bash scripts/maintenance/update.sh
```

更新器默认使用当前分支配置的 upstream，也可通过
`LIGHT_BELT_UPDATE_BRANCH=origin/1125-full-update` 显式指定。三条路径保留设备数据、证书及有效本地配置，并最终使用同一套服务和音频配置。

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

旧系统 Host/default-sink 服务会停用，Host 和 RT5616 默认音频在用户作用域运行。安装前从 pi 会话确认原生 PulseAudio 和实际 RT5616 sink；遇到 PipeWire-Pulse、无法识别的服务器或缺少 RT5616 sink 时，预检失败且不改动设备。

没有图形会话时，API 可以启动，黑幕等待 GNOME 登录。存在图形会话时，验收还要求 mpv IPC 应答、`vo-configured=true`、`fullscreen=true` 和 Wayland context。显示器上的黑幕、GPU 驱动与重启生命周期仍需实机验收，不能由 API ready 代替。

### 不固化 runtime IP

`config/runtime/wled-ddp-mdns.yaml` 每次由 `scripts/runtime/resolve_nodes.py` 根据现场 mDNS 生成。未解析节点会被 disabled，而不是把旧 IP 带到新设备。

### 不自动开启后台 Git 更新

bootstrap 会安装并启用 Host、BlueZ、RT5616 默认输出等必要服务，并停用已识别的旧公共配对/自动 Agent 和音频优先级服务。

以下默认不 enable：

- `lb-update.timer`
- `lb-backup-data.timer` 和 `hdmi-setup.service` 保持原策略，不随部署开启

`lb-update.timer` 即使曾被开启也会在默认部署中停止并禁用。手动 LIGHT-BELT 更新器控制当前用户 Host，并在图形会话存在时核对实际 mpv 输出就绪状态。

### Bluetooth 与音频路由

BlueZ 保留发现、配对记录和 A2DP 能力。Host 是设备配对确认、获选手机及可听路由的唯一策略所有者；部署停用可识别的旧公共模式、自动 Agent 和独立音频优先级服务。PulseAudio A2DP 自动 loopback 必须关闭，实际参数由部署预检和安装后读回确认。部署不按单一延迟值猜测路由所有权，也不会卸载未知 module-loopback。

pi 用户会话的原生 PulseAudio 和 RT5616 sink 是安装前置条件。PipeWire-Pulse、无法识别的服务端或 sink 缺失时预检失败。真实手机配对、播放路由、音视频体验和重启行为仍需设备验收。

### 验证状态

- **NOT HARDWARE VERIFIED：** 当前蓝牙配对、获选手机路由、音频恢复体验，以及 Host/音频用户服务的 reboot/no-SSH 生命周期，必须在当前 NanoPC-T6 重新验收。

### Wi-Fi regulatory domain

bootstrap 会：

- 安装 `iw`
- 写 `/etc/modprobe.d/regdom.conf`
- 尝试 `iw reg set CN`
- 在最终验收读取 `/sys/module/cfg80211/parameters/ieee80211_regdom`

但不会盲目修改 bootloader。若内核仍显示 `00`，应由厂家镜像/bootloader 固化 `CN` 后再验收。

## 重复执行

apt、服务安装、Bluetooth cleanup、runtime 生成和 GNOME 设置按幂等思路设计；重复安装不会创建重复服务或路由配置。

Python 安装与更新共用固定版本 `uv 0.9.5` 的锁定同步逻辑，以 `pyproject.toml` 和 `uv.lock` 为依据，生产安装只选 Host 依赖。现有兼容 `.venv` 不自动重建或切换解释器；声明与锁不一致时失败。系统蓝牙服务仍使用系统 Python，不能混入 Host 环境。

bootstrap 在修改 Python 环境前停止运行中的 Host，并记录将要变更的音频配置和服务文件。旧设备首次迁移命令还传入上一发布提交。失败时先恢复旧代码、锁定依赖、原音频配置、服务模板和启用状态，再启动原服务。如果恢复途中报错，脚本保留恢复文件并报告受影响的步骤。单独运行 Python 安装器时仍拒绝修改活跃 Host 的环境。系统包和独立更新策略保持现有维护政策。

以上新增安装与恢复分支完成本地软件验证后，仍须在当前设备验收：**NOT HARDWARE VERIFIED**。Windows 开发环境使用 `scripts/dev/bootstrap_python.ps1`；共享 `.python` 连接只验证，不同步、不重建。

## NanoPC-T6 实机验收

以下步骤需在目标设备上执行。当前 RT5616 profile、真实 A2DP 音频、可见黑幕与冷启动均为 **NOT HARDWARE VERIFIED**。

完整现场检查见 [H1–H6 验收命令](rk3588-unified-acceptance.md)和[无 APP 蓝牙联调](../reference/host-control-api.md)。

**首次部署。** 在 `pi` 的 GNOME Wayland 会话内运行默认部署。RT5616 服务从 PulseAudio 查询本机声卡、profile 和 sink。已有可用输出时沿用当前 profile。仅有输入时选择同一卡的可用输出 profile，优先保留输入能力。服务等待输出出现后设置默认 sink。手机可听路由由 Host 建立；PulseAudio policy 保留 A2DP source，但关闭自动 loopback。

若服务报错，先用这些只读命令区分 ALSA 未枚举、PulseAudio 未发布输出 profile，以及输出 profile 已启用但 sink 未出现。只有输入能力的声卡无法靠设置默认 sink 变成可播放设备，需根据 ALSA 清单核对 BSP、声卡驱动和 UCM 配置。

```bash
cat /proc/asound/cards
command -v aplay >/dev/null && aplay -l
pactl --format=json list cards
pactl --format=json list sinks
pactl get-default-sink
journalctl --user -u light-belt-audio-default-sink.service -b --no-pager -n 100
```

首次部署后运行软件检查。`--require-wayland` 要求图形会话就绪，默认安装检查允许等待图形登录。RT5616 已发布输出 sink 且活动端口明确报告 `not available` 时，部署登记 RT5616 为首选输出并将播放标记为 **NOT HARDWARE VERIFIED**。插线后由 PulseAudio 重新评估默认输出。声卡缺失、驱动通信异常或无法创建 sink 仍使部署失败。

```bash
cd /home/pi/LIGHT-BELT
bash scripts/deploy/rk3588/verify-install.sh --require-wayland
cat /proc/sys/kernel/random/boot_id
uname -m
printf '%s\n' "$XDG_SESSION_TYPE" "$WAYLAND_DISPLAY"
./.venv/bin/python -V
~/.local/bin/uv --version
bash scripts/deploy/rk3588/setup-python.sh --check
bash scripts/deploy/rk3588/setup-update-policy.sh --check
systemctl list-timers --all apt-daily.timer apt-daily-upgrade.timer lb-update.timer
apt-cache policy libc6
loginctl show-user pi -p Linger
systemctl --user is-enabled light-belt-host.service light-belt-audio-default-sink.service
systemctl --user is-active light-belt-host.service light-belt-audio-default-sink.service
curl --fail http://127.0.0.1:8443/api/v1/status
./.venv/bin/python -m host_services.runtime_health --mpv-socket "/run/user/$(id -u)/light-belt/mpv.sock"
bluetoothctl show
pactl info
pactl get-default-sink
pactl list short modules
bash scripts/deploy/rk3588/set-default-audio-sink.sh --check
journalctl --user -u light-belt-host -u light-belt-audio-default-sink -b --no-pager -n 100
```

目视确认登录后是全屏黑幕。接好音频线，通过 Host 正式业务接口配对手机并授予播放权；核对 PulseAudio 当前 A2DP route 实际落在 RT5616，并听测播放。再启动本地媒体，确认 Host 只管理获选手机的可听路由。

```bash
pactl list short sources
pactl list short source-outputs
pactl list short sink-inputs
pactl list short sinks
pactl list short modules
```

**重复部署。** 记录凭据文件摘要、更新策略和当前桌面设置，重复执行默认部署后核对记录。音频 oneshot 每次部署会重新执行，已正确的 profile 不会被重复切换。

可在重复部署前后各运行 `gsettings get org.gnome.desktop.session idle-delay`、
`gsettings get org.gnome.desktop.screensaver lock-enabled` 和
`gsettings get org.gnome.desktop.notifications show-banners`，核对值保持一致。
若设备使用 `/etc/gdm3/custom.conf`，可同时比对 `sudo sha256sum /etc/gdm3/custom.conf`。

```bash
cd /home/pi/LIGHT-BELT
bash scripts/bootstrap-rk3588.sh &&
bash scripts/deploy/rk3588/verify-install.sh --require-wayland
```

**重启验收。** 记录 `cat /proc/sys/kernel/random/boot_id` 的输出，再执行 `sudo reboot`。按设备现有 GDM 登录策略进入 `pi` 图形会话，在没有 SSH 会话帮助的情况下先目视确认黑幕，然后从本机终端运行 `verify-install.sh --require-wayland`，确认 boot ID 已变化、Host 与默认音频服务在当前启动中成功运行，并重新做手机播放检查。
