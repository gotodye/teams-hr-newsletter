@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo   teams-hr-newsletter — GitHub 部署
echo ========================================
echo.

where gh >nul 2>&1
if errorlevel 1 (
  echo 請先安裝 GitHub CLI: winget install GitHub.cli
  echo 然後執行: gh auth login
  pause
  exit /b 1
)

if not exist .git (
  echo Initializing git...
  git init
  git branch -M main
)

git add -A
git status

echo.
set /p CONFIRM=Commit and push to gotodye/teams-hr-newsletter? (y/n):
if /i not "%CONFIRM%"=="y" exit /b 0

git commit -m "Initial HR strategic newsletter project (split from teams-morning-bot)"

gh repo view gotodye/teams-hr-newsletter >nul 2>&1
if errorlevel 1 (
  echo Creating GitHub repo...
  gh repo create gotodye/teams-hr-newsletter --public --source=. --remote=origin --push
) else (
  git remote remove origin 2>nul
  git remote add origin https://github.com/gotodye/teams-hr-newsletter.git
  git push -u origin main
)

echo.
echo Done. Set GitHub Secrets:
echo   HR_TEAMS_WEBHOOK_URL
echo   OPENAI_API_KEY
echo   HR_TEAMS_WEBHOOK_URL_EXTRA (optional)
pause
