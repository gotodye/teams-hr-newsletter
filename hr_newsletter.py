"""Generate the daily CHRO strategic HR newsletter."""

from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta

import requests

from hr_sources import HRArticle, fetch_hr_articles, format_sources_for_prompt

logger = logging.getLogger(__name__)

# Must match adaptive-card button count in hr_main.py
REFERENCE_ARTICLE_LIMIT = 3

STRATEGIC_THEMES: tuple[str, ...] = (
    "打造雇主品牌",
    "增加員工滿意度",
    "建構員工安全（心理安全、職場安全感，非單純法規合規）",
)

MAX_THEME_USES_PER_WEEK = 2
COMPOSITE_WEEKLY_FOCUS = (
    "綜合三項戰略主題（雇主品牌、員工滿意度、員工安全均衡帶入）"
)

CHRO_SYSTEM_PROMPT = """你是一位具備 20 年以上經驗、擁有國際視野的資深戰略人資長（CHRO）。
你正在為公司執行長撰寫每日專屬的【HR 戰略決策快報】Newsletter。

寫作要求：
- 嚴格依照指定三段式結構輸出
- 正文（不含主旨與連結區）控制在 350-400 字
- 語氣專業、策略導向、溫和但具穿透力
- 絕對不要提及考勤、勞健保、薪資申報等行政瑣事
- 融入重視人才、新世代即時回饋、心理安全感、人效 ROI 等觀念
- 內容需呼應公司 HR 戰略主題：雇主品牌、員工滿意度、員工安全
- 使用繁體中文
"""


def _format_source_ref_lines(
    articles: list[HRArticle],
    limit: int = REFERENCE_ARTICLE_LIMIT,
) -> str:
    if not articles:
        return (
            "- （請依今日趨勢列出 HBR / McKinsey / Josh Bersin 等文章標題，"
            "勿輸出網址或來源 feed 名稱）"
        )
    return "\n".join(f"- {article.title}" for article in articles[:limit])


def _strip_raw_urls(text: str) -> str:
    """Remove raw http(s) URLs if the model still emits them."""
    cleaned = re.sub(r"https?://\S+", "", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.rstrip()


def _week_start_monday(today: date) -> date:
    return today - timedelta(days=today.weekday())


def _pick_theme_for_day(day: date, usage: dict[str, int]) -> str | None:
    """Pick a theme that has not exceeded the weekly cap, or None if all are capped."""
    start = (day.toordinal() + day.weekday()) % len(STRATEGIC_THEMES)
    for offset in range(len(STRATEGIC_THEMES)):
        theme = STRATEGIC_THEMES[(start + offset) % len(STRATEGIC_THEMES)]
        if usage[theme] < MAX_THEME_USES_PER_WEEK:
            return theme
    return None


def _theme_usage_before(today: date) -> dict[str, int]:
    """Count how many times each theme was the daily focus earlier this week."""
    usage = {theme: 0 for theme in STRATEGIC_THEMES}
    week_start = _week_start_monday(today)
    for offset in range((today - week_start).days):
        day = week_start + timedelta(days=offset)
        theme = _pick_theme_for_day(day, usage)
        if theme:
            usage[theme] += 1
    return usage


def focus_theme_for_date(today: date) -> str:
    """Return today's focus theme; each theme appears at most twice per ISO week."""
    usage = _theme_usage_before(today)
    theme = _pick_theme_for_day(today, usage)
    return theme if theme else COMPOSITE_WEEKLY_FOCUS


def _build_user_prompt(today: date, source_block: str, articles: list[HRArticle]) -> str:
    source_ref_lines = _format_source_ref_lines(articles)
    theme_lines = "\n".join(f"- {theme}" for theme in STRATEGIC_THEMES)
    focus_theme = focus_theme_for_date(today)
    weekly_cap_note = (
        f"- 同一戰略主題每週最多作為「今日切入角度」{MAX_THEME_USES_PER_WEEK} 次；"
        f"若今日為綜合角度，請三項均衡帶入，勿偏重單一主題"
        if focus_theme == COMPOSITE_WEEKLY_FOCUS
        else f"- 同一戰略主題每週最多作為「今日切入角度」{MAX_THEME_USES_PER_WEEK} 次"
    )

    return f"""今日日期：{today.isoformat()}

以下是系統抓取的全球 HR / 管理媒體與社群趨勢素材：
{source_block}

公司長期 HR 戰略主題（請在洞察與對策中呼應，至少連結其中一項）：
{theme_lines}
今日建議切入角度：{focus_theme}
{weekly_cap_note}

請嚴格依照以下格式輸出（不要加任何前言或結語）：
- 連結將由系統以 Teams 按鈕呈現，請勿在本文輸出任何 http/https 網址
- 「員工安全」指心理安全、信任與可發聲的職場環境，勿寫成勞檢或工安罰則新聞

主旨：【HR 戰略快報】[今日痛點關鍵字] ✕ [預期帶來的商業效益]

1. 全球/社群觀測（What）
[2-3 句話，專業客觀，具經營者高度]

2. 商業本質洞察（Why）
[戰略高度點破管理本質，溫和堅定融入新世代管理觀念]

3. 我們的行動對策（Actionable Advice）
[1-2 點具體可落地建議，以「建議我們公司可以嘗試…」或「我正帶領團隊規劃…」開頭]

---
📌 今日參考來源（僅列文章標題，勿輸出網址或 feed 名稱如 Google News HR）：
{source_ref_lines}
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


def _extract_gemini_text(data: dict) -> str:
    candidate = data.get("candidates", [{}])[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason == "MAX_TOKENS":
        logger.warning("Gemini response truncated (finishReason=MAX_TOKENS)")

    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(
        part["text"]
        for part in parts
        if part.get("text") and not part.get("thought")
    ).strip()
    if not text:
        raise RuntimeError(
            f"Gemini returned empty text (finishReason={finish_reason})"
        )
    return text


def _gemini_generation_config() -> dict:
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    config: dict = {
        "temperature": 0.7,
        "maxOutputTokens": 2048,
    }
    # thinkingConfig is only valid on Gemini 3.x; omit for 2.x to avoid 400 errors.
    if model.startswith("gemini-3"):
        config["thinkingConfig"] = {"thinkingLevel": "minimal"}
    return config


def _call_gemini(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("需要設定 GEMINI_API_KEY 才能生成 HR 快報")

    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    combined = f"{CHRO_SYSTEM_PROMPT}\n\n{prompt}"
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": combined}]}],
            "generationConfig": _gemini_generation_config(),
        },
        timeout=60,
    )
    if not response.ok:
        logger.error("Gemini API error %s: %s", response.status_code, response.text[:500])
        response.raise_for_status()
    return _extract_gemini_text(response.json())


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

    provider = os.environ.get("AI_PROVIDER", "gemini").lower()
    if provider == "gemini":
        newsletter = _call_gemini(prompt)
    else:
        newsletter = _call_openai(prompt)

    newsletter = _strip_raw_urls(newsletter)
    subject = _extract_subject(newsletter)
    logger.info("HR newsletter generated (%s chars)", len(newsletter))
    return newsletter, subject, articles
