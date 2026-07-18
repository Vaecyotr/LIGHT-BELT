#ifndef LIGHT_BELT_ESP32_CONFIG_EXAMPLE_H
#define LIGHT_BELT_ESP32_CONFIG_EXAMPLE_H

// Shared protocol and output defaults. Physical topology is selected only by
// the esp32-s3-node-N PlatformIO environment.
#define UDP_PORT 9001
#define SAFE_TIMEOUT_MS 1000

// Project-owned values. Do not use FastLED color-order tokens here.
#define WS2811_COLOR_ORDER_RGB 0
#define WS2811_COLOR_ORDER_GRB 1
#define WS2811_COLOR_ORDER WS2811_COLOR_ORDER_GRB

#if WS2811_COLOR_ORDER != WS2811_COLOR_ORDER_RGB && \
    WS2811_COLOR_ORDER != WS2811_COLOR_ORDER_GRB
#error "WS2811_COLOR_ORDER must be RGB or GRB"
#endif

// The production profiles use fixed 192.168.31.x addresses selected by each
// node header. Keep the firmware on this subnet instead of relying on an
// undocumented DHCP reservation.
#define WIFI_IPV4_A 192
#define WIFI_IPV4_B 168
#define WIFI_IPV4_C 31
#define WIFI_GATEWAY_D 1
#define WIFI_SUBNET_A 255
#define WIFI_SUBNET_B 255
#define WIFI_SUBNET_C 255
#define WIFI_SUBNET_D 0

#endif
