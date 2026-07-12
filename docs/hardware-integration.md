> [!WARNING]
> STALE V1 INTEGRATION PLAN.
>
> This document predates the confirmed six-wire RGB+CCT hardware and the
> successful standalone STM32/COB and ESP32-S3/WS2811 hardware tests.
> Use docs/CLOSED_LOOP_SPEC.md as the target architecture.
> This file may be rewritten after the v2 implementation is complete.

> [!NOTE]
> UDP v3 ESP32 firmware is now available for one complete node frame with up
> to three independent WS2811 GPIO outputs (GPIO4/5/6). It stages every
> configured output only after whole-frame CRC/topology/sequence validation,
> then performs one multi-output refresh; timeout refreshes all configured
> outputs black. `apply_at_us` is parsed but not scheduled yet. This behavior,
> all wiring, and cross-node synchronization remain **NOT HARDWARE VERIFIED**.
> The older v1/v2 integration detail below is historical context, not the
> current digital protocol contract; use `docs/CLOSED_LOOP_SPEC.md` and the
> UDP v3 firmware README for current behavior.

# Hardware Integration Guide

This document describes the future hardware integration interfaces. All descriptions are for planning purposes. No physical hardware has been connected or verified.

## System Architecture

```
RK3588 (Linux ARM64)
  ├── Video analysis (OpenCV)
  ├── Audio analysis (NumPy/SciPy)
  ├── Lighting engine
  ├── UDP output ──► Wi-Fi ──► ESP32-S3 ──► WS2812B (digital strips)
  └── Serial output ──► RS-485 ──► STM32F103C8T6 ──► PWM ──► RGBW COB (analog zones)
```

## RK3588 → ESP32-S3 (Digital Strips)

### Interface
- **Transport**: UDP over Wi-Fi
- **Protocol**: Binary 14-byte header + N×3 payload (see docs/protocol.md)
- **Rate**: 30 FPS per strip
- **Max pixels**: 218 per packet (fits 1400-byte UDP payload)

### Integration Steps (Not Yet Verified)
1. Flash ESP32-S3 with firmware to receive UDP packets on port 9001
2. ESP32-S3 decodes binary protocol, outputs via RMT/FastLED to WS2812B
3. Verify packet integrity with XOR checksum
4. Test with 144-pixel, 100-pixel, and 72-pixel strips
5. Measure end-to-end latency

### Current Status
- **Software encoder**: Implemented and tested (UdpPacket.encode/decode)
- **Checksum**: 16-bit XOR, tested with corruption detection
- **UDP socket**: Implemented (optional pyserial binding)
- **Hardware**: NOT YET TESTED with ESP32-S3

## RK3588 → STM32F103C8T6 (Analog RGBW Zones)

### Interface
- **Transport**: RS-485 serial
- **Protocol**: 11-byte fixed frame (see docs/protocol.md)
- **Baud rate**: 115200 (configurable)
- **Frame rate**: 30 FPS per zone

### Integration Steps (Not Yet Verified)
1. Flash STM32F103C8T6 with firmware to receive 11-byte frames
2. STM32 decodes frame, validates checksum, outputs PWM to YYNMOS-8
3. YYNMOS-8 drives 24V 5-wire common-anode RGBW COB LED strip
4. Verify PWM duty cycle matches brightness and color
5. Test fade transitions (Fade field in milliseconds)

### Current Status
- **Software encoder/decoder**: Implemented and tested (SerialPacket.encode/decode)
- **Checksum**: 8-bit arithmetic sum (NOT CRC)
- **Stream parser**: Implemented with noise/fragment/bad-frame recovery
- **Memory transport**: Available for testing without hardware
- **Hardware**: NOT YET TESTED with STM32/RS-485

## Analog RGBW vs Digital Strips

| Property | Analog RGBW (STM32) | Digital (ESP32-S3) |
|----------|---------------------|---------------------|
| Protocol | 11-byte fixed frame | Variable binary packet |
| Per-pixel control | No (zone uniform) | Yes |
| White channel | Yes (dedicated W) | No (RGB only) |
| Brightness | 0-100 (PWM duty) | 0-255 per channel |
| Transport | RS-485 | Wi-Fi UDP |
| Cable | 5-wire (common anode) | 3-wire (data only) |
| Voltage | 24V | 5V/12V |

## Integration Testing Order

1. Software-only loopback tests (completed)
2. Memory transport tests (completed)
3. Loopback UDP test on RK3588 (pending hardware)
4. Serial loopback on RK3588 (pending hardware)
5. STM32 firmware development (pending)
6. ESP32-S3 firmware development (pending)
7. Physical strip integration (pending)
8. Chamber installation (pending)

## Safety Notes

- **Not for medical use**: This is a lighting prototype, not a medical device
- **Power isolation**: 24V LED power must be isolated from logic circuits
- **No life support**: Do not use for critical safety functions
- **Heat management**: COB strips may require heatsinking at full brightness
