@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\pythonw.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
    if errorlevel 1 (
        echo Setup failed, see the messages above.
        pause
        exit /b 1
    )
)
start "" "venv\Scripts\pythonw.exe" "%~dp0dashboard.py"
