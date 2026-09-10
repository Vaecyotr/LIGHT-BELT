# 测试治理与 Cleanup 收尾审计（2026-09-10）

本轮只修改测试及其治理文档，不修改 Host、brightness、Config singleton、
ParameterSpec、Engine/ShowRuntime、effect 架构、mapping、codec/transport 或 Show 内容。
Host 仍从 `assets/` 发现 Show；config Show 只是测试 / CLI / 兼容 fixture。

## 执行结果

解释器已验证：工作树 `.python/Scripts/python.exe` 指向项目共享 bundled venv，
`light_engine` 从当前工作树导入（`PROJECT_PYTHON_OK`，返回码 0）。
清理前默认 production：1199 passed，55.58 秒，3 warnings，返回码 0；
原始逐文件结果为 `tmp/test-audit/cleanup-production-before.json`。
基线执行时源码/配置/依赖状态未变化，因此本轮复用该基线。

下表为本轮完整执行，不是 collect-only。秒数取 pytest 整轮报告，包含收集等开销；
逐文件秒数为 setup/call/teardown 累加，不应与整轮墙钟时间混淆。
共享 fixture 计入第一个消费者。无跳过、xfail 或放宽断言以隐藏失败。

| 层 | 收集 / 执行 | 结果与整轮耗时 | 返回码 |
| --- | ---: | --- | ---: |
| fast | 381 / 381 | 381 passed in 3.11s | 0 |
| production | 1192 / 1192 | 1192 passed, 3 warnings in 33.75s | 0 |
| full | 1495 / 1495 | 1495 passed, 3 warnings in 254.05s (0:04:14) | 0 |
| history | 115 / 115 | 115 passed in 190.24s (0:03:10) | 0 |

前后数量：fast 386→381；production 1199→1192；full 1497→1495；history 116→115。
full 净变化为删除 2 项临时 SHA、删除 2 项旧 Phase 32 冻结、增加 1 项容量边界、
拆出 1 项独立历史 Cabin digest 测试；三个慢测试和三个证据比较测试只换层，未删除。

首轮受影响定向测试 39 passed / 1 failed，33.14 秒，返回码 1：拆分音乐性能测试时
误删了普通音乐断言仍使用的 NumPy import。恢复 import 后，相关两个文件 6 passed，
10.28 秒，返回码 0。其他定向用例未受此修正影响；最终 full 再次覆盖全部受影响测试。
原始记录：`cleanup-targeted.{json,log}`、`cleanup-targeted-music-recheck.{json,log}`。

### 最慢测试与文件

清理前 production：10 秒音频验收 10.16 秒；300 秒音乐历史压力 4.76 秒；
音乐 fixture 行为 1.33 秒。最慢文件：Engine 17.97 秒（23 项）、Music Control
7.04 秒（5 项）、Host Adapter 4.88 秒（22 项）。

**fast 最慢单项阶段**（原始 `--durations=25` 的前三项）：

- `1.62s call     tests/test_video_mapping.py::TestVideoAmbientMapping::test_five_color_map`
- `0.05s call     tests/test_clock.py::TestMonotonicClock::test_tick_returns_delta`
- `0.04s call     tests/test_video_mapping.py::TestVideoAudioFusionMapping::test_zones_different`

最慢文件（累计执行秒数）：

- `tests/test_video_mapping.py`：1.764 秒，29 项。
- `tests/test_config.py`：0.216 秒，17 项。
- `tests/test_clock.py`：0.070 秒，16 项。

**production 最慢单项阶段**（原始 `--durations=25` 的前三项）：

- `2.13s call     tests/test_music_control.py::test_locked_fixture_music_expectations_and_json_summaries`
- `1.10s call     tests/test_wled_nine_node_profiles.py::test_energy_wakeup_has_only_real_digital_targets`
- `1.07s call     tests/test_engine.py::TestAudioVideoBothStop::test_both_stop_at_longest`

最慢文件（累计执行秒数）：

- `tests/test_engine.py`：7.607 秒，22 项。
- `tests/test_host_real_engine_adapter.py`：4.882 秒，22 项。
- `tests/test_music_control.py`：3.340 秒，4 项。

**full 最慢单项阶段**（原始 `--durations=25` 的前三项）：

- `62.16s call     tests/test_show_e2e_acceptance.py::test_phase_17_show_acceptance_outputs_required_evidence`
- `42.11s setup    tests/test_single_strip_visual_showcase_observability.py::test_full_30fps_runtime_is_deterministic_media_free_and_safe`
- `22.72s call     tests/test_ws2811_staged_shows.py::test_stage3_runs_all_9000_frames_through_transform_mapping_and_udp`

最慢文件（累计执行秒数）：

- `tests/test_show_e2e_acceptance.py`：62.164 秒，1 项。
- `tests/test_single_strip_visual_showcase_observability.py`：45.193 秒，18 项。
- `tests/test_single_strip_acceptance_show(1).py`：31.607 秒，8 项。

**history 最慢单项阶段**（原始 `--durations=25` 的前三项）：

- `61.03s call     tests/test_show_e2e_acceptance.py::test_phase_17_show_acceptance_outputs_required_evidence`
- `44.07s setup    tests/test_single_strip_visual_showcase_observability.py::test_full_30fps_runtime_is_deterministic_media_free_and_safe`
- `19.45s call     tests/test_ws2811_staged_shows.py::test_stage3_runs_all_9000_frames_through_transform_mapping_and_udp`

最慢文件（累计执行秒数）：

- `tests/test_show_e2e_acceptance.py`：61.037 秒，1 项。
- `tests/test_single_strip_visual_showcase_observability.py`：47.480 秒，18 项。
- `tests/test_single_strip_acceptance_show(1).py`：32.100 秒，8 项。

## 最终分层与删除依据

