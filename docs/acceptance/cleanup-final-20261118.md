# LIGHT-BELT 清理分支最终修复验收

基线为 `7c32c6209fa4e68cb8335bb0f8915fd63202104b`，工作树为 `light-belt-cleanup-1108`，本地分支为 `codex/1108-repository-cleanup`。开始时工作树干净，fetch 后的 `origin/1108` 为 `178cd5b`，`origin/1108-repository-cleanup` 为 `7c32c62`。

对照 WT04 为 `1108` / `178cd5b`，有未提交的测试治理、Kiosk及REST直通改动。需求原文从其实际文件逐项提取，Kiosk及配套行为按用户指令同步。WT04 的29个既有修改/新增路径及其状态已记录在本地验证目录并在收尾复核。

## 需求与交付追踪

[现行需求文件](../../feature_gap_08-54.md)逐项保留8～54的47个编号、名称与原文，各项列出能力、交付入口、源码/测试依据和剩余条件。T00～T20的21个主任务及其子项、D01～D10的10项决策保留完成、被替代、开放或外部依赖状态。[实施计划](../IMPLEMENTATION_PLAN.md)指向同一追踪文件。

38项软件能力、7项部分满足、2项未实现的口径保持。第35项区域主色、第44项趋势、第47项节拍质量、传感器/舱控/手机音源、内容权利、照度和实机更新均有后续落点。T08恢复 attack/release 元数据标注为 seconds、实现为速率系数的单位核对义务。60秒 strip_31 实测只关闭其内部时钟单带节目范围。

## Kiosk和REST行为

Kiosk源码、依赖声明、发布页面和测试从WT04实际内容同步，Host的 `deps.py` 同步其直通行为。页面加载、播放、亮度、音量与停止请求均可省略 Authorization，页面提供请求错误反馈。配对及刷新接口保留，WebSocket握手仍需一次性票据；票据可匿名申请，失效或重复使用返回4401。

[部署说明](../current/host-service-deployment.md)、[APP说明](../reference/host-api-v1.md)和[OpenAPI](../reference/host-api-v1.openapi.yaml)记录相同策略。该行为是用户批准的WT04同步，取代原T20的强制Bearer目标。能够访问Host监听地址的客户端可以发送控制请求。 旧页面配对/刷新会话的Node用例随该设计退役；同步后的3项Node用例检查无Authorization直连、Host拒绝提示及网络错误恢复。服务端签名、刷新轮换、真实模式凭据及WS票据仍由Python合同测试覆盖。

## 旧Phase17节目的去留

维持删除 `assets/phase-17-full-show-wled-five-board/phase-17-full-show-wled-five-board.yaml`。原文件与归档副本的Git blob均为 `a7e1db7624bc1170040f1241b628b803e9131ce1`。WT04该目录只含YAML，原有显式消费者是旧manifest示例；当前Kiosk从Host查询列表，现行配置及源码没有固定调用该Show ID。

[节目发现回归](../../tests/test_host_shows_loader.py)直接读取现存assets并验证列表保留活力唤醒、隐藏内部路径，退休ID在触碰播放器前返回NOT_FOUND且保留当前会话。其余发现、manifest覆盖、有效媒体播放、加载/seek/EOF回归继续执行。仓库外客户端和设备上的自定义manifest未提供，兼容结论覆盖当前仓库与V1契约。

## 已删除测试的重要断言

原清理差异在tests下共22个删除条目，其中21个测试模块和1份夹具README。逐项断言对照保存在本地验证记录。以下列出主要接续关系。

| 删除单元 | 保留或迁移的行为与现行测试 |
| --- | --- |
| 三个agent测试 | 随旧campaign/pipeline退役，测试旧工具自身的调度、提示词和工作树操作。 |
| authoring-modulation验收 | 颜色时间线、调制中性值、组合与路径由audio_modulation_loader/runtime、show_engine_audio_modulation、color_timeline、virtual_paths和compositor覆盖。 |
| legacy_compat | PhysicalFrame直传、同一对象、输出计数、无RoutedFrame由phased_output_matrix覆盖。 |
| node2-effects-demo | 通用映射/方向、当前单带媒体独立性及输出由physical_mapping和single_strip_live_showcase覆盖。 |
| phase32_effect_closeout | 将静音不生新波且已有波继续衰减的组合断言补到phase32_native_effects。 |
| serial | RS485v2范围、CRC标准值、编解码、分片噪声、地址和memory默认由rs485_v2覆盖。 |
| udp | UDPv2的magic/CRC/长度/flags/序列由udp_v2覆盖；补回同一PhysicalFrame重复发送得到77、77。 |
| show_e2e_acceptance | 多目标、混合、fade、时钟和音乐回退由engine、show_engine、compositor、adaptive_selector、engine_music_control_state覆盖；跨传输序列及latest完整帧由phased_output_matrix/output_safety覆盖。 |
| single-strip-acceptance-v1两个模块 | 当前live showcase、effects、show_v2、host_video_input覆盖有限像素、黑场、确定性、媒体与Show行为；退休880秒编排的逐cue清单和固定摘要随节目退役。 |
| PPT、visual showcase三个模块 | 当前live showcase及独立comet/history/twinkle/运动时钟/相干场回归保留；旧116秒和356.8秒节目设计随其退役。 |
| wled_two_output_as_one_demo | virtual_paths保留跨缝连续性，phase32_topology_ddp补回按output_id排序、双输出红20/绿20、完整120字节RGB24和PUSH的精确断言。 |
| 五个WS2811旧节目模块 | 固定蓝色/时间表退役；多目标隔离、缺输入黑场和节点独立性由engine/physical_mapping/branch isolation覆盖；cabin_v3_e2e_acceptance和output_safety实际编码所有配置输出的黑帧/安全标记，UDPv3保留共享序列与调度回归。 |

