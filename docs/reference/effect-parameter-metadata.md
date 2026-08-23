# 内部效果参数元数据（Phase 37）

`light_engine.effects` 的 live `EffectRegistry` 是每个效果 authoring 参数的唯一权威。
每个 `EffectRegistration` 保存不可变的 `ParameterSpec` 元组；旧的
`registration.parameter_keys` 只从该元组派生，供 Show loader 的未知字段检查兼容使用。

每个规格包含：

- `name`：效果专有参数名；
- `kind`：`float`、`integer`、`boolean`、`enum`、`rgb`、`scalar_source`、
  `color_timeline`、`id_list` 或 `object`；
- `minimum` / `maximum`、`choices`、`unit`：仅在当前契约有权威边界时出现；
- `runtime_mutable`：renderer 可在运行帧读取该值；
- `modulatable`：比 `runtime_mutable` 更严格、可供 `parameter_modulation` 使用的安全 float；
- `description`：作者可读的简短说明。

规格校验在效果专用校验器之前运行，统一执行类型、枚举和可表达的单值边界。
专用校验器仍负责关系约束，例如 `highlight_gain >= base_gain` 和
`ceiling_gain >= floor_gain`。规格不复制 renderer 或 Config 默认值：那些默认值仍由既有实现拥有。
可选 `scalar_source` 参数保留既有兼容性：显式 YAML `null` 与省略该字段等价，表示没有外部标量源。

导出中的 `common_params` 是 capability 声明的完整稳定顺序（包括 `color`）；派生
`common_controls` 仍只表示现有的 `speed` / `intensity` 公共控制集合。

## 调制安全

`runtime_mutable: true` 不表示可安全连续调制。计数、路径状态尺寸、轨迹、事件寿命、滤波/历史
状态和可能造成相位跳变的值都保持 `modulatable: false`。通用 `brightness`、`speed`、`intensity`
属于既有 common-control / audio-modulation 路径，永远不能成为通用效果参数调制目标。

当前保守允许的内部调制目标（`kind=float`、`runtime_mutable=true`、`modulatable=true`）是：

- `breath.min_brightness`
- `color_wave.hue_span_degrees`
- `video_audio_fusion.video_weight`
- `video_audio_fusion.audio_weight`
- `video_audio_fusion.bass_boost`
- `video_audio_fusion.treble_limit`
- `color_wipe.edge_softness_px`
- `flowing_bands.base_gain`
- `flowing_bands.highlight_gain`
- `onset_ripple.floor_gain`
- `coherent_noise_field.contrast`

Phase 38 的 `parameter_modulation` 只消费上述 live 元数据；完整语法见
[parameter-modulation.md](parameter-modulation.md)。`breath.min_brightness`、video/audio fusion 的
四个可调参数现在带有其 renderer 语义所需的权威安全边界。该功能没有 Host endpoint 或 APP V1 字段。

## 导出

在仓库根目录执行：

```powershell
.\.python\Scripts\python.exe scripts\export_authoring_contract.py > authoring-contract.json
```

输出是由 live registry 直接导出的 JSON，带稳定的 registration 顺序；它适合开发者、Show 作者和
后续文档工具消费。不要维护手写的并行效果参数表。
