# Host API Validation Summary

候选 Host API 可以在当前 LIGHT-BELT 架构上实现，不需要推倒现有 Engine、ShowRuntime、Effect、Mapping、Output，也不需要修改 RS-485 v2、UDP v2、STM32、ESP32 协议。推荐下一步进入“冻结 Host API V1.0”前的 Host Service 设计，但当前结果只能称为 Candidate v0.9。

## 可以直接保留的候选参数

- `effect_type`: `static`, `breath`, `color_wave`, `chase`, `comet`, `audio_pulse`, `bass_pulse`, `spectrum`, `video_ambient`, `video_audio_fusion`, `calm`, `demo`。当前全部已注册，依据 `light_engine/effects/__init__.py`。
- 实体 `target_id`: `all`, `ceiling_left`, `ceiling_right`, `wall_left`, `wall_right`, `front`, `rear`。当前 layout 中存在对应 zone/strip，依据 `config/layout.yaml`。
- `virtual_path.screen_to_wall`: 当前存在 path `screen_to_wall`，但 Host 需要解析成 virtual_path target，依据 `config/layout.yaml` 和 `light_engine/mapping/virtual.py`。
- `node_type`: `stm32_rgbcct`, `esp32_ws2811`。当前分别对应 RS-485 v2 analog nodes 和 UDP v2 digital node，依据 `light_engine/outputs/rs485_v2.py`、`light_engine/outputs/udp_v2.py`。
- 认证与会话字段可以保留在 Host Service 层，不影响引擎。

## 需要调整的候选参数

- `screen` 需要调整为 Host alias，当前建议 `screen -> front`。
- `screen_surround` 需要调整为 Host alias/group，当前建议 `screen_surround -> front + wall_left + wall_right`。
- `target_id` 必须由 Host `TargetRegistry` 展开为 analog、digital、both 或 virtual_path，不能直接等同 show 内部 target。
- `color_temperature` 需要 Host 层 Kelvin -> RGB+CCT 策略，不能写入协议层。
- `transition_ms` 应定义为 Host 软件过渡；RS-485 可额外使用 `fade_ms`，UDP 由 Host 分帧渐变。
- `last_seen_ms` 当前没有真实节点回传，建议当前使用 `last_output_ms`；真实 `last_seen_ms` 需要新增 Host Service 层实现并接入设备诊断。

## 当前没有但可通过新增 Host Service 实现的功能

- HTTPS REST + WSS 服务、配对、token、ws ticket、session。
- Runtime Controller：`play`, `pause`, `stop`, `seek`, `show_id` 选择。
- ShowCatalog：`GET /shows` 的 show 列表和 show_id 映射。
- StateAggregator：`GET /state` 和 WSS `runtime.state`, `playback.progress`, `device.status`, `error.event`, `heartbeat`。
- LightCommand Adapter：`lights/set` 的 target brightness、Kelvin 色温和 transition。
- EffectCommand Adapter：运行时 `effects/set`，含通用 params 归一化和 effect-specific 参数白名单。

## 是否建议进入下一步

建议进入下一步“冻结 Host API V1.0”前的设计工作，但不建议直接冻结当前候选文本。下一步应先设计 Host Service / Adapter，并把 Candidate v0.9 中的别名、状态转换、seek/reset 语义、设备状态来源写清楚后再冻结 V1.0。

硬件状态仍为 `NOT HARDWARE VERIFIED`；当前审计只证明软件架构兼容。
