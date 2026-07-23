# LIGHT-BELT Host API Candidate Validation

本文件审计候选 APP -> RK3588 Host Service API 与当前 LIGHT-BELT 架构的兼容性。结论基于当前仓库源码和权威文档，不实现 Host Service，不新增正式接口，不把候选 API 视为 V1.0 定稿。

## A. 总体结论

- 候选 Host API 可以在当前架构基础上实现。当前 Engine 已经具备 `Engine`、`ShowRuntime`、`Effect`、`PhysicalMapping`、`OutputTransform`、RS-485 v2、UDP v2 分层，Host API 适合作为外层 Host Service / Adapter。
- 不需要推倒现有架构。当前架构已经满足“效果硬件无关、物理映射独立、协议纯编码、Engine 统一 sequence”的核心边界，见 `CLAUDE.md`、`docs/CLOSED_LOOP_SPEC.md`、`docs/IMPLEMENTATION_PLAN.md`、`light_engine/engine/__init__.py`、`light_engine/mapping/physical.py`。
- 主要需要新增 Host Service / Adapter 层：认证、REST/WSS、会话、状态聚合、Runtime Controller、LightCommand Adapter、EffectCommand Adapter、APP 可见 target 别名映射。
- 不应影响现有 RS485/UDP/STM32/ESP32 协议。候选 API 的字段应在 Host Service 层转成现有 `PhysicalFrame`、`OutputTransform` 或 runtime 控制命令，不能改 RS-485 v2 / UDP v2 wire format。
- 当前没有真实硬件验证证据；所有硬件在线、last_seen、设备状态类结论均为 `NOT HARDWARE VERIFIED`，只能由 Host Service 聚合本机输出健康和未来固件诊断。

关键代码依据：

- Engine sequence、clock、effect/show runtime、diagnostics：`light_engine/engine/__init__.py`
- RGB+CCT 和 logical frame 模型：`light_engine/models.py`
- 物理映射与 node frame：`light_engine/mapping/physical.py`
- layout 真实 zone / strip / virtual_path：`config/layout.yaml`
- show target 与 timeline：`light_engine/show/loader.py`、`light_engine/show/compositor.py`、`docs/contracts/TIME_CONTRACT.md`、`docs/contracts/FRAME_CONTRACT.md`
- effect registry：`light_engine/effects/__init__.py`、`light_engine/effects/base.py`
- 输出健康与 transport 模式：`light_engine/outputs/__init__.py`
- RS-485 v2 / UDP v2：`light_engine/outputs/rs485_v2.py`、`light_engine/outputs/udp_v2.py`

## B. 兼容性矩阵

