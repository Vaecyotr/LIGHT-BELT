> [!WARNING]
> LEGACY V1 DOCUMENT.
>
> This file documents the currently implemented legacy protocol.
> It is not the target closed-loop architecture.
> The v2 target is defined by docs/CLOSED_LOOP_SPEC.md.
> During migration, preserve this document only for compatibility analysis
> and legacy protocol tests.

# Communication Protocols

## STM32 Serial/RS-485 Protocol (11-byte Fixed Frame)

### Purpose

Transmits RGBW color, brightness, and fade timing to STM32F103C8T6 for analog COB LED strips.

### Frame Format

```
Offset  Size  Field       Range      Description
------  ----  -----       -----      -----------
0       1     Header      0x55       Frame start marker
1       1     CMD         0x01-0xFF  Command byte
2       1     R           0-255      Red channel
3       1     G           0-255      Green channel
4       1     B           0-255      Blue channel
5       1     W           0-255      White channel
6       1     Brightness  0-100      Global brightness (percent)
7       2     Fade       0-65535     Fade time in milliseconds (big-endian)
9       1     CheckSum    0-255      8-bit sum of bytes 1-8
10      1     Footer      0xAA       Frame end marker

Total: 11 bytes (fixed)
```

### CheckSum Algorithm

```
checksum = (Byte1 + Byte2 + Byte3 + Byte4 + Byte5 + Byte6 + Byte7 + Byte8) & 0xFF
```

This is an **8-bit arithmetic sum**, NOT a CRC. The term "CheckSum" is used throughout the codebase. No functions, variables, or comments reference CRC.

### Fixed Test Vector

Input:
- CMD = 0x01
- R = 255, G = 128, B = 0, W = 32
- Brightness = 80
- Fade = 1000 ms

Expected output:
```
55 01 FF 80 00 20 50 03 E8 DB AA
```

Where:
- 0xDB = (0x01 + 0xFF + 0x80 + 0x00 + 0x20 + 0x50 + 0x03 + 0xE8) & 0xFF = 0x3DB & 0xFF = 0xDB

### Protocol Limitations (v1)

- **No node address**: Current protocol assumes a single node or one physical link per node.
- **No protocol version field**: Future versions will add a version byte.
- **Multi-node RS-485**: Requires future protocol upgrade (add address byte, increase frame length).
- **Fixed 11-byte length**: No variable-length payload support.

### Error Handling

- Frames with wrong length → discarded
- Frames with wrong header/footer → discarded
- Frames with bad checksum → discarded
- Streaming parser resynchronizes on next valid header after error frame
- Buffer limited to 4096 bytes to prevent unlimited growth

---

## UDP Digital Strip Protocol

### Purpose

Transmits pixel data to ESP32-S3 for WS2811/WS2812B digital LED strips via Wi-Fi.

### Binary Packet Format

```
Offset  Size  Field          Description
------  ----  -----          -----------
0       2     Magic          0x4C45 ("LE" for Light Engine)
2       2     Version        1 (protocol version)
4       2     Sequence       0-65535 (monotonically increasing)
6       2     Strip ID       0-65535 (logical strip identifier)
8       2     Pixel Offset   0-65535 (starting pixel index)
10      2     Pixel Count    0-65535 (number of pixels in payload)
12      N*3   Pixels         N × (R,G,B) bytes, each 0-255
12+N*3  2     Checksum       16-bit XOR checksum over header+payload

Total: 14 + N*3 bytes
```

### Checksum

16-bit XOR checksum:
```python
result = 0
for i in range(0, len(data)-1, 2):
    result ^= (data[i] << 8) | data[i+1]
if len(data) % 2:
    result ^= data[-1] << 8
return result & 0xFFFF
```

### Fragmentation

- Max packet size: 1400 bytes (safe UDP payload)
- Max pixels per packet: 218 (fits in 1400 bytes)
- Each fragment has its own offset and count
- No fragment reassembly at protocol level (ESP32 handles per-packet)
- New frame sequence number overwrites previous incomplete frame

### JSON Debug Mode

For debugging only (not for real-time hardware control):
- JSON Lines format: one JSON object per line
- Contains decoded pixel data, zone data, and metadata
- Used by JsonOutput backend
