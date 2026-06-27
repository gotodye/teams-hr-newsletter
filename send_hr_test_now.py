#!/usr/bin/env python3
"""Send a real-format HR newsletter test message to Teams immediately."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

from hr_main import get_hr_webhook_urls, get_today, send_hr_newsletter_to_teams
from hr_newsletter import generate_hr_newsletter
from hr_sources import HRArticle

TZ_TAIWAN = ZoneInfo("Asia/Taipei")

SAMPLE_ARTICLES = [
    HRArticle(
        title="3 Forces Are Redefining the Transition from Manager to Leader",
        url="https://hbr.org/2026/06/3-forces-are-redefining-the-transition-from-manager-to-leader",
        published=datetime.now(TZ_TAIWAN),
        source="HBR Leadership",
    ),
    HRArticle(
        title="Prevent Team Friction from Turning into Dysfunction",
        url="https://hbr.org/2026/06/prevent-team-friction-from-turning-into-dysfunction",
        published=datetime.now(TZ_TAIWAN),
        source="HBR Leadership",
    ),
    HRArticle(
        title="The Josh Bersin Institute, HR 2030, and the Global HR Excellence Certification",
        url="https://joshbersin.com/2026/06/the-josh-bersin-institute-hr-2030-and-the-global-hr-excellence-certification/",
        published=datetime.now(TZ_TAIWAN),
        source="Josh Bersin",
    ),
]

SAMPLE_NEWSLETTER = """主旨：【HR 戰略快報】主管斷層 ✕ 守住團隊韌性與人效

1. 全球/社群觀測（What）
HBR 近期連發研究指出，主管邁向領導者的轉型正面臨 AI 治理、跨境變局與人才準備不足的「三重擠壓」；同時強調最強團隊並非零衝突，而是懂得讀懂彼此在壓力下的溝通模式。Josh Bersin 於 Irresistible 2026 亦呼籲，HR 2030 時代管理者的價值正從「控管績效」轉向「淬煉超級主管」。

2. 商業本質洞察（Why）
這揭示一個殘酷真相：昔日「會做事就上管理職」的晉升邏輯已失效。新世代中間層若缺乏心理安全感與即時回饋機制，表面團隊摩擦將迅速升級為組織功能失調，直接吞噬人效 ROI。人才不再是可替換的資源，而是承載策略執行的唯一載體；您真正的控制槓桿，是投資「領導者養成」而非事後救火。

3. 我們的行動對策（Actionable Advice）
建議我們公司可以嘗試：為高潛主管設計「AI 時代領導轉型工作坊」，聚焦決策授權與跨文化協作。我正帶領團隊規劃「團隊摩擦健檢」機制，透過季度 360° 即時回饋，將衝突轉化為創新動能。

---
📌 今日參考來源（僅列文章標題，勿輸出網址）：
- 3 Forces Are Redefining the Transition from Manager to Leader
- Prevent Team Friction from Turning into Dysfunction
- The Josh Bersin Institute, HR 2030, and the Global HR Excellence Certification"""


def main() -> int:
    today = get_today()
    urls = get_hr_webhook_urls()
    if not urls:
        print(
            "ERROR: Set HR_TEAMS_WEBHOOK_URL in .env "
            "(Power Automate DM webhook — not a Teams channel webhook)"
        )
        return 1

    if any("sig=" not in u for u in urls):
        print("WARN: One or more URLs missing sig= — may get 401.")

    use_ai = os.environ.get("USE_AI", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    articles: list[HRArticle] = SAMPLE_ARTICLES

    if use_ai and api_key:
        print("Generating live HR newsletter with AI...")
        try:
            newsletter, subject, articles = generate_hr_newsletter(today)
            print(f"Sources: {', '.join(a.source for a in articles)}")
        except Exception as exc:
            print(f"AI failed ({exc}), using sample newsletter.")
            newsletter = SAMPLE_NEWSLETTER
            subject = "【HR 戰略快報】主管斷層 ✕ 守住團隊韌性與人效"
            articles = SAMPLE_ARTICLES
    else:
        print("Sending sample HR newsletter (set USE_AI=true + OPENAI_API_KEY for live AI).")
        newsletter = SAMPLE_NEWSLETTER
        subject = "【HR 戰略快報】主管斷層 ✕ 守住團隊韌性與人效"
        articles = SAMPLE_ARTICLES

    print("Sending to Teams...")
    try:
        send_hr_newsletter_to_teams(newsletter, subject, today, articles)
        print("SUCCESS — check Teams chat with Flow bot.")
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
