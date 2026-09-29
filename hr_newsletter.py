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

# Long-term company pillars — lightly echo at most one; never the sole daily topic.
STRATEGIC_PILLARS: tuple[str, ...] = (
    "雇主品牌",
    "員工滿意度",
    "員工安全（心理安全與可發聲文化，非法規合規）",
)

# Daily CHRO angles — rotate so the same focus is not reused within 7 days.
DAILY_THEMES: tuple[str, ...] = (
    "人才密度與關鍵職能缺口",
    "中階主管能力與授權",
    "AI 對工作設計、人效與組織結構的影響",
    "績效與回饋制度",
    "組織設計、跨部門協作與決策速度",
    "高潛人才與接班",
    "薪酬哲學與內部公平（策略層，非算薪作業）",
    "混合工作與現場／遠端節奏",
    "招募漏斗與雇主品牌的交付面（體驗與速度，非口號）",
    "文化落地與行為改變",
)

THEME_LOOKBACK_DAYS = 7
MAX_THEME_USES_IN_WINDOW = 1

_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "人才密度與關鍵職能缺口": (
        "skill", "workforce", "talent density", "capability", "職能", "人才缺口", "關鍵人才",
    ),
    "中階主管能力與授權": (
        "manager", "middle manager", "span of control", "empower", "主管", "授權", "中階",
    ),
    "AI 對工作設計、人效與組織結構的影響": (
        "generative ai", "automation", "ai job", "人效", "工作設計", "自動化",
    ),
    "績效與回饋制度": (
        "performance management", "feedback", "okrs", "績效", "回饋",
    ),
    "組織設計、跨部門協作與決策速度": (
        "org design", "organization design", "silo", "decision", "組織設計", "跨部門", "決策",
    ),
    "高潛人才與接班": (
        "succession", "high potential", "hi-po", "接班", "高潛",
    ),
    "薪酬哲學與內部公平（策略層，非算薪作業）": (
        "compensation", "pay equity", "total rewards", "薪酬", "薪資哲學", "內部公平",
    ),
    "混合工作與現場／遠端節奏": (
        "hybrid", "remote work", "return to office", "混合辦公", "遠端", "回辦公室",
    ),
    "招募漏斗與雇主品牌的交付面（體驗與速度，非口號）": (
        "recruiting", "hiring", "employer brand", "candidate experience", "招募", "徵才", "雇主品牌",
    ),
    "文化落地與行為改變": (
        "culture", "psychological safety", "engagement", "文化", "心理安全", "行為",
    ),
}

CASE_LINK_LIMIT = 2  # 國內 + 國外

_CASE_LINKS_BLOCK = re.compile(
    r"^CASE_LINKS:\s*\n(.*?)(?:\n---|\Z)",
    re.MULTILINE | re.DOTALL,
)
_CASE_LINK_LINE = re.compile(
    r"^(國內|國外)[｜|](.+?)[｜|](https?://\S+)\s*$",
    re.MULTILINE,
)
_REFERENCE_SECTION = re.compile(
    r"(?:\n---\s*)?\n📌\s*今日參考來源[^\n]*\n.*",
    re.DOTALL,
)

