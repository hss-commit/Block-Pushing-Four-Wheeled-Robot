#include <Arduino.h>
#ifdef VISION_BLUETOOTH
#include <BluetoothSerial.h>
#else
#include <WebServer.h>
#include <WiFi.h>
#endif
#ifdef VISION_WIFI_STA
#include "esp32_hotspot_config.h"
#endif
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>

// Same wiring and motor command as the existing four-motor test.
constexpr int kMotorTx = 17;
constexpr uint32_t kPulseMs = 250;
constexpr char kProtocol[] = "vision-pulse-v1";
constexpr char kStop[] = "$Car:0,0,0,0!";
constexpr char kForward[] = "$Car:0.1,0.1,0.1,0.1!";
constexpr char kLeft[] = "$Car:-0.1,0.1,-0.1,0.1!"; // A/C left, B/D right
constexpr char kRight[] = "$Car:0.1,-0.1,0.1,-0.1!";
#ifdef VISION_BLUETOOTH
BluetoothSerial bluetooth;
#else
WebServer server(80);
#endif
QueueHandle_t commands;
portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
bool busy = false;
String lastToken;

void setBusy(bool value) {
  portENTER_CRITICAL(&stateMux);
  busy = value;
  portEXIT_CRITICAL(&stateMux);
}

bool isBusy() {
  portENTER_CRITICAL(&stateMux);
  bool value = busy;
  portEXIT_CRITICAL(&stateMux);
  return value;
}

void requestStop() {
  const uint8_t command = 0;
  xQueueOverwrite(commands, &command);
}

void motorTask(void *) {
  bool moving = false;
  uint32_t stopAt = 0, lastStop = 0;
  while (true) {
    uint8_t command;
    if (xQueueReceive(commands, &command, pdMS_TO_TICKS(10)) == pdTRUE) {
      if (command >= 1 && command <= 4 && !moving) {
        moving = true;
        stopAt = millis() + (command == 1 ? kPulseMs : 120);
        Serial1.print(command <= 2 ? kForward : command == 3 ? kLeft : kRight);
        Serial.printf("STEP %u: command sent\n", command);
      } else if (command == 0) {
        moving = false;
        Serial1.print(kStop);
        lastStop = millis();
        setBusy(false);
        Serial.println("STOP: command sent");
      }
    }
    // Independent task: slow/incomplete communication cannot postpone this.
    if (moving && static_cast<int32_t>(millis() - stopAt) >= 0) {
      moving = false;
      Serial1.print(kStop);
      lastStop = millis();
      setBusy(false);
      Serial.println("Action time limit: STOP sent");
    }
    if (!moving && millis() - lastStop >= 100) {
      Serial1.print(kStop);
      lastStop = millis();
    }
  }
}

#ifdef VISION_BLUETOOTH
#include "esp32_vision_bluetooth.h"
#else
void reply(int code, const char *result) {
  server.sendHeader("Cache-Control", "no-store");
  server.send(code, "application/json", String("{\"protocol\":\"") + kProtocol +
              "\",\"result\":\"" + result + "\",\"busy\":" +
              (isBusy() ? "true" : "false") + ",\"pulse_ms\":250,\"step_ms\":120}");
}
#endif

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200, SERIAL_8N1, -1, kMotorTx);
  delay(300);
  Serial1.print("$MOTOR_4CH_SET:0!");
  delay(100);
  Serial1.print(kStop);
  commands = xQueueCreate(1, sizeof(uint8_t));
  if (!commands || xTaskCreate(motorTask, "motor-stop", 3072, nullptr, 2, nullptr) != pdPASS) {
    Serial.println("Motor watchdog initialization failed; wireless disabled");
    while (true) { Serial1.print(kStop); delay(100); }
  }
