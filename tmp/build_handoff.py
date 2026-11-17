from pathlib import Path
import shutil, json, zipfile

root = Path(__file__).resolve().parents[1]
out = root / 'output' / 'robot_debug_minimal_20261117'
out.mkdir(parents=True, exist_ok=True)
files = {
 'control': ['launcher.py','keyboard_remote.py','vision_wifi_test.py','vision_approach_test.py','approach_control.py','single_push_control.py','multi_push_control.py','straight_push_control.py','bluetooth_link.py'],
 'vision': ['photo_vision.py','robot_vision.py','latest_camera.py','robot_marker.json','generate_robot_marker.py'],
 'strategy': ['planner.py','runtime.py','scene_priority.py','config.json'],
}
for folder, names in files.items():
    (out/folder).mkdir(exist_ok=True)
    for name in names: shutil.copy2(root/folder/name, out/folder/name)
def write(name, text):
    path=out/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8')
write('control/launcher.local.json',json.dumps({'ip':'192.168.4.1','camera':0,'mode':'2'},indent=2))
write('requirements.txt','opencv-python==5.0.0.93\nnumpy==2.5.3\npyserial==3.5\n')
write('01_install.cmd','''@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -X utf8 check_environment.py
if errorlevel 1 goto fail
echo Installation complete. Run 02_start.cmd.
pause
exit /b 0
:fail
echo FAILED. Install Python 3.12 x64 with Python Launcher, check network, then retry.
pause
exit /b 1
''')
write('02_start.cmd','''@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
echo Run 01_install.cmd first.
pause
exit /b 1
)
".venv\Scripts\python.exe" -X utf8 control\launcher.py
pause
''')
write('check_environment.py','''"""Offline import/config check: no camera access or motor commands."""
import importlib
from pathlib import Path
import cv2, numpy, serial
from strategy.planner import Config
from vision.robot_vision import load_config
for name in ('control.launcher','control.keyboard_remote','control.vision_wifi_test',
             'control.vision_approach_test','control.bluetooth_link','vision.photo_vision'):
    importlib.import_module(name)
Config.load(Path(__file__).parent/'strategy'/'config.json')
load_config()
dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
assert cv2.aruco.generateImageMarker(dictionary,0,100).shape==(100,100)
assert hasattr(cv2,'imshow')
print('PASS: imports, configuration, ArUco generation. Camera/network/car NOT tested.')
print('OpenCV',cv2.__version__,'NumPy',numpy.__version__,'pyserial',serial.__version__)
''')
for name in ['esp32_vision_firmware.h','manual_ramp.h']:
    (out/'firmware/src').mkdir(parents=True,exist_ok=True)
    shutil.copy2(root/'control'/name,out/'firmware/src'/name)
