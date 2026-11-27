# RK3588 统一生产架构验收

在隔离的 NanoPC-T6 上按[一键部署手册](rk3588-bootstrap.md)安装 `https://github.com/Vaecyotr/LIGHT-BELT.git` 的 `1126` 批准提交，以 `pi` 账户执行设备命令。使用两部测试手机和第三部已配对的验证手机，记录机型、APP 版本、Host 提交、镜像、控制器固件和媒体版本。现场结果均为 **NOT HARDWARE VERIFIED**。

## H1 · 镜像、声卡、显示和控制网络

```bash
cd /home/pi/LIGHT-BELT
git status --short --branch
git branch -vv
git rev-parse HEAD
uname -a
cat /etc/os-release
bluetoothctl list
bluetoothctl show
pactl info
pactl get-default-sink
pactl --format=json list sinks
pactl list short modules
ip -br address
ss -ltnp 'sport = :8443'
bash scripts/deploy/rk3588/verify-install.sh
```

核对原生 PulseAudio、RT5616 输出、实际 `module-bluetooth-policy` 参数 `a2dp_source=false` 和蓝牙控制器。配置启用 TLS 时，使用设备证书所对应的受信地址。分别从舱内电脑和隔离验证端执行下列连通性检查，保留结果及实际接口、VLAN 或访问控制规则。舱内电脑应能访问，公网及不受信任网络的验证端应连不上控制端口。

从受控舱内电脑执行以下 PowerShell 命令。使用设备实际的 HTTP 地址或证书受信的 HTTPS 地址。先采集未插线状态，再插线并等待 PulseAudio 重新检测，执行下一段。`commit` 应与设备的 `git rev-parse HEAD` 及批准的发布提交一致。

```powershell
$HostUrl = 'http://192.168.31.236:8443' # 替换为设备实际地址和协议
function Get-Rt5616Check {
    $hostStatus = (Invoke-RestMethod "$HostUrl/api/v1/status" -ErrorAction Stop).data
    $audioStatus = (Invoke-RestMethod "$HostUrl/api/v1/audio" -ErrorAction Stop).data
    [pscustomobject]@{
        Commit = $hostStatus.commit
        Ready = $hostStatus.ready
        AudioOutputAvailable = $audioStatus.audio_output_available
    }
}
$BeforeCable = Get-Rt5616Check
```

```powershell
$AfterCable = Get-Rt5616Check
$BeforeCable, $AfterCable | Format-Table -AutoSize
```

已确认目标 RT5616 sink 且端口明确等待插线时，预期 `Ready=True`、`AudioOutputAvailable=False`。插线后等待 RT5616 成为实际目标输出，再核对两项均为 `True`。若迟迟未恢复，读取 `/control/state` 的 `audio_output`，查看目标 sink、端口和原因。

```powershell
$CabinAddress = '192.168.31.236' # 替换为本次设备实际地址
Test-NetConnection -ComputerName $CabinAddress -Port 8443
Invoke-RestMethod "https://${CabinAddress}:8443/api/v1/status"
```

HTTP 部署将 URL 改为 `http`。核对星空顶的实际地址、端口和设备资料，再采集一条正常触发的网络包和目视结果。默认值 `192.168.31.205:3333` 必须以现场拓扑核准。

## H2 · 双手机准入与唯一扬声器赢家

藉由[正式控制接口](../reference/host-control-api.md)完成两部手机连接，依次验证 A 先播、B 后播、手选 B、B 暂停或断开后 A 接班。随后用第三部已配对手机尝试自动回连。使用本机 HCI 记录辨别第三条链路是否一度实际建立，记录两部手机是否保持连接以及获选手机是否始终只有一台。API 的 `CONNECTION_LIMIT` 和事后断开记录分别保留。

```bash
sudo btmon -w /tmp/light-belt-h2.btsnoop
```

在另一终端于每个切换点采集：

```bash
pactl --format=json list sink-inputs
pactl --format=json list source-outputs
pactl list short modules
journalctl --user -u light-belt-host.service -b --no-pager -n 100
```

应有一条 Host 验证的获选手机可听路由。使用实机听感、路由读回及 HCI 证据核对出声、准入和曲目切换。采集包含设备标识时，分享前脱敏。