测试登记补齐8个现存模块，均保留此前隐含的production层。所有原有条目的tier未改变，现存120个测试模块全部登记。现场Show登记改为60秒，验收索引列出现存两个单带目录，Phase40基准路径改为 `scripts/benchmarks/benchmark_color_source.py`。

## 实际验证

Windows Python使用仓库解释器，环境核验通过。原始日志、inventory、完整展开命令和失败记录写在忽略的 `tmp/final-cleanup-acceptance-20261118/`。

| 检查 | 通过 | 失败 | 跳过 | 警告 | 耗时 | 进程退出码 |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 修改前fast | 386 | 0 | 0 | 0 | 16.57 s | 0 |
| 最终专项 | 159 | 0 | 0 | 1 | 27.81 s | 0 |
| 最终fast | 386 | 0 | 0 | 0 | 10.69 s | 0 |
| 默认production | 1373 | 0 | 1 | 1 | 106.10 s | 0 |
| full | 1668 | 0 | 1 | 1 | 631.64 s | 0 |
| 最终文档与黄金向量专项 | 16 | 0 | 0 | 0 | 3.13 s | 0 |
| Kiosk Node测试 | 3 | 0 | 0 | 0 | 0.420 s | 0 |
| Vite构建及发布资源核对 | 1 | 0 | 0 | 0 | 2.25 s | 0 |
| 原生固件协议/状态/编码器 | 58 | 0 | 0 | 0 | 13.54 s（含编译） | 0 |
| STM32 bluepill_f103c8 | 1 | 0 | 0 | 0 | 15.48 s | 0 |
| ESP32-S3节点1～13 | 13 | 0 | 0 | 0 | 1403.34 s | 0 |

full包含65个history层测试项，8个部署/安装模块的95项均执行、零失败，包括用户服务迁移、旧系统服务恢复、环境锁、事务失败回滚、Wayland/音频/蓝牙策略。该组复用full运行结果。

其余已执行检查均退出0：

- 六个正式主题YAML和60秒现场Show通过validate-show，三份Profile静态加载通过；inspect-topology确认九条数字灯带与DDP配置。
- 115个Python文件、24个Shell及Windows bootstrap通过语法解析。
- 发布包四个资源与WT04和重建内容一致，HTML的两条资源引用可访问且不被Git忽略。
- pip check和npm依赖树无不一致。全部24个OpenAPI路径均允许直通REST。
- 本地Markdown目标与章节锚点检查、47项原文/编号、21个T/10个D表、测试登记及Git差异检查通过。

完整测试命令在仓库根使用 `$e='tmp/final-cleanup-acceptance-20261118'`：

```powershell
.\.python\Scripts\python.exe -B -m pytest -q --suite fast "--basetemp=$e/final-fast-temp" "--inventory-json=$e/final-fast.json" --tb=short -rs
.\.python\Scripts\python.exe -B -m pytest -q "--basetemp=$e/final-production-temp" "--inventory-json=$e/final-production.json" --tb=short -rs
.\.python\Scripts\python.exe -B -m pytest -q --suite full "--basetemp=$e/final-full-temp" "--inventory-json=$e/final-full.json" --tb=short -rs
npm.cmd --prefix kiosk test
npm.cmd --prefix kiosk run build -- --outDir ../tmp/final-cleanup-acceptance-20261118/kiosk-rebuild --emptyOutDir
```

固件构建将本工作树临时映射为L:，PlatformIO状态放在工作树本地，分别执行 `pio run -d L:/firmware/stm32_rgbcct_node -e bluepill_f103c8 -j 2` 和ESP32各节点显式环境。仅构建文件。原生协议使用 `firmware/esp32_ws2811_node/scripts/run_native_tests_msvc.ps1`；Unity源码此前缺失，通过 `pio pkg install -d firmware/esp32_ws2811_node -e native --library throwtheswitch/Unity@2.6.1 --no-save` 准备工作树本地测试依赖后复验。

## 失败记录与验收范围

- 同步前的匿名合同测试预期得到4失败/16通过，用于确认旧Bearer行为与WT04要求的差异；同步后全部通过。
- 第一次专项有1失败/158通过，原因是新增DDP测试将类型字段误写为显示ID。按原协议改为类型0x0B、显示ID0x01，既有运行实现未变。
- 一次受限环境专项打印159通过，但进程退出-1073741816，未计为成功；同源代码在原生环境重跑及full均退出0，该异常尚无足够证据归因到源码。
- 原生固件初次缺Unity源码；本地依赖准备后58项通过。辅助匿名播放探针首次未完整替换播放器入口，返回MPV_UNAVAILABLE；补全替身后五个匿名操作全部返回200。
- full/production的一项跳过来自Windows目录symlink能力，Starlette TestClient弃用警告与基线一致；既有跳过条件和断言未放宽。
- 正式媒体、目标机输出、整舱同步、手机音源、传感/舱控和真实升级回滚仍按需求清单验收。阶段程序测试和固件构建覆盖软件，现存硬件记录的范围保持。

结论为 **PASS WITH CONDITIONS**。软件修复、完整回归和构建已通过，可作为新开发基线；整机交付、现场性能与授权材料继续按开放任务关闭。REST直通策略按用户要求应用，运行实例的可达范围决定能发送控制请求的客户端范围。
