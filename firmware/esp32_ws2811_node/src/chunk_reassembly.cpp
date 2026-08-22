#include "chunk_reassembly.h"

#include <stdlib.h>
#include <string.h>

namespace light_belt {
namespace {

void *defaultAllocate(size_t bytes) { return malloc(bytes); }
void defaultRelease(void *pointer) { free(pointer); }

bool isSessionStart(uint32_t sequence, uint8_t flags) {
  return sequence == 1U && (flags & UDP_V3_FLAG_KEY_FRAME) != 0;
}

bool samePixel(const RgbPixel &pixel, const uint8_t *rgb) {
  return pixel.r == rgb[0] && pixel.g == rgb[1] && pixel.b == rgb[2];
}

}  // namespace

UdpV3ChunkReassembler::UdpV3ChunkReassembler(
    const ReassemblyAllocator *allocator)
    : allocator_(allocator == nullptr
                     ? ReassemblyAllocator{defaultAllocate, defaultRelease}
                     : *allocator) {}

UdpV3ChunkReassembler::~UdpV3ChunkReassembler() { reset(); }

bool UdpV3ChunkReassembler::begin(
    const OutputDescriptor *outputs, uint8_t output_count) {
  reset();
  if (allocator_.allocate == nullptr || allocator_.release == nullptr ||
      !validateOutputDescriptors(outputs, output_count)) {
    return false;
  }

  size_t total = 0;
  for (uint8_t index = 0; index < output_count; ++index) {
    if (outputs[index].pixel_count > FRAME_PIXEL_CAPACITY) {
      return false;
    }
    outputs_[index] = outputs[index];
    output_offsets_[index] = total;
    total += outputs[index].pixel_count;
  }
  if (total == 0) {
    return false;
  }

  pixels_ = static_cast<RgbPixel *>(
      allocator_.allocate(total * sizeof(RgbPixel)));
  if (pixels_ == nullptr) {
    return false;
  }
  received_ = static_cast<uint8_t *>(allocator_.allocate(total));
  if (received_ == nullptr) {
    allocator_.release(pixels_);
    pixels_ = nullptr;
    return false;
  }
  memset(pixels_, 0, total * sizeof(RgbPixel));
  memset(received_, 0, total);
  output_count_ = output_count;
  total_pixels_ = total;
  initialized_ = true;
  return true;
}

void UdpV3ChunkReassembler::reset() {
  if (pixels_ != nullptr && allocator_.release != nullptr) {
    allocator_.release(pixels_);
  }
  if (received_ != nullptr && allocator_.release != nullptr) {
    allocator_.release(received_);
  }
  pixels_ = nullptr;
  received_ = nullptr;
  output_count_ = 0;
  total_pixels_ = 0;
  received_count_ = 0;
  initialized_ = false;
  active_ = false;
  has_completed_ = false;
}

bool UdpV3ChunkReassembler::sameActiveIdentity(
    const UdpV3ChunkFrame &packet) const {
  return active_ && packet.node_id == active_node_id_ &&
         packet.flags == active_flags_ && packet.sequence == active_sequence_ &&
         packet.media_timestamp_us == active_media_timestamp_us_ &&
         packet.apply_at_us == active_apply_at_us_;
}

bool UdpV3ChunkReassembler::sameCompletedIdentity(
    const UdpV3ChunkFrame &packet) const {
  return has_completed_ && packet.node_id == completed_node_id_ &&
         packet.flags == completed_flags_ &&
         packet.sequence == completed_sequence_ &&
         packet.media_timestamp_us == completed_media_timestamp_us_ &&
         packet.apply_at_us == completed_apply_at_us_;
}

void UdpV3ChunkReassembler::startFrame(const UdpV3ChunkFrame &packet) {
  memset(received_, 0, total_pixels_);
  received_count_ = 0;
  active_ = true;
  active_node_id_ = packet.node_id;
  active_flags_ = packet.flags;
  active_sequence_ = packet.sequence;
  active_media_timestamp_us_ = packet.media_timestamp_us;
  active_apply_at_us_ = packet.apply_at_us;
}

int UdpV3ChunkReassembler::findOutput(uint8_t output_id) const {
  for (uint8_t index = 0; index < output_count_; ++index) {
    if (outputs_[index].output_id == output_id) {
      return index;
    }
  }
  return -1;
}

ReassemblyResult UdpV3ChunkReassembler::accept(
    const UdpV3ChunkFrame &packet, OwnedNodeFrame *completed) {
  if (!initialized_ || completed == nullptr || packet.chunk_count == 0 ||
      packet.chunk_count > MAX_OUTPUTS) {
    return ReassemblyResult::Rejected;
  }
  if (sameCompletedIdentity(packet)) {
    return ReassemblyResult::Duplicate;
  }

  // Re-check the in-memory view before changing the active identity. The wire
  // parser performs the same checks, while this protects direct callers and
  // guarantees a rejected datagram cannot discard an older incomplete frame.
  for (uint8_t chunk_index = 0; chunk_index < packet.chunk_count;
       ++chunk_index) {
    const UdpV3ChunkView &chunk = packet.chunks[chunk_index];
    const int output_index = findOutput(chunk.descriptor.output_id);
    if (output_index < 0 || chunk.payload == nullptr ||
        chunk.descriptor.gpio != outputs_[output_index].gpio ||
        chunk.descriptor.pixel_count != outputs_[output_index].pixel_count ||
        chunk.chunk_pixel_count == 0 ||
        chunk.payload_len != chunk.chunk_pixel_count * 3U ||
        static_cast<uint32_t>(chunk.chunk_offset) +
                chunk.chunk_pixel_count >
            outputs_[output_index].pixel_count) {
      return ReassemblyResult::Rejected;
    }
  }

  if (active_ && packet.sequence == active_sequence_ &&
      !sameActiveIdentity(packet)) {
    return ReassemblyResult::Rejected;
  }
  if (!sameActiveIdentity(packet)) {
    const bool key_reset = isSessionStart(packet.sequence, packet.flags);
    const bool newer_than_reference = active_
        ? isNewerSequence(packet.sequence, active_sequence_)
        : !has_completed_ ||
              isNewerSequence(packet.sequence, completed_sequence_);
    if (!key_reset && !newer_than_reference) {
      return ReassemblyResult::Rejected;
    }
    startFrame(packet);
  }

  // Validate every overlap before mutating any byte from this datagram.
  for (uint8_t chunk_index = 0; chunk_index < packet.chunk_count;
       ++chunk_index) {
    const UdpV3ChunkView &chunk = packet.chunks[chunk_index];
    const int output_index = findOutput(chunk.descriptor.output_id);
    const size_t global_start =
        output_offsets_[output_index] + chunk.chunk_offset;
    for (uint16_t pixel = 0; pixel < chunk.chunk_pixel_count; ++pixel) {
      const size_t global = global_start + pixel;
      if (received_[global] != 0 &&
          !samePixel(pixels_[global], chunk.payload + pixel * 3U)) {
        return ReassemblyResult::Rejected;
      }
    }
  }

  for (uint8_t chunk_index = 0; chunk_index < packet.chunk_count;
       ++chunk_index) {
    const UdpV3ChunkView &chunk = packet.chunks[chunk_index];
    const int output_index = findOutput(chunk.descriptor.output_id);
    const size_t global_start =
        output_offsets_[output_index] + chunk.chunk_offset;
    for (uint16_t pixel = 0; pixel < chunk.chunk_pixel_count; ++pixel) {
      const size_t global = global_start + pixel;
      if (received_[global] == 0) {
        const uint8_t *rgb = chunk.payload + pixel * 3U;
        pixels_[global] = {rgb[0], rgb[1], rgb[2]};
        received_[global] = 1;
        ++received_count_;
      }
    }
  }
  if (received_count_ != total_pixels_) {
    return ReassemblyResult::Incomplete;
  }

  OwnedNodeFrame staged{};
  staged.node_id = active_node_id_;
  staged.flags = active_flags_;
  staged.sequence = active_sequence_;
  staged.media_timestamp_us = active_media_timestamp_us_;
  staged.apply_at_us = active_apply_at_us_;
  staged.output_count = output_count_;
  for (uint8_t output = 0; output < output_count_; ++output) {
    staged.outputs[output].descriptor = outputs_[output];
    memcpy(staged.outputs[output].pixels, pixels_ + output_offsets_[output],
           static_cast<size_t>(outputs_[output].pixel_count) *
               sizeof(RgbPixel));
  }
  *completed = staged;
  return ReassemblyResult::Complete;
}

void UdpV3ChunkReassembler::noteComplete(const OwnedNodeFrame &frame) {
  active_ = false;
  received_count_ = 0;
  has_completed_ = true;
  completed_node_id_ = frame.node_id;
  completed_flags_ = frame.flags;
  completed_sequence_ = frame.sequence;
  completed_media_timestamp_us_ = frame.media_timestamp_us;
  completed_apply_at_us_ = frame.apply_at_us;
}

}  // namespace light_belt