| API / message 名称 | 候选字段 | 当前代码是否已有对应概念 | 当前代码来源文件 | 是否可直接映射 | 是否需要新增 Host Service 状态 | 是否需要修改现有 Engine / Effect / Mapping / Output | 风险等级 | 建议 |
|---|---|---|---|---|---|---|---|---|
| `POST /api/v1/auth/pair` | `pairing_code`, `client_id`, `client_name`, `client_type`, `app_version`, token 输出 | 没有；引擎无用户/客户端概念 | 无对应核心文件 | 不可映射到引擎；可在 Host Service 独立实现 | 是：PairingStore、ClientRegistry、TokenStore | 否 | LOW | 保留在 Host Service |
| `POST /api/v1/auth/refresh` | `refresh_token`, `access_token`, `expires_in`, `scope` | 没有；与灯效无关 | 无对应核心文件 | 不映射 | 是：TokenStore | 否 | LOW | 保留在 Host Service |
| `POST /api/v1/session/ws-ticket` | `access_token`, `ws_ticket`, `subscribe`, `session_id` | 没有 WSS 会话；有 runtime diagnostics 可作为事件来源 | `light_engine/engine/__init__.py` | 部分：`subscribe` 可映射到 WSS 主题 | 是：SessionStore、WSTicketStore、SubscriptionRegistry | 否 | LOW | 保留；限定 scope |
| `GET /api/v1/state` | `system_state`, `playback_state`, `show_id`, `position_ms`, `duration_ms`, `brightness`, `color_temperature`, `audio_link_enabled`, `video_link_enabled`, `devices` | 有部分诊断和运行时字段；无统一 APP 状态模型 | `Engine.diagnostics()` in `light_engine/engine/__init__.py`; `health_summary()` in `light_engine/outputs/__init__.py`; `ShowDefinition.duration` in `light_engine/show/models.py` | 部分可映射 | 是：StateAggregator | 否 | MEDIUM | 保留但调整字段来源 |
| `GET /api/v1/shows` | show id/name/duration/metadata | 有 show loader 和 `ShowDefinition.id/duration/cues`，没有 show library/index | `light_engine/show/loader.py`, `light_engine/show/models.py`, `config/show.example.yaml` | 部分可映射 | 是：ShowCatalog | 否 | LOW | 保留；返回 Host 管理的 show 列表 |
| `POST /api/v1/playback/play` | `show_id`, `start_position_ms` | Engine 可 `set_effect()` / `set_show_runtime()` 并 `run()`；CLI 可加载 show；没有远程控制器 | `light_engine/engine/__init__.py`, `light_engine/cli/__init__.py` | 部分可映射 | 是：Runtime Controller | 不改核心优先；若要长驻线程控制需外层封装 | MEDIUM | 保留；必须经 Runtime Controller |
| `POST /api/v1/playback/pause` | session/runtime id | Clock 有 pause 语义；Engine loop 可识别 `clock.paused`；没有 REST pause 命令 | `light_engine/clock.py`, `light_engine/engine/__init__.py`, `docs/contracts/TIME_CONTRACT.md` | 部分可映射 | 是：Runtime Controller | 否，推荐用可控 Clock Adapter | MEDIUM | 保留；语义为冻结 media timestamp |
| `POST /api/v1/playback/stop` | session/runtime id | Engine 有 `_running` 和 shutdown safe frame；没有公开 stop API | `light_engine/engine/__init__.py`, `light_engine/outputs/transform.py` | 部分可映射 | 是：Runtime Controller | 可通过外层停止线程，不改协议 | MEDIUM | 保留；必须触发 safe frame |
| `POST /api/v1/playback/seek` | `position_ms` | Clock/ShowRuntime 支持 reset/replay；任意倒退 seek 不是 V1 保证 | `docs/contracts/TIME_CONTRACT.md`, `light_engine/engine/__init__.py`, `light_engine/show/compositor.py` | 部分可映射 | 是：Runtime Controller | 不建议改 Engine；由 controller reset/replay | HIGH | 调整：写明 seek 需要 reset/replay |
| `POST /api/v1/lights/set` | `target_id`, `brightness`, `color_temperature`, `transition_ms` | 全局亮度在 `OutputTransform`；物理 fade_ms 在 mapping；没有运行时 per-target override 和 CCT kelvin API | `light_engine/outputs/transform.py`, `light_engine/mapping/physical.py`, `config/layout.yaml` | 部分可映射 | 是：LightCommand Adapter、TargetRegistry | 否；优先外层覆盖 logical frame / transform | MEDIUM | 保留但拆分语义 |
| `POST /api/v1/effects/set` | `target_id`, `effect_type`, `params.color/speed/intensity` | effect registry 已有全部候选 effect；show runtime 有 target-scoped effect；单 effect path 有 `set_effect()` | `light_engine/effects/__init__.py`, `light_engine/show/compositor.py`, `light_engine/engine/__init__.py` | 部分可映射 | 是：EffectCommand Adapter | 不改协议；可新增外层 ephemeral show/runtime adapter | MEDIUM | 保留但调整 params |
| `session.connected` | `session_id`, client info | 无 WSS，会话与引擎无关 | 无对应核心文件 | 不映射 | 是：SessionStore | 否 | LOW | 保留在 Host Service |
| `runtime.state` | `system_state`, `playback_state`, `show_id`, links, brightness | 有 Engine diagnostics、mode、media_position、output health | `light_engine/engine/__init__.py` | 部分可映射 | 是：StateAggregator | 否 | MEDIUM | 保留；由 StateAggregator 生成 |
| `playback.progress` | `position_ms`, `duration_ms`, `show_id` | 有 `Engine.timestamp`、`ShowDefinition.duration`、media reader duration | `light_engine/engine/__init__.py`, `light_engine/media/__init__.py`, `light_engine/show/models.py` | 部分可映射 | 是：Runtime Controller 状态 | 否 | LOW | 保留 |
| `device.status` | `node_id`, `node_type`, `status`, `last_seen_ms`, `error_code` | 有 node mapping 和 output health；没有 per-node online telemetry | `light_engine/mapping/physical.py`, `light_engine/outputs/__init__.py`, firmware protocol files | 部分可映射 | 是：DeviceRegistry/StateAggregator | 否 | MEDIUM | 调整：标明 Host 推断状态 |
| `error.event` | error code/message/source | 有 `last_error` 和 output health；无统一 error event model | `light_engine/engine/__init__.py`, `light_engine/outputs/__init__.py` | 部分可映射 | 是：ErrorEvent model | 否 | LOW | 保留 |
| `heartbeat` | `session_id`, time | 没有；WSS 层职责 | 无对应核心文件 | 不映射 | 是：WebSocket service | 否 | LOW | 保留在 Host Service |

