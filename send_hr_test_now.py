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
from hr_newsletter import CaseLink, generate_hr_newsletter
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

SAMPLE_CASE_LINKS = [
    CaseLink(
        region="國內",
        title="Prevent Team Friction from Turning into Dysfunction",
        url="https://hbr.org/2026/06/prevent-team-friction-from-turning-into-dysfunction",
    ),
    CaseLink(
        region="國外",
        title="3 Forces Are Redefining the Transition from Manager to Leader",
        url="https://hbr.org/2026/06/3-forces-are-redefining-the-transition-from-manager-to-leader",
    ),
]

SAMPLE_NEWSLETTER = """主旨：【HR ✕ 管理新知】從主管到領導者 ✕ 把「做事強」養成「帶人強」

📈 今日新知（What）
HBR 近期指出，主管邁向領導者的轉型正遇上 AI 治理、跨境變局與人才準備不足的「三重擠壓」；而最強的團隊也不是零衝突，而是懂得讀懂彼此在壓力下的溝通模式。Josh Bersin 在 Irresistible 2026 也提到，管理者的價值正從「控管績效」轉向「培養超級主管」。

💡 為什麼重要（Why）
「會做事就升管理職」的老邏輯正在失效。中階主管若缺少心理安全與即時回饋，表面的團隊摩擦會很快升級成組織的功能失調，默默吞掉人效。對想帶好團隊的人來說，真正的槓桿是「把人養起來」，而不是事後救火。

🎯 帶走的重點（How）
- 把一對一從「進度盤問」改成「成長對話」：先問「你卡在哪、需要我移開什麼障礙」，再談進度。
- 試一個「團隊摩擦健檢」：每季用一次匿名快問，把衝突攤成可討論的議題，而不是壓下去。
【實作參考】
· 國內｜某科技業導入季度 friction review，團隊衝突事件下降、留任率回升。
· 國外｜HBR 研究指出，頂尖團隊以「建設性摩擦」取代零衝突，創新提案數明顯成長。

---
📌 今日延伸閱讀：
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
    case_links: list[CaseLink] = SAMPLE_CASE_LINKS

    if use_ai and api_key:
        print("Generating live HR newsletter with AI...")
        try:
            newsletter, subject, articles, case_links = generate_hr_newsletter(today)
            print(f"Sources: {', '.join(a.source for a in articles)}")
            print(f"Case links: {len(case_links)}")
        except Exception as exc:
            print(f"AI failed ({exc}), using sample newsletter.")
            newsletter = SAMPLE_NEWSLETTER
            subject = "【HR ✕ 管理新知】從主管到領導者 ✕ 把「做事強」養成「帶人強」"
            articles = SAMPLE_ARTICLES
            case_links = SAMPLE_CASE_LINKS
    else:
        print("Sending sample HR newsletter (set USE_AI=true + OPENAI_API_KEY for live AI).")
        newsletter = SAMPLE_NEWSLETTER
        subject = "【HR ✕ 管理新知】從主管到領導者 ✕ 把「做事強」養成「帶人強」"
        articles = SAMPLE_ARTICLES
        case_links = SAMPLE_CASE_LINKS

    print("Sending to Teams...")
    try:
        send_hr_newsletter_to_teams(newsletter, subject, today, articles, case_links)
        print("SUCCESS — check Teams chat with Flow bot.")
        return 0
    except Exception as exc:
        print(f"FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
