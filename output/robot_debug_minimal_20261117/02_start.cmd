@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
echo Run 01_install.cmd first.
pause
exit /b 1
)
".venv\Scripts\python.exe" -X utf8 control\launcher.py
pause
