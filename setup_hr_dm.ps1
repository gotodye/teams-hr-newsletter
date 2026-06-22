#Requires -Version 5.1
<#
.SYNOPSIS
  一鍵設定 HR 快報「發給自己」的 Power Automate Webhook，並寫入 .env
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectRoot ".env"
$DocUrl = "https://make.powerautomate.com/create"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  HR 快報 — 發給自己（Teams 私訊）設定" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "即將開啟 Power Automate，請依序操作：" -ForegroundColor Yellow
Write-Host ""
Write-Host "  1. 若跳出登入視窗 → 使用公司 Microsoft 帳號登入" -ForegroundColor White
Write-Host "  2. 點選「Instant cloud flow / 即時雲端流程」" -ForegroundColor White
Write-Host "  3. 流程名稱：HR Newsletter Test to Me" -ForegroundColor White
Write-Host "  4. 觸發程序搜尋並選：When a Teams webhook request is received" -ForegroundColor White
Write-Host "  5. 建立後 → + New step → Microsoft Teams" -ForegroundColor White
Write-Host "  6. 動作：Post adaptive card in a chat or channel" -ForegroundColor White
Write-Host "  7. Post as: Flow bot | Post in: Chat | Recipient: 你自己 (Angus)" -ForegroundColor White
Write-Host "  8. Adaptive Card: @{triggerBody()?['card']}" -ForegroundColor Green
Write-Host "  9. Save → 複製 HTTP POST URL" -ForegroundColor White
Write-Host ""

Start-Process $DocUrl

Read-Host "完成上述步驟後，請將 Webhook URL 貼到下方並按 Enter"

$webhookUrl = Read-Host "HR_TEAMS_WEBHOOK_URL"
$webhookUrl = $webhookUrl.Trim()

if (-not $webhookUrl.StartsWith("https://")) {
    Write-Host "錯誤：URL 必須以 https:// 開頭" -ForegroundColor Red
    exit 1
}

$envLines = @()
if (Test-Path $EnvFile) {
    $envLines = Get-Content $EnvFile -Encoding UTF8
    $found = $false
    for ($i = 0; $i -lt $envLines.Count; $i++) {
        if ($envLines[$i] -match '^\s*HR_TEAMS_WEBHOOK_URL\s*=') {
            $envLines[$i] = "HR_TEAMS_WEBHOOK_URL=$webhookUrl"
            $found = $true
            break
        }
    }
    if (-not $found) {
        $envLines += ""
        $envLines += "# HR 快報 — Power Automate 私訊 Webhook"
        $envLines += "HR_TEAMS_WEBHOOK_URL=$webhookUrl"
    }
} else {
    $envLines = @(
        "# HR 戰略快報 — 本機設定檔",
        "HR_TEAMS_WEBHOOK_URL=$webhookUrl"
    )
}

$envLines | Set-Content $EnvFile -Encoding UTF8
Write-Host ""
Write-Host "已寫入 $EnvFile" -ForegroundColor Green
Write-Host ""

$runTest = Read-Host "是否立即測試發送？(y/n)"
if ($runTest -eq 'y' -or $runTest -eq 'Y') {
    if (-not $env:OPENAI_API_KEY) {
        $key = Read-Host "請輸入 OPENAI_API_KEY（測試生成快報用）"
        if ($key) { $env:OPENAI_API_KEY = $key.Trim() }
    }
    if (-not $env:OPENAI_API_KEY) {
        Write-Host "未設定 OPENAI_API_KEY，跳過測試。可稍後執行: python hr_main.py" -ForegroundColor Yellow
    } else {
        Push-Location $ProjectRoot
        python hr_main.py
        Pop-Location
        Write-Host ""
        Write-Host "請檢查 Teams 私訊是否收到 HR 快報！" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "部署到 GitHub 時，請將相同 URL 設為 Secret: HR_TEAMS_WEBHOOK_URL" -ForegroundColor Yellow
Write-Host "詳細說明: docs\hr_teams_dm_setup.md" -ForegroundColor Gray
Write-Host ""
