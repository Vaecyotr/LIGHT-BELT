#include <Arduino.h>
#include <driver/spi_master.h>
#include <esp_attr.h>
#include <esp_err.h>
#include <soc/soc.h>
#include <soc/soc_memory_types.h>

#include <cstring>

namespace {

constexpr uint8_t kDataPin = 4;
constexpr uint16_t kGroupCount = 10;
constexpr uint8_t kWireBytes[] = {16, 16, 16};
constexpr int kSpiClockHz = 16000000;
constexpr uint8_t kSpiTicksPerWsBit = 20;
constexpr uint8_t kBridgeZeroHighTicks = 5;
constexpr uint8_t kCandidateZeroHighTicks = 6;
constexpr uint8_t kOneHighTicks = 10;
constexpr size_t kEncodedDataBytes =
    kGroupCount * sizeof(kWireBytes) * 8 * kSpiTicksPerWsBit / 8;
constexpr uint32_t kResetLowUs = 80;
constexpr size_t kResetLowBytesPerSide =
    kSpiClockHz / 1000000 * kResetLowUs / 8;
constexpr size_t kTransferBytes =
    kResetLowBytesPerSide + kEncodedDataBytes + kResetLowBytesPerSide;
constexpr uint32_t kStartupInterFrameMs = 5;
constexpr uint32_t kOneShotHoldMs = 5000;
constexpr uint32_t kRepeatDurationMs = 10000;
constexpr uint32_t kRepeatIntervalMs = 33;
constexpr uint8_t kDataPins[] = {4, 5, 6};
constexpr uint8_t kDirectionPins[] = {15, 16, 17};

static_assert(kEncodedDataBytes == 600,
              "Ten WS2811 groups must encode to 600 bytes");
static_assert(kTransferBytes == 920,
              "The DMA transaction must contain 920 bytes");
static_assert(
    kResetLowBytesPerSide * 8ULL * 1000000ULL / kSpiClockHz >= 50,
    "Both low-level guards must meet the WS2811 reset time");

DMA_ATTR uint8_t transfer[kTransferBytes]{};
spi_device_handle_t device = nullptr;

void appendSymbol(size_t &bit_cursor, uint8_t high_ticks) {
  for (uint8_t tick = 0; tick < kSpiTicksPerWsBit; ++tick) {
    if (tick < high_ticks) {
      transfer[bit_cursor / 8] |=
          static_cast<uint8_t>(0x80U >> (bit_cursor % 8));
    }
    ++bit_cursor;
  }
}

void buildTransfer(uint8_t zero_high_ticks) {
  std::memset(transfer, 0, sizeof(transfer));
  size_t bit_cursor = kResetLowBytesPerSide * 8;

  for (uint16_t group = 0; group < kGroupCount; ++group) {
    for (const uint8_t byte : kWireBytes) {
      for (uint8_t mask = 0x80; mask != 0; mask >>= 1) {
        appendSymbol(bit_cursor,
                     (byte & mask) != 0 ? kOneHighTicks : zero_high_ticks);
      }
    }
  }

  ESP_ERROR_CHECK(
      bit_cursor == (kResetLowBytesPerSide + kEncodedDataBytes) * 8
          ? ESP_OK
          : ESP_ERR_INVALID_SIZE);
  ESP_ERROR_CHECK(esp_ptr_dma_capable(transfer) ? ESP_OK
                                                 : ESP_ERR_INVALID_STATE);
}

void configureSpi() {
  ESP_ERROR_CHECK(
      spi_get_actual_clock(APB_CLK_FREQ, kSpiClockHz, 128) == kSpiClockHz
          ? ESP_OK
          : ESP_ERR_INVALID_STATE);

  spi_bus_config_t bus{};
  bus.mosi_io_num = kDataPin;
  bus.miso_io_num = -1;
  bus.sclk_io_num = -1;
  bus.quadwp_io_num = -1;
  bus.quadhd_io_num = -1;
  bus.data4_io_num = -1;
  bus.data5_io_num = -1;
  bus.data6_io_num = -1;
  bus.data7_io_num = -1;
  bus.max_transfer_sz = kTransferBytes;
  bus.flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_MOSI;
  bus.intr_flags = 0;
  ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO));

  spi_device_interface_config_t config{};
  config.mode = 0;
  config.duty_cycle_pos = 128;
  config.clock_speed_hz = kSpiClockHz;
  config.spics_io_num = -1;
  config.flags = SPI_DEVICE_HALFDUPLEX;
  config.queue_size = 1;
  ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &config, &device));
}

void sendFrame() {
  spi_transaction_t transaction{};
  transaction.length = kTransferBytes * 8;
  transaction.tx_buffer = transfer;
  ESP_ERROR_CHECK(spi_device_polling_transmit(device, &transaction));
}

void sendStartupPair(uint8_t zero_high_ticks, const char *phase) {
  buildTransfer(zero_high_ticks);
  Serial.printf("%s one_shot zero_high_ticks=%u\n", phase, zero_high_ticks);
  sendFrame();
  delay(kStartupInterFrameMs);
  sendFrame();
}

void repeatCurrentTransfer(const char *phase) {
  Serial.printf("%s repeat_30fps\n", phase);
  const uint32_t repeat_started_ms = millis();
  while (static_cast<uint32_t>(millis() - repeat_started_ms) <
         kRepeatDurationMs) {
    sendFrame();
    delay(kRepeatIntervalMs);
  }
}

}  // namespace

void setup() {
  Serial.begin(115200);

  for (const uint8_t pin : kDataPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  for (const uint8_t pin : kDirectionPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, HIGH);
  }

  configureSpi();

  // A exactly reproduces the old 3.2 MHz 1000/1100 waveform at 16 MHz.
  sendStartupPair(kBridgeZeroHighTicks, "A_bridge");
  delay(kOneShotHoldMs);
  repeatCurrentTransfer("A_bridge");

  // B changes only T0H/T0L by one 16 MHz tick; all other timing is unchanged.
  sendStartupPair(kCandidateZeroHighTicks, "B_t0h_plus_62_5ns");
  delay(kOneShotHoldMs);
  repeatCurrentTransfer("B_t0h_plus_62_5ns");
  Serial.println("frozen");
}

// Phase 3: stop sending permanently so the strip holds its last latched state.
void loop() { delay(1000); }
