#!/usr/bin/env python3
"""Diagnose HR newsletter: Gemini API + webhook (no send unless --send)."""

from __future__ import annotations

import argparse
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


def test_gemini() -> bool:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
    provider = os.environ.get("AI_PROVIDER", "gemini").lower()

    print(f"AI_PROVIDER={provider}")
    print(f"GEMINI_MODEL={model}")
    if not key:
        print("FAIL: GEMINI_API_KEY not set")
        return False

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{"parts": [{"text": "Reply with OK only."}]}],
        "generationConfig": {"maxOutputTokens": 16, "temperature": 0},
    }
    r = requests.post(url, json=payload, timeout=30)
    print(f"Gemini HTTP {r.status_code}")
    print(r.text[:600])
    if not r.ok:
        return False
    print("Gemini OK")
    return True


def test_webhook() -> bool:
    url = os.environ.get("HR_TEAMS_WEBHOOK_URL", "").strip()
    if not url:
        print("FAIL: HR_TEAMS_WEBHOOK_URL not set")
        return False
    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": [{"type": "TextBlock", "text": "HR diagnose test", "wrap": True}],
    }
    payload = {
        "card": card,
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
        "Attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }
    r = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    print(f"Webhook HTTP {r.status_code}")
    print(r.text[:300] if r.text else "(empty)")
    return r.ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Also POST test card to Teams")
    args = parser.parse_args()

    ok = test_gemini()
    if args.send:
        ok = test_webhook() and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