- 日常：相关定向测试 + fast；普通任务完成：默认 production；大规模、跨层、发布前：full；
  单独追溯历史：history。production 包含 fast；full 包含全部层（含 history）。
- 显式路径不带 `--suite` 时不做层过滤；显式 `--suite` 仍会过滤路径。
  新文件未分类时进入 production。选择机制本轮未改。
- 10 秒真实时钟音频帧数、300 秒模拟历史压力、吞吐容量检查原样迁移到 full，
  不缩短时长或调整容差。production 保留较短停止、时长/帧数控制、音乐行为/确定性，
  并新增跨容量边界检查；Host Adapter/API 当前路径不因累积耗时迁走。
- `test_cleanup_contracts.py` 两项临时 SHA 只证明清理前后当前 Show 不变，没有独立行为保护。
  删除它们；其余三项证明比较器仅忽略顶层 commit、仍拒绝渲染值/嵌套来源变化，
  迁入 `test_campaign_evidence_comparison.py`，归 full；因此删除临时文件而非删掉这些断言。
- `test_phase32_energy_wakeup_non_regression.py` 两项检查对当前文件施加旧 SHA 和
  assets==config 关系，已与批准的独立角色约定冲突。它的消费者是 pytest 历史门禁和过去
  acceptance 命令记录，无运行时消费者。旧值保存在
  [Phase 32 历史记录](history/phase32-energy-wakeup-freeze.md)，删除执行测试，未更新 golden。
- Cabin 固定历史渲染摘要移入独立 history 测试；full 原文件仍验证协议 golden 身份、
  拒绝损坏/不完整/越界帧、安全全黑帧，以及 reset 后动态 replay 一致。
- 当前加载/目标覆盖保留于 `test_wled_nine_node_profiles.py`、Show 校验/运行测试；
  Host 发现覆盖在 `test_host_shows_loader.py`（临时目录）。这些覆盖并非对实际生产 assets
  文件与当前部署兼容性的验收，没有增加当前原件与兼容 fixture 相等约束。
- 带 `(1)` 的 campaign、UDP/serial 潜在重叠、旧 profile/Show corpus 均保留：
  存在独立断言、回放或维护消费者，未证明可无损合并。停止继续寻找删除机会。

## SHA / digest 用途清单

原则：**功能正确 → 行为测试；文件变化 → Git/review；发布/固件/协议精确身份 → SHA**。
动态两次运行摘要相等检查的是确定性，不是冻结普通文件。
审计覆盖 `tests/` Python、JSON、manifest、README，以及被测试调用的摘要脚本和协议 golden。
搜索原始结果位于 `tmp/test-audit/cleanup-sha-python-search.txt`；以下按消费者归类。

| 对象 / 消费者 | 类型与层 | 处理与理由 |
| --- | --- | --- |
| 当前 assets Show 字节和 config Show 规范化 YAML / 原 cleanup 两项 | 临时文件冻结 / 原 fast | 删除；本轮未改内容，变化由 Git review 判断 |
| 当前 Show 旧 SHA、双份 Show 相等、6 个固定 render 摘要 / 原 Phase32 两项 | 失效历史验收 | 删除执行测试，旧值只留历史文档；不刷新摘要 |
| `firmware/shared/udp_v3_golden.json` / `test_cabin_v3_e2e_acceptance.py` | 协议逐字节身份 / full | 保留 `json_sha256`，同时保留解码、CRC、边界和帧完整性断言 |
| Cabin archived Show/profile 的 `deterministic_replay_sha256` / `test_cabin_v3_historical_replay.py` | 历史 Phase31 render 身份 / history | 从 full 文件拆出，仅历史执行；动态 reset 一致性留在 full |
| 五个 locked WAV + audio `manifest.json` / `test_music_control.py` | 明确锁定的输入 fixture 身份 / production | 保留 SHA 和字节数；音频分析行为依赖相同样本输入，不是普通 YAML 冻结 |
| acceptance 生成文件的 `artifact_sha256` / `test_authoring_modulation_acceptance.py` | 动态产物 manifest 一致性 / history | 保留重新计算与 manifest 比较；不是硬编码源码/Show SHA |
| `two_run_digests`、生成报告/manifest / `test_show_e2e_acceptance.py` → `scripts/show_acceptance.py` | 两次行为确定性、产物来源记录 / history | 保留；manifest/G8 的摘要动态记录，未用固定当前源码 SHA 代替行为 |
| 历史 baseline 中三份 `show_sha256` / `test_single_strip_acceptance_campaign.py` | 历史 campaign Show 身份 / history | 保留在 history，普通生产 Show 不受该冻结约束 |
| `PINNED_DIGESTS` / `test_single_strip_acceptance_show(1).py` | 历史逐帧 render 身份 / history | 保留旧值及独立有限性、对比和确定性断言，不刷新 |
| `EXPECTED_TRACE_SHA256` / `test_ws2811_breath_trace_replay.py` → replay 脚本 | 历史数据报 trace 身份 / history | 保留，同时验证 round-trip 和可见等级 |
| 全流 SHA / `test_single_strip_visual_showcase_observability.py` | 动态条件对比 / history | 保留；比较当次两次输出，差异诊断能定位具体帧，并非固定文件身份 |
| twinkle cue/seed SHA / `test_twinkle_event_fields_phase33.py` | 确定性种子算法 / production | 保留；输入为 seed/cue ID，不读取/冻结文件 |
| show-orchestration `MANIFEST.sha256` / `scripts/archive/show-orchestration-v1/verify-baseline.py` | 归档基线精确身份 / 手动历史工具 | 保留锁定 G1–G8 fixture 校验，不在 production 添加文件冻结门禁 |
| `generated_from_head` / `tests/conftest.py` 及 campaign/evidence 测试 | Git 来源元数据 / history、full | 保留来源格式与当前 HEAD 校验；不是源文件 SHA，不能替代行为字段比较 |
| APP V1 fixture 的 `source_commit` / `test_app_host_api_v1_freeze.py` | 已发布 API fixture 来源 / production | 保留明确发布版本身份及当前 facade 行为对比，不对当前源码计算固定 SHA |
| `test_golden_consistency.py` 与 UDP/RS485 codec tests | 协议 JSON/header/编码精确相等 / full | 保留；虽不全用 SHA，逐字节协议身份具有独立价值 |

