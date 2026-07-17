"""Generate the daily CHRO strategic HR newsletter."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
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

CASE_LINK_LIMIT = 2  # 國內 + 國外

_CASE_LINKS_BLOCK = re.compile(
    r"^CASE_LINKS:\s*\n(.*?)(?:\n---|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CASE_LINK_LINE = re.compile(
    r"^(國內|國外)[｜|](.+?)[｜|](https?://\S+)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class CaseLink:
    region: str
    title: str
    url: str


CHRO_SYSTEM_PROMPT = """你是一位具備 20 年以上經驗、擁有國際視野的資深戰略人資長（CHRO）。
你正在為公司執行長撰寫每日專屬的【HR 戰略決策快報】Newsletter。

寫作要求：
- 嚴格依照指定三段式結構輸出
- 正文（不含主旨、連結區與 CASE_LINKS）控制在 400-480 字
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


def _resolve_case_url(title: str, url: str, articles: list[HRArticle]) -> str:
    url = url.strip()
    if url.startswith("http"):
        return url
    title_key = title.strip().lower()
    for article in articles:
        if title_key in article.title.lower() or article.title.lower() in title_key:
            return article.url
    return url


def _parse_case_links(raw: str, articles: list[HRArticle]) -> list[CaseLink]:
    block = _CASE_LINKS_BLOCK.search(raw)
    if not block:
        return []

    cases: list[CaseLink] = []
    seen_urls: set[str] = set()
    for match in _CASE_LINK_LINE.finditer(block.group(1)):
        region, title, url = match.group(1), match.group(2).strip(), match.group(3).strip()
        resolved = _resolve_case_url(title, url, articles)
        if not resolved.startswith("http"):
            logger.warning("Skipping case link without URL: %s / %s", region, title)
            continue
        url_key = resolved.split("?")[0].rstrip("/").lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        cases.append(CaseLink(region=region, title=title, url=resolved))
        if len(cases) >= CASE_LINK_LIMIT:
            break
    return cases


def _remove_case_links_block(text: str) -> str:
    cleaned = _CASE_LINKS_BLOCK.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def finalize_newsletter(raw: str, articles: list[HRArticle]) -> tuple[str, list[CaseLink]]:
    """Strip machine-readable link blocks and accidental URLs from newsletter body."""
    case_links = _parse_case_links(raw, articles)
    body = _remove_case_links_block(raw)
    body = _strip_raw_urls(body)
    return body, case_links


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
[1-2 點尚未執行的建議方案；以「建議方案：…」或「建議我們可評估／試行…」開頭。
勿寫成已在進行或已完成的口吻（避免「我正帶領」「我們已導入」「正在推動」等）]
【案例參考】（必填，各 1 則，每則 1-2 句：公司/組織＋做法＋可借鑑成效，勿寫網址）
· 國內｜[台灣或亞太企業案例]
· 國外｜[國際企業案例]

CASE_LINKS:
國內｜[案例來源文章標題]｜[必須從上方素材複製的完整 URL]
國外｜[案例來源文章標題]｜[必須從上方素材複製的完整 URL]
（CASE_LINKS 區塊由系統轉為 Teams 按鈕，勿出現在正文）

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


def generate_hr_newsletter(today: date) -> tuple[str, str, list[HRArticle], list[CaseLink]]:
    """Return (newsletter_text, subject_line, source_articles, case_links)."""
    articles = fetch_hr_articles()
    source_block = format_sources_for_prompt(articles)
    prompt = _build_user_prompt(today, source_block, articles)

    provider = os.environ.get("AI_PROVIDER", "gemini").lower()
    if provider == "gemini":
        raw = _call_gemini(prompt)
    else:
        raw = _call_openai(prompt)

    newsletter, case_links = finalize_newsletter(raw, articles)
    subject = _extract_subject(newsletter)
    logger.info(
        "HR newsletter generated (%s chars, %s case links)",
        len(newsletter),
        len(case_links),
    )
    return newsletter, subject, articles, case_links
