# Host API Candidate Mapping

本文件给出候选 Host API 到当前 LIGHT-BELT 代码的映射建议。它不是 V1.0 接口定义，也不新增正式接口。

## effect_type -> LIGHT-BELT internal effect type

| Host API effect_type | LIGHT-BELT internal effect type | 代码依据 | 映射建议 |
|---|---|---|---|
| `static` | `static` | `light_engine/effects/static.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `breath` | `breath` | `light_engine/effects/breath.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `color_wave` | `color_wave` | `light_engine/effects/color_wave.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `chase` | `chase` | `light_engine/effects/chase.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `comet` | `comet` | `light_engine/effects/comet.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `audio_pulse` | `audio_pulse` | `light_engine/effects/audio_pulse.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `bass_pulse` | `bass_pulse` | `light_engine/effects/bass_pulse.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `spectrum` | `spectrum` | `light_engine/effects/spectrum.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `video_ambient` | `video_ambient` | `light_engine/effects/video_ambient.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `video_audio_fusion` | `video_audio_fusion` | `light_engine/effects/video_audio_fusion.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `calm` | `calm` | `light_engine/effects/calm.py`, `light_engine/effects/__init__.py` | 直接映射 |
| `demo` | `demo` | `light_engine/effects/demo.py`, `light_engine/effects/__init__.py` | 直接映射；APP 建议标记为调试/演示 |

参数映射：

| Host API param | 当前内部概念 | 代码依据 | 映射建议 |
|---|---|---|---|
| `color.r/g/b` `0~255` | effect color config usually RGB `[0,1]` | `config/effects.yaml`, `light_engine/effects/base.py` | EffectCommand Adapter 归一化为 `[0,1]` |
| `speed` `[0,1]` | `EffectContext.speed` 和部分 effect-specific speed | `light_engine/models.py`, `light_engine/effects/chase.py`, `light_engine/effects/color_wave.py`, `light_engine/effects/comet.py` | Adapter 统一映射到 context speed 或 effect 参数 |
| `intensity` `[0,1]` | `EffectContext.intensity` | `light_engine/models.py` | Adapter 映射到 context intensity |
| effect-specific params | `_EFFECT_PARAMETER_KEYS` | `light_engine/effects/base.py` | Adapter 按 effect 白名单校验 |

## target_id -> LIGHT-BELT internal zone/strip/segment/path

| Host API target_id | Internal mapping | 代码依据 | 映射建议 |
|---|---|---|---|
| `all` | `TargetSelector(kind="all")`; all analog zones + all digital strips | `light_engine/show/loader.py`, `light_engine/show/compositor.py` | 直接映射 |
| `ceiling_left` | analog zone `ceiling_left`; digital strip `ceiling_left`; digital segment `ceiling_left_main`; analog node 1; digital node 7 offset 0 count 144 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `ceiling_right` | analog zone `ceiling_right`; digital strip `ceiling_right`; digital segment `ceiling_right_main`; analog node 2; digital node 7 offset 144 count 144 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `wall_left` | analog zone `wall_left`; digital strip `wall_left`; digital segment `wall_left_main`; analog node 3; digital node 7 offset 288 count 100 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `wall_right` | analog zone `wall_right`; digital strip `wall_right`; digital segment `wall_right_main`; analog node 4; digital node 7 offset 388 count 100 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `front` | analog zone `front`; digital strip `front`; digital segment `front_main`; analog node 5; digital node 7 offset 488 count 72 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `rear` | analog zone `rear`; digital strip `rear`; digital segment `rear_main`; analog node 6; digital node 7 offset 560 count 72 | `config/layout.yaml` | Host 组合目标，默认 analog+digital |
| `screen` | no direct layout target; closest current target is `front` | `config/layout.yaml` | 需要调整候选参数：Host alias `screen -> front` |
| `screen_surround` | no direct layout target; possible alias `front + wall_left + wall_right` | `config/layout.yaml` | 需要调整候选参数：Host alias / group |
| `virtual_path.screen_to_wall` | virtual path id `screen_to_wall`; internal virtual strip id `__virtual_path__:screen_to_wall` during render | `config/layout.yaml`, `light_engine/mapping/virtual.py`, `light_engine/show/compositor.py` | Host 解析点号前缀为 `TargetSelector(kind="virtual_path", id="screen_to_wall")` |

## state field -> LIGHT-BELT internal state/stat/model

