#ifndef LIGHT_BELT_ESP32_RESOURCE_LIMITS_H
#define LIGHT_BELT_ESP32_RESOURCE_LIMITS_H

#include <stddef.h>
#include <stdint.h>

#if defined(LIGHT_BELT_NODE_CONFIG)
#include "config.h"

namespace light_belt {

static constexpr uint8_t CONFIGURED_OUTPUT_COUNT = OUTPUT_COUNT;
static constexpr size_t CONFIGURED_TOTAL_PIXELS =
    static_cast<size_t>(OUTPUT_0_PIXELS)
#if OUTPUT_COUNT >= 2
    + OUTPUT_1_PIXELS
#endif
#if OUTPUT_COUNT >= 3
    + OUTPUT_2_PIXELS
#endif
    ;

static constexpr uint16_t configuredMaxPixelsPerOutput() {
  uint16_t maximum = OUTPUT_0_PIXELS;
#if OUTPUT_COUNT >= 2
  maximum = OUTPUT_1_PIXELS > maximum ? OUTPUT_1_PIXELS : maximum;
#endif
#if OUTPUT_COUNT >= 3
  maximum = OUTPUT_2_PIXELS > maximum ? OUTPUT_2_PIXELS : maximum;
#endif
  return maximum;
}

static constexpr uint16_t FRAME_PIXEL_CAPACITY =
    configuredMaxPixelsPerOutput();
static constexpr size_t CONFIGURED_COMPLETE_FRAME_LEN =
    29U + static_cast<size_t>(CONFIGURED_OUTPUT_COUNT) * 10U +
    static_cast<size_t>(CONFIGURED_TOTAL_PIXELS) * 3U + 4U;
static constexpr size_t CONFIGURED_PACKET_BUFFER_LEN =
    CONFIGURED_COMPLETE_FRAME_LEN < UDP_V3_RECEIVE_BUFFER_BYTES
        ? CONFIGURED_COMPLETE_FRAME_LEN
        : UDP_V3_RECEIVE_BUFFER_BYTES;

}  // namespace light_belt

#else

namespace light_belt {

// Native tests exercise the longest current contract boundary without
// imposing this harness capacity on an ESP32 image.
static constexpr uint8_t CONFIGURED_OUTPUT_COUNT = 3;
static constexpr uint16_t FRAME_PIXEL_CAPACITY = 512;
static constexpr size_t CONFIGURED_TOTAL_PIXELS =
    static_cast<size_t>(CONFIGURED_OUTPUT_COUNT) * FRAME_PIXEL_CAPACITY;
static constexpr size_t CONFIGURED_PACKET_BUFFER_LEN = 4096U;

}  // namespace light_belt

#endif

#endif