write('firmware/src/main.cpp','#include "esp32_vision_firmware.h"\n')
write('firmware/src/esp32_hotspot_config.h','''#pragma once
// Set these to your actual phone hotspot before uploading.
constexpr char kPhoneHotspotSsid[] = "CHANGE_ME_SSID";
constexpr char kPhoneHotspotPassword[] = "CHANGE_ME_PASSWORD";
''')
write('firmware/platformio.ini','''[env:esp32dev]
platform = espressif32@7.1.3
board = esp32dev
framework = arduino
monitor_speed = 115200
build_flags = -DVISION_WIFI_STA
''')
write('README.md','''# 小车调试交接：精简运行版

代码快照：2026-11-17。本包用于 Windows 10/11 + Python 3.12（64位）。核心 Python 与控制固件逻辑直接复制当前工作区；没有为缩短代码改写控制算法。保留菜单1～7及其依赖；移除报告、视频、历史实验、日志、虚拟环境、编译缓存和整套测试。蓝牙兼容文件是现有入口的可选依赖，日常按 Wi-Fi 使用即可。

## 先跑起来

1. 把整个压缩包解压到可写目录，例如 `D:\\robot_debug`；不要只复制一个 Python 文件，也不要直接在压缩包内启动。
2. 安装 Python 3.12 64位，并勾选 Python Launcher。双击 `01_install.cmd`，联网安装本机验证过的三项依赖；看到 PASS 和 Installation complete 后继续。首次需要联网，包内不带 Python 安装程序和依赖安装包。
3. 双击 `02_start.cmd`。先选 `S`，填写实际小车 IP、摄像头编号。包里的 `192.168.4.1` 仅为占位，手机热点下通常不是这个地址；不要照抄原电脑的 IP。默认模式2、相机0。
4. 先选 **2，只看视觉**。可用 USB 摄像头；使用手机摄像头则先安装并连接 DroidCam 客户端，确认电脑能看到画面。编号通常从0开始尝试，关闭其他占用相机的程序。
5. 电脑和 ESP32 加入同一个 2.4 GHz 手机热点。从 ESP32 串口监视器（115200）读取 `car address: http://...`，填入 S。浏览器打开该地址的 `/status` 应返回 JSON；这个操作不发运动命令。IP 重新联网后可能变化。

安装报错请保留终端错误。不要在同一个环境混装 headless 版本 OpenCV，它不提供本程序需要的窗口界面。本包的 `.venv` 由组员在自己电脑上创建，不依赖原电脑路径。

## 菜单怎么用

| 菜单 | 用途 | 启动方式 |
|---|---|---|
| 2 | 视觉识别，不控制车 | 优先调通相机、四角、取色、定位 |
| 5 | 键盘遥控 | 点击遥控窗口，CONNECTED后按住WASD/方向键，松开停车；空格/X停车 |
| 7 | 手动摆正后单块直推入黄区 | READY后空格开始，X停车 |
| 6 | 多块逐个入黄区 | 空格提交启动请求，条件就绪后执行；X取消并停车 |
| 1 | 单块推移默认100mm | 标定、取色、稳定后倒计时3秒自动运动 |
| 3 | 视觉短动作通信测试 | 空格触发 |
| 4 | 自动接近目标 | 进阶联调，先确认左右转向 |

建议顺序：2 → 5 → 7 → 6。菜单1会自动倒计时运动，不是等待空格。实车自动测试按 X 停车，Esc 退出。模式6准备阶段空格会记住启动请求；需要取消时按X，不能以“暂时没动”认为没有启动请求。R重新准备/重连，之后重新请求启动。

## 视觉设置（换电脑/相机后必须核对）

- 标定选四个真实场地内角，顺序左上、右上、右下、左下，Enter确认；展开后黄色目标区在下方。点击一个方块中心取色，确认每块被单独识别。
- 场地物理尺度沿用1200mm；实际场地不一致时需要核对 `strategy/config.json` 以及视觉/控制中的尺度假设，不能仅把相机画面当毫米。
- 车顶使用 `DICT_4X4_50`、ID 0，黑色码边长50mm。需要重新打印时运行 `.venv\\Scripts\\python.exe vision\\generate_robot_marker.py`，打开生成的 `vision/markers/打印我方定位码.html`，按100%打印并实测尺寸。
- 菜单 M 设置码尺寸、完整车体外廓和码偏移。当前快照长180mm、宽210mm，是11月17日为了覆盖车尾/推板的试调值，不是重新实测的尺寸；必须对照实物检查。偏移仍为0。
- 模式6先摆2～3个分散块，车远离场地边缘；检查车轮/车尾没有被当成方块。当前版本已取消大框尺寸停止阈值，大框会按中心跟踪，所以粘连块仍需人工排查。

## ESP32 固件（已有匹配固件时不必重烧）

`firmware/` 是独立 PlatformIO 工程。用 VS Code + PlatformIO 打开该目录。修改 `src/esp32_hotspot_config.h` 中热点名称和密码，再 Build / Upload，串口监视器115200查看IP。首次需联网下载工具链。此包不包含个人热点密码。

本工程适配现有 ESP32 + UART 四轮驱动板，GPIO17发送 `$Car:a,b,c,d!`，不是直接给电机驱动芯片写PWM的通用程序。沿用现有接线和驱动板协议，不要把本固件直接套到另一种底盘。

通信协议 `vision-pulse-v1`；状态回执应含 `pulse_ms:250`、`step_ms:120`。连续遥控需要 `manual_hold_ms:700`、`manual_ramp_v:1`；模式6需要 `gentle_step_ms:80`。能力缺失时更新匹配固件，不要删掉检查强行运行。固件保留限时动作、断续期停车及低速转向渐进加速。

## 哪些代码必须一起给

| 目录/文件 | 作用 |
|---|---|
| control/launcher.py | 菜单、IP/相机/尺寸设置 |
| control/vision_approach_test.py | 视觉与动作的主循环，接近、单块、多块、直推入口 |
| control/*_control.py | 各模式控制逻辑；被主循环导入，不能只留一个 |
| control/vision_wifi_test.py | HTTP通信及短动作入口，遥控与自动模式共同依赖 |
| control/keyboard_remote.py | 键盘遥控 |
| vision/ | 识别、最新相机帧、车顶码、外廓过滤及尺寸配置 |
| strategy/ | 规划、运行时、识别结果排序和配置；视觉模式也会导入 |
| firmware/ | 可选重烧的匹配车端代码 |
| requirements.txt、两个cmd | 在新电脑建立环境并启动 |

## 调试回传与当前边界

故障时提供：运行菜单编号、终端错误、画面截图，以及 `vision/results/` 下本次时间目录。视觉控制中 S 可保存现场；模式6日志为 `multi-push-时间/events.jsonl`。先看停止原因再改算法：常见为IP/状态超时、相机编号不对、车体靠边、场地几何无效、定位码丢失、方块匹配歧义。

本包可以安装并启动软件；实车运行仍需要摄像头、匹配固件、同网连接、正确标定和实际底盘。软件模拟通过不等于实车成功；当前不能把多块实车连续入区当成已验收。打包过程中不连接小车、不发送运动命令。

无需硬件的环境检查：`.venv\\Scripts\\python.exe check_environment.py`。此检查覆盖模块导入、配置读取及ArUco生成，不代替相机、网络、车体动作验收。
''')
print(out)
