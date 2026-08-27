# LIGHT-BELT 网络架构 设计文档：板载 AP 自洽岛

> 版本：v0.2（Phase 41A 同步版）
> 日期：2026-08-25
> 状态：架构与部署语义已同步；RK3568 现场门禁尚未执行，见 §10。
> 本文档不声称硬件通过。所有未实测项均标记为 **NOT HARDWARE VERIFIED / NOT RUN**。

---

## 0. 原则说明

1. 本文档保留架构取舍与历史背景；可执行的 RK3568 硬件门禁集中在 §10。除 §10 外不把命令当作生产配置来源。
2. **不抄可从源文件读到的数值**。SSID、IP、像素数、MAC、GPIO 这些，本文档只给“建议值”或“去哪读”，真值以 `config/` 下生效文件和固件配置为准。文档里出现的地址（如 `192.168.50.1`）都是**占位建议值**，最终以实现阶段写进配置的为准，不要把本文档当数值来源。
3. 本方案与仓库现有 `design.md`（声音反应模式）不冲突，是同一套硬件上的**网络层**设计，两者可并存。

---

## 1. 一页速览

| 项 | 结论 |
|---|---|
| 核心决策 | 板子自己开热点（AP），9 节点 + 平板都连这个 AP，**灯光系统不依赖任何外部网络** |
| 免填 IP | APP→Host 可使用 Cabin AP 的固定网关；Host→WLED 仍必须走 stable hostname → Avahi/mDNS → dynamic IPv4，不依赖现场路由器 |
| 节点联网 | 节点永远只连“板子 AP”这一个恒定 SSID，跨场地零重配 |
| 上云/联网 | **可选**。上行可用 Ethernet、另一网络接口或现场 Wi-Fi；有网就上云/自更新，没网灯照常用 |
| 稳态操作 | 只有两个动作：给板子上电、让平板连板子热点 |
| 主要代价 | AP 能力取决于部署板卡与所选 Wi-Fi 接口；RK3568 实验使用外接 adapter，NanoPC-T6 未来使用预装 combo module，均需实测验证 |
| 不可消除的手动项 | starry_sky 需重刷一次固件成恒定 SSID（一劳永逸） |
| 未定项 | 见 §11。核心是网卡选型确认 + AP 压力实测，两条过了整套即成立 |

---

## 2. 背景：要解决什么

交付后没有物理窗口，且现场网络不受控。前几版方案都在“让板子连现场 WiFi”这条路上打补丁，暴露出四个都不在我们掌控范围内的变量：

- **DHCP 换 IP**：板子连现场网靠 DHCP，重启/续租/断电恢复都可能换地址，APP 存的 IP 失效，且无自动恢复路径（板子还在线，AP 兜底不触发）。
- **现场路由器拿不到**：DHCP 保留（静态租约）这条最干净的解，需要企业 IT 权限，我们无法决定。
- **现场网可能封组播 / 开客户端隔离**：企业 AP 常见配置，会直接搞死 mDNS 发现和 WLED 原生 Sound Sync。
- **节点也要联网**：配网服务只把**板子**接进现场网，5（→9）个 ESP32 节点 + starry_sky 各自还得连上现场 WiFi，且 starry_sky 的 SSID 是编译期写死的。

结论：只要灯光系统依赖现场网，确定性就掌握在别人手里。本方案把依赖搬回我们能控的板子上。

---

## 3. 核心决策：板载 AP 自洽岛

**Host 用部署配置指定的 Wi-Fi 接口常驻开热点**（SSID 恒定，建议 `LIGHTBELT-CORE`，真值以配置为准）。所有 ESP32 节点、starry_sky、控制平板都连这个热点。灯光系统在这个小圈子里自洽运行，**不需要 Internet、不需要现场 Wi-Fi**。

由此，前面四个变量当场全部消失：

- **APP→Host**：Cabin AP 的 `LIGHT_BELT_CABIN_AP_IPV4_CIDR` 提供稳定的内部网关，APP 可以默认访问该网关；这只解决 APP 到 Host 的寻址。
- **Host→WLED**：仍按 `strip_XX → wled-strip-XX.local → Avahi/mDNS → 当前 dynamic IPv4` 解析。永久 AP 消除了对现场 LAN 的依赖，但没有消除 WLED mDNS，也不得改成 MAC、静态节点 IP 或子网扫描。
- **节点联网**：节点只认“板子 AP”这一个恒定 SSID。换任何场地，节点零重配——因为它们根本不再需要知道现场网存在。
- **starry_sky**：一次性重刷成板子 AP 的 SSID，之后永不再刷，编译期写死 SSID 的老毛病被“刷成恒定值”根治。
- **Sound Sync**：在受控 Cabin AP 内预期可用、风险低于现场 LAN，但仍需真实 RK3568/AP/WLED 硬件验证；不得表述为“绝对通”。

