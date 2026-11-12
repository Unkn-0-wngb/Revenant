@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import torch, matplotlib, tensorboard, psutil, joblib, lzo, PIL" 2>nul && goto run
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
    echo Setup failed, see the messages above.
    pause
    exit /b 1
)
:run
start "" "venv\Scripts\pythonw.exe" "%~dp0dashboard.py"
