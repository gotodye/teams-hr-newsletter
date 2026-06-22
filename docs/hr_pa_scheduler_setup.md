# HR 快報 — Power Automate 每日 06:00 排程觸發

GitHub Actions **不再使用 cron**。改由 Power Automate 在台灣時間 **06:00** 準時觸發 GitHub workflow，生成快報後再 POST 到「發送私訊」的 webhook flow。

## 架構（兩個 flow）

```
Flow A: HR Newsletter Scheduler 06:00     Flow B: HR Newsletter Test to Me
  Recurrence 06:00 TW                         Webhook 觸發
       │                                            │
       └─ HTTP → GitHub Actions                     │
              (生成 + Gemini)                        │
                    │                                │
                    └──── POST webhook ──────────────┘
                              │
                    Post card → Angus
                    Post card → Winnie
```

| Flow | 類型 | 用途 |
|---|---|---|
| **HR Newsletter Scheduler 06:00** | 排程雲端流程 | 每天 06:00 叫 GitHub 跑快報 |
| **HR Newsletter Test to Me** | 即時雲端流程 | 收 webhook → 發 Teams 私訊 |

> **不要刪** Flow B。Flow A 只負責「準時開跑」；Flow B 的 URL 仍是 `HR_TEAMS_WEBHOOK_URL`。

---

## 步驟 1：建立 GitHub Personal Access Token

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. **Generate new token**
3. Repository access：**Only select** → `gotodye/teams-hr-newsletter`
4. Permissions → **Actions**: **Read and write**
5. 產生後複製 token（只顯示一次）

---

## 步驟 2：建立排程 flow（Flow A）

1. [Power Automate](https://make.powerautomate.com) → **建立** → **排程雲端流程**
2. 名稱：`HR Newsletter Scheduler 06:00`
3. 觸發程序：**Recurrence / 週期**

### Recurrence 設定

| 欄位 | 值 |
|---|---|
| 間隔 | `1` |
| 頻率 | **Day / 天** |
| Time zone | **(UTC+08:00) Taipei** |
| At these hours | `6` |
| At these minutes | `0` |

4. **+ New step** → 搜尋 **HTTP**（內建動作，不是 Teams webhook）

### HTTP 動作設定

| 欄位 | 值 |
|---|---|
| Method | `POST` |
| URI | `https://api.github.com/repos/gotodye/teams-hr-newsletter/dispatches` |
| Headers | 見下方 |
| Body | 見下方 |

**Headers**（新增三列）：

| Key | Value |
|---|---|
| `Accept` | `application/vnd.github+json` |
| `Authorization` | `Bearer 你的GitHub_PAT` |
| `X-GitHub-Api-Version` | `2022-11-28` |
| `Content-Type` | `application/json` |

**Body**：

```json
{
  "event_type": "hr-newsletter-daily",
  "client_payload": {}
}
```

5. **儲存** → **測試** → **手動** → **執行流程**

6. 到 GitHub 確認：  
   https://github.com/gotodye/teams-hr-newsletter/actions  
   應出現新的 **HR Strategic Newsletter** run

---

## 步驟 3：推送程式碼（移除 GitHub cron）

本機已移除 `schedule:` cron。請推送：

```powershell
cd C:\Users\Angus\Projects\teams-hr-newsletter
git add .github/workflows/hr_newsletter.yml docs/hr_pa_scheduler_setup.md README.md
git commit -m "Schedule HR newsletter via Power Automate 06:00 instead of GitHub cron"
git push origin main
```

---

## 常見問題

### Q：為什麼不用 GitHub cron？
GitHub Actions 排程可能延遲 5–15 分鐘。Power Automate Recurrence 在企業環境通常更準時。

### Q：06:00 觸發後多久收到 Teams？
GitHub Actions 啟動約 30 秒～2 分鐘，Gemini 生成約 10–30 秒，整體約 **06:01–06:03** 收到屬正常。

### Q：還能手動測試嗎？
可以。GitHub Actions → **HR Strategic Newsletter** → **Run workflow**。

### Q：PAT 要放哪？
放在 Power Automate HTTP 動作的 `Authorization` header。建議用 **Azure Key Vault** 或 PA 的 secure input；不要寫進 GitHub repo。

### Q：國定假日要停嗎？
目前 HR 快報**沒有**假日跳過（morning-bot 有）。若需要可再於 Flow A 加「條件」判斷星期一到五。

---

## 檢查清單

- [ ] Flow A：`HR Newsletter Scheduler 06:00` 已建立且 **On**
- [ ] Flow B：`HR Newsletter Test to Me` 仍 **On**（Angus + Winnie）
- [ ] GitHub PAT 有效、權限含 Actions write
- [ ] `teams-hr-newsletter` 已推送（無 cron）
- [ ] 手動跑 Flow A 一次，Actions 成功、Teams 收到訊息