未发现测试对普通可演进源码施加固定文件 SHA。历史 Phase/campaign 摘要未刷新，
协议/固件/发布身份资料未更改；本轮未引入任何新的固定文件 SHA。

## 本轮与此前改动边界

工作区进入本轮时已有 17 个 tracked 文件变更及 5 个 untracked 治理文件。
其中 pipeline.py 及专属 8 项测试的删除、Host 测试断言调整、Show 注释/文档归档说明、
conftest/pyproject 分层设置、Phase33 重复 SHA 删除、campaign fixture 共享是此前改动，
本轮不认领为新增工作，也未回滚。

本轮修改：AGENTS、CLAUDE、tests README、审计报告、archive README、suite 清单、
Engine/Music/Cabin 测试拆分。新增：实时 Engine 验收、音乐压力/性能、证据比较、Cabin
历史 replay 四个测试文件和 Phase32 历史记录。删除：临时 cleanup 文件及 Phase32 旧冻结文件。
进入本轮的上述文件副本在忽略目录 `tmp/test-audit/cleanup-incoming/`，可与最终结果对比。
`git diff --stat` 不包含新增未跟踪文件，应与 `git status --short` 一起阅读。

此前 pipeline 删除的依据仍有效：其类/导入/调用只存在于本体及专属测试，
生产输出队列实际消费者是 `outputs.LatestFrameQueue`（DDP/UDP/serial）。
本轮不继续删除运行时代码。未改 Host 发现路径或两个当前 Show 的内容。

## 最终逐文件清单

数量按参数化实例计算；下表耗时来自同一轮 full。前数量是本轮开始前 1497 项集合，
不是更早的 1500 项集合。非可执行支持文件数量为 0；未测时间不写成 0 秒。

