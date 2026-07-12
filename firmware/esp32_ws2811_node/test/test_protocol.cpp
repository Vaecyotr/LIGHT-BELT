#ifdef ARDUINO
#include <Arduino.h>
#endif
#include <string.h>
#include <unity.h>

#include "../../shared/udp_v3_golden.h"
#include "../src/frame_state.h"
#include "../src/protocol.h"

namespace {

const light_belt::OutputDescriptor kOneOutput[] = {{1, 4, 2}};
const light_belt::OutputDescriptor kTwoOutputs[] = {{1, 4, 2}, {2, 5, 1}};
const light_belt::OutputDescriptor kThreeOutputs[] = {
    {1, 4, 1}, {2, 5, 2}, {3, 6, 3}};

void writeU16(uint8_t *target, uint16_t value) {
  target[0] = static_cast<uint8_t>(value >> 8);
  target[1] = static_cast<uint8_t>(value);
}

void writeU32(uint8_t *target, uint32_t value) {
  target[0] = static_cast<uint8_t>(value >> 24);
  target[1] = static_cast<uint8_t>(value >> 16);
  target[2] = static_cast<uint8_t>(value >> 8);
  target[3] = static_cast<uint8_t>(value);
}

void repairCrc(uint8_t *raw, size_t len) {
  writeU32(raw + len - light_belt::UDP_V3_CRC_LEN,
           light_belt::crc32Ethernet(raw, len - light_belt::UDP_V3_CRC_LEN));
}

size_t makeFrame(
    uint8_t *raw,
    uint8_t node_id,
    uint32_t sequence,
    const light_belt::OutputDescriptor *outputs,
    uint8_t output_count,
    uint64_t apply_at_us = 0) {
  memset(raw, 0, light_belt::UDP_V3_MAX_PACKET_LEN);
  writeU16(raw, light_belt::UDP_V3_MAGIC);
  raw[2] = light_belt::UDP_V3_VERSION;
  raw[3] = light_belt::UDP_V3_MESSAGE_FRAME;
  raw[4] = node_id;
  raw[5] = light_belt::UDP_V3_FLAG_KEY_FRAME;
  writeU32(raw + 6, sequence);
  // The test does not need a nonzero media timestamp; apply_at proves parsing.
  for (uint8_t byte = 0; byte < 8; ++byte) {
    raw[18 + byte] = static_cast<uint8_t>(apply_at_us >> (56 - byte * 8));
  }
  raw[26] = output_count;
  size_t cursor = light_belt::UDP_V3_HEADER_LEN;
  for (uint8_t output = 0; output < output_count; ++output) {
    raw[cursor] = outputs[output].output_id;
    raw[cursor + 1] = outputs[output].gpio;
    writeU16(raw + cursor + 2, outputs[output].pixel_count);
    writeU16(raw + cursor + 4, outputs[output].pixel_count * 3U);
    cursor += light_belt::UDP_V3_OUTPUT_DESCRIPTOR_LEN;
    for (uint16_t pixel = 0; pixel < outputs[output].pixel_count; ++pixel) {
      raw[cursor++] = static_cast<uint8_t>(10 * (output + 1) + pixel);
      raw[cursor++] = static_cast<uint8_t>(20 * (output + 1) + pixel);
      raw[cursor++] = static_cast<uint8_t>(30 * (output + 1) + pixel);
    }
  }
  writeU16(raw + 27, static_cast<uint16_t>(cursor - light_belt::UDP_V3_HEADER_LEN));
  const size_t len = cursor + light_belt::UDP_V3_CRC_LEN;
  repairCrc(raw, len);
  return len;
}

light_belt::UdpV3Frame parse(
    const uint8_t *raw,
    size_t len,
    uint8_t node_id,
    const light_belt::OutputDescriptor *outputs,
    uint8_t output_count) {
  light_belt::UdpV3Frame frame{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::Ok),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, len, node_id, outputs, output_count, &frame)));
  return frame;
}

void test_udp_v3_golden_vector_parses_and_stages_independently() {
  const light_belt::UdpV3Frame frame = parse(
      UDP_V3_GOLDEN_0, UDP_V3_GOLDEN_0_len, 2, kTwoOutputs, 2);
  TEST_ASSERT_EQUAL_UINT32(0x01020304, frame.sequence);
  TEST_ASSERT_EQUAL_UINT64(1234567, frame.media_timestamp_us);
  TEST_ASSERT_EQUAL_UINT64(0, frame.apply_at_us);
  TEST_ASSERT_EQUAL_UINT8(2, frame.output_count);
  TEST_ASSERT_EQUAL_UINT8(1, frame.outputs[0].payload[0]);
  TEST_ASSERT_EQUAL_UINT8(254, frame.outputs[1].payload[0]);

  light_belt::MultiOutputFrameState state(kTwoOutputs, 2);
  TEST_ASSERT_TRUE(state.configurationValid());
  TEST_ASSERT_TRUE(state.applyFrame(frame));
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());
  TEST_ASSERT_EQUAL_UINT8(1, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT8(6, state.pixels(0)[1].b);
  TEST_ASSERT_EQUAL_UINT8(254, state.pixels(1)[0].r);
  TEST_ASSERT_EQUAL_UINT8(128, state.pixels(1)[0].g);
}