## C. effect_type 审计

当前真实注册的 effect 来自 `light_engine/effects/__init__.py` 和 `light_engine/effects/base.py`。

| Host API 候选 effect_type | 当前代码内部 effect 名称 | 是否一致 | 是否需要映射 | 相关文件路径 | 建议是否保留该 Host API 名称 |
|---|---|---|---|---|---|
| `static` | `static` | 是 | 否 | `light_engine/effects/static.py` | 保留 |
| `breath` | `breath` | 是 | 否 | `light_engine/effects/breath.py` | 保留 |
| `color_wave` | `color_wave` | 是 | 否 | `light_engine/effects/color_wave.py` | 保留 |
| `chase` | `chase` | 是 | 否 | `light_engine/effects/chase.py` | 保留 |
| `comet` | `comet` | 是 | 否 | `light_engine/effects/comet.py` | 保留 |
| `audio_pulse` | `audio_pulse` | 是 | 否 | `light_engine/effects/audio_pulse.py` | 保留 |
| `bass_pulse` | `bass_pulse` | 是 | 否 | `light_engine/effects/bass_pulse.py` | 保留 |
| `spectrum` | `spectrum` | 是 | 否 | `light_engine/effects/spectrum.py` | 保留 |
| `video_ambient` | `video_ambient` | 是 | 否 | `light_engine/effects/video_ambient.py` | 保留 |
| `video_audio_fusion` | `video_audio_fusion` | 是 | 否 | `light_engine/effects/video_audio_fusion.py` | 保留 |
| `calm` | `calm` | 是 | 否 | `light_engine/effects/calm.py` | 保留 |
| `demo` | `demo` | 是 | 否 | `light_engine/effects/demo.py` | 保留；APP 中建议标记为调试/演示 |

参数审计：

- 候选 `params.color` 与 `static`、`breath`、`audio_pulse`、`bass_pulse`、`calm` 的现有参数可映射，但当前颜色参数是 RGB `[0,1]` 配置；Host API 若用 `0~255`，需要 EffectCommand Adapter 做归一化。
- 候选 `speed` 可映射到 `EffectContext.speed` 或部分 effect 参数，但不是所有 effect 都有同名参数；需要 Adapter 按 effect 白名单处理。
- 候选 `intensity` 可映射到 `EffectContext.intensity`，但当前很多 effect 主要读取配置参数；需要 Adapter 注入 context 或构造临时 show cue 参数。
- 不能把 `color/speed/intensity` 声明成所有 effect 的统一强制参数；应声明为 Host Adapter 支持的通用覆盖字段，不能替代 `light_engine/effects/base.py` 中的 effect-specific 参数白名单。

## D. target_id 审计

当前真实目标来自 `config/layout.yaml`、`light_engine/mapping/__init__.py`、`light_engine/show/loader.py`、`light_engine/show/compositor.py`。注意：`docs/contracts/FRAME_CONTRACT.md` 明确 analog 与 digital 是不同 target 域，即使文本 ID 相同也不能隐式互转。

