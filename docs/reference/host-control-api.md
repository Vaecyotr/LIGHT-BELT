# Host Control API: Bluetooth acceptance guide

This guide documents the current anonymous `/control` API. Use it only from the
trusted cabin network. Set `$HostUrl` to the deployed Host listener, using its
configured HTTP or HTTPS scheme. No APP token or browser enrollment is required.

```powershell
$HostUrl = 'https://192.168.31.236:8443'
$ErrorActionPreference = 'Stop'
function Get-ControlState {
    Invoke-RestMethod -Method Get -Uri "$HostUrl/control/state"
}
function Invoke-Control {
    param([string]$Method, [string]$Path, $Body)
    $requestParameters = @{ Method = $Method; Uri = "$HostUrl$Path" }
    if ($null -ne $Body) {
        $requestParameters.ContentType = 'application/json'
        $requestParameters.Body = $Body | ConvertTo-Json -Compress
    }
    Invoke-RestMethod @requestParameters
}
```

The common envelope is `{ "ok": true, "request_id": "…", "data": … }`.
Bluetooth commands return HTTP `202 Accepted`: the command was accepted, while
connection and route state must be read from `data` or a subsequent state read.
Errors carry `error.code` and `error.message`; capacity is `409
CONNECTION_LIMIT`, expired challenge is `410 CHALLENGE_EXPIRED`, and unavailable
Bluetooth is `503 BLUETOOTH_UNAVAILABLE`.

## Endpoints

| Method and path | Body | Purpose |
|---|---|---|
| `GET /control/state` | none | Read shared control state. |
| `PUT /control/analysis` | `{"mode":"auto"}` or `{"mode":"mic"}` | Use eligible digital audio or the explicitly selected microphone. |
| `PUT /control/lighting` | `{"intent":"follow"}` / `music` / `off`, optional `if_intent` | Set lighting intent. To leave `off`, send the current state version as `if_intent`. A stale version returns `409 STALE_INTENT`. |
| `POST /control/play` | `{"show_id":"…","start_position_ms":0}` | Start a show and retain user lighting preferences. The V1 playback entry applies its documented playback reset. |
| `POST /control/bluetooth/scan` | none | Start discovery; it stops on its timer or when the add window closes. |
| `POST /control/bluetooth/add` | none | Open inbound pairing window and discovery (default 60 seconds). |
| `DELETE /control/bluetooth/add` | none | Close window/discovery and invalidate its outstanding challenges. |
| `POST /control/bluetooth/devices/{device}/pair` | none | Actively pair a discovered device; this does not open the inbound add window. |
| `POST /control/bluetooth/devices/{device}/connect` | none | Connect an already paired phone. |
| `POST /control/bluetooth/devices/{device}/disconnect` | none | Disconnect a phone. |
| `DELETE /control/bluetooth/devices/{device}` | none | Forget a phone from BlueZ. |
| `POST /control/bluetooth/pair/cancel` | `{"operation_id":"…"}` | Cancel a pairing operation. |
| `POST /control/bluetooth/answer` | `{"challenge":"…","device":"AA:BB:…","accept":true,"value":null}` | Confirm/reject a challenge; value carries a requested PIN/passkey. |
| `PUT /control/speaker` | `{"device":"AA:BB:…"}` or `{"device":null}` | Select an audible phone or clear explicit selection. |

Use BlueZ addresses from state as `{device}`. URL encode reserved characters.
Challenge and operation IDs are opaque. Display-only challenges such as
`display_passkey` are informational; do not submit them to `/answer`.

## State fields

`GET /control/state` returns the Host's shared state. Bluetooth and audio fields
of interest are:

- `data.bluetooth.available`: BlueZ owner exists and Host registration of the
  default Agent has succeeded.
- `data.bluetooth.devices[]`: device `id`, name, pairing/connection state,
  transport/player status, and observed capabilities.
- `data.bluetooth.challenges[]`: challenge `id`, `device_id`, `kind`, optional
  `value`, `display_only`, and expiry metadata.
- `data.bluetooth.operations`: operation ID mapped to `pending`, `succeeded`,
  `failed`, or `cancelled` plus device ID.
- `data.speaker`: target device and route state (`idle`, `waiting`, `switching`,
  `routed`, `fault`); route details appear only after verification.
