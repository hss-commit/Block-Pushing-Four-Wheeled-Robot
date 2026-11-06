# 视觉蓝牙联动测试

适用于本项目已确认的 ESP32-WROOM-32（经典蓝牙 SPP），电脑通过蓝牙串口控制，手机继续用 USB DroidCam 提供画面。无需连接 ESP32 Wi-Fi 热点。ESP32 仍通过 D17 → 驱动板 UART RX、GND → GND 发送电机指令。

## 先烧录，再配对

1. 四轮架空，驱动板开关 OFF。先用电脑 USB 给 ESP32 供电，暂时排除独立供电的问题。
2. VS Code / PlatformIO 打开本目录 `测试用例/视觉蓝牙联动测试`，点 √ 编译、→ 上传。USB 上传端口此前是 COM3，以当前设备为准。这会替换 ESP32 上的 Wi-Fi 版程序。
3. 115200 串口监视器应显示 `ESP32-Vision-BT / pairing PIN: 1234 / Bluetooth ready`。若出现 Bluetooth failed，保留完整启动日志排查。
4. 电脑 Windows 设置 → 蓝牙和设备 → 添加设备 → 蓝牙，选择 **ESP32-Vision-BT**；若要求 PIN，输入 **1234**。本版仅供当前单车测试，设备名和 PIN 固定。不要用手机占用该蓝牙连接。
5. 在 Windows 的“更多蓝牙设置 → COM 端口”中，找到 ESP32-Vision-BT 的**传出**端口；必要时点添加，选择传出并指定该设备的串行服务。也可在设备管理器的“端口”中核对。蓝牙端口号由 Windows 分配，**不要把 USB 上传用的 COM3 当作蓝牙端口**。
6. 回到项目根目录双击 **检查蓝牙连接.cmd**，输入蓝牙传出端口，例如 COM7。它只检查协议并发送停止，不会主动转动车轮。程序会列出当前端口供核对；列表本身不保证设备已配对或可连接。

当前 USB 供电能开 Wi-Fi、原独立供电不能的原因尚未查明。蓝牙程序不等于修好了供电；先在 USB 供电下验连接，再用可靠的 USB 电源测试脱离电脑后的运行。驱动板 UART 5V 给 ESP32 供电的能力尚未确认，勿据此直接改接供电；12V 电池不能直接接 ESP32。

## 视觉和动作

1. 检查连接通过后关闭检查窗口；手机 USB DroidCam 连电脑，镜头完整看到四轮。打开驱动板，保持四轮架空。
2. 双击 **启动视觉蓝牙联动测试.cmd**，输入相同蓝牙传出端口。
3. N/P 切换画面，识别出绿色车头箭头、稳定后显示 READY。按一次空格，发送一次约250ms低速直行；X停止，R准备下一轮，Esc退出。方向和停车可靠后才做低速落地测试。
4. 再使用 **启动视觉蓝牙自动接近测试.cmd**：四角标定、点击方块取色，READY后按空格启动一次接近。方向动作约120ms，到接近点停止。流程和限制见 [自动接近测试说明](../../control/自动接近测试说明.md)。

命令行（从项目根目录执行）：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m control.bluetooth_link --port COM7
.\.venv\Scripts\python.exe -X utf8 control/vision_wifi_test.py --bluetooth-port COM7
.\.venv\Scripts\python.exe -X utf8 control/vision_approach_test.py --bluetooth-port COM7
```

`--camera 1` 可指定摄像头；`--dry-run` 仅显示识别，不打开蓝牙串口。不要同时运行检查程序、视觉程序或其他串口终端占用同一蓝牙端口。超时会结束测试，不自动重试运动；保持观察，按需关闭驱动板。

## 实现及验证边界

蓝牙版与原 Wi-Fi 版通过 `control/esp32_vision_firmware.h` 共用电机任务；`control/esp32_vision_bluetooth.h` 实现蓝牙协议。工程依赖这些项目内文件，不要只拷贝本文件夹单独使用。

每行请求为 `32位小写十六进制id /status`、`id /stop`，或 `id /pulse - 到期毫秒`、`id /step forward|left|right 到期毫秒`；JSON 回复使用 `vision-bt-v1` 并带回相同id。电脑先读取设备时间，为运动设置200ms有效期，车端拒绝无效或过期动作。相同最后运动id不重复执行；电脑不重试运动请求。过长、非法或未及时结束的请求触发停止，蓝牙连接断开被检测到时请求停止。

电机独立任务在约250ms/120ms后发送停止，空闲重复发送零速度，存在调度和机械制动延迟。这些回执只能证明ESP32接受了请求，不能证明驱动板实际执行、轮子方向或停车距离正确。未接编码器/驱动板回读；不代表完成自主推块。

2026-11-03：蓝牙版及原 Wi-Fi 版均已通过 PlatformIO 编译。`control/test_bluetooth_link.py` 使用模拟串口检查分段回复、错误序号、握手/停止、方向、过期时间回绕、拒绝/超时不重试、关闭端口；既有视觉触发和自动接近软件测试通过。尚未烧录蓝牙版、实际配对或实车验证。模拟串口检查不能代替蓝牙链路延迟和车端运行验证。

参考：[Espressif BluetoothSerial 文档](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/bluetooth.html)、[Windows 蓝牙配对](https://support.microsoft.com/en-gb/windows/hardware/bluetooth/pair-a-bluetooth-device-in-windows)。本项目沿用本机已安装的 Arduino-ESP32 2.0.17 工具链及其配对 API。
