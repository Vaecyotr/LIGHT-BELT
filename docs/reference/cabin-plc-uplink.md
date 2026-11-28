# 舱 PLC 读取与数据上报（U01）

- `light-belt-plc-status.service`：通过 USB-485 按 Modbus RTU 只读舱 PLC（9600 8N1），
  提供 `GET http://<RK>:8081/api/v1/plc/status`，返回 24 个点。只发 01/02/03 功能码，不写 PLC。
  串口独占打开，其他程序要 PLC 数据都调这个接口。
- Host 内的上报：每 1 秒从本机 8081 读一次 PLC，存成一条 `source=plc` 事件（15 个字段，见
  cabin_uplink_api 表）；每 1 秒把最早的至多 100 条 POST 到 APP 方服务器
  `/api/v1/cabin/events`。`accepted` 里的删掉；400 丢弃这一批；401、500、网络不通都留着下次再发。
  待发事件存在 `~/.config/light-belt/uplink/events.sqlite3`，重启不丢。
  登录（B02–B09）还没实现，`user_id`、`username` 目前一律为 null。

## 每台设备的配置

写在 `~/.config/light-belt/host.env`（权限 600，不进 git，重复部署不覆盖）：

| 变量 | 说明 |
| --- | --- |
| `LIGHT_BELT_PLC_SERIAL` | USB-485 路径，用 `ls /dev/serial/by-id/` 查。不配则 PLC 接口不启动 |
| `LIGHT_BELT_PLC_STATION` | PLC 站号，默认 10 |
| `LIGHT_BELT_UPLINK_SERVER` | APP 方服务器，如 `https://example.com`，路径自动补 `/api/v1/cabin/events` |
| `LIGHT_BELT_CABIN_ID` | APP 方分配的 device.sn |
| `LIGHT_BELT_DEVICE_TOKEN` | APP 方给的 device_token |

后三项缺任何一项都不上报，其余功能不受影响。改完重启：
`systemctl --user restart light-belt-plc-status.service light-belt-host.service`。
