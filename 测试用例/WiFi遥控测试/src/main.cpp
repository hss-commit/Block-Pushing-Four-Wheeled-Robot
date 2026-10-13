#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>

// 沿用串口试转工程的接线：D17 -> 驱动板 UART RX，两板 GND 相连。
constexpr int motorTxPin = 17;
constexpr unsigned long runMs = 1000;
constexpr char apName[] = "ESP32-Car-Test";
constexpr char apPassword[] = "esp32car123";
constexpr char motorTypeCommand[] = "$MOTOR_4CH_SET:0!"; // 0 = 520 电机
constexpr char stopCommand[] = "$Car:0,0,0,0!";

WebServer server(80);
bool moving = false;
unsigned long stopAt = 0;

const char page[] = R"HTML(
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESP32 小车测试</title>
<style>
body{font-family:Arial,sans-serif;max-width:400px;margin:30px auto;padding:16px;text-align:center}
button{font-size:22px;width:100%;padding:16px;margin:7px 0;border:0;border-radius:10px;background:#2065ba;color:white}
button.stop{background:#bc3030}p{color:#555}
</style></head><body><h1>小车 Wi-Fi 测试</h1>
<p>先让车轮悬空。每按一次，动作持续 1 秒后自动停止。</p>
<form action="/move" method="post">
<button name="direction" value="forward">前进</button>
<button name="direction" value="backward">后退</button>
<button name="direction" value="left">左转</button>
<button name="direction" value="right">右转</button>
<button class="stop" name="direction" value="stop">立即停止</button>
</form></body></html>
)HTML";

void stopMotors() {
  Serial1.print(stopCommand);
  moving = false;
}

void handleMove() {
  const String direction = server.arg("direction");
  const char *command = nullptr;

  if (direction == "forward") command = "$Car:0.3,0.3,0.3,0.3!";
  else if (direction == "backward") command = "$Car:-0.3,-0.3,-0.3,-0.3!";
  else if (direction == "left") command = "$Car:0,0.3,0,0.3!";   // A/C 左，B/D 右
  else if (direction == "right") command = "$Car:0.3,0,0.3,0!";
  else if (direction != "stop") {
    server.send(400, "text/plain", "Unknown direction");
    return;
  }

  stopMotors();
  if (command != nullptr) {
    Serial1.print(motorTypeCommand);
    delay(100);
    Serial1.print(command);
    moving = true;
    stopAt = millis() + runMs;
  }
  Serial.print("网页指令: ");
  Serial.println(direction);
  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "");
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200, SERIAL_8N1, -1, motorTxPin);
  delay(300);
  Serial1.print(motorTypeCommand);
  delay(100);
  stopMotors();

  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP(apName, apPassword)) {
    Serial.println("Wi-Fi 热点启动失败");
    return;
  }
  server.on("/", HTTP_GET, []() { server.send(200, "text/html; charset=utf-8", page); });
  server.on("/move", HTTP_POST, handleMove);
  server.begin();
  Serial.print("连接热点 ESP32-Car-Test，浏览器打开 http://");
  Serial.println(WiFi.softAPIP());
}

void loop() {
  server.handleClient();
  if (moving && static_cast<int32_t>(millis() - stopAt) >= 0) {
    stopMotors();
    Serial.println("1 秒已到，发送停止命令");
  }
}
