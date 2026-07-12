# ESP32 Windows commissioning

Status: **NOT HARDWARE VERIFIED**.

This procedure keeps the complete five-node host topology while commissioning
the four controllers currently installed. The board wired to `strip_12/91/92`
is logical Node 4, and the board wired to `strip_22` is logical Node 5.

| Installed board | Node header | Outputs |
|---|---|---|
| `strip_11/21/31` | `node_configs/node_1.h` | `10/10/10` |
| `strip_41/42`, GPIO6 currently disconnected | `node_configs/node_2.h` | `10/20/20` |
| `strip_12/91/92` | `node_configs/node_4.h` | `40/20/20` |
| `strip_22` | `node_configs/node_5.h` | `40` |

Future Node 3 uses `node_configs/node_3.h` for `strip_44/45/93`. Node 2 keeps
its third 20-pixel output configured even while `strip_43` is disconnected, so
the firmware accepts the host's complete three-output UDP v3 frame.

## 1. Create the local firmware configuration

From the repository root:

```powershell
Copy-Item `
  firmware\esp32_ws2811_node\src\config.local.example.h `
  firmware\esp32_ws2811_node\src\config.local.h
```

Edit `config.local.h` and replace the Wi-Fi placeholders. Select one node by
changing its final include, for example:

```cpp
#define WIFI_SSID "REPLACE_WITH_WIFI_SSID"
#define WIFI_PASSWORD "REPLACE_WITH_WIFI_PASSWORD"
#include "node_configs/node_1.h"
```

`config.local.h` is ignored by Git. Never put Wi-Fi credentials in a committed
node header or YAML profile.

## 2. Connect and identify one controller

Connect only the controller being commissioned by USB. Find its Windows port:

```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Name
```

If no port appears, install the USB-UART driver used by that ESP32-S3 board.

## 3. Build and upload

Replace `COM7` with the detected port:

```powershell
pio run -d firmware/esp32_ws2811_node
pio run -d firmware/esp32_ws2811_node -t upload --upload-port COM7
```

Repeat for logical Nodes 1, 2, 4, and 5, changing only the selected node header
before each build/upload. Label the physical controller with the logical node
ID immediately after upload.

## 4. Reserve addresses in the router

Power one controller at a time, find its MAC address in the router's DHCP
client list, and reserve these addresses:

| Logical node | Reserved address |
|---:|---|
| 1 | `192.168.1.201` |
| 2 | `192.168.1.202` |
| 3 | `192.168.1.203` (future controller) |
| 4 | `192.168.1.204` |
| 5 | `192.168.1.205` |

If the router does not use `192.168.1.0/24`, choose five unused addresses in
its actual LAN subnet and update
`config/profiles/cabin-lighting-v3-site-local.yaml` to match. Disable Wi-Fi
client/AP isolation so the Windows host can reach the controllers.

## 5. Validate and run the host

```powershell
.\.python\Scripts\python.exe -m light_engine `
  --config config\profiles\cabin-lighting-v3-site-local.yaml `
  validate-show --show config\shows\cabin-commissioning-show-v2.yaml

.\.python\Scripts\python.exe -m light_engine `
  --config config\profiles\cabin-lighting-v3-site-local.yaml `
  run --show config\shows\cabin-commissioning-show-v2.yaml
```

Commission one output at a time with current-limited power. Node 3 datagrams
will be sent to the reserved address and silently discarded until that future
controller exists. UDP send success does not prove physical receipt; verify
each installed output visually and confirm it goes black after about one
second without accepted frames.
