"""Fetch recent HR / leadership articles from trusted management media feeds."""

from __future__ import annotations

import logging
import re
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

HR_FEEDS: dict[str, str] = {
    "Josh Bersin": "https://joshbersin.com/feed/",
    "HBR Leadership": "https://hbr.org/topic/subject/leadership.rss",
    "McKinsey People": "https://www.mckinsey.com/featured-insights/rss",
}

HR_TOPIC_FEEDS: dict[str, str] = {
    "Google News HR": (
        "https://news.google.com/rss/search?"
        "q=human+resources+OR+workplace+culture+OR+leadership+when:2d"
        "&hl=en-US&gl=US&ceid=US:en"
    ),
}


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
    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "teams-hr-newsletter/1.0"},
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
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


def fetch_hr_articles(
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    limit: int = 8,
) -> list[HRArticle]:
    """Return recent HR-relevant articles from configured feeds."""
    cutoff = datetime.now(TZ_TAIWAN) - timedelta(hours=lookback_hours)
    collected: list[HRArticle] = []

    for source, feed_url in {**HR_FEEDS, **HR_TOPIC_FEEDS}.items():
        try:
            fetched = _fetch_rss(feed_url, source)
            recent = [item for item in fetched if _within_lookback(item, cutoff)]
            collected.extend(recent)
            logger.info("Fetched %s recent items from %s", len(recent), source)
        except Exception:
            logger.warning("Failed to fetch feed: %s", source, exc_info=True)

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