DOMESTIC_SOURCES = frozenset({"Google News 台灣", "Google News 經理人"})
INTL_SOURCES = frozenset(
    {
        "Josh Bersin",
        "McKinsey Insights",
        "HR Dive",
        "Google News HR",
        "Google News HBR",
    }
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
- 緊扣「今日切入角度」與當日素材；勿每天套用同一組話術
- 心理安全感、即時回饋、人效 ROI、雇主品牌僅在與今日角度相關時使用，不必全寫
- 公司長期支柱（雇主品牌、員工滿意度、員工安全）最多輕點一項，勿寫成全文主軸
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


def _strip_reference_section(text: str) -> str:
    return _REFERENCE_SECTION.sub("", text).rstrip()


def _build_reference_section(articles: list[HRArticle]) -> str:
    if not articles:
        return ""
    lines = _format_source_ref_lines(articles)
    return f"\n\n---\n📌 今日參考來源：\n{lines}"


def _ensure_reference_section(body: str, articles: list[HRArticle]) -> str:
    body = _strip_reference_section(body)
    return body + _build_reference_section(articles)


def _pick_article(
    articles: list[HRArticle],
    sources: frozenset[str],
    exclude_urls: set[str],
) -> HRArticle | None:
    for article in articles:
        if article.source in sources and article.url not in exclude_urls:
            return article
    return None


def _pick_domestic_article(
    articles: list[HRArticle],
    exclude_urls: set[str],
) -> HRArticle | None:
    article = _pick_article(articles, DOMESTIC_SOURCES, exclude_urls)
    if article:
        return article
    for article in articles:
        if article.url in exclude_urls:
            continue
        if re.search(r"[\u4e00-\u9fff]", article.title):
            return article
    return None


def _pick_intl_article(
    articles: list[HRArticle],
    exclude_urls: set[str],
) -> HRArticle | None:
    return _pick_article(articles, INTL_SOURCES, exclude_urls)


def _fallback_case_links(
    articles: list[HRArticle],
    existing: list[CaseLink],
) -> list[CaseLink]:
    if len(existing) >= CASE_LINK_LIMIT or not articles:
        return existing

    result = list(existing)
    used_urls = {case.url for case in result}
    regions = {case.region for case in result}

    if "國內" not in regions:
        domestic = _pick_domestic_article(articles, used_urls)
        if domestic:
            result.append(
                CaseLink(region="國內", title=domestic.title, url=domestic.url)
            )
            used_urls.add(domestic.url)

    if len(result) < CASE_LINK_LIMIT and "國外" not in regions:
        intl = _pick_intl_article(articles, used_urls)
        if intl:
            result.append(CaseLink(region="國外", title=intl.title, url=intl.url))

    return result[:CASE_LINK_LIMIT]


def finalize_newsletter(raw: str, articles: list[HRArticle]) -> tuple[str, list[CaseLink]]:
    """Strip machine-readable link blocks and ensure reference links are present."""
    case_links = _parse_case_links(raw, articles)
    body = _remove_case_links_block(raw)
    body = _strip_raw_urls(body)
    case_links = _fallback_case_links(articles, case_links)
    body = _ensure_reference_section(body, articles)
    return body, case_links


def _calendar_theme(day: date) -> str:
    return DAILY_THEMES[day.toordinal() % len(DAILY_THEMES)]


def _recent_calendar_themes(today: date) -> set[str]:
    used: set[str] = set()
    for offset in range(1, THEME_LOOKBACK_DAYS):
        used.add(_calendar_theme(today - timedelta(days=offset)))
    return used


def _score_theme(theme: str, articles: list[HRArticle]) -> int:
    keywords = _THEME_KEYWORDS.get(theme, ())
    if not keywords or not articles:
        return 0
    score = 0
    for article in articles:
        haystack = f"{article.title} {article.summary}".lower()
        for keyword in keywords:
            if keyword.lower() in haystack:
                score += 1
                break
    return score


def focus_theme_for_date(
    today: date,
    articles: list[HRArticle] | None = None,
) -> str:
    """Pick today's angle; the same theme is used at most once in any 7-day window."""
    blocked = _recent_calendar_themes(today)
    calendar = _calendar_theme(today)
    if not articles:
        return calendar

    ranked = sorted(
        (
            (theme, _score_theme(theme, articles))
            for theme in DAILY_THEMES
            if theme not in blocked
        ),
        key=lambda row: row[1],
        reverse=True,
    )
    if ranked and ranked[0][1] > 0:
        return ranked[0][0]
    return calendar if calendar not in blocked else ranked[0][0]


def _build_user_prompt(today: date, source_block: str, articles: list[HRArticle]) -> str:
    pillar_lines = "\n".join(f"- {pillar}" for pillar in STRATEGIC_PILLARS)
    focus_theme = focus_theme_for_date(today, articles)

    return f"""今日日期：{today.isoformat()}

以下是系統抓取的全球 HR / 管理媒體與社群趨勢素材：
{source_block}

公司長期 HR 支柱（全文最多輕點一項，勿當主軸）：
{pillar_lines}
今日切入角度（必須作為主軸，勿改寫成滿意度／心理安全／雇主品牌套話）：{focus_theme}
- 同一切入角度 {THEME_LOOKBACK_DAYS} 天內最多使用 {MAX_THEME_USES_IN_WINDOW} 次
- What 段須點到上方實際素材中的 1-2 則（用標題或現象，勿寫網址）
- 案例的產業或做法須貼近今日角度；避免反覆使用同一間公司或同一套 DEI／心理安全故事

請嚴格依照以下格式輸出（不要加任何前言或結語）：
- 連結將由系統以 Teams 按鈕呈現，請勿在本文輸出任何 http/https 網址
- 「員工安全」若出現，僅指心理安全與可發聲文化，勿寫成勞檢或工安罰則

主旨：【HR 戰略快報】[今日痛點關鍵字] ✕ [預期帶來的商業效益]

1. 全球/社群觀測（What）
[2-3 句話，專業客觀，具經營者高度；緊扣今日素材與切入角度]

2. 商業本質洞察（Why）
[點破與今日角度相關的管理本質，勿套用與角度無關的新世代口號]

3. 我們的行動對策（Actionable Advice）
[1-2 點尚未執行、且對應今日角度的建議方案；以「建議方案：…」或「建議我們可評估／試行…」開頭。
勿寫成已在進行或已完成的口吻（避免「我正帶領」「我們已導入」「正在推動」等）]
【案例參考】
（標題僅輸出「【案例參考】」四字，勿附帶括號說明；其下國內／國外各 1 則，每則 1-2 句：公司/組織＋做法＋可借鑑成效，勿寫網址）
· 國內｜[台灣或亞太企業案例]
· 國外｜[國際企業案例]

CASE_LINKS:
國內｜[案例來源文章標題]｜[必須從上方素材複製的完整 URL]
國外｜[案例來源文章標題]｜[必須從上方素材複製的完整 URL]
（CASE_LINKS 區塊由系統轉為 Teams 按鈕，勿出現在正文；若未提供，系統會自動從素材補上）

（📌 今日參考來源區塊由系統自動附加，AI 無需輸出）
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
            "temperature": 0.8,
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
        "temperature": 0.8,
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
        "HR newsletter generated (%s chars, %s case links, theme=%s)",
        len(newsletter),
        len(case_links),
        focus_theme_for_date(today, articles),
    )
    return newsletter, subject, articles, case_links
