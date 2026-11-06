@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 -m control.bluetooth_link
set /p "robot_bt_port=输入 ESP32-Vision-BT 的传出端口（例如 COM7）："
if not defined robot_bt_port exit /b 1
".venv\Scripts\python.exe" -X utf8 -m control.bluetooth_link --port "%robot_bt_port%"
pause