| 文件 | 前→后数量 | 层 | full 累计秒 | 用途 / 保留依据 |
| --- | ---: | --- | ---: | --- |
| `conftest.py` | 0→0 | full | 不适用 | Test-layer collection policy and optional per-file count/timing reports. Selection infrastructure; new unclassified tests remain in production coverage. |
| `tests/__init__.py` | 0→0 | production | 不适用 | Test package marker. Import support; contains no executable test cases. |
| `tests/conftest.py` | 0→0 | history | 不适用 | Shared deterministic single-strip campaign generation and provenance-aware evidence comparisons. One session generation shared by campaign/observability; all behavioral fields still compared. |
| `tests/test_adaptive_selector.py` | 19→19 | fast | 0.024 | Adaptive music-state selection, gating, determinism, and G7 decision contract. Direct current selector behavior with bounded in-memory fixtures. |
| `tests/test_agent_campaign.py` | 13→13 | full | 0.125 | Agent campaign manifest validation, model routing, retries, and report archival. Repository automation is valuable but outside the lighting production regression path. |
| `tests/test_agent_prompts.py` | 4→4 | full | 0.045 | Agent implementation/repair prompt construction and quality-report placement. Maintains development tooling and writes temporary artifacts; run in full maintenance coverage. |
| `tests/test_agent_python.py` | 7→7 | full | 0.034 | Bundled Python discovery and Windows reparse-point safety for agent scripts. Critical workspace safety checks, but unrelated to shipped lighting behavior. |
| `tests/test_analysis.py` | 23→23 | production | 0.947 | Audio/video analyzers, media windows, spectral flux, beat handling, reset, and timestamp inspection. Current signal-analysis behavior; media codecs and generated files make it broader than fast. |
| `tests/test_app_host_api_v1_freeze.py` | 6→6 | production | 0.417 | Released host REST/OpenAPI surface, public capability projection, target privacy, and released facade compatibility. Current public API compatibility uses a released fixture with commit provenance; this compares behavior, not a hash of evolving source files. |
| `tests/test_audio_modulation_loader.py` | 5→5 | fast | 0.007 | Show YAML audio-modulation model loading and precise validation paths. Small current authoring-contract unit coverage. |
| `tests/test_audio_modulation_runtime.py` | 3→3 | fast | 0.003 | Cue audio-modulation formulas, smoothing, bounds, and missing-input neutrality. Small deterministic runtime unit coverage. |
| `tests/test_authoring_modulation_acceptance.py` | 1→1 | history | 0.299 | Frozen Phase 22 authoring-modulation acceptance report and digest evidence. Validates a phase-specific evidence artifact rather than an independent current runtime contract; preserve intact in history. |
| `tests/test_branch_lifecycle_compatibility_phase34.py` | 5→5 | production | 0.050 | Backward compatibility for omitted branch lifecycle and archived branch fixture output. Compatibility for accepted Show grammar remains current even though its fixture is archived. |
| `tests/test_branch_lifecycle_continuity_phase34.py` | 8→8 | production | 0.049 | Pre-roll continuity, replay, authored color history, and live gains across stateful effects. Current lifecycle semantics across several effects; keep in production due cross-effect cost. |
| `tests/test_branch_lifecycle_output_isolation_phase34.py` | 3→3 | production | 0.100 | Hidden pre-roll composition isolation and engine transport/sequence ownership. Protects current no-leak and one-logical-frame architecture constraints. |
| `tests/test_branch_lifecycle_performance_phase34.py` | 3→3 | full | 0.413 | Branch lifecycle benchmark fixture, smoke metrics, and adopted performance evidence. The benchmark remains useful maintenance evidence but should not gate ordinary production regression. |
| `tests/test_branch_lifecycle_runtime_phase34.py` | 7→7 | fast | 0.009 | Start-on-release and pre-roll state advancement, release, reset, and mixed lifecycle behavior. Direct deterministic current runtime semantics despite the phase suffix. |
| `tests/test_brightness_tracks.py` | 17→17 | production | 0.017 | V2 brightness-track schema, interpolation, overlap rules, defaults, and transform ownership. Current Show capability with loader/runtime/transform integration. |
| `tests/test_cabin_v3_e2e_acceptance.py` | 7→7 | full | 0.523 | Complete cabin V3 topology, Show paths, mapping, scheduled UDP transport, codec rejection, safe state, and replay. Large maintenance protocol acceptance remains valuable even though WLED/DDP is the current default. |
| `tests/test_cabin_v3_historical_replay.py` | 0→1 | history | 0.086 | Phase 31 fixed render digest against archived cabin Show/profile. Historical identity only; protocol identity, safe black output and reset determinism stay in full. |
| `tests/test_campaign_evidence_comparison.py` | 0→3 | full | 0.288 | Evidence comparison permits only top-level generation commit changes. Long-term maintenance helper safety; preserves rendered values and nested provenance without freezing current Show files. |
| `tests/test_cli.py` | 2→2 | production | 0.102 | Validated topology inspection data and CLI JSON output. Current user-facing inspection behavior with modest integration scope. |
| `tests/test_clock.py` | 16→16 | fast | 0.074 | Monotonic, offline, fake, media, master, and MPV IPC clock units. Mostly small deterministic clock contracts; real time checks should keep tolerant bounds. |
| `tests/test_clock_integration.py` | 4→4 | production | 0.582 | Injected clocks, pause, seek/reset, sequence ownership, and end-of-media engine behavior. Current engine/clock boundary behavior. |
| `tests/test_color.py` | 29→29 | fast | 0.017 | RGB/HSV/RGBW/RGBCCT conversion, gamma, brightness, interpolation, clamping, and finite-input safety. Foundational pure color math. |
| `tests/test_color_timeline.py` | 15→15 | fast | 0.013 | RGB keyframe interpolation and color-timeline loader validation. Small current authoring/runtime primitive. |
| `tests/test_comet_moving_emitters.py` | 28→28 | fast | 0.030 | Comet multi-emitter geometry, trajectories, replay, frame-rate equivalence, virtual paths, and validation. Current effect capability independent of current Show usage. |
| `tests/test_common_motion_clock_phase34.py` | 19→19 | fast | 0.018 | Integrated common-motion clock slopes, pause/resume, audio/adaptive changes, reset, and input safety. Foundational current motion semantics despite the phase suffix. |
| `tests/test_compositor.py` | 9→9 | fast | 0.006 | Sparse composition, blend modes, deterministic ordering, immutability, finite inputs, and virtual-path splitting. Foundational pure compositor contract. |
| `tests/test_config.py` | 17→17 | fast | 0.282 | Configuration validators, access, defaults, singleton behavior, and profile loading. Small core configuration units. |
| `tests/test_config_validation.py` | 59→59 | production | 2.409 | Checked-in profiles, output selection, topology policies, scheduling, endpoints, and production output wiring. Current fail-closed configuration and deployment contract. |
| `tests/test_current_deployment_docs.py` | 9→9 | production | 0.010 | Authority-document agreement on current nine-node WLED deployment and legacy protocol labeling. Current production topology and terminology agreement remains a production contract. |
| `tests/test_e2e_acceptance.py` | 1→1 | full | 4.589 | Ten-second synthetic video/audio run through analyzers, engine, mapping, and outputs. Broad media end-to-end smoke is valuable but relatively heavy and environment-sensitive. |
| `tests/test_effect_color_timeline.py` | 6→6 | fast | 0.005 | Static, breath, and audio-pulse consumption of cue-local color timelines. Current effect behavior with deterministic inputs. |
| `tests/test_effect_registry.py` | 28→28 | fast | 0.021 | Effect registration, V1 parameter metadata, common intensity/speed, and authored range contracts. Central live registry contract. |
| `tests/test_effects.py` | 50→50 | production | 0.042 | All registered effect renderers, state/reset behavior, parameters, and representative output geometry. Essential current capability coverage; broad size makes it production rather than fast. Consolidate only exact overlaps when newer focused tests prove the same observable contract. |
| `tests/test_engine.py` | 23→22 | production | 7.996 | Engine stop conditions, duration/frame limits, sequences, lifecycle, and safe shutdown. Central engine regression coverage. |
| `tests/test_engine_music_control_state.py` | 6→6 | production | 0.209 | Engine-derived music-control sequences, fixed/adaptive cue delivery, reset, and repeated timestamps. Current engine/show/audio integration. |
| `tests/test_engine_realtime_acceptance.py` | 0→1 | full | 10.161 | Ten-second real-time audio frame-count acceptance. Measured 10.16 seconds before split; unchanged sustained acceptance. Short stop, duration and frame-limit contracts stay in production. |
| `tests/test_engine_wled_audio_source.py` | 15→15 | production | 0.596 | Production live WLED audio-source precedence, lifecycle, stale recovery, and explicit failure. Current production audio ingestion and no-fallback contract. |
| `tests/test_golden_consistency.py` | 3→3 | full | 0.486 | Host/firmware golden JSON codec agreement and deterministic generated headers. Protocol golden vectors are authoritative maintenance checks and must remain in full coverage. |
| `tests/test_history_stream_phase33.py` | 22→22 | production | 0.025 | History-stream ordering, capacity, fixed steps, frame-rate equivalence, timelines, gains, replay, paths, and validation. Current effect capability despite the phase suffix; broad stateful coverage belongs in production. |
| `tests/test_host_effect_registry.py` | 8→8 | production | 0.206 | Host public capability projection versus live registry validation and manual common controls. Protects public/private API separation and live request validation. |
| `tests/test_host_layout_vocab.py` | 17→17 | production | 0.015 | Host target/device vocabulary and derived capability metadata from layout. Current host discovery contract. |
| `tests/test_host_real_engine_adapter.py` | 22→22 | production | 4.898 | Host subprocess launch/stop/resume/manual command behavior and generated manual Show filtering. Current host-to-engine adapter behavior using fakes. |
| `tests/test_host_service_api.py` | 75→75 | production | 1.960 | Host REST state, pairing, shows, playback, lights, scenes, audio, errors, CORS, MPV, brightness, and natural-end watchdog. Large but central released host API regression suite. |
| `tests/test_host_shows_loader.py` | 19→19 | production | 0.148 | Host Show/media discovery, manifests, ffprobe duration, and mixed media cases. Current host content discovery behavior. |
| `tests/test_host_starry_sky.py` | 8→8 | production | 0.014 | Idempotent starry-sky hardware toggle state and failure handling. Current host side-effect adapter contract exercised with fakes. |
| `tests/test_host_wled_profile_resolution.py` | 13→13 | production | 0.070 | Current WLED profile resolution, disabled/custom devices, fail-closed discovery, and refresh timing. Direct current deployment behavior. |
| `tests/test_json_output.py` | 1→1 | fast | 0.007 | JSON output serialization of physical node grouping. Small output adapter contract. |
| `tests/test_legacy_compat.py` | 2→2 | production | 0.001 | Removal of RoutedFrame and direct PhysicalFrame dispatch through send_all. Direct PhysicalFrame dispatch is an active architecture contract. |
| `tests/test_models.py` | 49→49 | fast | 0.035 | Core frame, strip, color, audio/video feature, and effect-context validation and normalization. Foundational pure model contracts. |
| `tests/test_music_control.py` | 5→4 | production | 2.720 | Locked audio fixture identity, music expectations, deterministic streams and bounded-history capacity edge. Current music behavior and exact audio input identity; sustained pressure/throughput live in full. |
| `tests/test_music_control_performance.py` | 0→2 | full | 6.313 | 300-second simulated history pressure and measured 60-FPS processing capacity. Long pressure and environment-sensitive performance acceptance; bounded-capacity edge and music semantics stay in production. |
| `tests/test_node2_effects_demo.py` | 5→5 | history | 7.056 | Retired node-2 comparative effects Show, exact DDP warm frames, mapping, and visibility bounds. Freezes a deployment/demo artifact outside the approved current Show; preserve for replay rather than default regression. |
| `tests/test_onset_ripple_phase33.py` | 14→14 | production | 0.012 | Onset-ripple origin, propagation, event birth, silence/staleness, replay, paths, and validation. Current stateful effect capability despite the phase suffix. |
| `tests/test_output_health.py` | 6→6 | production | 0.004 | Logical/packet health accounting, contiguous RS-485 packets, UDP failure accounting, and serialization. Current observability and frame-integrity contract. |
| `tests/test_output_lifecycle.py` | 8→8 | production | 0.033 | Output rollback, socket ownership, production send/flush failure, reopen, and safe-frame fanout. Current fail-closed output lifecycle and safety behavior. |
| `tests/test_output_safety.py` | 11→11 | production | 0.088 | Explicit production/memory/fake modes, latest-frame queues, safe state, output selection, and failure propagation. Direct core architecture and safety constraints. |
| `tests/test_output_transform.py` | 10→10 | fast | 0.012 | Single brightness application, power limiting, gamma, white bias, immutability, quantization, and safe frame. Foundational output-transform ownership contract. |
| `tests/test_phase32_effect_closeout.py` | 1→1 | fast | 0.001 | Onset-ripple silence prevents births while an existing wave decays. Behavior overlaps onset-ripple coverage and inspects private effect._waves. Merge a public-output version into test_onset_ripple_phase33.py and remove the private count assertion. |
| `tests/test_phase32_native_effects.py` | 30→30 | production | 0.045 | Flowing bands, onset ripple, and heat fire registry, validation, rendering, paths, timelines, and replay. Current effect capabilities despite the phase suffix. |
| `tests/test_phase32_topology_ddp.py` | 21→21 | production | 1.175 | Current profile topology scope, runtime discovery, DDP boundaries/sequences, and UDP V3 chunk-budget separation. Current WLED/DDP deployment and transport-separation contracts. |
| `tests/test_phase33_scalar_color_wipe.py` | 31→31 | production | 0.046 | Scalar-source bounds plus externally driven color-wipe progress, smoothing, replay, paths, and validation. Current effect and authoring behavior despite the phase suffix. |
| `tests/test_phase33_software_acceptance.py` | 7→7 | production | 0.004 | Effect catalog/non-goal closure and scalar-source exclusions. Duplicate historical SHA removed; current exact registry and bounded-authoring contracts retained unchanged. |
| `tests/test_phase34_common_motion_acceptance.py` | 7→7 | production | 0.023 | Cross-effect common-speed schedule for simple and complex motion families. Current cross-effect semantic acceptance. Replace private _last_steps, _last_target_tick, _position, _phase, and _positions checks with observable frame positions or an explicitly public diagnostic contract. |
| `tests/test_phase34_complex_effect_motion.py` | 9→9 | production | 0.018 | Integrated motion for history, heat, ripple, and comet under speed changes, VFR, pause, seek, and replay. Current complex-effect motion contract despite the phase suffix. |
| `tests/test_phase35_coherent_noise_field.py` | 14→14 | fast | 0.012 | Coherent noise primitive/effect bounds, seeds, feature scale, motion, replay, registry, paths, and timelines. Current effect capability independent of current Show use. |
| `tests/test_phase36_wled_closure.py` | 24→24 | production | 0.019 | Step pulse, breath waveform, soft wipe, and color-wave compatibility and new geometry controls. Current renderer behavior and backward-compatible defaults. |
| `tests/test_phase37_parameter_metadata.py` | 9→9 | production | 0.486 | Live immutable parameter specs, validator agreement, modulation safety, export, and null scalar compatibility. Current authoring contract and live registry/export consistency. |
| `tests/test_phase38_parameter_modulation.py` | 36→36 | production | 0.037 | Parameter modulation formulas, source normalization, fallback, smoothing, loader/runtime safety, pre-roll, and legacy coexistence. Current authoring/runtime capability despite the phase suffix. |
| `tests/test_phase39_color_source.py` | 35→35 | production | 0.029 | All color-source types, sampling ownership, fallbacks, paths, event determinism, pre-roll, registry audit, and validation. Current authoring/runtime capability despite the phase suffix. |
| `tests/test_phase40_software_contract_closure.py` | 5→5 | full | 0.009 | Authoring source index/manual completeness, live registry discovery, product boundaries, and frozen Phase 40 plan text. Current authoring navigation and exported inventory remain useful. Split the old plan-state sentence test into history so plan evolution does not break current documentation validation. |
| `tests/test_phased_output_matrix.py` | 1→1 | full | 0.005 | All output adapters consume one PhysicalFrame and preserve shared sequence/accounting. Broad cross-output maintenance contract includes legacy RS-485/UDP V2 but still enforces core frame ownership. |
| `tests/test_physical_mapping.py` | 28→28 | production | 0.584 | Analog/digital topology validation, segment mapping, black defaults, node identity, bounds, and color-copy isolation. Central logical-to-physical architecture coverage. |
| `tests/test_resolve_nodes.py` | 11→11 | production | 0.654 | mDNS node resolution, fail-closed partial results, tracked-template protection, and atomic runtime-file replacement. Current production WLED discovery and configuration safety. |
| `tests/test_rgbcct.py` | 7→7 | fast | 0.006 | Focused RGBCCT conversion invariants for primaries, neutral/warm/cool white, power limits, and monotonic brightness. Some overlap with test_color.py, but this concise five-channel contract directly reflects repository architecture and is worth retaining. |
| `tests/test_rs485_v2.py` | 6→6 | full | 0.006 | RS-485 V2 codec golden, CRC, stream recovery, addressing, wrapping, and shared physical-frame sequence. Non-default protocol remains supported maintenance coverage. |
| `tests/test_serial.py` | 8→8 | full | 0.007 | Legacy serial removal plus RS-485 V2 codec/parser and memory-output defaults. Substantially overlaps test_rs485_v2.py. Merge unique legacy-removal/range/default-mode assertions there, preserving protocol coverage. |
| `tests/test_setup_service.py` | 30→30 | full | 0.193 | Site/portable Wi-Fi reconciliation, fail-closed network management, API conflicts, watchdogs, cleanup, and secret redaction. Deployment service behavior is important but platform-oriented and outside fast production lighting regression. |
| `tests/test_show_branch_lifecycle_schema_phase34.py` | 5→5 | fast | 0.030 | Branch lifecycle Show schema defaults, explicit values, error paths, and model/loader agreement. Small current Show grammar contract despite archived compatibility fixture. |
| `tests/test_show_common_effect_controls.py` | 11→11 | production | 0.014 | V2 common brightness/speed/intensity defaults, validation, adaptive/fixed composition, clamping, and V1 exclusion. Current Show authoring and render behavior. |
| `tests/test_show_config.py` | 25→25 | production | 0.095 | Show V1 schema strictness, cue transitions/references/timing, adaptive parameters, typed round-trip, and virtual paths. Core Show loader and validation contract. |
| `tests/test_show_e2e_acceptance.py` | 1→1 | history | 62.164 | Frozen Phase 17 Show-orchestration acceptance evidence generation. Checks phase-specific acceptance artifacts rather than the independent runtime contracts already covered elsewhere; preserve intact in history. |
| `tests/test_show_engine.py` | 7→7 | production | 0.341 | Show engine base composition, duration boundary, backward clock failure, validation purity, adaptive runtime, and output failures. Current Show execution and failure propagation. |
| `tests/test_show_engine_audio_modulation.py` | 4→4 | production | 0.005 | Show runtime ordering and locality for audio modulation on fixed/adaptive cues. Current Show/audio integration behavior. |
| `tests/test_show_v2.py` | 29→29 | production | 0.212 | Show V2 paths, selectors, colors, origins, branches, continuous mixed-path rendering, and V1 normalization. Central current authoring/runtime capability. |
| `tests/test_simple_effects_motion_phase34.py` | 17→17 | fast | 0.034 | Simple effect integrated motion under speed changes, pause, frame rates, and compositor origin. Current motion behavior despite legacy-golden wording. |
| `tests/test_simulator.py` | 12→12 | full | 3.487 | Simulator latest-frame consumption, concurrency, counters, engine FPS/duration, auto-exit, and physical grouping display. Useful simulator and timing integration, but wall-clock/concurrency checks are unsuitable for fast gating. |
| `tests/test_single_strip_acceptance_campaign.py` | 19→19 | history | 11.636 | Generated single-strip acceptance Shows, coverage records, digests, finite frames, and evidence vocabulary. Primarily validates generated campaign artifacts and frozen software evidence; live effect contracts remain covered by focused production tests. |
| `tests/test_single_strip_acceptance_observability(1).py` | 1→1 | history | 2.657 | Additional observability classification for every generated main-show cue. Separate historical campaign with overlapping concepts but unique assertions; map unique coverage before any merge. Filename suffix alone is not deletion evidence. |
| `tests/test_single_strip_acceptance_observability.py` | 12→12 | history | 0.021 | Generated single-strip campaign observability metrics, contrast pairs, motion, warmup, limits, and deterministic rerender. Acceptance evidence tied to a generated campaign; preserve in history rather than production selection. |
| `tests/test_single_strip_acceptance_show(1).py` | 8→8 | history | 31.607 | Generated single-strip Show registry parity, profile validation, render determinism/digests, contrasts, and synthetic video. Separate historical campaign with overlapping concepts but unique assertions; map unique coverage before any merge. Filename suffix alone is not deletion evidence. |
| `tests/test_single_strip_visual_showcase.py` | 7→7 | history | 0.346 | Frozen 356.8-second 74-cue visual-showcase authoring structure, timing, variants, separators, finale, and palette. Freezes a specific generated artifact rather than a general current capability. |
| `tests/test_single_strip_visual_showcase_observability.py` | 18→18 | history | 45.193 | Frozen visual-showcase traces and detailed quantitative evidence for motion, geometry, controls, history, noise, and twinkle. Large acceptance evidence bound to a retired generated showcase; current effect semantics stay in focused production modules. |
| `tests/test_site_node_configs.py` | 5→5 | full | 0.037 | ESP32 header/config mapping, PlatformIO environments, startup identity, secret separation, and native firmware component builds. Firmware/configuration verification is valuable full-suite coverage; software build success is not hardware verification. |
| `tests/test_target_resolution.py` | 4→4 | fast | 0.003 | Target kinds, virtual-path global views, scoped cue context, and explicit missing-target errors. Small current resolver contract. |
| `tests/test_timeline.py` | 8→8 | fast | 0.011 | Cue boundary weights/local time, fades, consecutive cues, deterministic reset, pause, and backward-time handling. Foundational Show timing semantics. |
| `tests/test_twinkle_event_fields_phase33.py` | 16→16 | fast | 0.015 | Twinkle event-field geometry, gating/gain, cue-scoped RNG, replay, virtual paths, and validation. Current effect capability despite the phase suffix. |
| `tests/test_udp.py` | 8→8 | full | 0.006 | Legacy UDP output removal plus UDP V2 codec, CRC, bounds, sequencing, and checksum. Substantially overlaps test_udp_v2.py. Merge unique legacy-removal, independent-sequence, and checksum assertions into that maintained protocol module. |
| `tests/test_udp_v2.py` | 7→7 | full | 0.004 | UDP V2 codec golden, corruption/bounds/staleness rejection, and one-datagram-per-node output. Legacy maintenance protocol remains explicitly supported in full coverage. |
| `tests/test_udp_v3.py` | 19→19 | full | 0.013 | UDP V3 frame codec/goldens, independent outputs, schedule pairing, rejection rules, and transport framing. Authoritative maintenance protocol coverage. |
| `tests/test_udp_v3_chunking.py` | 16→16 | full | 0.031 | UDP V3 chunk packetization/reassembly, ordering, duplicates, overlap, bounds, goldens, and atomic transport encoding. Important maintenance protocol contract with broad combinatorial coverage. |
| `tests/test_udp_v3_scheduling.py` | 27→27 | full | 0.022 | UDP V3 clock beacons, scheduled apply times, epochs, clock safety, broadcast/unicast, and encode-before-send. Important scheduled transport contract; keep in full protocol maintenance. |
| `tests/test_util.py` | 19→19 | fast | 0.012 | EMA/color smoothing, attack-release envelope, rolling history, noise gate, delta limiting, and safe division. Small foundational numerical utilities. |
| `tests/test_video_mapping.py` | 29→29 | fast | 0.209 | Video-zone validation/resolution, direction, RGBCCT conversion, ambient mapping, and video/audio fusion. Current deterministic mapping and fusion behavior. |
| `tests/test_virtual_paths.py` | 9→9 | production | 0.007 | Virtual-path segment geometry, seams, reverse, gaps, sparse output, single render, topology independence, and summary. Central current logical-path architecture contract. |
| `tests/test_wled_audio_sync.py` | 15→15 | production | 0.010 | WLED audio-sync packet decoder, multicast source lifecycle, ordering, stale recovery, invalid packets, and reset. Current production live-audio protocol with mocked sockets. |
| `tests/test_wled_nine_node_profiles.py` | 5→5 | production | 1.196 | Current nine-node DDP profile, one-output policy, enabled-node sends, maintenance profile parity, and Energy Wakeup targets. Direct approved deployment baseline. |
| `tests/test_wled_two_output_as_one_demo.py` | 2→2 | history | 0.239 | Retired two-output WLED virtual path and concatenated DDP payload demo. Demo-specific artifact outside the current one-output WLED policy; preserve only for historical replay. |
| `tests/test_ws2811_breath_show.py` | 3→3 | history | 0.534 | Retired WS2811 breath Show exact blue output and black guard intervals. Specific retired Show/deployment acceptance. |
| `tests/test_ws2811_breath_trace_replay.py` | 1→1 | history | 0.183 | Frozen WS2811 breath trace semantic round-trip. Explicit frozen replay artifact. |
| `tests/test_ws2811_emergency_gate1m_show.py` | 3→3 | history | 0.450 | Retired one-minute emergency Show exact frames, safe frame, deterministic payloads, and scene/write budgets. Deployment-specific frozen acceptance with large render loops. |
| `tests/test_ws2811_emergency_node8_two_node.py` | 10→10 | history | 0.706 | Retired node-8/two-node emergency profiles, exact UDP packets, and scene/skip budgets. Deployment-specific historical replay matrix. |
| `tests/test_ws2811_emergency_show.py` | 2→2 | history | 0.162 | Retired emergency Show allowlisted UDP payloads, safe state, content, and write budget. Deployment-specific frozen acceptance. |
| `tests/test_ws2811_node8_breath_show.py` | 1→1 | history | 0.183 | Retired node-8 breath Show target isolation and exact DDP output. Specific retired deployment demonstration. |
| `tests/test_ws2811_staged_shows.py` | 16→16 | history | 26.831 | Retired staged WS2811 diagnostic/install/full-site Shows across exact long-duration render and UDP mapping scenarios. Large campaign acceptance for retired staged deployment assets; retained in history and included in full, outside ordinary production regression. |
| `tests/test_ws2811_two_node_all_effects_show.py` | 1→1 | history | 0.142 | Archived 171-second two-node Show preserving the original 17 effect IDs. Test explicitly freezes an archived Show and superseded effect inventory. |
| `tests/test_ws2811_two_node_breath_isolation_show.py` | 1→1 | history | 0.681 | Retired two-node breath-isolation stages and safe UDP frames. Specific retired deployment demonstration. |
| `tests/test_ws2811_two_node_breath_show.py` | 1→1 | history | 0.593 | Retired two-node in-phase breath DDP packets and safe shutdown. Specific retired deployment demonstration. |
| `tests/test_ws2811_two_node_virtual_path_comet_show.py` | 1→1 | history | 0.240 | Retired two-strip virtual-path comet crossing in both directions. Specific archived Show demonstration; general seam behavior remains covered in production virtual-path/effect tests. |
| `tests/test_cleanup_contracts.py` | 5→0 | 已删除 | 不适用 | 见上述逐项去留依据 |
| `tests/test_phase32_energy_wakeup_non_regression.py` | 2→0 | 已删除 | 不适用 | 见上述逐项去留依据 |