> 澄清一个易混点：核心是“**板子自己开网，APP 使用稳定 AP 网关**”，不是把 WLED 节点改成固定 IP。Host 到 WLED 的当前 mDNS 解析链仍保留。

---

## 4. 可选上行：上云 / 联网

灯光自洽不代表放弃联网。灯控只依赖 Cabin AP；可选 uplink 用于上云、自更新（自更新链路已实现，见规划文档），但不能成为 Host、WLED、DDP 或 APP 本地控制的启动依赖。

- 有上行：自动上云、拉 GitHub 更新。
- 无上行：灯光照常，仅自更新暂停（已是优雅降级行为），需要时临时用手机热点给板子推一次。

**平台边界（仅结论）**：RK3568 实验使用外接 Wi-Fi adapter；未来 NanoPC-T6 使用预装 Wi-Fi/Bluetooth combo module。可选 uplink 可走 Ethernet 或另一网络接口；不能在灯控核心中写死某个板卡、接口名或“必须两块 USB Wi-Fi”的假设。Phase 41A 不实现 Bluetooth 共存或 NAT。

---

## 5. 稳态效果（各方视角）

**操作者**：给板子上电 → 平板连板子热点 → 开 APP → 直接播。没有填 WiFi、没有查 IP、没有等连网。

**APP**：默认地址可指 Cabin AP 的稳定网关，直接访问 Host。（“填现场 Wi-Fi”不在灯光主流程里；若要上行，可另做可选设置项，与灯光能否使用无关。）

**节点（WLED ×5→9）**：开机自动连 Cabin AP；逻辑目标通过 stable WLED hostname 识别，由 Avahi/mDNS 解析到当前 dynamic IPv4。`resolve_nodes.py` 不使用 MAC registry、静态租约、子网扫描或 HTTP discovery。

**starry_sky**：连板子 AP（刷成恒定 SSID 后自动连）。

**平板上网**：平板连的是板子热点，默认**没有外网**。对专用控制平板通常无所谓；Phase 41A 不实现 NAT，若未来需要边控灯边上网，另行设计并验证。

---

## 6. 与旧方案对比

| | 岛架构（本方案） | 连现场网 + 静态IP/mDNS（旧方向） |
|---|---|---|
| 确定性来源 | 我们自己的板子（可测、可改、可冻结） | 现场网（隔离、封组播、拿不到路由器） |
| 免填 IP | APP→Host 可用稳定 AP 网关；Host→WLED 仍由 mDNS 解析 | 赌 DHCP 稳定 / 赌 Android 解析 `.local` / APP 加服务发现 |
| 节点联网 | 一个恒定 SSID，跨场零重配 | 每换场地需逐节点预灌现场 SSID |
| 需提前拿现场 WiFi 凭据 | 否（上行是可选项） | 是（否则节点连不上） |
| Sound Sync | 受控 AP 内预期可用，仍需硬件验证 | 受现场网组播策略影响 |
| 代价 | 加一块网卡 + AP 压力实测 | 与现场网络逐一较劲 |

---

## 7. 内容 / 媒体传输

原则一句话：**谁最终要用这个内容，就让谁去云上拿。** 板子才是要播媒体、跑节目的那个，让板子去拿最自然；平板缩小为“遥控器”。

| 内容类型 | 走哪条路 | 平板是否需两头切网 |
|---|---|---|
| 灯光节目 / 代码（YAML 等） | 板子自更新自动从 GitHub 拉，平板不参与 | 否（已解决） |
| 媒体（视频/音频）/ 云数据 —— 板子有上行 | 平板在 APP 点“下载 X”，板子自己从云拉 | 否 |
| 同上，且要平板同时上网 | 板子把上行 NAT 给平板（加料项） | 否 |
| 板子彻底离线（下策兜底） | 平板先在有网时下到本地，再切板子热点上传 | 是（手动切两次，仅偶尔用） |

结论：不必默认走“传到平板本地”那条，那是板子完全无网时的下策。只要板子有任一上行，就让板子自取。

---

## 8. 一次性交付前工作（设计层面清单，操作细节留待实现阶段）

以下在最后物理窗口做掉、做完冻结，之后换任何场地不再碰。**本节只列“要做的事”，不列“怎么做”。**

1. 在目标板上按部署配置选择 Wi-Fi 接口并配好常驻 AP（恒定 SSID + 内部网关地址）；RK3568 实验为外接 adapter，NanoPC-T6 未来为预装 combo module。
2. 给 5（→9）个 ESP32 节点各灌一次 Cabin AP 的恒定 SSID。
3. starry_sky 重刷成板子 AP 的恒定 SSID（需原作者 ESP-IDF 工程 + 现场 USB）。
4. APP 默认地址设为 Cabin AP 网关；WLED 节点仍使用既有 hostname/mDNS 解析链。
5. （若需上云）配置可选 Ethernet 或其他接口 uplink，不改变本地灯控依赖。

