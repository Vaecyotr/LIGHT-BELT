#include "frame_state.h"

#include <string.h>

namespace light_belt {

MultiOutputFrameState::MultiOutputFrameState(
    const OutputDescriptor *outputs, uint8_t output_count)
    : valid_(validateOutputDescriptors(outputs, output_count)),
      output_count_(valid_ ? output_count : 0) {
  if (valid_) {
    for (uint8_t index = 0; index < output_count_; ++index) {
      outputs_[index] = outputs[index];
    }
  }
}

bool MultiOutputFrameState::configurationValid() const { return valid_; }

bool MultiOutputFrameState::applyFrame(const UdpV3Frame &frame) {
  if (!valid_ || frame.output_count != output_count_ ||
      (has_sequence_ && !isNewerSequence(frame.sequence, last_sequence_))) {
    return false;
  }

  // Parse has already verified the complete configured output set.  Copy to a
  // private staged frame first; the visible buffers change only after all
  // output payloads have been decoded.
  RgbPixel staged[MAX_OUTPUTS][MAX_PIXELS_PER_OUTPUT] = {};
  for (uint8_t configured_index = 0; configured_index < output_count_; ++configured_index) {
    const OutputDescriptor &configured = outputs_[configured_index];
    const UdpV3OutputView *received = nullptr;
    for (uint8_t received_index = 0; received_index < frame.output_count; ++received_index) {
      if (frame.outputs[received_index].descriptor.output_id == configured.output_id) {
        received = &frame.outputs[received_index];
        break;
      }
    }
    if (received == nullptr || received->descriptor.gpio != configured.gpio ||
        received->descriptor.pixel_count != configured.pixel_count ||
        received->payload_len != configured.pixel_count * 3U) {
      return false;
    }
    for (uint16_t pixel = 0; pixel < configured.pixel_count; ++pixel) {
      const uint16_t offset = pixel * 3U;
      staged[configured_index][pixel] = {
          received->payload[offset],
          received->payload[offset + 1],
          received->payload[offset + 2],
      };
    }
  }

  memcpy(displayed_, staged, sizeof(displayed_));
  last_sequence_ = frame.sequence;
  has_sequence_ = true;
  has_accepted_frame_ = true;
  ++refresh_count_;
  return true;
}

bool MultiOutputFrameState::applySafeBlack() {
  if (!valid_) {
    return false;
  }
  memset(displayed_, 0, sizeof(displayed_));
  ++refresh_count_;
  return true;
}

bool MultiOutputFrameState::timedOut(uint32_t now_ms, uint32_t timeout_ms) const {
  return has_accepted_frame_ && static_cast<uint32_t>(now_ms - last_accepted_ms_) > timeout_ms;
}

void MultiOutputFrameState::noteAcceptedAt(uint32_t now_ms) { last_accepted_ms_ = now_ms; }

const OutputDescriptor &MultiOutputFrameState::descriptor(uint8_t output_index) const {
  return outputs_[output_index];
}

const RgbPixel *MultiOutputFrameState::pixels(uint8_t output_index) const {
  return displayed_[output_index];
}

uint8_t MultiOutputFrameState::outputCount() const { return output_count_; }

uint32_t MultiOutputFrameState::refreshCount() const { return refresh_count_; }

bool MultiOutputFrameState::hasAcceptedFrame() const { return has_accepted_frame_; }

}  // namespace light_belt
