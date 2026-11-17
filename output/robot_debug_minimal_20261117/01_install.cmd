@echo off
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
