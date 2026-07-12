#ifndef LIGHT_BELT_ESP32_CONFIG_EXAMPLE_H
#define LIGHT_BELT_ESP32_CONFIG_EXAMPLE_H

// NOT HARDWARE VERIFIED.  Each enabled entry is one electrically independent
// WS2811 strip behind its own SN74LVC1T45 level shifter.  Only GPIO4, GPIO5,
// and GPIO6 are supported, and no two entries may share a GPIO or output ID.
#define NODE_ID 1
#define OUTPUT_COUNT 3

#define OUTPUT_0_ID 1
#define OUTPUT_0_GPIO 4
#define OUTPUT_0_PIXELS 10

#define OUTPUT_1_ID 2
#define OUTPUT_1_GPIO 5
#define OUTPUT_1_PIXELS 10

#define OUTPUT_2_ID 3
#define OUTPUT_2_GPIO 6
#define OUTPUT_2_PIXELS 10

#define UDP_PORT 9001
#define COLOR_ORDER GRB
#define BRIGHTNESS_MAX 255
#define SAFE_TIMEOUT_MS 1000

#endif
