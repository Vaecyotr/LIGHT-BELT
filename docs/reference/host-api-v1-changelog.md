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

## V1.0 固定的 target alias（历史归档 / 已被 strip_* 体系取代）

> **说明**：下表为早期 Candidate / 审计阶段固定记录。当前正式 APP target contract 已全面切换为基于 Profile 动态派生的 `strip_<label>`（如 `strip_11`、`strip_21`、`strip_31`、`strip_41`）以及 `all`、`starry_sky` 体系。下表仅保留作为历史记录，当前示例与接口均以 `strip_*` 为准。

| target_id | V1.0 语义（历史） |
|---|---|
| `all` | 全部区域 |
| `ceiling_left` | 左侧顶部区域（superseded） |
| `ceiling_right` | 右侧顶部区域（superseded） |
| `wall_left` | 左墙区域（superseded） |
| `wall_right` | 右墙区域（superseded） |
| `front` | 前方区域（superseded） |
| `rear` | 后方区域（superseded） |
| `screen` | 屏幕区域（superseded） |
| `screen_surround` | 屏幕环绕区域（superseded） |
| `virtual_path.screen_to_wall` | 屏幕到墙面的连续路径（superseded） |

## V1.0 固定的 Host Service 层语义

- 认证、token、session、ws_ticket 为 Host Service 层语义。
- REST response envelope 为 Host Service 层语义。
- WebSocket message envelope 为 Host Service 层语义。
- `system_state`、`playback_state`、`position_ms`、`duration_ms` 为 Host Service 对 APP 输出的状态语义。
- `brightness`、`color_temperature`、`transition_ms` 为 Host Service 接收 APP 控制命令的语义。
- `device.status` 消息和设备字段为 Host Service 面向 APP 的设备状态语义。

## V1.2 新增（brightness_scale + /playback/state）

- 新增 `GET /api/v1/brightness`，返回当前亮度乘数 `brightness_scale`（默认 `0.5`）。
- 新增 `POST /api/v1/brightness/set`，接受 `brightness_scale`（`0.0~1.0`）并立即推送到所有 WLED 节点。
- 新增 `GET /api/v1/playback/state`，返回实时播放位置（来自 mpv）、当前节目（过滤内部字段）、`brightness_scale` 和音频状态。
- `POST /api/v1/playback/reset`：清除手动覆盖并重启节目 YAML 灯光引擎；若当前为暂停状态则自动恢复播放；结束后推送 `brightness_scale`。
- `POST /api/v1/playback/play` 自动将 `brightness_scale` 重置为默认值 `0.5` 并推送到 WLED 节点。
- `GET /api/v1/state` 响应增加 `brightness_scale` 字段。
- `runtime.state` WebSocket 消息增加 `brightness_scale` 字段。
- `GET /api/v1/capabilities` 的 `supports` 对象增加 `brightness_scale: true`。

## 对外文档与 OpenAPI 一致性

- `docs/reference/host-api-v1.md` 是 APP 方阅读文档。
- `docs/reference/host-api-v1.openapi.yaml` 是 Apifox / Postman / Swagger 可导入接口描述。
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

## Phase 40 最终文档与 APP V1 基线收口（2026-08-23）

- **APP V1 历史兼容基线锁定**：
  - Source Repo: `https://github.com/zxlzzz/LIGHT-BELT`
  - Source Commit: `0380e4e1ecb926148d9afc07b7f95f6ad0aa4c6b` (`0380e4e`)
  - Source Date: `2026-08-19`
  - Reason: Phase 32 之前的已知稳定集成状态（APP + Host + Show 播放均可正常配合工作）。
- **APP 职责与系统边界**：
  - APP 负责：Show 选择、播放、暂停、继续、停止、seek/进度、总体灯光亮度（`brightness_scale`）、音量、静音、状态显示。
  - APP 不负责：指定某条灯带用什么 effect、编辑 effect 参数、参数调制（`parameter_modulation`）、颜色源（`ColorSource`）、连续虚拟路径（`virtual_path`）、分支生命周期、运动时钟等。
  - Phase 35-40 的所有高级灯效能力完全封装在 Show YAML 与 RK3588 `light_engine` 内部。
- **清理旧 target alias 文档残留**：
  - 明确早期固定区域别名（`ceiling_left`、`ceiling_right`、`wall_left`、`wall_right`、`front`、`rear`、`screen`、`screen_surround`、`virtual_path.screen_to_wall` 等）已被当前 profile/layout 动态派生的 `strip_*`、`all`、`starry_sky` 取代。
  - `docs/reference/host-api-v1.md` 中的示例已全部更新为当前的 `strip_*` 示例。
- **API 版本稳定性**：
  - 维持 Host API V1 规范不变，不升级为 V2。
  - 内部 EffectRegistry 扩张（22 种灯效、111 个参数、ColorSource）不向 APP 暴露，APP 无需任何修改。
- **测试追溯与回归保障**：
  - 新增历史基线 fixture `tests/fixtures/app_v1/pre_phase32_0380e4e.json`，确保 APP V1 compatibility facade 严格匹配历史稳定公开合同。