| Host API 候选 target_id | 当前代码内部 zone_id / strip_id / segment_id / path | 是否存在 | 是否需要虚拟映射 | 是否适合作为 APP 可见名称 | 建议是否保留该 target_id |
|---|---|---|---|---|---|
| `all` | show target kind `all`; all analog zones + all digital strips | 是 | 否 | 是 | 保留 |
| `ceiling_left` | analog zone `ceiling_left`; digital strip `ceiling_left`; segment `ceiling_left_main`; node 1 / node 7 range 0-143 | 是 | 是：Host 需决定 analog、digital 或 both | 是 | 保留；定义为组合目标 |
| `ceiling_right` | analog zone `ceiling_right`; digital strip `ceiling_right`; segment `ceiling_right_main`; node 2 / node 7 range 144-287 | 是 | 是 | 是 | 保留；定义为组合目标 |
| `wall_left` | analog zone `wall_left`; digital strip `wall_left`; segment `wall_left_main`; node 3 / node 7 range 288-387 | 是 | 是 | 是 | 保留；定义为组合目标 |
| `wall_right` | analog zone `wall_right`; digital strip `wall_right`; segment `wall_right_main`; node 4 / node 7 range 388-487 | 是 | 是 | 是 | 保留；定义为组合目标 |
| `front` | analog zone `front`; digital strip `front`; segment `front_main`; node 5 / node 7 range 488-559 | 是 | 是 | 是 | 保留；定义为组合目标 |
| `rear` | analog zone `rear`; digital strip `rear`; segment `rear_main`; node 6 / node 7 range 560-631 | 是 | 是 | 是 | 保留；定义为组合目标 |
| `screen` | 没有 `screen` zone/strip/path；`front` 可能是近似屏幕前部 | 否 | 是 | 可以，但当前不真实 | 调整：映射到 `front` 或新增 Host alias `screen -> front` |
| `screen_surround` | 没有同名目标；可组合 `front + wall_left + wall_right` 或 `virtual_path.screen_to_wall` | 否 | 是 | 可以，但需明确定义 | 调整：Host alias，不写入核心 layout |
| `virtual_path.screen_to_wall` | layout virtual path id `screen_to_wall`; show target kind `virtual_path` | 是 | 是：Host 前缀需剥离为 path id | 是 | 保留；规范为 `virtual_path:screen_to_wall` 或继续支持点号别名 |

建议：Host API 的 `target_id` 不要直接等同 show loader 的 `TargetSelector.kind/id`。应新增 Host `TargetRegistry`，把 APP 可见名解析为：

- `all` -> `TargetSelector(kind="all")`
- 六个实体区 -> analog zone + digital strip 组合目标
- `virtual_path.screen_to_wall` -> `TargetSelector(kind="virtual_path", id="screen_to_wall")`
- `screen` / `screen_surround` -> Host alias，当前不写入 layout

## E. playback 控制审计

| 能力 | 当前支持状态 | 代码依据 | 审计结论 |
|---|---|---|---|
| `play` | 底层可运行 `Engine.run()`；CLI 可 `run/demo/run-mpv` | `light_engine/engine/__init__.py`, `light_engine/cli/__init__.py` | 需要新增 Runtime Controller，把 REST play 转为启动/恢复引擎任务 |
| `pause` | Clock 有 pause 属性；Engine 在 paused 时跳过分析更新 | `light_engine/clock.py`, `light_engine/engine/__init__.py`, `docs/contracts/TIME_CONTRACT.md` | 需要新增 Runtime Controller 和可控 Clock Adapter |
| `stop` | Engine shutdown 会发送 safe frame；没有公开 stop command | `light_engine/engine/__init__.py`, `light_engine/outputs/transform.py` | 需要新增 Runtime Controller；停止必须触发安全帧 |
| `seek` | 支持 seek 检测和 reset/replay 语义；任意 stateful backward seek 不是 V1 保证 | `docs/contracts/TIME_CONTRACT.md`, `light_engine/engine/__init__.py`, `light_engine/show/compositor.py` | 需要新增 Runtime Controller；候选参数需写明 reset/replay |
| `show_id` 选择 | `ShowDefinition.id` 存在，CLI 可加载 show path；无 show catalog | `light_engine/show/models.py`, `light_engine/show/loader.py`, `light_engine/cli/__init__.py` | 需要新增 ShowCatalog，把 `show_id` 映射到文件/定义 |
| `start_position_ms` | Engine duration/timestamp 使用秒；可由 Clock 初始化/seek 实现 | `light_engine/clock.py`, `light_engine/engine/__init__.py` | 需要新增 Runtime Controller；单位转换 ms -> seconds |
| `duration_ms` | show/media duration 可读；不是统一 state 字段 | `light_engine/show/models.py`, `light_engine/media/__init__.py` | StateAggregator 生成 |
| `position_ms` | `Engine.timestamp` / diagnostics `media_position` 使用秒 | `light_engine/engine/__init__.py` | StateAggregator 转换 |

