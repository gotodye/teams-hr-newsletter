@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Sending HR newsletter test to Teams...
python send_hr_test_now.py
if errorlevel 1 (
  echo.
  echo Failed. Try: py send_hr_test_now.py
  py send_hr_test_now.py
)
pause
