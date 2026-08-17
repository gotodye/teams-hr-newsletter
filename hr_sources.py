"""Fetch recent HR / leadership articles from trusted management media feeds."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Iterable
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

TZ_TAIWAN = ZoneInfo("Asia/Taipei")
DEFAULT_LOOKBACK_HOURS = 48
EXTENDED_LOOKBACK_HOURS = 168  # 7 days — fallback when default window yields nothing

HR_FEEDS: dict[str, str] = {
    "Josh Bersin": "https://joshbersin.com/feed/",
    "McKinsey Insights": "https://www.mckinsey.com/insights/rss",
    "HR Dive": "https://www.hrdive.com/feeds/news/",
}

HR_TOPIC_FEEDS: dict[str, str] = {
    "Google News HBR": (
        "https://news.google.com/rss/search?"
        "q=site:hbr.org+leadership+OR+workplace+OR+employee+when:7d"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Google News 經理人": (
        "https://news.google.com/rss/search?"
        "q=site:managertoday.com.tw+when:7d"
        "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    ),
    "Google News HR": (
        "https://news.google.com/rss/search?"
        "q=human+resources+OR+workplace+culture+OR+leadership+OR+employer+brand"
        "+OR+employee+engagement+OR+employee+satisfaction+OR+psychological+safety"
        "+OR+workplace+safety+when:2d"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
    "Google News 台灣": (
        "https://news.google.com/rss/search?"
        "q=%E4%BA%BA%E8%B3%87+OR+%E9%A0%98%E5%B0%8E%E5%8A%9B+OR+%E8%81%B7%E5%A0%B4"
        "+OR+%E9%9B%87%E4%B8%BB%E5%93%81%E7%89%8C+OR+%E5%93%A1%E5%B7%A5%E6%BB%BF%E6%84%8F%E5%BA%A6"
        "+OR+%E5%BF%83%E7%90%86%E5%AE%89%E5%85%A8+OR+%E5%93%A1%E5%B7%A5%E5%AE%89%E5%85%A8+when:2d"
        "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    ),
}

# Blog-style feeds publish less frequently — allow a longer window per source.
FEED_LOOKBACK_HOURS: dict[str, int] = {
    "Josh Bersin": 168,
    "McKinsey Insights": 168,
    "HR Dive": 96,
    "Google News HBR": 168,
    "Google News 經理人": 168,
}

NEWS_AGGREGATOR_SOURCES = frozenset(
    {
        "Google News HR",
        "Google News 台灣",
        "Google News HBR",
        "Google News 經理人",
    }
)

_RETRYABLE_HTTP = frozenset({429, 502, 503, 504})

# All feeds — admin, compliance, or clearly off-topic for CHRO briefings.
GLOBAL_TITLE_EXCLUDE: tuple[str, ...] = (
    "懶人包",
    "勞基法",
    "勞健保",
    "薪資申報",
    "考勤",
    "加班費",
    "特休計算",
    "函釋",
    "最高罰",
    "罰款",
    "新制一次看",
    "新制將上路",
    "法規正式上路",
    "世界盃",
    "FIFA",
    "駕照大改革",
    "醫療補助升級",
    "FMLA",
    "EEOC",
    "GINA",
)

# News aggregators — repetitive policy / lawsuit headlines.
AGGREGATOR_TITLE_EXCLUDE: tuple[str, ...] = (
    "職場霸凌",
    "職安法",
    "職災",
    "勞檢",
    "申訴",
    "起訴",
    "罰鍰",
    "違反勞基法",
    "討論牆",
    "涉職場霸凌",
)

_TITLE_EXCLUDE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"罰\d+萬"),
    re.compile(r"新制[｜|]"),
)


@dataclass(frozen=True)
class HRArticle:
    title: str
    url: str
    published: datetime
    source: str
    summary: str = ""


def _parse_published(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=TZ_TAIWAN)
        return parsed.astimezone(TZ_TAIWAN)
    except (TypeError, ValueError):
        return None


def _strip_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _fetch_rss(url: str, source: str) -> list[HRArticle]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                timeout=20,
                headers={"User-Agent": "teams-hr-newsletter/1.0"},
            )
            response.raise_for_status()
            return _parse_rss_content(response.content, source)
        except requests.HTTPError as exc:
            last_error = exc
            status = exc.response.status_code if exc.response is not None else None
            if status in _RETRYABLE_HTTP and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise
        except Exception as exc:
            last_error = exc
            raise
    if last_error:
        raise last_error
    return []


def _parse_rss_content(content: bytes, source: str) -> list[HRArticle]:
    root = ElementTree.fromstring(content)
    channel = root.find("channel")
    if channel is None:
        return []

    items: list[HRArticle] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = _parse_published(item.findtext("pubDate") or "")
        summary = _strip_html(item.findtext("description") or "")
        if not title or not link or published is None:
            continue
        items.append(
            HRArticle(
                title=title,
                url=link,
                published=published,
                source=source,
                summary=summary[:280],
            )
        )
    return items


def _within_lookback(item: HRArticle, cutoff: datetime) -> bool:
    return item.published >= cutoff


def _title_exclusion_reason(title: str, source: str) -> str | None:
    text = title.strip()
    if not text:
        return "empty"

    lowered = text.lower()
    for keyword in GLOBAL_TITLE_EXCLUDE:
        if keyword.lower() in lowered or keyword in text:
            return keyword

    for pattern in _TITLE_EXCLUDE_PATTERNS:
        if pattern.search(text):
            return pattern.pattern

    if source in NEWS_AGGREGATOR_SOURCES:
        for keyword in AGGREGATOR_TITLE_EXCLUDE:
            if keyword in text:
                return keyword

    return None


def _filter_by_title(articles: Iterable[HRArticle], source: str) -> list[HRArticle]:
    kept: list[HRArticle] = []
    for article in articles:
        reason = _title_exclusion_reason(article.title, source)
        if reason:
            logger.info(
                "Excluded [%s] %s (keyword: %s)",
                source,
                article.title[:80],
                reason,
            )
            continue
        kept.append(article)
    return kept


def _dedupe_articles(articles: Iterable[HRArticle]) -> list[HRArticle]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    unique: list[HRArticle] = []

    for article in articles:
        url_key = article.url.split("?")[0].rstrip("/").lower()
        title_key = re.sub(r"\s+", " ", article.title.lower()).strip()
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        unique.append(article)

    unique.sort(key=lambda row: row.published, reverse=True)
    return unique


def _collect_articles(
    lookback_hours: int,
    per_feed_lookback: dict[str, int] | None = None,
) -> list[HRArticle]:
    """Fetch and filter articles using per-source lookback windows."""
    per_feed_lookback = per_feed_lookback or {}
    now = datetime.now(TZ_TAIWAN)
    collected: list[HRArticle] = []

    for source, feed_url in {**HR_FEEDS, **HR_TOPIC_FEEDS}.items():
        source_hours = per_feed_lookback.get(source, lookback_hours)
        cutoff = now - timedelta(hours=source_hours)
        try:
            fetched = _fetch_rss(feed_url, source)
            recent = [item for item in fetched if _within_lookback(item, cutoff)]
            recent = _filter_by_title(recent, source)
            collected.extend(recent)
            logger.info(
                "Kept %s items from %s after title filter (lookback %sh)",
                len(recent),
                source,
                source_hours,
            )
        except Exception:
            logger.warning("Failed to fetch feed: %s", source, exc_info=True)

    return collected


def fetch_hr_articles(
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    limit: int = 8,
) -> list[HRArticle]:
    """Return recent HR-relevant articles from configured feeds."""
    per_feed_lookback = {
        source: FEED_LOOKBACK_HOURS.get(source, lookback_hours)
        for source in {**HR_FEEDS, **HR_TOPIC_FEEDS}
    }
    collected = _collect_articles(lookback_hours, per_feed_lookback)

    if not collected:
        logger.warning(
            "No articles in default lookback; retrying with %sh window",
            EXTENDED_LOOKBACK_HOURS,
        )
        extended = {
            source: max(hours, EXTENDED_LOOKBACK_HOURS)
            for source, hours in per_feed_lookback.items()
        }
        collected = _collect_articles(EXTENDED_LOOKBACK_HOURS, extended)

    articles = _dedupe_articles(collected)[:limit]
    logger.info("Selected %s HR articles for newsletter", len(articles))
    return articles


def format_sources_for_prompt(articles: list[HRArticle]) -> str:
    """Serialize article list for the LLM prompt."""
    if not articles:
        return "（今日暫無可抓取之新文章，請依 HR 戰略趨勢常識撰寫，並在連結區註明來源待補）"

    lines: list[str] = []
    for index, article in enumerate(articles, start=1):
        lines.append(
            f"{index}. [{article.source}] {article.title}\n"
            f"   URL: {article.url}\n"
            f"   摘要: {article.summary or '（無摘要）'}"
        )
    return "\n".join(lines)
