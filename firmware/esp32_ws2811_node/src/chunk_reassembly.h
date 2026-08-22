#ifndef LIGHT_BELT_ESP32_CHUNK_REASSEMBLY_H
#define LIGHT_BELT_ESP32_CHUNK_REASSEMBLY_H

#include <stddef.h>
#include <stdint.h>

#include "owned_frame.h"
#include "protocol.h"

namespace light_belt {

struct ReassemblyAllocator {
  void *(*allocate)(size_t bytes);
  void (*release)(void *pointer);
};

enum class ReassemblyResult {
  Rejected,
  Incomplete,
  Complete,
  Duplicate,
};

// Owns exactly one incomplete logical frame. Storage is allocated from the
// compiled output descriptors during begin(); no wire value can enlarge it.
class UdpV3ChunkReassembler {
 public:
  explicit UdpV3ChunkReassembler(
      const ReassemblyAllocator *allocator = nullptr);
  ~UdpV3ChunkReassembler();

  UdpV3ChunkReassembler(const UdpV3ChunkReassembler &) = delete;
  UdpV3ChunkReassembler &operator=(const UdpV3ChunkReassembler &) = delete;

  bool begin(const OutputDescriptor *outputs, uint8_t output_count);
  ReassemblyResult accept(
      const UdpV3ChunkFrame &packet, OwnedNodeFrame *completed);
  void noteComplete(const OwnedNodeFrame &frame);
  void reset();

 private:
  bool sameActiveIdentity(const UdpV3ChunkFrame &packet) const;
  bool sameCompletedIdentity(const UdpV3ChunkFrame &packet) const;
  void startFrame(const UdpV3ChunkFrame &packet);
  int findOutput(uint8_t output_id) const;

  ReassemblyAllocator allocator_;
  OutputDescriptor outputs_[MAX_OUTPUTS]{};
  size_t output_offsets_[MAX_OUTPUTS]{};
  uint8_t output_count_ = 0;
  size_t total_pixels_ = 0;
  RgbPixel *pixels_ = nullptr;
  uint8_t *received_ = nullptr;
  size_t received_count_ = 0;
  bool initialized_ = false;
  bool active_ = false;
  uint8_t active_node_id_ = 0;
  uint8_t active_flags_ = 0;
  uint32_t active_sequence_ = 0;
  uint64_t active_media_timestamp_us_ = 0;
  uint64_t active_apply_at_us_ = 0;
  bool has_completed_ = false;
  uint8_t completed_node_id_ = 0;
  uint8_t completed_flags_ = 0;
  uint32_t completed_sequence_ = 0;
  uint64_t completed_media_timestamp_us_ = 0;
  uint64_t completed_apply_at_us_ = 0;
};

}  // namespace light_belt

#endif
