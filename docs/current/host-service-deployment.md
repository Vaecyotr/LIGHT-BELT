# 主机接口服务：开发与部署说明

`host_services/` 协调 APP 接口、节目发现、播放器与灯光引擎。本页说明本地开发、节目资料与服务配置；目标设备的完整安装入口是 [RK3588 一键部署](rk3588-bootstrap.md)。

## Windows 开发环境

在仓库根目录运行：

```powershell
& .\scripts\dev\bootstrap_python.ps1
.\.python\Scripts\python.exe -m host_services
```

开发启动默认使用模拟适配器。不要把接口响应正常当作设备已经输出灯光。共享 `.python` 目录连接只做验证，不安装、删除或同步依赖；需要修复共享环境时，由其拥有者协调全部工作树。

独立环境使用 `pyproject.toml` 的 `host`、`dev` extras 和 `uv.lock` 同步。`host_services/requirements.txt` 是从锁文件导出的兼容清单，不单独维护版本，也不作为自动更新入口。

## RK3588 部署与后续更新

统一版本发布于 `https://github.com/Vaecyotr/LIGHT-BELT.git` 的 `1126`。全新安装、旧机迁移与后续更新分别按一键部署手册核对仓库、分支和批准提交。 [部署命令](rk3588-bootstrap.md#设备进入统一部署的三种路径)

当前目标路径为 `/home/pi/LIGHT-BELT`，用户为 `pi`，桌面为 GNOME Wayland。bootstrap 准备 `.venv`、独立更新策略和运行配置，将 Host 安装为用户服务并启用 linger。GNOME 登录项导入真实图形会话环境，Host 通过 `.venv/bin/python -m host_services` 启动，生产模式由 unit 选择 `ENGINE_ADAPTER=real`。

设备 Host 环境文件与 TLS 证书由设备本地管理并在迁移时保留。退役的 JWT 和配对码不再生成，也不作为真实后端启动条件。

首次安装与后续更新共同使用部署目录中的依赖同步逻辑，按锁文件安装 Host 依赖，排除开发依赖。声明与锁文件不一致时失败，设备端不重新解析或改写锁文件。已有兼容 Python 环境复用；系统蓝牙工具的 Python 与系统库单独管理。

更新脚本在修改依赖前停止 Host，并检查同步、服务启动及健康状态；失败时尝试恢复旧代码和旧锁对应环境。旧包若未缓存且网络不可用，恢复也可能失败，此时保留恢复记录并报告停止状态，不能宣称更新成功。后台更新、备份和显示服务的启用策略以设备说明为准，整理文件不代表开启定时任务。

设备开机、显示、音视频、蓝牙和安装更新生命周期仍需实机验收。**NOT HARDWARE VERIFIED**。

更新器从真实 `/api/v1/status` 的 `data` 层读取启动时冻结的完整 Git 提交、
源码干净状态、真实适配器模式与应用就绪状态。节点在线状态单独判定。
已确认 RT5616 sink 且仅等待插线时，业务 `ready` 可为 `true`，`/api/v1/audio` 的 `audio_output_available` 为 `false`。
更新前也校验旧实例，缺少该健康合同的旧版须在维护窗口先安装兼容版本，
自动更新会在停止服务或修改代码前拒绝执行。更新定时器的启用状态保持原策略。

## 节目定义、媒体与可选覆盖清单

Host 从 `assets/<show_id>/` 自动发现节目，视频、音频或 YAML 均可构成可发现条目。目录名参与 `show_id`，不能作为普通资料文件夹随意改名。

`assets/energy-wakeup/energy-wakeup.yaml` 是保留的生产节目原件；`config/shows/energy-wakeup.yaml` 是独立测试与显式 CLI 校验资料，两者不要求相同。

可选的 `data/shows_manifest.json` 在发现后覆盖名称、媒体路径等字段，也可以补入兼容条目。缺少它不会清空 `assets` 已发现的节目；目录没有可发现内容时，列表才可能为空。示例见 [shows-manifest.example.json](../../config/examples/shows-manifest.example.json)。

| 字段 | 用途 |
|---|---|
| `show_id` | 与发现目录关联或新增条目的接口标识 |
| `name`、`description` | 人可读名称和说明 |
| `duration_ms` | 覆盖已发现时长，单位毫秒 |
| `media_path` | 指向实际可读媒体的路径 |

以 `shows_loader.py` 的发现及覆盖行为为准。当前 `engine_adapter._load_shows()` 没有传入 `config.py` 中的 `SHOWS_MANIFEST_PATH`；不能承诺修改该声明就能改变加载位置。本轮不改变加载逻辑。媒体、生成配置和运行数据通常不进入 Git，必须在设备上独立准备。

## API 接口检查

接口默认监听 `0.0.0.0:8443`；状态入口为 `/api/v1/status`，交互式接口说明为 `/docs`。

检查部署时使用状态接口、API 文档、接口请求与验收工具。

受控网络中的客户端可直接调用业务 REST 接口。WebSocket 仍使用一次性票据；蓝牙配对与播放权操作通过 Host 正式业务接口完成。

## TLS 配置

需要 HTTPS 时，在设备 Host 环境中配置 TLS 开关和证书路径。升级保留现有证书与环境文件；私钥留在设备受保护目录，不纳入仓库。

HTTP 配置下使用 WS，HTTPS 配置下使用 WSS。匿名业务接口只部署在受控舱内网，不应暴露给公网或不受信任网络。
