#include <Arduino.h>

// ESP32 D17 (TX) -> 驱动板 UART RX；两块板的 GND 相连。
constexpr int motorTxPin = 17;
constexpr char stopCommand[] = "$Car:0,0,0,0!";
constexpr char straightCommand[] = "$Car:0.3,0.3,0.3,0.3!";
constexpr char leftTurnCommand[] = "$Car:0,0.3,0,0.3!"; // A/C 左，B/D 右
constexpr const char *runCommands[6] = {
    "$Car:0.1,0,0,0!",
    "$Car:0,0.1,0,0!",
    "$Car:0,0,0.1,0!",
    "$Car:0,0,0,0.1!",
    "$Car:0.5,0.5,0,0!",
    straightCommand,
};

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200, SERIAL_8N1, -1, motorTxPin);
  delay(300);
  Serial1.print("$MOTOR_4CH_SET:0!"); // 0 = 520 电机
  delay(100);
  Serial1.print(stopCommand);
  Serial.println("1-4 单路，5 A+B，6 四路，7 固定动作，8 A路串口诊断，9 单独左转；车轮先悬空。");
}

void loop() {
  if (!Serial.available()) return;

  const char input = Serial.read();
  if (input < '1' || input > '9') return;

  if (input == '8') {
    // 按厂家示例只设置类型、给 A 路速度、再停止；避开常规指令前置的停止命令。
    Serial1.print("$MOTOR_4CH_SET:0!");
    Serial1.flush();
    delay(300);
    Serial1.print("$Car:0.1,0,0,0!");
    Serial1.flush();
    Serial.println("诊断命令已发出：A 路低速试转 1 秒");
    delay(1000);
    Serial1.print(stopCommand);
    Serial.println("已发送停止命令");
    return;
  }

  Serial1.print(stopCommand);
  Serial1.print("$MOTOR_4CH_SET:0!");
  delay(100);
  if (input == '7' || input == '9') {
    if (input == '7') {
      Serial1.print(straightCommand);
      Serial.println("四路以 0.3 直走 1 秒");
      delay(1000);
    }
    Serial1.print(leftTurnCommand);
    Serial.println("左侧 A/C 停止，右侧 B/D 以 0.3 左转 1 秒");
    delay(1000);
    Serial1.print(stopCommand);
    Serial.println("已发送停止命令");
    return;
  }
  Serial1.print(runCommands[input - '1']);
  if (input == '5') {
    Serial.println("A+B 两台电机同时较高速试转 2 秒");
  } else if (input == '6') {
    Serial.println("A+B+C+D 四台电机同时以 0.3 试转 1 秒");
  } else {
    Serial.print("电机接口 ");
    Serial.print(input);
    Serial.println(" 低速试转 1 秒");
  }
  delay(input == '5' ? 2000 : 1000);
  Serial1.print(stopCommand);
  Serial.println("已发送停止命令");
}
