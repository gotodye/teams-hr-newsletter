# HR 戰略決策快報

每日 **07:00（台灣時間）** 自動抓取 HBR、Josh Bersin、McKinsey 等來源，生成 CHRO 風格快報（350–400 字），透過 **Power Automate** 發送至 Microsoft Teams **私訊**。

> 晨間推播機器人已獨立至 [teams-morning-bot](https://github.com/gotodye/teams-morning-bot)。

## 功能

- 抓取全球 HR / 領導力媒體 RSS（近 48 小時）
- AI 生成三段式 CHRO 快報（OpenAI 或 Gemini）
- 透過 Power Automate Adaptive Card 發送至指定收件人
- GitHub Actions 每日排程 + 手動觸發

## 專案結構

```
teams-hr-newsletter/
├── hr_main.py                 # 主程式（生成 + 發送）
├── hr_newsletter.py           # CHRO 快報 AI 生成
├── hr_sources.py              # RSS 來源抓取
├── send_hr_test_now.py        # 立即測試發送
├── docs/hr_teams_dm_setup.md  # Power Automate 私訊設定教學
└── .github/workflows/hr_newsletter.yml
```

## 快速開始

### 1. Power Automate 設定

依 [`docs/hr_teams_dm_setup.md`](docs/hr_teams_dm_setup.md) 建立「Webhook → 個人聊天」流程，取得 `HR_TEAMS_WEBHOOK_URL`（**不可**使用 Teams 頻道 Webhook，否則會誤發到群組）。

### 2. 本機設定

```powershell
cd C:\Users\Angus\Projects\teams-hr-newsletter
copy .env.example .env
notepad .env
pip install -r requirements.txt
```

### 3. 測試

```powershell
# Webhook 連線測試（不需 AI）
.\test_hr_webhook.bat

# 發送範例快報
.\send_hr_test_now.bat

# 預覽（不發送 Teams）
.\preview_hr.bat

# 完整 AI 生成 + 發送
python hr_main.py
```

## GitHub Actions

在 GitHub repo → **Settings** → **Secrets** 設定：

| Secret | 說明 |
|---|---|
| `HR_TEAMS_WEBHOOK_URL` | Power Automate HTTP POST URL（含 `sig=`） |
| `HR_TEAMS_WEBHOOK_URL_EXTRA` | 第二位收件人獨立流程 URL（選填） |
| `OPENAI_API_KEY` | AI 生成（或改用 `GEMINI_API_KEY`） |

Workflow 會在 secret 未設定或誤用頻道 webhook 時**直接失敗**，避免誤發到 HK-ALL 等群組。

排程：`0 23 * * *` UTC = 台灣時間 **07:00**。

## 多位收件人

**推薦**：單一 Power Automate 流程 + 平行分支（Angus + Winnie），詳見 `docs/hr_teams_dm_setup.md`。

**備選**：複製流程，設定 `HR_TEAMS_WEBHOOK_URL_EXTRA`。

## 授權

MIT License
