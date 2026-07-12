#ifndef LIGHT_BELT_ESP32_NODE_2_H
#define LIGHT_BELT_ESP32_NODE_2_H

#undef NODE_ID
#undef OUTPUT_COUNT
#undef OUTPUT_0_ID
#undef OUTPUT_0_GPIO
#undef OUTPUT_0_PIXELS
#undef OUTPUT_1_ID
#undef OUTPUT_1_GPIO
#undef OUTPUT_1_PIXELS
#undef OUTPUT_2_ID
#undef OUTPUT_2_GPIO
#undef OUTPUT_2_PIXELS

#define NODE_ID 2
#define OUTPUT_COUNT 3
#define OUTPUT_0_ID 1
#define OUTPUT_0_GPIO 4
#define OUTPUT_0_PIXELS 10
#define OUTPUT_1_ID 2
#define OUTPUT_1_GPIO 5
#define OUTPUT_1_PIXELS 20
// Keep output 3 configured while strip_43 is physically disconnected so the
// node continues to accept the host's complete three-output UDP v3 frame.
#define OUTPUT_2_ID 3
#define OUTPUT_2_GPIO 6
#define OUTPUT_2_PIXELS 20

#endif
