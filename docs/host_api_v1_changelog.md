# LIGHT-BELT Host API V1.0 Changelog

本文档为内部变更记录，不作为 APP 对外文档。

## V1.0 来源

Host API V1.0 基于 Candidate validation / mapping 审计结果整理，Candidate 文件仅作为内部归档参考，不作为对外接口契约。V1.0 对外文档只描述 APP 调用方式；内部实现边界、审计证据和风险分析保留在候选审计文档中。

## 从 Candidate v0.9 吸收的修正

- 将 `screen` 固定为 APP 可见 target alias，语义为屏幕区域。
- 将 `screen_surround` 固定为 APP 可见 target alias，语义为屏幕环绕区域。
- 保留 `virtual_path.screen_to_wall` 点号形式，作为 APP 可见连续路径 target。
- 将 `last_output_ms` 纳入设备状态，表示 Host Service 最近一次向该节点输出的时间。
- 将 `last_seen_ms` 保留为设备状态字段，语义固定为最近一次收到设备状态时间。
- 将 `hardware_verified` 固定为 Host Service 层设备状态字段，供 APP 展示连接确认状态。
- 将 `audio_available` / `video_available` 与 `audio_link_enabled` / `video_link_enabled` 拆分，避免 APP 混淆“输入可用”和“联动启用”。
- 将 `params` 固定为通用 effect 参数对象，包含 `color`、`speed`、`intensity`。
- 将 `effect_params` 固定为 effect 专用参数对象。
- 将 `transition_ms` 固定为 Host Service 层过渡语义，用于 `lights/set` 和 `effects/set`。

## V1.0 固定的 target alias

| target_id | V1.0 语义 |
|---|---|
| `all` | 全部区域 |
| `ceiling_left` | 左侧顶部区域 |
| `ceiling_right` | 右侧顶部区域 |
| `wall_left` | 左墙区域 |
| `wall_right` | 右墙区域 |
| `front` | 前方区域 |
| `rear` | 后方区域 |
| `screen` | 屏幕区域 |
| `screen_surround` | 屏幕环绕区域 |
| `virtual_path.screen_to_wall` | 屏幕到墙面的连续路径 |

## V1.0 固定的 Host Service 层语义

- 认证、token、session、ws_ticket 为 Host Service 层语义。
- REST response envelope 为 Host Service 层语义。
- WebSocket message envelope 为 Host Service 层语义。
- `system_state`、`playback_state`、`position_ms`、`duration_ms` 为 Host Service 对 APP 输出的状态语义。
- `brightness`、`color_temperature`、`transition_ms` 为 Host Service 接收 APP 控制命令的语义。
- `device.status` 消息和设备字段为 Host Service 面向 APP 的设备状态语义。

## 对外文档与 OpenAPI 一致性

- `docs/host_api_v1.md` 是 APP 方阅读文档。
- `docs/host_api_v1.openapi.yaml` 是 Apifox / Postman / Swagger 可导入接口描述。
- 二者使用相同的 endpoint、request schema、response envelope、枚举值和错误码。

## V1.0 对外口径收紧

- 新增 `GET /api/v1/status`，用于 APP 在配对前检测 Host Service 在线状态。
- 新增 `GET /api/v1/capabilities`，用于 APP 动态获取 targets、effects、WebSocket 消息类型和 supports。
- 新增 `POST /api/v1/playback/resume`，用于从暂停状态继续播放。
- 对外设备状态主字段从 `node_id` / `node_type` 调整为 `device_id` / `device_type`。
- 对外设备类型固定为 `light_zone`、`light_path`、`host_output`。
- `hardware_verified` 改名为 `connection_confirmed`，语义固定为 Host Service 当前确认该逻辑设备连接状态。
- 内部节点信息仅保留在可选 `debug.node_id` / `debug.node_type`。
- `/effects/set` 的 chase 示例移除 `params.color`，新增 static 颜色设置示例。
- 对外文档明确 `target_id` 是 Host Service 暴露给 APP 的逻辑目标。

## V1.0 部署状态口径修订

- 将对外文档中的联调地址口径调整为“RK3588 部署后联调信息”。
- 明确 RK3588 固定局域网 IP 为 `192.168.31.236`。
- 明确当前 LIGHT-BELT Host Service 尚未部署到 RK3588。
- 明确 HTTPS Base URL 与 WebSocket URL 是部署后的固定对接地址。
- 明确当前文档用于 APP 开发、Mock 和接口冻结。
- 将 Certificate Fingerprint 说明为预生成证书指纹。
- 明确实际联调以部署到 RK3588 的 Host Service 使用的证书为准。
