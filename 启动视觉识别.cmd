@echo off
chcp 65001 >nul
cd /d "%~dp0"
".venv\Scripts\python.exe" -X utf8 "vision\photo_vision.py" %*
if errorlevel 1 pause
