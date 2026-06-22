#Requires -Version 5.1
# One-time setup: add Winnie's Power Automate webhook to .env

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectRoot ".env"

Write-Host ""
Write-Host "=== HR Newsletter: Add Winnie as recipient ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Winnie needs her OWN Power Automate flow (or a 2nd Post card step)."
Write-Host "Steps in make.powerautomate.com:"
Write-Host "  1. My flows -> HR Newsletter Test to Me -> ... -> Copy"
Write-Host "  2. Rename copy to: HR Newsletter to Winnie"
Write-Host "  3. Post card -> Recipient: ONLY winnie@eui.money"
Write-Host "  4. Trigger: Anyone -> Save"
Write-Host "  5. Copy HTTP URL from trigger (must include sig=)"
Write-Host ""

$winnieUrl = Read-Host "Paste Winnie flow HTTP URL"
if (-not $winnieUrl) {
    Write-Host "Cancelled." -ForegroundColor Yellow
    exit 1
}
if ($winnieUrl -notmatch "sig=") {
    Write-Host "WARN: URL missing sig= - may not work." -ForegroundColor Yellow
}

if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: .env not found" -ForegroundColor Red
    exit 1
}

$lines = Get-Content $EnvFile -Encoding UTF8
$updated = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*HR_TEAMS_WEBHOOK_URL_EXTRA\s*=') {
        $lines[$i] = "HR_TEAMS_WEBHOOK_URL_EXTRA=$winnieUrl"
        $updated = $true
        break
    }
}
if (-not $updated) {
    $lines += ""
    $lines += "# Winnie HR newsletter webhook"
    $lines += "HR_TEAMS_WEBHOOK_URL_EXTRA=$winnieUrl"
}

Set-Content -Path $EnvFile -Value $lines -Encoding UTF8
Write-Host ""
Write-Host "Saved HR_TEAMS_WEBHOOK_URL_EXTRA" -ForegroundColor Green
Write-Host "Test: python send_hr_test_now.py" -ForegroundColor Green
