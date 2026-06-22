@echo off
chcp 65001 >nul
cd /d "%~dp0"
python test_hr_webhook.py
if errorlevel 1 (
  echo.
  echo Python failed, trying PowerShell fallback...
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_hr_webhook.ps1"
)
pause