void test_one_two_and_three_outputs_are_independent_and_refresh_once() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  for (uint8_t output_count = 1; output_count <= 3; ++output_count) {
    const light_belt::OutputDescriptor *outputs =
        output_count == 1 ? kOneOutput : output_count == 2 ? kTwoOutputs : kThreeOutputs;
    const size_t len = makeFrame(raw, 9, 10 + output_count, outputs, output_count, 77);
    const light_belt::UdpV3Frame frame = parse(raw, len, 9, outputs, output_count);
    light_belt::MultiOutputFrameState state(outputs, output_count);
    TEST_ASSERT_TRUE(state.applyFrame(frame));
    TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());
    for (uint8_t output = 0; output < output_count; ++output) {
      TEST_ASSERT_EQUAL_UINT8(10 * (output + 1), state.pixels(output)[0].r);
      TEST_ASSERT_EQUAL_UINT8(20 * (output + 1), state.pixels(output)[0].g);
      TEST_ASSERT_EQUAL_UINT8(30 * (output + 1), state.pixels(output)[0].b);
    }
  }
}

void test_invalid_incomplete_duplicate_and_oversized_frames_do_not_change_display() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t valid_len = makeFrame(raw, 2, 50, kTwoOutputs, 2);
  light_belt::MultiOutputFrameState state(kTwoOutputs, 2);
  TEST_ASSERT_TRUE(state.applyFrame(parse(raw, valid_len, 2, kTwoOutputs, 2)));
  const uint8_t initial_red = state.pixels(0)[0].r;

  raw[valid_len - 1] ^= 1;  // Only the transmitted CRC is now invalid.
  light_belt::UdpV3Frame ignored{};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::BadCrc),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, valid_len, 2, kTwoOutputs, 2, &ignored)));
  TEST_ASSERT_EQUAL_UINT8(initial_red, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());

  const size_t duplicate_len = makeFrame(raw, 2, 51, kTwoOutputs, 2);
  raw[light_belt::UDP_V3_HEADER_LEN + light_belt::UDP_V3_OUTPUT_DESCRIPTOR_LEN +
      kTwoOutputs[0].pixel_count * 3U] = 1;
  repairCrc(raw, duplicate_len);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::DuplicateOutput),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, duplicate_len, 2, kTwoOutputs, 2, &ignored)));

  const size_t incomplete_len = makeFrame(raw, 2, 52, kOneOutput, 1);
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::IncompleteOutputSet),
      static_cast<int>(light_belt::parseUdpV3Frame(
          raw, incomplete_len, 2, kTwoOutputs, 2, &ignored)));
  TEST_ASSERT_EQUAL_UINT8(initial_red, state.pixels(0)[0].r);
  TEST_ASSERT_EQUAL_UINT32(1, state.refreshCount());

  uint8_t too_large[light_belt::UDP_V3_MAX_PACKET_LEN + 1] = {};
  TEST_ASSERT_EQUAL(
      static_cast<int>(light_belt::ParseResult::TooLarge),
      static_cast<int>(light_belt::parseUdpV3Frame(
          too_large, sizeof(too_large), 2, kTwoOutputs, 2, &ignored)));
}

void test_duplicate_stale_and_wrap_sequences_are_rejected_or_accepted_consistently() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  light_belt::MultiOutputFrameState state(kOneOutput, 1);
  size_t len = makeFrame(raw, 3, 0xFFFFFFFF, kOneOutput, 1);
  TEST_ASSERT_TRUE(state.applyFrame(parse(raw, len, 3, kOneOutput, 1)));
  len = makeFrame(raw, 3, 0, kOneOutput, 1);
  TEST_ASSERT_TRUE(state.applyFrame(parse(raw, len, 3, kOneOutput, 1)));
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  TEST_ASSERT_FALSE(state.applyFrame(parse(raw, len, 3, kOneOutput, 1)));
  len = makeFrame(raw, 3, 0xFFFFFFFF, kOneOutput, 1);
  TEST_ASSERT_FALSE(state.applyFrame(parse(raw, len, 3, kOneOutput, 1)));
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
}

void test_timeout_blacks_all_configured_outputs() {
  uint8_t raw[light_belt::UDP_V3_MAX_PACKET_LEN] = {};
  const size_t len = makeFrame(raw, 4, 1, kThreeOutputs, 3);
  light_belt::MultiOutputFrameState state(kThreeOutputs, 3);
  TEST_ASSERT_TRUE(state.applyFrame(parse(raw, len, 4, kThreeOutputs, 3)));
  state.noteAcceptedAt(100);
  TEST_ASSERT_FALSE(state.timedOut(1100, 1000));
  TEST_ASSERT_TRUE(state.timedOut(1101, 1000));
  TEST_ASSERT_TRUE(state.applySafeBlack());
  TEST_ASSERT_EQUAL_UINT32(2, state.refreshCount());
  for (uint8_t output = 0; output < state.outputCount(); ++output) {
    for (uint16_t pixel = 0; pixel < state.descriptor(output).pixel_count; ++pixel) {
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].r);
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].g);
      TEST_ASSERT_EQUAL_UINT8(0, state.pixels(output)[pixel].b);
    }
  }
}

}  // namespace

void setUp() {}
void tearDown() {}

int runTests() {
  UNITY_BEGIN();
  RUN_TEST(test_udp_v3_golden_vector_parses_and_stages_independently);
  RUN_TEST(test_one_two_and_three_outputs_are_independent_and_refresh_once);
  RUN_TEST(test_invalid_incomplete_duplicate_and_oversized_frames_do_not_change_display);
  RUN_TEST(test_duplicate_stale_and_wrap_sequences_are_rejected_or_accepted_consistently);
  RUN_TEST(test_timeout_blacks_all_configured_outputs);
  return UNITY_END();
}

#ifdef ARDUINO
void setup() { (void)runTests(); }
void loop() {}
#else
int main(int, char **) {
  return runTests();
}
#endif
