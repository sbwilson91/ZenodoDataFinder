"""
utils/ai_logic.py

Drop-in replacement for the HuggingFace summarisation backend.
Swaps to Gemini 2.5 Flash via the native Gemini API using only `requests`
(already in requirements.txt — no new dependencies needed).

Interface is identical to the original: get_ai_summary(prompt, max_tokens)
so nothing else in the bot needs to change.

Secret required: GOOGLE_API_KEY (free, no credit card — get at aistudio.google.com)
"""

import os
import time
import requests


_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


def get_ai_summary(prompt: str, max_tokens: int = 500) -> str:
    """
    Generate a summary using Gemini 2.5 Flash.

    Args:
        prompt:     The full prompt string (same as before)
        max_tokens: Maximum output tokens (default 500)

    Returns:
        Generated text string

    Raises:
        requests.HTTPError on non-2xx responses (after retries)
    """
    api_key = os.environ["GOOGLE_API_KEY"]

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.3,   # consistent, factual summaries
        },
    }

    # Simple retry with exponential backoff for transient 429s / 503s
    for attempt in range(3):
        resp = requests.post(
            _GEMINI_URL,
            params={"key": api_key},
            json=payload,
            timeout=30,
        )

        if resp.status_code in (429, 503):
            wait = 2 ** attempt * 5   # 5s, 10s, 20s
            print(f"  Rate limited ({resp.status_code}), retrying in {wait}s…")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        break

    candidates = resp.json().get("candidates", [])
    if not candidates:
        return ""

    parts = candidates[0].get("content", {}).get("parts", [])
    return parts[0].get("text", "").strip() if parts else ""