## H3 · 定向 PCM 与节目音频恢复

让节目播放含已知音轨的片段。用两部手机播放可区别的音频，例如 A 播语音、B 播节奏信号，按 H2 切换获选手机。切换前后保存 `pactl --format=json list sink-inputs`、`pactl --format=json list source-outputs`、`/control/state` 及 `/api/v1/playback/state`。`analysis` 的数字源应与获选手机或节目对应。比对源索引时同时记录归属和目标 sink，复用同一索引时重新核验。

分别让 B 暂停、断开和重新接入，验证视频位置连续，节目原声按当前 `user_muted` 恢复。获选手机播放期间在正式接口修改用户静音，然后断开手机，重复验证恢复行为。让数字源失效，确认状态报告数字故障，再明确选择麦克风并复测灯光分析。

```powershell
Invoke-Control PUT '/control/analysis' @{ mode = 'auto' }
Invoke-Control POST '/api/v1/audio/set' @{ muted = $true }
Get-ControlState | ConvertTo-Json -Depth 12
Invoke-Control POST '/api/v1/audio/set' @{ muted = $false }
Invoke-Control PUT '/control/analysis' @{ mode = 'mic' }
Get-ControlState | ConvertTo-Json -Depth 12
Invoke-Control PUT '/control/analysis' @{ mode = 'auto' }
```

`Invoke-Control` 和 `Get-ControlState` 从[控制接口指南](../reference/host-control-api.md)加载。采集过程避免创建额外 PulseAudio loopback。

## H4 · 局域网直接联调与正式 APP

先在没有 APP 的条件下使用电脑和正式接口指南，完成新手机搜索、入站或主动配对、挑战确认、连接、双手机播放权选择、实际音乐和灯光联动、断开、忘记。另留一部部署前已配对的手机，验证跨版本重连。复现过期、拒绝、取消和关闭窗口后重放原挑战的结果。

再换正式 APP，分别记录冷启动、恢复使用、节目开播、WS 掉线重连、配对和控制。日志保留脱敏请求路径、HTTP 状态及随后发生的 APP 行为。若旧 APP 仍依赖 Pair 或 Refresh 并因此停止业务流程，保留可复现轨迹和客户端版本。

## H5 · DDP 接班、显光与辅助设备

```bash
cd /home/pi/LIGHT-BELT
grep -E 'host:|enabled:' config/runtime/wled-ddp-mdns.yaml
pgrep -af 'light_engine[.]managed'
sudo tcpdump -ni any -s0 -w /tmp/light-belt-h5.pcap 'udp port 4048 or udp port 3333'
```

按节目→手机音乐→手动效果、Seek、换片、节目灯效先于媒体结束、显式关灯、无接班 EOF 的顺序执行，按节点检查实际报文、帧序和切换间隔。并用摄像或光学观测确认无旧色闪现和非预期黑间隔。关灯后分别调亮度、调用 V1 开播、重发旧恢复版本和重启，检查拒绝结果与实际熄灯。用 WLED `GET /json/si` 记录相应节点 `state.on` 和 `info.live`，把本机提交时间、设备读回和物理显光分开记录。对星空顶执行手动开关和含辅助触发的节目 Seek，比对实际地址和每次数据报，记录有无设备反馈。

## H6 · 上电、掉电、黑幕、全片和长稳

在无 SSH 帮助的情况下重复上电，先核对 API 在图形登录前可用，再登录 `pi` 查看黑幕和 mpv 全屏。重复一次正常重启和一次隔离台架掉电。每次启动运行：

```bash
cd /home/pi/LIGHT-BELT
cat /proc/sys/kernel/random/boot_id
bash scripts/deploy/rk3588/verify-install.sh --require-wayland
systemctl --user status light-belt-host.service --no-pager
journalctl --user -u light-belt-host.service -b --no-pager -n 200
```

播放全片到 EOF，分别覆盖有接班和无接班，检查最后帧、音频、进程和灯带的回落。记录约定的长稳窗口及 CPU、内存、进程重启、PCM 中断、DDP 丢帧和黑幕状态。以实际测得的结果填写现场报告。