- `data.audio_output_available`: the target output sink is usable.
  `SUSPENDED` is a normal available state while a PulseAudio sink is idle.
  An active port reporting `no` or `not available` makes output unavailable.
  `unknown` is retained as a raw observation because RT5616 ports may lack jack detection.
  A temporary default such as `auto_null` does not confirm RT5616 output.
- `data.audio_output`: observed sink name/index/state, active port and
  availability, and a reason when unavailable.
- `data.lighting.intent` and `data.lighting.intent_token`: saved lighting
  preference and compare-and-set token. On restart, restore a prior intent only
  while the current intent is `off`; never replay stale non-off intent.

Host versions may add audio/route diagnostics to state. An accepted response is
not proof of a connected phone or audible output; read back the corresponding
state fields.

## First-phone walkthrough

These commands operate the real Host API. Response shapes described here are
examples, not captured hardware responses. Use IDs and addresses from your own
Host state.

1. Check Host and discover the phone:

   ```powershell
   Get-ControlState | ConvertTo-Json -Depth 12
   Invoke-Control POST '/control/bluetooth/scan' $null | ConvertTo-Json -Depth 12
   Start-Sleep -Seconds 3
   $s = Get-ControlState
   $s | ConvertTo-Json -Depth 12
   ```

2. Open the add window for inbound pairing initiated from the phone:

   ```powershell
   Invoke-Control POST '/control/bluetooth/add' $null | ConvertTo-Json -Depth 12
   ```

   Active pairing from the Host uses the device `pair` action after discovery;
   it does not require or alter the inbound add window:

   ```powershell
   $pairResponse = Invoke-Control POST '/control/bluetooth/devices/AA:BB:CC:DD:EE:FF/pair' $null
   $operationId = $pairResponse.data.result
   $pairResponse | ConvertTo-Json -Depth 12
   ```

   The fixture HTTP regression captures the successful response shape as follows;
   IDs and current state are generated by the fixture and are not RK3588 evidence:

   ```json
   {
     "ok": true,
     "request_id": "req-<fixture-generated>",
     "data": {
       "result": "<fixture-operation-id>",
       "bluetooth": { "available": true, "operations": {}, "challenges": [] },
       "speaker": { "device": null, "status": "idle", "route": null },
       "lighting": { "intent": "follow", "intent_token": "<fixture-token>" },
       "audio_output_available": true,
       "audio_output": { "sink": "fixture-rt5616", "state": "SUSPENDED",
                         "port_availability": "unknown" }
     }
   }
   ```

   Challenge and operation completion are asynchronous observations; poll
   `GET /control/state` until `data.bluetooth.challenges` contains the challenge
   or `operations[operation_id].state` reaches a terminal value.

   Inspect pending confirmation challenges and match their device address before
   accepting:

   ```powershell
   $s = Get-ControlState
   $s.data.bluetooth.challenges | ConvertTo-Json -Depth 8
   $c = $s.data.bluetooth.challenges |
       Where-Object { $_.device_id -eq 'AA:BB:CC:DD:EE:FF' -and -not $_.display_only } |
       Select-Object -First 1
   Invoke-Control POST '/control/bluetooth/answer' @{
       challenge = $c.id; device = $c.device_id; accept = $true; value = $null
   } | ConvertTo-Json -Depth 12
   ```

   For a PIN or passkey challenge, provide the user-entered value. Reject with
   `accept = $false`. Close the window when done:

   ```powershell
   Invoke-Control DELETE '/control/bluetooth/add' $null | ConvertTo-Json -Depth 12
   ```

   Cancel a still-pending active pairing operation with its ID:

   ```powershell
   Invoke-Control POST '/control/bluetooth/pair/cancel' @{ operation_id = $operationId } |
       ConvertTo-Json -Depth 12
   ```

   The same challenge request accepts a PIN or passkey as a string. Keep leading
   zeroes, for example:

   ```powershell
   Invoke-Control POST '/control/bluetooth/answer' @{
       challenge = $c.id; device = $c.device_id; accept = $true; value = '004281'
   } | ConvertTo-Json -Depth 12
   ```

3. Connect and confirm BlueZ reports it connected:

   ```powershell
   Invoke-Control POST '/control/bluetooth/devices/AA:BB:CC:DD:EE:FF/connect' $null |
       ConvertTo-Json -Depth 12
   Get-ControlState | ConvertTo-Json -Depth 12
   ```

