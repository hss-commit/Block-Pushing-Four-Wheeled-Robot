# 无线最小诊断

用途：区别视觉/电机程序的问题与开发板、电源、启动状态的问题。程序不初始化电机UART，也不发送任何运动指令。先关闭驱动板，核对ESP32供电，避免同时使用VIN和USB两路供电。

## 建议先测Wi-Fi

1. PlatformIO打开本目录，默认环境为 **wifi**，编译、上传。它会替换ESP32上的蓝牙联动程序。
2. ESP32由电脑USB供电时，在手机Wi-Fi列表中搜索 **ESP32-DIAG**。不需要连接互联网，也不用打开视觉程序。
3. 断电并拔掉USB，改用原来的VIN独立供电，再用同一部手机搜索这个热点。
4. 如果电脑USB能搜到、VIN不能搜到，说明移除视觉、蓝牙和电机程序后故障仍存在，重点查原供电路径、启动/复位电路或板子；不能只凭此区分是哪一个。
5. 如果两种供电都能搜到，原联动程序的初始化、资源或与驱动板连接的交互仍需排查。这个结果不能证明所有负载下供电都稳定。

同一供电条件下，另可断电后拔掉D17信号线再试，以排除驱动板信号线的影响。每轮只改变一个条件，记录是否能搜到热点。

## 需要蓝牙对照时

在PlatformIO左侧 Project Tasks → **bluetooth** 中选择 Build / Upload。它只启动 **ESP32-BT-DIAG**（PIN 1234），并把收到的蓝牙串口字节原样回传，与官方SerialToSerialBT的通信行为相同。默认wifi环境仍是Wi-Fi单独测试，**两种无线不会同时开启**。

蓝牙仍使用同一块板的蓝牙地址；Windows可能保留旧名称。只在确需测试时移除旧配对后重新搜索。Windows里已记住的设备条目不能证明当前正在广播。原来的 `检查蓝牙连接.cmd` 期望联动JSON协议，不适用于这个原样回传诊断固件；蓝牙回传应使用串口终端验证。

115200串口日志记录 `DIAG: boot`、`WiFi AP READY/FAILED` 或 `Bluetooth READY/FAILED`，以及每秒一次uptime/free_heap。周期性重现boot、uptime反复归零表示在重启。通过板载USB读日志会改变供电/复位条件，不能将这种日志冒充VIN独立运行日志。独立运行日志需外置3.3V逻辑USB转串口仅接GND和ESP32 TX0→适配器RX，不接供电、DTR和RTS；没有对应工具时先做热点对照，不盲目接线。

退出诊断后，重新上传 `测试用例/视觉蓝牙联动测试` 才能运行原来的视觉控制。

参考官方例程：[WiFiAccessPoint](https://github.com/espressif/arduino-esp32/tree/2.0.17/libraries/WiFi/examples/WiFiAccessPoint)、[SerialToSerialBT](https://github.com/espressif/arduino-esp32/blob/2.0.17/libraries/BluetoothSerial/examples/SerialToSerialBT/SerialToSerialBT.ino)。本工程为诊断改编版，编译通过不等于独立供电已修好。
