# assets/ —— 生产节目与媒体资源

生产 Host 从这里发现 Show 定义及其媒体文件（mp4 / mkv / wav 等）。
`energy-wakeup/energy-wakeup.yaml` 是不可变的原始生产 Show 来源。

- 媒体通常由本地部署提供并按 `.gitignore` 规则排除；Show YAML 仍是受跟踪的项目资源。
- Host 自动发现不依赖 manifest；可选 manifest 用于覆盖发现出的元数据或路径。
- `config/shows/energy-wakeup.yaml` 是测试、显式 CLI 校验和兼容基线，不选择 Host 的生产 Show。
- 媒体更新应保持 Show 定义中的相对路径一致；部署入口见 `docs/current/host-service-deployment.md`。
