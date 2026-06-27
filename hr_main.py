#!/usr/bin/env python3
"""每日 HR 戰略決策快報 — 自動生成並發送至 Microsoft Teams。"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

from hr_newsletter import REFERENCE_ARTICLE_LIMIT, generate_hr_newsletter
from hr_sources import HRArticle

load_dotenv()

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TZ_TAIWAN = ZoneInfo("Asia/Taipei")


def get_today() -> date:
    override = os.environ.get("OVERRIDE_DATE", "").strip()
    if override:
        return date.fromisoformat(override)
    return datetime.now(TZ_TAIWAN).date()


def _is_powerautomate_webhook(webhook_url: str) -> bool:
    return "powerplatform.com" in webhook_url or "powerautomate" in webhook_url


def _resolve_webhook_format(webhook_url: str) -> str:
    fmt = os.environ.get("TEAMS_WEBHOOK_FORMAT", "auto").lower()
    if fmt != "auto":
        return fmt
    if _is_powerautomate_webhook(webhook_url):
        return "adaptive"
    return "adaptive"


_BUTTON_TITLE_MAX = 45


def _article_button_title(article: HRArticle) -> str:
    title = article.title.strip()
    if len(title) > _BUTTON_TITLE_MAX:
        title = title[: _BUTTON_TITLE_MAX - 1].rstrip() + "…"
    return title


def _build_adaptive_card(
    title: str,
    subtitle: str,
    message: str,
    articles: list[HRArticle] | None = None,
) -> dict:
    body = [
        {
            "type": "TextBlock",
            "text": title,
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": subtitle,
            "isSubtle": True,
            "spacing": "Small",
            "wrap": True,
        },
        {
            "type": "TextBlock",
            "text": message,
            "wrap": True,
            "spacing": "Medium",
        },
    ]

    card: dict = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }

    if articles:
        actions = [
            {
                "type": "Action.OpenUrl",
                "title": _article_button_title(article),
                "url": article.url,
            }
            for article in articles[:REFERENCE_ARTICLE_LIMIT]
            if article.url
        ]
        if actions:
            card["actions"] = actions

    return card


def _wrap_adaptive_card(card: dict) -> dict:
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": card,
            }
        ],
    }


def get_hr_webhook_urls() -> list[str]:
    """Return HR Power Automate webhook URLs (never fall back to channel webhooks)."""
    raw = os.environ.get("HR_TEAMS_WEBHOOK_URL", "").strip()
    if not raw:
        if os.environ.get("TEAMS_WEBHOOK_URL", "").strip():
            logger.error(
                "TEAMS_WEBHOOK_URL is set but HR_TEAMS_WEBHOOK_URL is missing. "
                "HR newsletter must use the Power Automate DM webhook, not the channel webhook."
            )
        return []

    urls: list[str] = []
    for part in raw.split(","):
        url = part.strip()
        if url and url not in urls:
            urls.append(url)

    extra = os.environ.get("HR_TEAMS_WEBHOOK_URL_EXTRA", "").strip()
    for part in extra.split(","):
        url = part.strip()
        if url and url not in urls:
            urls.append(url)

    return urls


def send_hr_newsletter_to_teams(
    newsletter: str,
    subject: str,
    today: date,
    articles: list[HRArticle] | None = None,
) -> None:
    webhook_urls = get_hr_webhook_urls()
    if not webhook_urls:
        raise RuntimeError(
            "請設定 HR_TEAMS_WEBHOOK_URL（Power Automate 私訊 Webhook）。"
            "不可使用 TEAMS_WEBHOOK_URL（頻道），否則會誤發到群組頻道。"
        )

    title = subject if subject.startswith("【") else f"【HR 戰略快報】{subject}"
    subtitle = today.strftime("%Y年%m月%d日 · CHRO 每日戰略決策快報")

    if os.environ.get("DRY_RUN", "").lower() == "true":
        logger.info("DRY_RUN — 不發送 Teams\n%s", newsletter)
        return

    webhook_format = _resolve_webhook_format(webhook_urls[0])
    if webhook_format == "simple":
        payload = {"text": f"**{title}**\n_{subtitle}_\n\n{newsletter}"}
    else:
        card = _build_adaptive_card(title, subtitle, newsletter, articles)
        payload = _wrap_adaptive_card(card)
        payload["title"] = title
        payload["text"] = newsletter
        payload["subtitle"] = subtitle
        payload["card"] = card
        if payload.get("attachments"):
            payload["Attachments"] = payload["attachments"]

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for index, webhook_url in enumerate(webhook_urls, start=1):
        response = requests.post(
            webhook_url,
            headers=headers,
            data=body,
            timeout=20,
        )
        response.raise_for_status()
        logger.info("HR newsletter sent to Teams (webhook %s/%s)", index, len(webhook_urls))


def main() -> int:
    today = get_today()
    logger.info("HR newsletter date (Taiwan): %s", today.isoformat())

    try:
        newsletter, subject, articles = generate_hr_newsletter(today)
        logger.info("Sources used: %s", ", ".join(article.source for article in articles))
        send_hr_newsletter_to_teams(newsletter, subject, today, articles)
        return 0
    except Exception:
        logger.exception("HR newsletter failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
