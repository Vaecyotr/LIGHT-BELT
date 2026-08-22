# Phase 33 Composable 1D Primitives 软件验收

日期：2026-08-22

结论：**软件验收通过；全部实体灯光、RK3588 性能、跨 ESP32 接缝观感与时序均 NOT HARDWARE VERIFIED。**

## 基线与工作树

- Worktree：`A:\BaiduNetdiskDownload\LIGHT-BELT\.agent-worktrees\WT04-github-main-reference`
- HEAD：`320dd90d638fddc63a5cc6a2cfd0cca46f0b4d3e`
- 初次 Phase 33 实施开始时工作树已有 195 项 Phase 31/32 修改或未跟踪路径；本阶段保留这些用户工作，未 reset、未
  checkout、未 stage、未 commit。
- 初次验收结束时 `git status --porcelain=v1` 为 203 项；closeout fix 开始前为 204 项，最终为
  205 项。该数量包含进入本阶段前的既有变化，不能作为 Phase 33 独立文件数。
- 不可变资产 `assets/energy-wakeup/energy-wakeup.yaml` 的基线与最终 SHA-256 均为
  `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D`。

## 验收范围与结果

1. `ScalarSource` V1 仅暴露自然归一化的 cue/audio signals；未纳入 unbounded `raw_level`、
   dominant frequency/magnitude、表达式、Python/eval 或 WLED 字段名。
2. `color_wipe` 保持 time-driven 默认值，并支持 external progress 与 frame-rate-independent slew。
3. `comet` 支持 count、phase spacing、wrap/bounce/sine 轨迹与零尾迹；原单 emitter 默认状态机保持。
4. `twinkle` 支持 event width、blur、gate 与 birth gain；颜色仍是 authored/palette/random，不存在
   audio palette framework。
5. `onset_ripple` 支持 fixed/random origin、one-way/bidirectional propagation 与 wrap；random origin
   保存为同一 deterministic `[0,1)` 相对坐标，再分别映射到每条独立 logical path 的长度；
   `virtual_path` 仍作为一条连续路径。silence/stale 不产生新 wave，活动 wave 继续自然衰减。
6. `history_stream` 是 Phase 33 唯一新增 effect ID。它按 fixed step 将 authored sample 变成有界
   logical-path spatial history；forward/reverse、reset/seek、30/60 FPS、timeline、ScalarSource gain 与
   `virtual_path` 均有软件测试。
7. Registry、Show loader、Host capabilities、Pydantic effect enum 与静态 OpenAPI 来自同一效果合同；
   当前 catalog 为 21 个 IDs，Phase 32 catalog 之外只增加 `history_stream`。
8. `coherent_noise_field`、Audio Reactive Palette、2D、Particle System、WLED aliases/API、ESP32 firmware
   和 Phase 34 均未实现。

## 实际命令与证据