## 可复核命令与证据

所有测试顺序执行，未与其他测试/硬件会话争用资源。命令末尾的日志复制仅保存 stdout/stderr，
通过 `exit $LASTEXITCODE` 保留 pytest 返回码。每项实际结果见上表或定向修正记录。

```powershell
.\.python\Scripts\python.exe -m pytest -q --durations=25 --inventory-json=tmp/test-audit/cleanup-production-before.json
.\.python\Scripts\python.exe -m pytest -q tests/test_engine.py tests/test_engine_realtime_acceptance.py tests/test_music_control.py tests/test_music_control_performance.py tests/test_campaign_evidence_comparison.py tests/test_cabin_v3_e2e_acceptance.py tests/test_cabin_v3_historical_replay.py --durations=10 --inventory-json=tmp/test-audit/cleanup-targeted.json
.\.python\Scripts\python.exe -m pytest -q tests/test_music_control.py tests/test_music_control_performance.py --durations=10 --inventory-json=tmp/test-audit/cleanup-targeted-music-recheck.json
.\.python\Scripts\python.exe -m pytest -q --suite fast --durations=25 --inventory-json=tmp/test-audit/cleanup-fast.json
.\.python\Scripts\python.exe -m pytest -q --durations=25 --inventory-json=tmp/test-audit/cleanup-production.json
.\.python\Scripts\python.exe -m pytest -q --suite full --durations=25 --inventory-json=tmp/test-audit/cleanup-full.json
.\.python\Scripts\python.exe -m pytest -q --suite history --durations=25 --inventory-json=tmp/test-audit/cleanup-history.json
```