4. Play music on the phone, select it for the audible route, and verify route
   readback:

   ```powershell
   Invoke-Control PUT '/control/speaker' @{ device = 'AA:BB:CC:DD:EE:FF' } |
       ConvertTo-Json -Depth 12
   Get-ControlState | ConvertTo-Json -Depth 12
   ```

   `speaker.status = routed` with verified route details means Host observed its
   owned PulseAudio route. Sink availability remains true with no phone connected
   when the idle sink is present and its port is available.

5. Repeat pairing for a second phone if needed. At most two phones can connect;
   choose one audible winner with `PUT /control/speaker`. A third admission must
   return `409 CONNECTION_LIMIT`. Disconnect and forget explicitly:

   ```powershell
   Invoke-Control POST '/control/bluetooth/devices/AA:BB:CC:DD:EE:FF/disconnect' $null
   Invoke-Control DELETE '/control/bluetooth/devices/AA:BB:CC:DD:EE:FF' $null
   ```

   A phone already paired by BlueZ can reconnect without reopening the add
   window. Use the existing address, then verify `connected` in state:

   ```powershell
   Invoke-Control POST '/control/bluetooth/devices/AA:BB:CC:DD:EE:FF/connect' $null
   Get-ControlState | ConvertTo-Json -Depth 12
   ```

6. Verify media handoff and lighting state while phone music is active:

   ```powershell
   Invoke-Control PUT '/control/speaker' @{ device = 'AA:BB:CC:DD:EE:FF' }
   Get-ControlState | ConvertTo-Json -Depth 12
   ```

   Record `video.state`, `speaker.status`, `bluetooth.devices[].player_status`,
   `analysis.phase`, `lighting.intent`, and the physical observation that phone
   audio is audible and the expected lighting response follows. The fixture
   regression proves response fields and route selection logic only; it cannot
   prove sound or light from hardware.

## curl.exe

Use `curl.exe` to avoid PowerShell's possible `curl` alias. Do not bypass TLS
certificate validation for a deployed listener.

```powershell
$HostUrl = 'https://192.168.31.236:8443'
curl.exe -sS "$HostUrl/control/state"
curl.exe -sS -X POST "$HostUrl/control/bluetooth/add"
curl.exe -sS -X POST "$HostUrl/control/bluetooth/answer" `
  -H 'Content-Type: application/json' `
  --data '{"challenge":"CHALLENGE_ID","device":"AA:BB:CC:DD:EE:FF","accept":true,"value":null}'
curl.exe -sS -X PUT "$HostUrl/control/speaker" `
  -H 'Content-Type: application/json' `
  --data '{"device":"AA:BB:CC:DD:EE:FF"}'
```

## Failure checks and evidence

- Expired, cancelled, window-invalidated, removed-device, and restarted-Agent
  challenges must not be accepted later.
- On BlueZ owner loss or Agent release, wait for `bluetooth.available=true`
  before retrying.
- With a confirmed RT5616 sink waiting for its jack, `/api/v1/status` can report
  `ready=true` while `audio_output_available=false`. A transmitting phone waits
  for the port before Host opens its speaker route. Missing or ambiguous sinks,
  unrecognized sink states and `pactl` failures still block this readiness check.
- Route ownership/readback failure puts the speaker in `fault`; program audio
  remains gated until route state is resolved. HTTP `202` does not establish
  audible output.
- If a phone appears but does not pair, check whether an inbound pairing window
  is open or whether active outbound Pair is being used, then inspect the exact
  challenge device, kind and expiry. Do not approve a challenge for another
  address.
- If a previously paired phone will not reconnect, verify BlueZ `paired` state,
  run the explicit `connect` action, and inspect `connected` and transport/player
  status. Re-pair only if the system no longer reports the phone paired.
- If phone audio is not heard, verify the selected device is connected and active,
  `speaker.status` is `routed`, route details are verified, and output sink/port
  observations are available. Keep user mute distinct from speaker arbitration
  when inspecting audio controls.
- Record physical listening, phone model, Host build and real response bodies
  during RK3588 acceptance. Example response shapes in this document are not
  physical observations. Hardware remains `NOT HARDWARE VERIFIED` until checked.
