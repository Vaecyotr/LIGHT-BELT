#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <string.h>

#include "config.h"
#include "led_output.h"
#include "protocol.h"

namespace {

WiFiUDP udp;
light_belt::LedOutput led_output;
uint8_t packet_buffer[light_belt::UDP_V3_MAX_PACKET_LEN];
bool safe_state_applied = false;
uint32_t last_placeholder_log_ms = 0;

bool hasPlaceholderWifi() {
  return strcmp(WIFI_SSID, "PLACEHOLDER_SSID") == 0 ||
         strcmp(WIFI_PASSWORD, "PLACEHOLDER_PASSWORD") == 0;
}

void connectWifi() {
  if (hasPlaceholderWifi()) {
    Serial.println("WiFi placeholder SSID; compile-only firmware will not connect");
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

}  // namespace

void setup() {
  Serial.begin(115200);
  if (!led_output.begin()) {
    Serial.println("Invalid multi-output configuration; firmware is in safe state");
  }
  connectWifi();
  udp.begin(UDP_PORT);
}

void loop() {
  const uint32_t now_ms = millis();
  if (hasPlaceholderWifi() && now_ms - last_placeholder_log_ms > 5000) {
    Serial.println("WiFi placeholder SSID");
    last_placeholder_log_ms = now_ms;
  }

  const int packet_size = udp.parsePacket();
  if (packet_size > 0 && static_cast<size_t>(packet_size) <= sizeof(packet_buffer)) {
    const int read_len = udp.read(packet_buffer, sizeof(packet_buffer));
    light_belt::UdpV3Frame frame{};
    const light_belt::ParseResult result =
        read_len == packet_size
            ? light_belt::parseUdpV3Frame(
                  packet_buffer,
                  static_cast<size_t>(read_len),
                  NODE_ID,
                  led_output.descriptors(),
                  led_output.outputCount(),
                  &frame)
            : light_belt::ParseResult::BadLengths;
    // apply_at_us is parsed in frame and intentionally not scheduled in v3's
    // first firmware release.  Invalid, duplicate, or stale frames do not
    // touch the displayed buffers.
    if (result == light_belt::ParseResult::Ok && led_output.acceptFrame(frame, now_ms)) {
      safe_state_applied = false;
    }
  }

  if (!safe_state_applied && led_output.timedOut(now_ms)) {
    led_output.showBlack();
    safe_state_applied = true;
  }
}