| 阶段 | 命令 | 返回码 | 结果 |
| --- | --- | ---: | --- |
| Python 验证 | `.\.python\Scripts\python.exe -c "import sys, pathlib, light_engine; ..."`（AGENTS.md 完整验证表达式） | 0 | `PROJECT_PYTHON_OK`；包来自本 worktree |
| 变更前基线 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | 1067 passed，3 warnings，547.19s |
| ScalarSource / wipe | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase33_scalar_color_wipe.py ...` | 0 | 最终聚焦合集 65 passed，1.06s |
| comet | `.\.python\Scripts\python.exe -m pytest -q tests/test_comet_moving_emitters.py tests/test_effects.py -k "comet or moving_emitters" tests/test_ws2811_two_node_virtual_path_comet_show.py` | 0 | 33 passed，46 deselected，0.90s |
| onset ripple | `.\.python\Scripts\python.exe -m pytest -q tests/test_onset_ripple_phase33.py tests/test_phase32_effect_closeout.py tests/test_phase32_native_effects.py` | 0 | 43 passed，1.587s |
| Wave 1 首次集成 | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase33_scalar_color_wipe.py tests/test_comet_moving_emitters.py tests/test_onset_ripple_phase33.py tests/test_effects.py tests/test_phase32_native_effects.py tests/test_phase32_effect_closeout.py tests/test_effect_registry.py tests/test_host_effect_registry.py tests/test_show_config.py tests/test_show_v2.py tests/test_virtual_paths.py tests/test_ws2811_two_node_virtual_path_comet_show.py` | 1 | 249 passed、1 failed，3.15s；静态 OpenAPI 尚未同步 comet params |
| Wave 1 集成复测 | 同上 | 0 | 250 passed，2.23s |
| Wave 1 全套 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | 1138 passed，3 warnings，569.51s |
| twinkle/history 聚焦 | `.\.python\Scripts\python.exe -m pytest -q tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py` | 0 | 38 passed，0.64s |
| twinkle legacy 聚焦 | `.\.python\Scripts\python.exe -m pytest -q tests/test_effects.py -k twinkle` | 0 | 5 passed，45 deselected，0.43s |
| Wave 2 首次集成 | `.\.python\Scripts\python.exe -m pytest -q tests/test_twinkle_event_fields_phase33.py tests/test_history_stream_phase33.py tests/test_phase33_scalar_color_wipe.py tests/test_comet_moving_emitters.py tests/test_onset_ripple_phase33.py tests/test_effects.py tests/test_effect_registry.py tests/test_host_effect_registry.py tests/test_show_config.py tests/test_show_v2.py tests/test_virtual_paths.py tests/test_phase32_effect_closeout.py tests/test_phase32_native_effects.py tests/test_phase32_energy_wakeup_non_regression.py` | 1 | 288 passed、2 failed，8.88s；旧测试固定写死 20-effect catalog |
| Wave 2 集成复测 | 同上 | 0 | 290 passed，6.55s |
| Wave 2 全套 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | 1177 passed，3 warnings，576.62s |
| Phase 33 acceptance 聚焦 | `.\.python\Scripts\python.exe -m pytest -q tests/test_phase33_software_acceptance.py tests/test_phase32_energy_wakeup_non_regression.py tests/test_host_effect_registry.py tests/test_effect_registry.py` | 0 | 45 passed，4.37s |
| 必需 benchmark | `.\.python\Scripts\python.exe -m light_engine benchmark --effect video_audio_fusion --frames 1800` | 0 | 1800 frames / 60.67s；131.4 FPS；P50 7.57ms；P95 10.12ms；P99 10.79ms；0 drops |
| 最终全套 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | **1185 passed，3 warnings，565.89s** |
| 差异检查 | `git diff --check` | 0 | 无 whitespace error；Windows CRLF conversion warnings 不影响返回码 |

三个最终 pytest warnings 均为既有 FastAPI/Starlette deprecation warnings：一个 `httpx`/TestClient
warning 与两个 `on_event` lifespan warnings；没有测试失败。

## Phase 33 closeout fix

2026-08-22 closeout 只修复两项，不扩展 Phase 33 功能，也不启动 Phase 34：

1. `onset_ripple(event_origin=random)` 原先把最长独立 strip 的长度写入 hash，并把生成的绝对像素
   origin 复用于所有 strip；较短 strip 因而可能完全收不到 wave。现在 wave 保存由 seed、cue ID 和
   event index 决定的归一化 `[0,1)` origin，每条独立 logical path 按自己的 `pixel_count` 映射。
   等长路径保持同位置；`virtual_path` 仍作为一条连续逻辑路径只映射一次。fixed、one-way、
   bidirectional、wrap、silence 中活动 wave 的语义不变。随机 seeded replay 仍确定性，但旧 bug 产生的
   绝对随机像素位置按设计发生兼容性修正。
2. 活跃/权威文档统一术语：ESP32 是项目灯光控制节点，WLED 是上游开源项目及其协议/效果/源码
   参考，RK3588 是中央 host/renderer/Show engine。保留 `WLED Audio Sync V2`、`WLED v16.0.1`、
   `wled_board` 兼容性 API 字段、真实 worktree/branch 名及历史 changelog；没有重命名代码符号或协议
   标识。

Closeout 实际命令与结果：

