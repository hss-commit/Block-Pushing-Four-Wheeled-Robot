@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 "运行软件检查.py"
set "robot_check_result=%errorlevel%"
pause
exit /b %robot_check_result%
