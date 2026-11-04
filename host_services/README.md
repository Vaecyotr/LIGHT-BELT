# 主机接口与播放协调服务

这里把操作界面、音视频播放器和灯光引擎连接起来，对外提供已约定的 APP 接口。目录名同时是 Python 导入和启动入口，因此保留。

- `main.py`：组装接口服务，并提供 `kiosk/dist/` 中的网页。
- `routers/`：按功能划分的接口入口。
- `engine_adapter.py`、`real_engine_adapter.py`：播放状态、播放器与真实灯光进程的协调。
- `shows_loader.py`：从 `assets/` 发现节目，再应用可选节目清单覆盖层。

接口约定见[APP 接口参考](../docs/reference/host-api-v1.md)。目标设备安装见[RK3588 部署](../docs/current/rk3588-bootstrap.md)，本地开发与服务配置见[Host 服务说明](../docs/current/host-service-deployment.md)。设备映射与传输实现在灯光引擎和配置层。
