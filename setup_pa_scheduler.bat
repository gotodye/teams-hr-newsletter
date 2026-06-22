@echo off
chcp 65001 >nul
echo.
echo  HR 快報 — Power Automate 06:00 排程設定說明
echo.
echo  完整教學: docs\hr_pa_scheduler_setup.md
echo.
start https://make.powerautomate.com/create
start notepad "%~dp0docs\hr_pa_scheduler_setup.md"
echo.
echo  請在 Power Automate 建立「排程雲端流程」:
echo    名稱: HR Newsletter Scheduler 06:00
echo    時間: 每天 06:00 (UTC+8 Taipei)
echo    動作: HTTP POST -^> GitHub repository_dispatch
echo.
pause
