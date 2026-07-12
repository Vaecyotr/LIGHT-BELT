#ifndef LIGHT_BELT_ESP32_PROTOCOL_H
#define LIGHT_BELT_ESP32_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

namespace light_belt {

// UDP v3: one complete, self-describing frame for one physical ESP32 node.
static constexpr uint16_t UDP_V3_MAGIC = 0x4C45;
static constexpr uint8_t UDP_V3_VERSION = 0x03;
static constexpr uint8_t UDP_V3_MESSAGE_FRAME = 0x01;
static constexpr uint8_t UDP_V3_FLAG_SAFE_STATE = 0x01;
static constexpr uint8_t UDP_V3_FLAG_KEY_FRAME = 0x02;
static constexpr uint8_t UDP_V3_ALLOWED_FLAGS =
    UDP_V3_FLAG_SAFE_STATE | UDP_V3_FLAG_KEY_FRAME;
static constexpr size_t UDP_V3_HEADER_LEN = 29;
static constexpr size_t UDP_V3_OUTPUT_DESCRIPTOR_LEN = 6;
static constexpr size_t UDP_V3_CRC_LEN = 4;
static constexpr uint8_t MAX_OUTPUTS = 3;
static constexpr uint16_t MAX_PIXELS_PER_OUTPUT = 100;
static constexpr size_t UDP_V3_MAX_PACKET_LEN =
    UDP_V3_HEADER_LEN +
    MAX_OUTPUTS * (UDP_V3_OUTPUT_DESCRIPTOR_LEN + MAX_PIXELS_PER_OUTPUT * 3U) +
    UDP_V3_CRC_LEN;

struct OutputDescriptor {
  uint8_t output_id;
  uint8_t gpio;
  uint16_t pixel_count;
};

struct UdpV3OutputView {
  OutputDescriptor descriptor;
  uint16_t payload_len;
  const uint8_t *payload;
};

struct UdpV3Frame {
  uint8_t node_id;
  uint8_t flags;
  uint32_t sequence;
  uint64_t media_timestamp_us;
  // A value of zero means immediate application in the initial firmware.
  uint64_t apply_at_us;
  uint8_t output_count;
  uint16_t payload_len;
  UdpV3OutputView outputs[MAX_OUTPUTS];
};

enum class ParseResult {
  Ok,
  TooShort,
  TooLarge,
  BadMagic,
  BadVersion,
  BadMessageType,
  WrongNode,
  BadFlags,
  BadOutputCount,
  BadLengths,
  UnknownOutput,
  DuplicateOutput,
  IncompleteOutputSet,
  BadCrc,
};

uint32_t crc32Ethernet(const uint8_t *data, size_t len);

bool validateOutputDescriptors(
    const OutputDescriptor *outputs, uint8_t output_count);

ParseResult parseUdpV3Frame(
    const uint8_t *data,
    size_t len,
    uint8_t local_node_id,
    const OutputDescriptor *configured_outputs,
    uint8_t configured_output_count,
    UdpV3Frame *out);

// Strictly newer under uint32 wrap-around semantics. Equal is a duplicate.
bool isNewerSequence(uint32_t candidate, uint32_t previous);

}  // namespace light_belt

#endif
