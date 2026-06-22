#Requires -Version 5.1
# Test HR newsletter Power Automate webhook.

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: .env not found. Set HR_TEAMS_WEBHOOK_URL first." -ForegroundColor Red
    exit 1
}

Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        Set-Item -Path "env:$($matches[1].Trim())" -Value $matches[2].Trim()
    }
}

$url = $env:HR_TEAMS_WEBHOOK_URL
if (-not $url) {
    Write-Host "ERROR: HR_TEAMS_WEBHOOK_URL is empty in .env" -ForegroundColor Red
    exit 1
}

if ($url -notmatch 'sig=') {
    Write-Host "WARN: URL missing sig= parameter. You may get 401." -ForegroundColor Yellow
}

$card = @{
    '$schema' = 'http://adaptivecards.io/schemas/adaptive-card.json'
    type      = 'AdaptiveCard'
    version   = '1.5'
    body      = @(
        @{
            type   = 'TextBlock'
            text   = 'HR Newsletter Webhook Test'
            weight = 'Bolder'
            size   = 'Large'
            wrap   = $true
        },
        @{
            type    = 'TextBlock'
            text    = 'If you see this, the webhook works.'
            wrap    = $true
            spacing = 'Medium'
        }
    )
}

$payload = @{
    type        = 'message'
    title       = 'HR Newsletter Test'
    text        = 'test'
    subtitle    = 'connection test'
    card        = $card
    attachments = @(@{ contentType = 'application/vnd.microsoft.card.adaptive'; content = $card })
    Attachments = @(@{ contentType = 'application/vnd.microsoft.card.adaptive'; content = $card })
}

$json = $payload | ConvertTo-Json -Depth 10 -Compress

Write-Host "Sending test to webhook..." -ForegroundColor Cyan

try {
    $response = Invoke-RestMethod -Uri $url -Method Post -Body $json -ContentType 'application/json; charset=utf-8'
    Write-Host "SUCCESS" -ForegroundColor Green
    $response | ConvertTo-Json -Depth 5
    Write-Host ""
    Write-Host "Check Teams chat with Flow bot (not a channel)." -ForegroundColor Yellow
} catch {
    Write-Host ("FAILED: " + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
