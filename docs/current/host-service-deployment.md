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

当前目标路径为 `/home/pi/LIGHT-BELT`，用户为 `pi`。按专用安装说明运行 bootstrap；它准备 `.venv`、生成运行配置并安装系统服务。Host 的启动入口为 `.venv/bin/python -m host_services`，生产模式由服务配置显式选择 `ENGINE_ADAPTER=real`。

生产启动前，在设备的 `/etc/light-belt/host.env` 中配置独立的
`LIGHT_BELT_JWT_SECRET` 和 `LIGHT_BELT_PAIRING_CODE`。密钥至少 32 字节，
配对码须替换开发默认值。该文件由 systemd 读取，应限制为管理员可读，
凭据不进入 Git。真实模式缺少有效配置会拒绝启动。

首次安装与后续更新共同使用部署目录中的依赖同步逻辑，按锁文件安装 Host 依赖，排除开发依赖。声明与锁文件不一致时失败，设备端不重新解析或改写锁文件。已有兼容 Python 环境复用；系统蓝牙工具的 Python 与系统库单独管理。

更新脚本在修改依赖前停止 Host，并检查同步、服务启动及健康状态；失败时尝试恢复旧代码和旧锁对应环境。旧包若未缓存且网络不可用，恢复也可能失败，此时保留恢复记录并报告停止状态，不能宣称更新成功。后台更新、备份和显示服务的启用策略以设备说明为准，整理文件不代表开启定时任务。

本次脚本与依赖整改只有本地软件验证。设备开机、显示、音视频、蓝牙和安装更新生命周期仍需实机验收：**NOT HARDWARE VERIFIED**。

更新器从真实 `/api/v1/status` 的 `data` 层读取启动时冻结的完整 Git 提交、
源码干净状态、真实适配器模式与应用就绪状态。节点在线状态单独判定。
更新前也校验旧实例，缺少该健康合同的旧版须在维护窗口先安装兼容版本，
自动更新会在停止服务或修改代码前拒绝执行。更新定时器的启用状态保持原策略。

## 节目定义、媒体与可选覆盖清单

Host 从 `assets/<show_id>/` 自动发现节目，视频、音频或 YAML 均可构成可发现条目。目录名参与 `show_id`，不能作为普通资料文件夹随意改名。

`assets/energy-wakeup/energy-wakeup.yaml` 是保留的生产节目原件；`config/shows/energy-wakeup.yaml` 是独立测试与显式 CLI 校验资料，两者不要求相同。

可选的 `data/shows_manifest.json` 在发现后覆盖名称、媒体路径等字段，也可以补入兼容条目。缺少它不会清空 `assets` 已发现的节目；目录没有可发现内容时，列表才可能为空。示例见 `host_services/shows_manifest.example.json`。

| 字段 | 用途 |
|---|---|
| `show_id` | 与发现目录关联或新增条目的接口标识 |
| `name`、`description` | 人可读名称和说明 |
| `duration_ms` | 覆盖已发现时长，单位毫秒 |
| `media_path` | 指向实际可读媒体的路径 |

以 `shows_loader.py` 的发现及覆盖行为为准。当前 `engine_adapter._load_shows()` 没有传入 `config.py` 中的 `SHOWS_MANIFEST_PATH`；不能承诺修改该声明就能改变加载位置。本轮不改变加载逻辑。媒体、生成配置和运行数据通常不进入 Git，必须在设备上独立准备。

## 网页与接口检查

接口默认监听 `0.0.0.0:8443`；状态入口为 `/api/v1/status`，交互式接口说明为 `/docs`。网页由 `kiosk/dist/` 提供，只有该目录存在时才挂载。

检查部署时，除了状态接口，还要打开 `/`，核对 HTML 引用的 JS、CSS 和 `/THIRD_PARTY_NOTICES.txt`。API 正常不代表网页发布包完整。网页源码修改后的构建由 `kiosk/package.json` 和 npm 锁文件管理；Python 安装不会自动构建网页。

Kiosk 使用现有 Bearer 配对与令牌轮换。打开页面后输入设备配对码，令牌仅保存在
页面内存中。页面重新加载或刷新令牌失效后重新配对。并发过期请求共享一次刷新，
拒绝和播放器错误在页面显示。`/status` 与网页静态资源继续公开访问。

## TLS 配置

当前默认 `ENABLE_TLS=False`。如显式启用 HTTPS，在设备上准备 `/etc/light-belt/cert.pem` 与 `/etc/light-belt/key.pem`，并核对 `host_services/config.py` 的 `TLS_CERTFILE`、`TLS_KEYFILE` 和 `ENABLE_TLS`。私钥留在设备受保护目录，不纳入仓库。

API文档中的HTTPS地址为目标接入合同。设备接入前需完成TLS或可信加密通道，
避免在普通HTTP链路上传输Bearer和配对码。票据地址跟随ASGI请求协议选择WS/WSS，
使用TLS终止代理时须正确配置可信代理边界。
