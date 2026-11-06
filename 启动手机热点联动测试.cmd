@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "robot_car_ip="
set /p "robot_car_ip=输入串口显示的ESP32 IP地址（仅数字和点，不加http://）："
if not defined robot_car_ip exit /b 1
".venv\Scripts\python.exe" -X utf8 "control\vision_wifi_test.py" --host "http://%robot_car_ip%" %*
if errorlevel 1 pause
