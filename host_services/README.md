# 主机接口与播放协调服务

Host 协调 mpv、BlueZ/PulseAudio 和灯光发送进程，供受控舱内网络中的客户端直接调用。

- `main.py`：管理 Host 生命周期和单一 HTTP 或 TLS 监听。
- `routers/`：按功能划分的接口入口。
- `engine_adapter.py`、`managed_adapter.py`：协调节目、意图、mpv 时钟和单一灯光发送进程。
- `bluetooth.py`、`bluez_backend.py`、`audio_routing.py`：处理手机配对和唯一可听路由。
- `control_preferences.py`：原子保存用户偏好。
- `shows_loader.py`：从 `assets/` 发现节目，再应用可选节目清单覆盖层。

接口约定见[APP 接口参考](../docs/reference/host-api-v1.md)和[舱内控制接口](../docs/reference/host-control-api.md)。目标设备安装见[RK3588 部署](../docs/current/rk3588-bootstrap.md)，本地开发与服务配置见[Host 服务说明](../docs/current/host-service-deployment.md)。