| Host API state field | Current internal source | 代码依据 | 映射建议 |
|---|---|---|---|
| `system_state` | Engine running/error + output health | `Engine.diagnostics()` in `light_engine/engine/__init__.py`, `health_summary()` in `light_engine/outputs/__init__.py` | StateAggregator 生成 |
| `playback_state` | Clock paused/ended + Runtime Controller desired state | `light_engine/clock.py`, `light_engine/engine/__init__.py` | 需要新增 Runtime Controller 状态 |
| `show_id` | `ShowDefinition.id` or current `Engine._diagnostics["mode"]` | `light_engine/show/models.py`, `light_engine/engine/__init__.py` | ShowCatalog + Runtime Controller 生成 |
| `position_ms` | `Engine.timestamp` / diagnostics `media_position` in seconds | `light_engine/engine/__init__.py` | StateAggregator 秒转毫秒 |
| `duration_ms` | `ShowDefinition.duration`, media reader duration, synthetic data duration | `light_engine/show/models.py`, `light_engine/media/__init__.py`, `light_engine/data/generators.py` | Runtime Controller 选择当前来源并转毫秒 |
| `brightness` | `OutputTransform.global_brightness`; config `system.smoothing.max_brightness` | `light_engine/outputs/transform.py`, `config/system.yaml` | Host runtime state + OutputTransform |
| `color_temperature` | no direct state; RGBCCT WW/CW channels exist | `light_engine/models.py`, `light_engine/outputs/transform.py` | 需要新增 Host Service 层 CCT state |
| `audio_link_enabled` | no explicit switch; audio availability exists | `Engine.diagnostics()` in `light_engine/engine/__init__.py` | 拆为 available + enabled |
| `video_link_enabled` | no explicit switch; video availability exists | `Engine.diagnostics()` in `light_engine/engine/__init__.py` | 拆为 available + enabled |
| `devices` | layout nodes + output health | `config/layout.yaml`, `light_engine/mapping/physical.py`, `light_engine/outputs/__init__.py` | DeviceRegistry + StateAggregator |

## node_type -> LIGHT-BELT output node/protocol

| Host API node_type | Current internal node/protocol | Node ids in current layout | 代码依据 | 映射建议 |
|---|---|---|---|---|
| `stm32_rgbcct` | RS-485 v2 analog RGB+CCT node command | 1-6 | `config/layout.yaml`, `light_engine/mapping/physical.py`, `light_engine/outputs/rs485_v2.py`, `firmware/stm32_rgbcct_node/src/protocol.h` | 直接映射 |
| `esp32_ws2811` | UDP v2 complete physical RGB frame | 7 currently | `config/layout.yaml`, `light_engine/mapping/physical.py`, `light_engine/outputs/udp_v2.py`, `firmware/esp32_ws2811_node/src/protocol.h` | 直接映射 |

设备状态字段建议：

- `node_id`: 使用 Host 状态内全局唯一 id；当前 analog 1-6，digital 7。
- `status`: 从 output health 和未来 node telemetry 生成。
- `last_output_ms`: 当前可由 Host 记录发送时间生成。
- `last_seen_ms`: 只有真实固件回传或诊断链路实现后生成；当前为 `NOT HARDWARE VERIFIED`。
- `error_code`: 从 `OutputHealth.last_error` 规范化。

## command -> LIGHT-BELT internal function/class/module

| Host API command | Internal function/class/module | 是否直接调用 | 映射建议 |
|---|---|---|---|
| `auth/pair` | none | 否 | Host Service 独立实现 PairingStore |
| `auth/refresh` | none | 否 | Host Service 独立实现 TokenStore |
| `session/ws-ticket` | none | 否 | Host Service 独立实现 WSS ticket |
| `state` | `Engine.diagnostics()`, `health_summary()` | 部分 | StateAggregator 读取并转换 |
| `shows` | `load_show()`, `ShowDefinition`, filesystem/catalog | 部分 | ShowCatalog 管理 show_id -> show file/definition |
| `playback/play` | `Engine.set_show_runtime()`, `Engine.set_effect()`, `Engine.run()` | 不应由 request thread 直接调用 | Runtime Controller 启动/恢复后台 engine task |
| `playback/pause` | `Clock.paused`, `FakeClock.set_paused()` test concept, mpv pause state | 否 | Runtime Controller 控制 media/mpv/clock |
| `playback/stop` | `Engine._running`, `_shutdown()` safe frame | 不直接调用私有字段 | Runtime Controller 请求停止并等待 shutdown |
| `playback/seek` | `Clock`, `Engine.reset()`, ShowRuntime reset/replay semantics | 部分 | Runtime Controller reset/replay 到目标时间 |
| `lights/set` | `OutputTransform`, `TargetResolver`, `PhysicalMapping` | 部分 | LightCommand Adapter 生成 runtime override |
| `effects/set` | `create_effect()`, `Engine.set_effect()`, `ShowRuntime`, `CueRenderJob` | 部分 | EffectCommand Adapter 生成 global effect 或 ephemeral targeted overlay |

## 不建议映射到核心协议的字段

以下字段属于 Host Service / APP 控制面，不应进入 RS-485 v2 或 UDP v2 wire format：

- `pairing_code`, `access_token`, `refresh_token`, `ws_ticket`, `session_id`
- `client_name`, `client_type`, `app_version`, `scope`, `subscribe`
- `system_state`, `playback_state`, `show_id`, `duration_ms`
- APP 可见 `target_id` 别名，如 `screen`, `screen_surround`
- Kelvin `color_temperature`
- WebSocket message names

RS-485 v2 和 UDP v2 应继续只表达物理帧数据、node id、sequence、flags、payload 和 CRC。