---

## 9. 部署配置与持久 AP 语义

`scripts/setup_service.py` 支持且只支持两种网络模式：`site_client` 与 `portable_ap`。部署通过环境变量提供参数，不在 Python 中按 RK3568/NanoPC-T6 分支：

```text
LIGHT_BELT_NETWORK_MODE=site_client|portable_ap
LIGHT_BELT_WLAN_INTERFACE=<selected Wi-Fi interface>
LIGHT_BELT_CABIN_AP_SSID=<persistent internal SSID>
LIGHT_BELT_CABIN_AP_PASSWORD=<WPA2 PSK, 8..63 characters>
LIGHT_BELT_CABIN_AP_IPV4_CIDR=<usable IPv4 gateway/CIDR>
LIGHT_BELT_CABIN_AP_CONNECTION=LIGHT-BELT Cabin AP
```

`site_client` 未提供新变量时保持历史流程：已保存/现场 Wi-Fi → 失败后临时 `LIGHT-BELT_Setup` 热点 → 配置现场 Wi-Fi。`portable_ap` 必须显式指定接口、SSID、WPA2 密码、网关/CIDR 与独立 NetworkManager connection；启动失败必须明确报错，不能静默接管错误 radio 或回退到开放热点。

Cabin AP 是持久的 NetworkManager profile：启用 `portable_ap` 时自动创建/校准并设置 autoconnect；服务重启或进程退出不得删除该 profile，NetworkManager 可独立恢复 AP。portable AP watchdog 只监视并重连 AP，不因没有 Internet 而关闭 AP；`/connect`、`/hotspot` 等现场配网入口不得拆掉 Cabin AP。

### 新 ESP32 替换约定

只有一块新 ESP32 时，可把它配置成既有逻辑节点 `strip_11`，使用既有 WLED hostname `wled-strip-11`（mDNS 名为 `wled-strip-11.local`）接入，不新增逻辑节点、不修改九节点 topology。GPIO、LED count、WS2811 电气时序/电源与亮度等是该 ESP32/WLED 的另行硬件配置，不能从 hostname 或逻辑节点推断，也不在本文档中伪造为已验证。

## 10. RK3568 H1–H6 硬件门禁现场 runbook

以下步骤必须在真实 RK3568、外接 Wi-Fi adapter、至少一块新 ESP32、实际 WS2811 与控制客户端上执行。命令中的 `<...>` 由现场值替换；密码只通过部署环境注入，不写入 shell 历史。当前本仓库未连接该硬件，因此 H1–H6 全部为 **NOT HARDWARE VERIFIED / NOT RUN**，不得填写 PASS。

### 10.1 预检与记录

```sh
export LIGHT_BELT_NETWORK_MODE=portable_ap
export LIGHT_BELT_WLAN_INTERFACE=<rk3568-ap-interface>
export LIGHT_BELT_CABIN_AP_SSID=<cabin-ssid>
export LIGHT_BELT_CABIN_AP_IPV4_CIDR=<gateway-ip>/<prefix>
export LIGHT_BELT_CABIN_AP_CONNECTION='LIGHT-BELT Cabin AP'
read -r -s -p 'Cabin AP WPA2 password: ' LIGHT_BELT_CABIN_AP_PASSWORD
export LIGHT_BELT_CABIN_AP_PASSWORD
printf '\n'
nmcli device status
nmcli connection show
```

将同一组变量写入实际 service 的 EnvironmentFile/部署配置，然后启动 `setup_service.py`；不能只在当前 shell 临时设置后宣称重启持久化通过。

### H1 — Wi-Fi adapter capability

```sh
IFACE="$LIGHT_BELT_WLAN_INTERFACE"
nmcli -f GENERAL.STATE,GENERAL.CONNECTION,GENERAL.DRIVER device show "$IFACE"
iw dev "$IFACE" info
iw list | sed -n '/Supported interface modes:/,/Band/p'
```

记录 adapter 被识别、NetworkManager 管理、driver 已加载且 `Supported interface modes` 含 `AP`。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

### H2 — Permanent Cabin AP

```sh
sudo systemctl restart <setup-service-unit>
nmcli connection show "$LIGHT_BELT_CABIN_AP_CONNECTION"
nmcli -f GENERAL.STATE,GENERAL.CONNECTION,IP4.ADDRESS device show "$IFACE"
curl --fail --connect-timeout 3 "http://${LIGHT_BELT_CABIN_AP_IPV4_CIDR%/*}:8080/status"
```