结论：候选 playback API 可保留，但当前没有 APP-facing playback controller。必须新增 Runtime Controller，不能直接暴露 Engine 私有字段，也不能承诺任意 seek 不重建状态。

## F. `lights/set` 审计

| 能力 | 当前支持状态 | 代码依据 | 结论 |
|---|---|---|---|
| 全局 `brightness` | 有全局 `OutputTransform.global_brightness`；亮度只能在 OutputTransform 应用一次 | `light_engine/outputs/transform.py`, `docs/IMPLEMENTATION_PLAN.md` | 可映射，但需要 Host 运行时更新 OutputTransform 或输出前覆盖 |
| 分 target `brightness` | 无直接 runtime API；有 per-zone warm/cool bias；show target-scoped composition 可影响目标 | `light_engine/show/compositor.py`, `light_engine/outputs/transform.py` | 需要新增 LightCommand Adapter |
| `color_temperature` | 有 RGBCCT WW/CW 通道；没有 Kelvin 2700~6500 -> WW/CW runtime API | `light_engine/models.py`, `light_engine/color/__init__.py`, `light_engine/outputs/transform.py` | 需要新增 Host Service 层实现 CCT 映射 |
| `transition_ms` | RS-485 physical mapping 有 `fade_ms`；show transitions 使用秒 | `light_engine/mapping/physical.py`, `light_engine/show/models.py` | 需要 Adapter 转成 fade/transition，不应改协议 |
| `target_id` 分组控制 | show 有 typed targets 和 groups；Host 候选为扁平 target_id | `light_engine/show/loader.py`, `light_engine/show/compositor.py` | 需要 TargetRegistry 和 LightCommand Adapter |

结论：`lights/set` 不能“直接调用现有能力”完成全部语义；应新增 `LightCommand Adapter`。可复用 `OutputTransform`、`TargetResolver`、`PhysicalMapping`，不需要修改 RS-485/UDP 协议。

## G. `effects/set` 审计

- 当前支持单 effect 切换：`Engine.set_effect(name)` 可替换全局 effect，见 `light_engine/engine/__init__.py`。
- 当前支持 show 内 target-scoped effect：`ShowRuntime`、`TargetResolver`、`CueRenderJob` 可对不同 targets 运行不同 effects，见 `light_engine/show/compositor.py`。
- 当前没有 REST 运行时 `effects/set`。如果 APP 要在不改 `show.yaml` 的情况下实时切换，必须新增 `EffectCommand Adapter`，把命令转成临时 cue / runtime overlay / single-effect change。
- 不必须通过节目单重新加载才能实现临时 effect；但若要保持现有 show 编排契约，推荐 Adapter 生成内存中的 ephemeral show overlay，而不是写回 `show.yaml`。
- `params.color/speed/intensity` 不能统一覆盖所有 effect 的全部参数。当前 effect-specific 参数白名单在 `light_engine/effects/base.py`；Host Adapter 应做归一化和参数白名单校验。
- 结论：`effects/set` 可保留，但需要新增 `EffectCommand Adapter`。不应修改 Effect 基类、Mapping、Output 协议。

## H. state 与 WebSocket 审计

| WebSocket 消息 | 当前状态来源 | 已有程度 | 需要新增 StateAggregator 的内容 |
|---|---|---|---|
| `runtime.state` | `Engine.diagnostics()`、`health_summary()`、config/system state | 部分已有 | `system_state`、`playback_state`、APP-facing brightness/CCT/link fields |
| `playback.progress` | `Engine.timestamp`、`Engine.diagnostics().media_position`、`ShowDefinition.duration`、media reader duration | 部分已有 | ms 单位转换、show_id、session/runtime id |
| `device.status` | `PhysicalMapping` node ids、`OutputHealth`、firmware protocol readiness | 只有 Host 侧推断 | per-node online/offline/error、last_seen_ms、error_code；硬件 telemetry 为 `NOT HARDWARE VERIFIED` |
| `error.event` | `Engine.diagnostics().last_error`、`OutputHealth.last_error` | 部分已有 | 统一 error code/source/severity/event id |
| `heartbeat` | 无；WSS 层职责 | 无 | WebSocket service 心跳 |
| `session.connected` | 无；认证/会话层职责 | 无 | SessionStore 和 WSS connection registry |

