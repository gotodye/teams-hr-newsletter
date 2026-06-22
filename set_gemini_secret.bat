@echo off
chcp 65001 >nul
echo Set GEMINI_API_KEY on gotodye/teams-hr-newsletter
echo.
set /p KEY=Paste Gemini API key:
if "%KEY%"=="" (
  echo Cancelled.
  pause
  exit /b 1
)
"C:\Program Files\GitHub CLI\gh.exe" secret set GEMINI_API_KEY --body "%KEY%" --repo gotodye/teams-hr-newsletter
if errorlevel 1 (
  echo Failed. Run: gh auth login
) else (
  echo OK - GEMINI_API_KEY set on teams-hr-newsletter
)
pause
