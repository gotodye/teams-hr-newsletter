"""Generate the daily CHRO strategic HR newsletter."""

from __future__ import annotations

import logging
import os
import re
from datetime import date

import requests

from hr_sources import HRArticle, fetch_hr_articles, format_sources_for_prompt

logger = logging.getLogger(__name__)

CHRO_SYSTEM_PROMPT = """你是一位具備 20 年以上經驗、擁有國際視野的資深戰略人資長（CHRO）。
你正在為公司執行長撰寫每日專屬的【HR 戰略決策快報】Newsletter。

寫作要求：
- 嚴格依照指定三段式結構輸出
- 正文（不含主旨與連結區）控制在 350-400 字
- 語氣專業、策略導向、溫和但具穿透力
- 絕對不要提及考勤、勞健保、薪資申報等行政瑣事
- 融入重視人才、新世代即時回饋、心理安全感、人效 ROI 等觀念
- 使用繁體中文
"""


def _build_user_prompt(today: date, source_block: str, articles: list[HRArticle]) -> str:
    link_lines = "\n".join(f"- {article.url}" for article in articles[:3])
    if not link_lines:
        link_lines = "- （請依今日趨勢補上 HBR / McKinsey / Josh Bersin 等來源連結）"

    return f"""今日日期：{today.isoformat()}

以下是系統抓取的全球 HR / 管理媒體與社群趨勢素材：
{source_block}

請嚴格依照以下格式輸出（不要加任何前言或結語）：

主旨：【HR 戰略快報】[今日痛點關鍵字] ✕ [預期帶來的商業效益]

1. 全球/社群觀測（What）
[2-3 句話，專業客觀，具經營者高度]

2. 商業本質洞察（Why）
[戰略高度點破管理本質，溫和堅定融入新世代管理觀念]

3. 我們的行動對策（Actionable Advice）
[1-2 點具體可落地建議，以「建議我們公司可以嘗試…」或「我正帶領團隊規劃…」開頭]

---
📌 今日趨勢/社群熱議原文連結：
{link_lines}
"""


def _call_openai(prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("需要設定 OPENAI_API_KEY 才能生成 HR 快報")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": CHRO_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 900,
            "temperature": 0.7,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()


def _call_gemini(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("需要設定 GEMINI_API_KEY 才能生成 HR 快報")

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "parts": [
                        {"text": CHRO_SYSTEM_PROMPT},
                        {"text": prompt},
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 900,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _extract_subject(newsletter: str) -> str:
    match = re.search(r"^主旨[：:]\s*(.+)$", newsletter, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "【HR 戰略快報】"


def generate_hr_newsletter(today: date) -> tuple[str, str, list[HRArticle]]:
    """Return (newsletter_text, subject_line, source_articles)."""
    articles = fetch_hr_articles()
    source_block = format_sources_for_prompt(articles)
    prompt = _build_user_prompt(today, source_block, articles)

    provider = os.environ.get("AI_PROVIDER", "openai").lower()
    if provider == "gemini":
        newsletter = _call_gemini(prompt)
    else:
        newsletter = _call_openai(prompt)

    subject = _extract_subject(newsletter)
    logger.info("HR newsletter generated (%s chars)", len(newsletter))
    return newsletter, subject, articles