结论：需要新增 `StateAggregator`。它读取 Engine diagnostics、output health、Runtime Controller、DeviceRegistry、SessionStore，再发布 REST state 和 WSS JSON 消息。

## I. 认证字段审计

`pairing_code`、`client_id`、`client_name`、`client_type`、`app_version`、`access_token`、`refresh_token`、`expires_in`、`scope`、`ws_ticket`、`subscribe`、`session_id` 与现有 LIGHT-BELT Engine 无关。它们可以只在 Host Service 层实现，不影响 Engine、ShowRuntime、Effect、Mapping、Output、RS-485、UDP、STM32、ESP32。

建议约束：

- `client_type` 保留 `tablet / phone / debug`，并在 Host Service 层校验。
- `scope` 至少拆为 `state:read`、`playback:write`、`lights:write`、`effects:write`、`debug:read`。
- `ws_ticket` 使用短时一次性票据，避免长期 access token 暴露在 WebSocket URL 或日志。

## J. 风险与调整建议

| 字段/能力 | 问题是什么 | 为什么冲突 | 推荐改成什么 | 是否影响 APP 方开发 |
|---|---|---|---|---|
| `target_id` 扁平字符串 | 当前 show 内部 target 是 typed domain；同名 analog/digital 不等价 | `docs/contracts/FRAME_CONTRACT.md` 禁止 analog/digital 隐式互转 | Host API 保留扁平名，但 Host `TargetRegistry` 明确展开为 analog/digital/both/virtual_path | 轻微影响；APP 仍用简单名称 |
| `screen` | 当前 layout 没有 `screen` | 真实配置只有 `front` 和 `screen_to_wall` path | 调整为 Host alias：`screen -> front`，或删除直到 layout 有真实 screen | 影响较小；APP 需显示为“Front/Screen”别名 |
| `screen_surround` | 当前 layout 没有该目标 | 没有同名 zone/strip/path，强行映射会制造不存在的物理目标 | 调整为 Host alias：`screen_surround -> front + wall_left + wall_right` | 影响较小；APP 需按组合目标显示 |
| `virtual_path.screen_to_wall` 点号形式 | 当前内部 path id 是 `screen_to_wall`，kind 是 `virtual_path` | 内部不是单一字符串 target | 保留 APP 名称，但 Host 解析为 `kind=virtual_path,id=screen_to_wall`；或 Candidate v0.9 推荐 `virtual_path:screen_to_wall` | 轻微影响；APP 可兼容旧点号 |
| `color_temperature` 全局/分区 | 当前只有 RGB+CCT 通道和 RGB->CCT 策略，没有 Kelvin runtime API | 直接塞入协议会破坏协议纯量化职责 | Host 新增 Kelvin -> WW/CW 策略，输出为 logical RGBCCT 或 transform bias | 中等；APP 仍可使用 Kelvin slider |
| `transition_ms` | RS-485 有 per-node `fade_ms`，digital WS2811 没有同等硬件 fade 字段 | 统一承诺所有输出硬件 transition 会过度承诺 | 调整为 Host software transition；RS-485 可同时设置 `fade_ms`，UDP 由 Host 分帧渐变 | 中等；APP 需接受软件过渡语义 |
| `last_seen_ms` | 当前没有固件回传或节点心跳 | 只能从 Host 发送时间推断，不能证明设备在线 | 调整为 `last_output_ms`；未来有固件诊断后再加 `last_seen_ms` | 中等；APP 设备页需显示推断状态 |
| `node_type` 值 | 候选 `stm32_rgbcct / esp32_ws2811` 合理，但 node_id 当前全局唯一且数字 node 为 7 | APP 可能以为 node_id 1 同时用于两类设备 | 保留 `node_type`，并要求 `node_id` 在 Host state 内全局唯一；RS-485 1-6，UDP 当前 7 | 轻微 |
| `playback_state.stopped` vs `idle` | 当前 Engine diagnostics 是 running boolean + mode，不区分所有状态 | REST 状态若直接推断会不稳定 | StateAggregator 明确定义 idle/ready/running/error 与 playback idle/playing/paused/stopped/error 的转换表 | 轻微 |
| `seek` | 任意倒退 seek 不是 Show Orchestration V1 保证 | Stateful effect 需要 reset/replay 才确定 | Candidate v0.9 写明 seek 通过 reset/replay 实现，不能保证无缝随机访问 | 中等；APP seek UI 可用但需显示加载/重建状态 |
| `effects/set.params` 统一 `color/speed/intensity` | 当前 effect 参数不是统一集合 | 忽略 effect-specific 参数会降低能力，强行统一会误导 | Candidate v0.9 保留 common params，并允许 `effect_params` 白名单扩展 | 中等；APP 表单需按 effect capability 生成 |
| `audio_link_enabled` / `video_link_enabled` | 当前是 media/analyzer 是否存在，不是用户开关 | 直接暴露 enabled 可能混淆“已连接”和“启用” | 拆为 `audio_available`/`video_available` 与 `audio_link_enabled`/`video_link_enabled` | 轻微 |