#ifdef VISION_BLUETOOTH
  if (!bluetooth.begin("ESP32-Vision-BT")) {
    Serial.println("Bluetooth failed; motors remain stopped");
    return;
  }
  bluetooth.setPin("1234");
  Serial.println("ESP32-Vision-BT / pairing PIN: 1234 / Bluetooth ready");
#else
#ifdef VISION_WIFI_STA
  WiFi.mode(WIFI_STA);
  // Receive car commands promptly instead of waiting for hotspot DTIM wakeups.
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(kPhoneHotspotSsid, kPhoneHotspotPassword);
  Serial.printf("Connecting to phone hotspot: %s\n", kPhoneHotspotSsid);
#else
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP("ESP32-Vision-Test", "esp32car123")) {
    Serial.println("Hotspot failed; motors remain stopped");
    return;
  }
#endif
  server.on("/status", HTTP_GET, []() { reply(200, "ready"); });
  server.on("/stop", HTTP_POST, []() { requestStop(); reply(200, "stop_queued"); });
  server.on("/step", HTTP_POST, []() {
    const String token = server.arg("id"), direction = server.arg("direction");
    uint8_t command = direction == "forward" ? 2 : direction == "left" ? 3 : direction == "right" ? 4 : 0;
    bool valid = token.length() == 32 && command != 0;
    for (size_t i = 0; i < token.length(); ++i) {
      char c = token[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) valid = false;
    }
    if (!valid) { requestStop(); reply(400, "bad_step"); return; }
    if (token == lastToken) { reply(200, "duplicate_ignored"); return; }
    if (isBusy()) { reply(409, "busy"); return; }
    lastToken = token;
    setBusy(true);
    xQueueOverwrite(commands, &command);
    reply(200, "step_queued");
  });
  server.on("/pulse", HTTP_POST, []() {
    const String token = server.arg("id");
    bool valid = token.length() == 32;
    for (size_t i = 0; i < token.length(); ++i) {
      char c = token[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) valid = false;
    }
    if (!valid) { requestStop(); reply(400, "bad_id"); return; }
    // Retrying the same request never starts another pulse.
    if (token == lastToken) { reply(200, "duplicate_ignored"); return; }
    if (isBusy()) { reply(409, "busy"); return; }
    lastToken = token;
    setBusy(true);
    const uint8_t command = 1;
    xQueueOverwrite(commands, &command);
    reply(200, "pulse_queued");
  });
  server.on("/", HTTP_GET, []() {
    server.send(200, "text/html; charset=utf-8",
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<h2>视觉无线联动测试</h2><p>运动由电脑画面中的空格键触发，约250毫秒后发送停止。</p>"
      "<form action='/stop' method='post'><button style='font-size:32px'>停止</button></form>");
  });
  server.onNotFound([]() { requestStop(); reply(404, "unknown_route"); });
#ifdef VISION_WIFI_STA
  Serial.println("Waiting for hotspot; HTTP address will be printed after connection.");
#else
  server.begin();
  Serial.print("ESP32-Vision-Test / password: esp32car123 / http://");
  Serial.println(WiFi.softAPIP());
#endif
#endif
}

void loop() {
#ifdef VISION_BLUETOOTH
  handleBluetooth();
#elif defined(VISION_WIFI_STA)
  static bool wasConnected = false;
  static uint32_t lastReconnect = 0;
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected != wasConnected) {
    requestStop();
    if (connected) {
      server.begin();
      Serial.print("Phone hotspot connected / car address: http://");
      Serial.println(WiFi.localIP());
    } else {
      server.stop();
      lastToken = "";
      Serial.println("Phone hotspot disconnected; STOP requested, waiting to reconnect.");
    }
    wasConnected = connected;
  }
  if (connected) {
    server.handleClient();
  } else {
    if (millis() - lastReconnect >= 10000) {
      lastReconnect = millis();
      Serial.printf("Hotspot not connected (status=%d); reconnecting.\n", WiFi.status());
      WiFi.reconnect();
    }
    delay(10);
  }
#else
  server.handleClient();
#endif
}
