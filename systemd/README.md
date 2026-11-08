# Linux 后台服务与定时任务配置

这里定义 RK3588 上哪些程序作为后台服务运行、如何启动与停止，以及哪些任务按时间触发。`systemd` 是 Linux 的服务管理工具名称。

顶层 `.service`、`.timer` 是系统级配置，`user/` 是用户服务配置。用户服务可通过 linger 随开机启动，两者安装位置和管理方式不同。实际安装脚本位于 `scripts/deploy/rk3588/`。

NanoPC-T6 GNOME Wayland 的默认 Host、默认音频和静音优先级运行于用户作用域。Host 使用 linger 随开机启动，`light-belt-host-session.desktop` 在 GNOME 登录后导入图形会话。顶层 Host 和 default-sink 定义保留为旧系统服务迁移资料，默认安装会停用旧实例。Bluetooth agent 和公共发现策略仍为系统服务。

按[RK3588 安装与检查说明](../docs/current/rk3588-bootstrap.md)部署。保存定时器配置不代表启用任务，更新不得顺便改变启用状态。当前设备用户、路径与硬件验证边界以部署说明为准。
