# 手机热点联动测试

连接关系：电脑 ↔ 手机热点 ↔ ESP32。ESP32使用Wi-Fi STA模式连接手机，电脑通过ESP32获得的局域网IP发送HTTP指令；手机仍用USB DroidCam提供画面。本版复用原联动固件的250ms直行、120ms方向动作和独立限时停车任务。

## 操作顺序

**2026-11-03 实连更新：** 本机已按MAC `10:52:1c:1e:e4:f4` 找到当前ESP32 IP `10.112.135.116`，实际GET `/status` 返回ready，手机热点允许本次电脑与ESP32互访。但5次状态查询耗时203～531ms，超过电脑端原有180ms超时。STA源码现加入 `WiFi.setSleep(false)` 并编译通过，以尝试减少默认省电引起的接收等待；关闭省电会增加耗电，依据见 [官方说明](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/wifi-driver/wifi-performance-and-power-save.html)。尚未上传此改动或验证延迟改善。原超时及车端动作限时保持不变；重新上传后先查询状态并测延迟，再做动作测试。此IP仅是本次热点分配值，不保证重连后仍相同。

1. 在手机上设置热点：名称 **Robot-Test**，密码 **esp32car123**，频段 **2.4GHz**，若可选安全模式则用WPA2兼容模式。iPhone可打开“最大兼容性”。保持热点开启。
2. 四轮架空，驱动板先关闭。ESP32先用电脑USB供电，先断开VIN外部供电线，避免两路电源同时接入。独立供电问题尚未查明，换网络不能证明已修复供电/启动故障。
3. 在VS Code / PlatformIO中打开本目录 `测试用例/手机热点联动测试`，点√编译、→上传。它会替换蓝牙或诊断固件。
4. 打开115200串口监视器，必要时按EN复位。应显示 `Connecting to phone hotspot: Robot-Test`，连上后显示 `Phone hotspot connected / car address: http://...`。记下**实际显示的IP地址**，不要沿用旧热点地址。也可在手机热点的已连接设备中找ESP32的地址。
5. 电脑Wi-Fi也连接 **Robot-Test**。在电脑浏览器打开 `http://实际IP/status`；例如串口打印192.168.43.123，就打开 `http://192.168.43.123/status`（示例地址不能照抄）。应返回包含 `vision-pulse-v1`、`ready`、`pulse_ms:250` 和 `step_ms:120` 的JSON。此GET只查询状态，不发运动指令。只有加入同一热点且设备之间能互相访问，才算联通；如果串口已连上但电脑无法访问，核对IP、电脑所连热点及热点设备间访问限制。
6. 关闭串口监视器，手机USB DroidCam画面正常后，打开驱动板并保持四轮架空。双击根目录 **启动手机热点联动测试.cmd**，输入上一步的IP（只输入数字和点）。出现摄像头画面后N/P选择手机镜头，READY后按一次空格，观察约250ms低速前进和停车；X停止，R重新准备，Esc退出。
7. 架空方向与停车确认后，再用 **启动手机热点自动接近测试.cmd**，输入同一IP，按 [自动接近说明](../../control/自动接近测试说明.md) 做标定、取色和单目标接近。到接近点停止，不推块。

若不想修改现有手机热点，可编辑 `control/esp32_hotspot_config.h` 中的名称和密码后重新编译、上传。默认值是测试用公开凭据；不要在共享仓库提交私人热点密码。

## 连接与停车

断开手机热点被车端检测到时会请求停止并关闭HTTP服务，恢复连接后重新提供HTTP服务并打印地址；未连接时每10秒尝试重连。短动作时限由独立电机任务执行，不依赖连接恢复。电脑通信出错会退出，车端恢复网络后不会自动恢复之前的运动；重新启动电脑测试程序并再次按空格授权。

手机热点重新打开后可能分配不同IP，重新查看地址并输入启动脚本。联动请求不经过互联网代理，局域网通信不需要公网服务器。手机能否在当前配置下允许客户端互访，以 `/status` 实测为准。

本工程与其他联动工程共用 `control/esp32_vision_firmware.h`，不要只复制本文件夹单独使用。D17→驱动板RX、GND共地的信号接线沿用原记录。

2026-11-03：本固件已通过PlatformIO编译；既有视觉触发/自动接近与本机HTTP测试通过；两个CMD入口已由真实cmd.exe验证可到达IP输入提示，并保持CRLF格式。尚未烧录或连接真实手机热点，未验证掉线、重连或实车动作；编译及本机HTTP测试不能代替这些硬件验证。

参考：[Espressif Wi-Fi STA API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html)、[ESP32-WROOM-32频段规格](https://documentation.espressif.com/esp32-wroom-32_datasheet_en.html)、[iPhone最大兼容性](https://support.apple.com/en-ca/guide/security/secfd166f620/web)。