## K. 最终建议版本：Host API Candidate v0.9

这是建议冻结前的 Candidate v0.9，不是 V1.0 定稿。

### Transport

- HTTPS Base URL: `https://<host>:8443/api/v1`
- WebSocket URL: `wss://<host>:8443/ws`
- TLS 指纹校验保留在 APP 配对/信任流程中。

### Auth / Session

- `POST /auth/pair`
  - request: `pairing_code`, `client_id`, `client_name`, `client_type`, `app_version`
  - response: `access_token`, `refresh_token`, `expires_in`, `scope`
- `POST /auth/refresh`
  - request: `refresh_token`
  - response: `access_token`, `refresh_token`, `expires_in`, `scope`
- `POST /session/ws-ticket`
  - request: `access_token`, `subscribe`
  - response: `ws_ticket`, `session_id`, `expires_in`

### State

- `GET /state`
  - `system_state`: `idle | ready | running | error`
  - `playback_state`: `idle | playing | paused | stopped | error`
  - `show_id`: string or null
  - `position_ms`: integer
  - `duration_ms`: integer
  - `brightness`: number `[0.0, 1.0]`
  - `color_temperature`: integer `[2700, 6500]`, Host-level policy
  - `audio_available`: boolean
  - `video_available`: boolean
  - `audio_link_enabled`: boolean
  - `video_link_enabled`: boolean
  - `devices`: array of Host-derived device states

### Devices

- `node_id`: integer, Host state 内全局唯一
- `node_type`: `stm32_rgbcct | esp32_ws2811`
- `status`: `online | offline | error`
- `last_output_ms`: integer
- `last_seen_ms`: integer only when real telemetry exists; otherwise omit
- `error_code`: string or null
- `hardware_verified`: boolean, current software-only runs must report `false`

### Shows / Playback

- `GET /shows`
  - returns Host-managed show catalog: `show_id`, `duration_ms`, optional label/description
- `POST /playback/play`
  - request: `show_id`, `start_position_ms`
  - semantics: Runtime Controller loads show/effect and starts/resumes engine task
- `POST /playback/pause`
  - semantics: freeze media/show timestamp; time-dependent state does not advance
- `POST /playback/stop`
  - semantics: stop runtime and send safe all-black frame
- `POST /playback/seek`
  - request: `position_ms`
  - semantics: reset/replay to position when backward or large jump is required

### Lights

- `POST /lights/set`
  - request: `target_id`, `brightness`, `color_temperature`, `transition_ms`
  - Host resolves `target_id` via TargetRegistry.
  - `brightness` is applied through Host runtime override / OutputTransform path, not in protocol codecs.
  - `color_temperature` maps to RGB+CCT strategy in Host layer.
  - `transition_ms` is software transition for all outputs; RS-485 may additionally use `fade_ms`.

### Effects

- `POST /effects/set`
  - request: `target_id`, `effect_type`, `params`
  - `effect_type`: keep all 12 registered names: `static`, `breath`, `color_wave`, `chase`, `comet`, `audio_pulse`, `bass_pulse`, `spectrum`, `video_ambient`, `video_audio_fusion`, `calm`, `demo`
  - common params: `color.r/g/b` as `0~255`, `speed` as `[0.0,1.0]`, `intensity` as `[0.0,1.0]`
  - Host Adapter normalizes common params and validates effect-specific params against current effect capability.

### WebSocket Messages

- `session.connected`
- `runtime.state`
- `playback.progress`
- `device.status`
- `error.event`
- `heartbeat`

All WSS messages are generated by Host Service / StateAggregator and must not require protocol changes in RS-485 v2 or UDP v2.
