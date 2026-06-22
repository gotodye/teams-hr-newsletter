# HR 快報 — 發送給「某一個人」（Teams 私訊）

Teams 的 Incoming Webhook **無法直接指定收件人**，必須透過 **Power Automate Workflow** 把訊息導向某位使用者的 **1:1 聊天**。

程式端仍只需一個 Webhook URL（`HR_TEAMS_WEBHOOK_URL`），**收件人是誰，在 Workflow 裡設定**。

---

## 設定步驟（約 5 分鐘）

### 1. 在 Power Automate 建立流程

1. 開啟 [Power Automate](https://make.powerautomate.com)
2. 左側選 **建立** → **即時雲端流程**
3. 流程名稱：`HR Newsletter to CEO`（自訂即可）
4. 觸發程序選 **「收到 Webhook 要求時」**（When a webhook request is received）
   - 若找不到，可搜尋 **HTTP** 或 **Teams webhook**
5. 建立後，複製產生的 **HTTP POST URL** → 這就是 `HR_TEAMS_WEBHOOK_URL`

### 2. 新增動作：發送到個人聊天

1. 點 **+ 新步驟**
2. 搜尋並選擇 **Microsoft Teams**
3. 動作選 **「在聊天室或頻道中張貼卡片」**（Post adaptive card in a chat or channel）
4. 依下表設定：

| 欄位 | 設定值 |
|---|---|
| 張貼身分 | **流程機器人**（Flow bot） |
| 張貼位置 | **聊天室**（Chat）← 不是「頻道」 |
| 收件人 | 選擇 **CEO / 老闆的姓名或 Email** |
| 自適應卡片 | `@{triggerBody()?['card']}` |

> 若動作名稱是「在聊天室或頻道中張貼訊息」，請改選 **張貼卡片** 版本，才能正確顯示快報格式。

### 3. 儲存並測試

1. 點 **儲存**
2. 在本機 `.env` 填入：

```env
HR_TEAMS_WEBHOOK_URL=https://prod-xx.westus.logic.azure.com/workflows/...
OPENAI_API_KEY=sk-...
```

3. 執行測試：

```powershell
python hr_main.py
```

4. 確認 **該使用者** 的 Teams 私訊收到快報（不是頻道）

---

## 常見問題

### Q：可以發給我自己測試嗎？
可以。Workflow 收件人先選自己的帳號，確認無誤後再改成 CEO。

### Q：CEO 會看到是誰發的？
訊息會以 **流程機器人（Flow bot）** 名義出現在聊天中。建議事先告知老闆：「每日 07:00 會由公司自動化系統推送 HR 戰略快報」。

### Q：可以同時發給多個人嗎？
可以，但 **不能** 在同一個「張貼卡片」步驟的 Recipient 欄位選多人（實際只會送到第一位）。

**推薦做法（與 Virginia 郵件通知相同）：單一 Webhook + 平行分支**

結構如下（一個觸發、左右兩條平行路徑）：

```
When a Teams webhook request is received
        ├─ Post card in a chat or channel → angus@eui.money
        └─ Post card in a chat or channel → winnie@eui.money
```

設定步驟：

1. 開啟 **HR Newsletter Test to Me**（或你的主 HR 流程）
2. 在 **Webhook 觸發器正下方** 的連接線上，點 **+** → 選 **新增平行分支**（Add parallel branch）
   - 若看不到：在觸發器與第一個動作之間的 **+** 上按右鍵，或點觸發器下方分叉圖示
3. **左分支**（原有）：張貼卡片 → Recipient = **angus@eui.money**
4. **右分支**（新增）：新增「在聊天室或頻道中張貼卡片」→ Recipient = **winnie@eui.money**
5. 兩個步驟其餘設定相同：

| 欄位 | 值 |
|---|---|
| 張貼身分 | Flow bot |
| 張貼位置 | Chat with Flow bot |
| 自適應卡片 | `@{triggerBody()?['card']}` |

6. 建議將兩個動作重新命名（如 `Post card Angus`、`Post card Winnie`），方便維護
7. 觸發條件維持 **Anyone** → 儲存 → 只保留 **一個** Webhook URL 在 `.env`

```env
HR_TEAMS_WEBHOOK_URL=https://...主流程的URL...
# 使用平行分支時，通常不需要 HR_TEAMS_WEBHOOK_URL_EXTRA
```

**備選：每位收件人獨立流程**（兩個 Webhook URL，程式會依序 POST）

```env
HR_TEAMS_WEBHOOK_URL=https://...angus流程的URL...
HR_TEAMS_WEBHOOK_URL_EXTRA=https://...winnie流程的URL...
```

### Q：流程顯示 Succeeded，但對方 Teams 沒收到？
請對方在 Teams 搜尋 **Flow bot**（流程機器人），**先傳任意一則訊息** 建立 1:1 聊天。  
第一次由 Flow bot 主動私訊前，必須先有這一步，否則訊息可能送不出去（流程仍會顯示成功）。

### Q：和頻道 Webhook 可以共用嗎？
**不可以。** HR 快報**只能**用 `HR_TEAMS_WEBHOOK_URL`（Power Automate 私訊）。  
若誤用 Teams 頻道 Webhook，訊息會發到 HK-ALL 等群組，Angus / Winnie 私訊收不到。

---

## GitHub Actions Secret

部署到雲端時，在 GitHub repo → **Settings** → **Secrets** 新增：

| Secret | 值 | 必填 |
|---|---|---|
| `HR_TEAMS_WEBHOOK_URL` | Power Automate「HR Newsletter Test to Me」HTTP POST URL（含 `sig=`） | ✅ |
| `HR_TEAMS_WEBHOOK_URL_EXTRA` | 第二位收件人的獨立流程 URL（若用單流程雙 Post card 步驟則不需要） | 選填 |
| `OPENAI_API_KEY` | AI 生成快報 | ✅ |

> GitHub Actions 若未設定 `HR_TEAMS_WEBHOOK_URL`，workflow 會在第一步直接失敗，**不會**再誤發到頻道。