原始 JSON 与 `.log` 保存在忽略目录 `tmp/test-audit/`；本报告保存可提交的汇总。

## 未解决项与边界

静态检查返回码 0：迁移的四个函数/类 AST 与进入本轮的副本一致；所有当前测试文件
均有分层记录；fast ⊆ production ⊆ full，full 收集项全部执行。
history 集合与清单完全一致、是 full 子集，115 项全部执行。`git diff --check` 返回码 0。

独立复核采用主代理 → `sol_reviewer`（GPT-5.6 Sol / medium），只读，无 supervisor，
无额外测试并发。Reviewer 确认迁移断言和历史 SHA 一致、无重复收集，并指出审计文档
未同步和实际 assets 验收措辞过宽；主代理已同步报告并明确覆盖边界。
同一 reviewer 随后复用作最终文档复核，确认两项发现均已解决、无残余矛盾。
一名 reviewer、两次只读检查、无 worker 重试；逐代理耗时/token 用量不可得，不作成本推断。

当前 Host/FastAPI/Starlette 弃用警告不属于本轮运行时改造范围。
未运行性能 benchmark 或固件构建：本轮仅测试治理，无相关运行时代码/协议修改，未触发此验收门槛。
未 stage、commit、push 或创建 PR。**NOT HARDWARE VERIFIED**。
本轮 Cleanup 到此停止，不继续架构重构或代码删除。

