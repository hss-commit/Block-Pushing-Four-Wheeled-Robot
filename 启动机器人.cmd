@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo 未找到项目运行环境，请保留本文件与项目文件夹的位置关系。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -X utf8 "control\launcher.py"
if errorlevel 1 pause