| 阶段 | 命令 | 返回码 | 结果 |
| --- | --- | ---: | --- |
| 主代理预检 onset | `.\.python\Scripts\python.exe -m pytest -q tests\test_onset_ripple_phase33.py` | 0 | 12 passed，0.62s |
| Agent A 变更前全套 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | 1185 passed，3 warnings，589.72s |
| Agent A onset 聚焦 | `.\.python\Scripts\python.exe -m pytest -q tests\test_onset_ripple_phase33.py` | 0 | 14 passed，0.56s |
| 主代理 onset 复测 | `.\.python\Scripts\python.exe -m pytest -q tests\test_onset_ripple_phase33.py` | 0 | 14 passed，0.43s |
| Phase 33 聚焦 | `.\.python\Scripts\python.exe -m pytest -q tests\test_phase33_scalar_color_wipe.py tests\test_comet_moving_emitters.py tests\test_onset_ripple_phase33.py tests\test_twinkle_event_fields_phase33.py tests\test_history_stream_phase33.py tests\test_phase33_software_acceptance.py` | 0 | 119 passed，1.17s |
| Registry / Show / virtual_path | `.\.python\Scripts\python.exe -m pytest -q tests\test_effect_registry.py tests\test_host_effect_registry.py tests\test_show_config.py tests\test_show_v2.py tests\test_virtual_paths.py tests\test_ws2811_two_node_virtual_path_comet_show.py tests\test_phase32_effect_closeout.py tests\test_phase32_native_effects.py` | 0 | 130 passed，2.19s |
| Energy Wakeup 不变性 | `.\.python\Scripts\python.exe -m pytest -q tests\test_phase32_energy_wakeup_non_regression.py` | 0 | 2 passed，2.51s |
| Closeout 最终全套 | `.\.python\Scripts\python.exe -m pytest -q` | 0 | **1187 passed，3 warnings，545.03s** |
| Closeout 最终资产哈希 | `Get-FileHash -Algorithm SHA256 assets/energy-wakeup/energy-wakeup.yaml` | 0 | `627D23A4C73E66F1913C7B5CBB15CF1B16926E6772289237165535A2278C142D` |
| Closeout 最终差异检查 | `git diff --check` | 0 | 无 whitespace error；仅有 Windows CRLF conversion warnings |

Closeout 触及 `light_engine/effects/onset_ripple.py`、`tests/test_onset_ripple_phase33.py` 以及活跃项目
文档；未修改 runtime registry、Show schema、协议、固件或 Energy Wakeup 资产。

## Phase 33 修改文件

生产与共享合同：

- `light_engine/effects/scalar_source.py`
- `light_engine/effects/color_wipe.py`
- `light_engine/effects/comet.py`
- `light_engine/effects/twinkle.py`
- `light_engine/effects/onset_ripple.py`
- `light_engine/effects/history_stream.py`
- `light_engine/effects/__init__.py`
- `light_engine/show/compositor.py`

测试：

- `tests/test_phase33_scalar_color_wipe.py`
- `tests/test_comet_moving_emitters.py`
- `tests/test_onset_ripple_phase33.py`
- `tests/test_twinkle_event_fields_phase33.py`
- `tests/test_history_stream_phase33.py`
- `tests/test_phase33_software_acceptance.py`
- `tests/test_effects.py`
- `tests/test_phase32_native_effects.py`

文档与公共元数据：

- `docs/IMPLEMENTATION_PLAN.md`
- `docs/reference/effect-reference.md`
- `docs/reference/host-api-v1.openapi.yaml`
- `docs/acceptance/phase33-software-acceptance.md`

## `git diff --stat`

最终检查时全工作树输出为：

```text
161 files changed, 3778 insertions(+), 11112 deletions(-)
```

该统计包含开始 Phase 33 前已经存在的 Phase 31/32 用户修改，并且 Git 的普通 `diff --stat` 不包含
未跟踪新文件；因此不能把它解释为 Phase 33 独立改动量。上节是本阶段实际触及文件清单。

## 已知后续议题（仅记录）

当前若干效果的 common dynamic speed 使用 `cue_time * current_speed` 推进相位或 step。运行中改变
speed 可能造成相位/step 跳变或短暂停滞；未来工作应明确 speed 是否需要改为随时间积分。候选包括
`history_stream`、`flowing_bands`、`single_dot`、`color_wipe`、`heat_fire`，以及可能的 `comet`。
本 closeout 不实现 common dynamic-speed integration redesign；该议题不是 Phase 33 blocker。

## 限制与未验证项

- benchmark 只在当前 Windows / Python 3.11.9 环境执行；RK3588 ARM64 性能 **NOT HARDWARE VERIFIED**。
- 未修改 ESP32 firmware、协议、DDP、物理 topology 或安全状态；固件 build 不属于批准的 Phase 33，
  因此未执行。
- `history_stream` 可以在精确 step 时间重建 authored color timeline；live audio gain 只使用当前
  context，不伪造不可获得的历史 audio samples。
- WLED v16.0.1 仅作为 visual mechanism 参考；没有 WLED 数值兼容、mode ID、Segment、palette ID 或
  runtime ownership 声明。
- 实体灯带颜色、接缝、功耗、网络、同步和观感全部 **NOT HARDWARE VERIFIED**。
- 未 commit；按批准停止在 Phase 33，不准备 Phase 34。
