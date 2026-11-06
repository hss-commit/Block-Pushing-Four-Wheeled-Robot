// Standalone radio diagnosis. No motor UART, motor commands or camera protocol.
#include <Arduino.h>
#include <esp_system.h>
#ifdef DIAG_WIFI
#include <WiFi.h>
#else
#include <BluetoothSerial.h>
BluetoothSerial bluetooth;
#endif

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("DIAG: boot, reset_reason=%d\n", static_cast<int>(esp_reset_reason()));
#ifdef DIAG_WIFI
  bool modeOk = WiFi.mode(WIFI_AP);
  bool radioOk = modeOk && WiFi.softAP("ESP32-DIAG", "esp32diag123");
  Serial.printf("DIAG: WiFi AP %s\n", radioOk ? "READY" : "FAILED");
  if (radioOk) Serial.println(WiFi.softAPIP());
#else
  bool radioOk = bluetooth.begin("ESP32-BT-DIAG");
  if (radioOk) bluetooth.setPin("1234");
  Serial.printf("DIAG: Bluetooth %s\n", radioOk ? "READY" : "FAILED");
#endif
}

void loop() {
  static uint32_t previous = 0;
  uint32_t now = millis();
  if (now - previous >= 1000) {
    previous = now;
    Serial.printf("DIAG: alive uptime_ms=%lu free_heap=%u\n", now, ESP.getFreeHeap());
  }
#ifdef DIAG_BLUETOOTH
  // Official SerialToSerialBT-style echo; no movement protocol is implemented.
  for (int n = 0; n < 128 && bluetooth.available(); ++n) bluetooth.write(bluetooth.read());
#endif
  delay(10);
}