用手机/笔记本加入 Cabin SSID，确认网关与 `/status` 可达；确认不需要 Internet。随后重启 RK3568，待 NetworkManager 完成后重复 `nmcli` 与客户端连接检查，验证 AP profile 自动恢复且服务退出未删除 profile。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

### H3 — New WLED ESP32 join

把新 ESP32 配成 `strip_11` 对应的 WLED 配置（hostname `wled-strip-11`），让其加入 Cabin AP；然后执行：

```sh
avahi-resolve -4 -n wled-strip-11.local
curl --fail --connect-timeout 3 http://wled-strip-11.local/json/info
```

记录 `.local` 解析到当前 dynamic IPv4、WLED UI/API 可达。其他八个节点可缺席。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

### H4 — Host partial-node discovery

在不编辑 tracked topology 的前提下生成运行时 profile，并确认只启用已解析节点：

```sh
./.python/bin/python scripts/resolve_nodes.py \
  --template config/profiles/rk3588-host-service.yaml \
  --out config/runtime/wled-ddp-mdns.yaml
grep -n -A4 -B2 'strip_11\|wled-strip-11' config/runtime/wled-ddp-mdns.yaml
```

期望 `strip_11` 为 `enabled: true`/当前 IPv4，其他未解析节点为 disabled；Host 服务健康，不能因 1 online/8 offline 修改 topology。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

### H5 — Real DDP output and safe stop

用实际 Host/Show 产生静态色和 chase 等移动效果，观察 WS2811 像素更新、颜色基本正确且移动到达真实灯带；可用现有 DDP smoke 工具辅助验证当前解析目标（像素数按现场 WLED 配置替换）：

```sh
./.python/bin/python scripts/wled_ddp_smoke_test.py \
  --host wled-strip-11.local --port 4048 --pixels <led-count> \
  --pattern chase --seconds 10
```

停止 Host 服务，记录 WLED 在 realtime timeout 后进入安全/关闭状态；不得只凭脚本退出码替代肉眼与实际灯带检查。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

### H6 — Recovery

分别重启 ESP32 与 RK3568，并记录从重启到可控的恢复时长：

```sh
sudo systemctl restart <host-service-unit>
avahi-resolve -4 -n wled-strip-11.local
curl --fail --connect-timeout 3 "http://${LIGHT_BELT_CABIN_AP_IPV4_CIDR%/*}:8443/api/v1/status"
```

确认恢复无需编辑 Show、手工改 IP 或修改 production topology；重复 H2/H3/H4 的关键检查。结果：**NOT HARDWARE VERIFIED / NOT RUN**。

当前软件会在新 Show、manual command 或 YAML resume 的子进程边界重新解析 profile，因此 session 间 DHCP 地址变化可恢复；活动 Show 已持有启动时的 DDP destination，活动期间 IP 变化不支持透明热更新，必须结束/重启该灯光 session。`MID_SESSION_IP_CHANGE: KNOWN FOLLOW-UP`。

**门禁结论：** 本次未执行真实 RK3568 硬件测试，故 RK3568 为 **NOT HARDWARE VERIFIED / NOT RUN**；NanoPC-T6、预装 Wi-Fi/Bluetooth combo 与 Wi-Fi/Bluetooth 共存均为 **NOT HARDWARE VERIFIED**。

## 11. 待确认 / 待验证（回来先看这里）

**硬阻塞级（不过则方案不成立）：**

- [ ] **RK3568 adapter/AP 能力**：按 H1/H2 实测；当前 **NOT HARDWARE VERIFIED / NOT RUN**。
- [ ] **AP 压力实测**：9 节点 + 平板全连 Cabin AP 并跑满负载，记录 ARP、吞吐、丢包与稳定性；当前 **NOT HARDWARE VERIFIED / NOT RUN**。

**取舍级（不影响成立，但需你拍板）：**

- [ ] 平板是否需要在控灯时同时上网？需要则另行设计 NAT（不属于 Phase 41A）。
- [ ] 上行走 Ethernet、现场 Wi-Fi 还是备用手机热点；它只决定可选 uplink，不得成为本地灯控依赖。
- [ ] AP 的 SSID / 密码 / 网段固定值定为多少（本文档占位值仅供讨论）。

**依赖他人：**

- [ ] starry_sky 重刷：需原固件作者提供 ESP-IDF 工程 + 现场 USB 访问。此项不因板子侧做得再好而消失。

---

## 12. 明确不在本文档范围

- 除 §10 硬件门禁检查外的生产安装命令、hostapd 参数和新脚本实现。
- 节点批量灌 SSID 的操作流程。
- starry_sky 刷写步骤。
- APP 侧改动的接口约定。

以上均留待“实现阶段”文档，在 §9 的硬阻塞项验证通过后再写。
