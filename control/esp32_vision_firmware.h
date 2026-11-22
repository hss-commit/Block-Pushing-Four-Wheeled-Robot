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
#include "manual_ramp.h"

// Same wiring and motor command as the existing four-motor test.
constexpr int kMotorTx = 17;
constexpr uint32_t kPulseMs = 250;
constexpr uint32_t kManualHoldMs = 700;
constexpr char kProtocol[] = "vision-pulse-v1";
constexpr char kStop[] = "$Car:0,0,0,0!";
constexpr char kForward[] = "$Car:0.1,0.1,0.1,0.1!";
constexpr char kBackward[] = "$Car:-0.1,-0.1,-0.1,-0.1!";
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
  uint8_t manualCommand = 0;
  uint32_t manualStartedAt = 0, lastManualWrite = 0;
  while (true) {
    uint8_t command;
    if (xQueueReceive(commands, &command, pdMS_TO_TICKS(10)) == pdTRUE) {
      if (command >= 6 && command <= 9) {
        if (!moving || manualCommand != command) {
          manualStartedAt = millis();
          lastManualWrite = millis()-50;
        }
        manualCommand = command;
        moving = true;
        stopAt = millis() + kManualHoldMs;
      } else if (command >= 14 && command <= 17 && !moving) {
        manualCommand = 0;
        moving = true;
        stopAt = millis() + (command >= 16 ? 35 : 60);
        const float speed = 0.05f;
        const float left = (command == 14 || command == 16) ? -speed : speed;
        const float right = -left;
        Serial1.printf("$Car:%.3f,%.3f,%.3f,%.3f!", left,right,left,right);
      } else if (command >= 10 && command <= 13 && !moving) {
        manualCommand = 0;
        moving = true;
        stopAt = millis()+80;
        const float speed = command >= 12 ? 0.025f : 0.04f;
        const float left = (command == 11 || command == 12) ? -speed : speed;
        const float right = (command == 11 || command == 13) ? -speed : speed;
        Serial1.printf("$Car:%.3f,%.3f,%.3f,%.3f!", left,right,left,right);
      } else if (command >= 1 && command <= 5 && !moving) {
        manualCommand = 0;
        moving = true;
        stopAt = millis() + (command == 1 ? kPulseMs : 120);
        Serial1.print(command <= 2 ? kForward : command == 3 ? kLeft : command == 4 ? kRight : kBackward);
        Serial.printf("STEP %u: command sent\n", command);
      } else if (command == 0) {
        manualCommand = 0;
        moving = false;
        Serial1.print(kStop);
        lastStop = millis();
        setBusy(false);
        Serial.println("STOP: command sent");
      }
    }
    // Independent task: slow/incomplete communication cannot postpone this.
    if (moving && static_cast<int32_t>(millis() - stopAt) >= 0) {
      manualCommand = 0;
      moving = false;
      Serial1.print(kStop);
      lastStop = millis();
      setBusy(false);
      Serial.println("Action time limit: STOP sent");
    }
    if (moving && manualCommand && millis()-lastManualWrite >= 50) {
      const float speed = manualSpeed(manualCommand, millis()-manualStartedAt);
      const float left = (manualCommand == 7 || manualCommand == 8) ? -speed : speed;
      const float right = (manualCommand == 7 || manualCommand == 9) ? -speed : speed;
      Serial1.printf("$Car:%.3f,%.3f,%.3f,%.3f!", left, right, left, right);
      lastManualWrite = millis();
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
              (isBusy() ? "true" : "false") + ",\"pulse_ms\":250,\"step_ms\":120,\"reverse_step\":true,\"manual_hold_ms\":700,\"manual_ramp_v\":1,\"gentle_step_ms\":80,\"medium_turn_ms\":60,\"fine_turn_ms\":35,\"turn_speed\":0.05}");
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
  server.on("/manual", HTTP_POST, []() {
    const String token = server.arg("id"), direction = server.arg("direction");
    uint8_t command = direction == "forward" ? 6 : direction == "backward" ? 7 : direction == "left" ? 8 : direction == "right" ? 9 : 0;
    bool valid = token.length() == 32 && command != 0;
    for (size_t i = 0; i < token.length(); ++i) {
      char c = token[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) valid = false;
    }
    if (!valid) { requestStop(); reply(400, "bad_manual"); return; }
    if (token == lastToken) { reply(200, "duplicate_ignored"); return; }
    lastToken = token;
    setBusy(true);
    xQueueOverwrite(commands, &command);
    reply(200, "manual_queued");
  });
  server.on("/step", HTTP_POST, []() {
    const String token = server.arg("id"), direction = server.arg("direction");
    uint8_t command = direction == "forward" ? 2 : direction == "left" ? 3 : direction == "right" ? 4 : direction == "backward" ? 5 : 0;
    bool valid = token.length() == 32 && command != 0;
    for (size_t i = 0; i < token.length(); ++i) {
      char c = token[i];
      if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) valid = false;
    }
    if (!valid) { requestStop(); reply(400, "bad_step"); return; }
    if (server.arg("gentle") == "1") {
      command = direction == "forward" ? 10 : direction == "backward" ? 11 : direction == "left" ? 12 : 13;
    }
    const String turnProfile = server.arg("turn_profile");
    if (turnProfile.length()) {
      if ((direction != "left" && direction != "right") ||
          (turnProfile != "medium" && turnProfile != "fine")) {
        requestStop(); reply(400, "bad_turn_profile"); return;
      }
      command = (turnProfile == "fine" ? 16 : 14) + (direction == "right" ? 1 : 0);
    }
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
