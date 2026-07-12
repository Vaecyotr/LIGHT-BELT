#ifndef LIGHT_BELT_ESP32_FRAME_STATE_H
#define LIGHT_BELT_ESP32_FRAME_STATE_H

#include <stdint.h>

#include "protocol.h"

namespace light_belt {

struct RgbPixel {
  uint8_t r;
  uint8_t g;
  uint8_t b;
};

// This class has no Arduino or FastLED dependency so native tests can prove
// staging, sequence, and timeout behavior before physical hardware is used.
class MultiOutputFrameState {
 public:
  MultiOutputFrameState(const OutputDescriptor *outputs, uint8_t output_count);

  bool configurationValid() const;
  bool applyFrame(const UdpV3Frame &frame);
  bool applySafeBlack();
  bool timedOut(uint32_t now_ms, uint32_t timeout_ms) const;
  void noteAcceptedAt(uint32_t now_ms);

  const OutputDescriptor &descriptor(uint8_t output_index) const;
  const RgbPixel *pixels(uint8_t output_index) const;
  uint8_t outputCount() const;
  uint32_t refreshCount() const;
  bool hasAcceptedFrame() const;

 private:
  bool valid_ = false;
  uint8_t output_count_ = 0;
  OutputDescriptor outputs_[MAX_OUTPUTS] = {};
  RgbPixel displayed_[MAX_OUTPUTS][MAX_PIXELS_PER_OUTPUT] = {};
  bool has_sequence_ = false;
  uint32_t last_sequence_ = 0;
  bool has_accepted_frame_ = false;
  uint32_t last_accepted_ms_ = 0;
  uint32_t refresh_count_ = 0;
};

}  // namespace light_belt

#endif
