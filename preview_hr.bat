@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if exist .env (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

echo ========================================
echo   HR 戰略快報 — 預覽模式
echo ========================================
echo.

set DRY_RUN=true
python hr_main.py

echo.
pause
