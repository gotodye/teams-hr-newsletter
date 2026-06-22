#!/usr/bin/env python3
"""Test HR newsletter Power Automate webhook. Run while PA Test is waiting."""

from __future__ import annotations

import json
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> int:
    url = os.environ.get("HR_TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        print("ERROR: Set HR_TEAMS_WEBHOOK_URL in .env")
        return 1

    if "sig=" not in url:
        print("WARN: URL missing sig= — you may get 401")
        print("Copy the full HTTP URL from the Power Automate trigger step.\n")

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [
            {
                "type": "TextBlock",
                "text": "【HR 戰略快報】Webhook 測試",
                "weight": "Bolder",
                "size": "Large",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": "若您看到此訊息，Webhook 已打通。",
                "wrap": True,
                "spacing": "Medium",
            },
        ],
    }

    payload = {
        "type": "message",
        "title": "【HR 戰略快報】Webhook 測試",
        "text": "測試訊息",
        "subtitle": "連線測試",
        "card": card,
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
        "Attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }

    print("Sending test to webhook...")
    print(f"URL: {url[:80]}...\n")

    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=20,
        )
        print(f"Status: {response.status_code}")
        print(response.text[:500] if response.text else "(empty body)")
        response.raise_for_status()
        print("\nSUCCESS — check Teams chat with Flow bot.")
        return 0
    except requests.HTTPError as exc:
        print(f"\nFAILED: {exc}")
        if "401" in str(exc):
            print("401 = URL incomplete. Copy full URL with sig= from PA trigger.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
