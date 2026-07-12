#ifndef LIGHT_BELT_ESP32_LED_OUTPUT_H
#define LIGHT_BELT_ESP32_LED_OUTPUT_H

#include <Arduino.h>
#include <FastLED.h>
#include <stdint.h>

#include "config.h"
#include "frame_state.h"
#include "protocol.h"

namespace light_belt {

class LedOutput {
 public:
  LedOutput();

  bool begin();
  // Returns true only after an entire valid, newer node frame has been staged
  // and committed.  The physical refresh is one FastLED.show() for all GPIOs.
  bool acceptFrame(const UdpV3Frame &frame, uint32_t now_ms);
  bool showBlack();
  bool timedOut(uint32_t now_ms) const;

  const OutputDescriptor *descriptors() const;
  uint8_t outputCount() const;

 private:
  MultiOutputFrameState state_;
  CRGB pixels_[MAX_OUTPUTS][MAX_PIXELS_PER_OUTPUT] = {};

  void copyStateToLeds();
};

}  // namespace light_belt

#endif