## Git diff --stat

工作区总 diff，包含此前改动；不含 untracked 新文件。命令返回码 0。

```text
 AGENTS.md                                          | 202 +++++++--------------
 CLAUDE.md                                          |  43 +++--
 config/shows/README.md                             |  27 +--
 config/shows/archive/README.md                     |  12 +-
 config/shows/energy-wakeup.yaml                    |   3 +-
 conftest.py                                        |  85 ++++++++-
 docs/current/cabin-lighting-v3-operator-guide.md   |   5 +-
 docs/current/show-authoring-source-index.md        |   4 +-
 docs/history/legacy-prototype/程序调用关系.md      |   2 +-
 light_engine/pipeline.py                           | 186 -------------------
 pyproject.toml                                     |   4 +-
 tests/test_cabin_v3_e2e_acceptance.py              |  21 ++-
 tests/test_engine.py                               |  19 --
 tests/test_host_service_api.py                     |  23 ++-
 tests/test_host_wled_profile_resolution.py         |  17 +-
 tests/test_music_control.py                        |  57 +-----
 tests/test_phase32_energy_wakeup_non_regression.py | 100 ----------
 tests/test_phase33_software_acceptance.py          |  13 +-
 tests/test_pipeline.py                             |  90 ---------
 tests/test_single_strip_acceptance_campaign.py     |  14 +-
 .../test_single_strip_acceptance_observability.py  |  12 +-
 21 files changed, 273 insertions(+), 666 deletions(-)
```
