"""HuggingFace AI summarization utility (chat completions router)."""
import os
import re
import time
import requests

HF_CHAT_URL    = "https://router.huggingface.co/v1/chat/completions"
DEFAULT_MODEL  = "meta-llama/Llama-3.1-8B-Instruct:cerebras"
FALLBACK_MODEL = "Qwen/Qwen2.5-7B-Instruct:cerebras"
MAX_RETRIES    = 3

SYSTEM_PROMPT = (
    "You are a scientific literature analyst. "
    "Summarize the provided abstract in 2-3 plain-English sentences, "
    "focusing on the key finding and its significance. "
    "Never invent information not present in the abstract."
)


def _call_chat(text, model_id, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": text[:1500]},
        ],
        "max_tokens": 256,
        "temperature": 0.2,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(HF_CHAT_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        elif resp.status_code == 503:
            wait = 25 * attempt
            print(f"Model loading — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
        elif resp.status_code == 429:
            wait = 60 * attempt
            print(f"Rate limited — waiting {wait}s...")
            time.sleep(wait)
        else:
            raise RuntimeError(
                f"HF API error {resp.status_code} for model '{model_id}': {resp.text[:200]}"
            )
    raise RuntimeError(f"HF API failed after {MAX_RETRIES} attempts.")


def get_ai_summary(text, hf_token=None, model_url=None):
    """Summarize text using HuggingFace chat completions router (Llama-3.1-8B).

    Args:
        text:      Raw text (HTML tags will be stripped). Truncated to 1500 chars.
        hf_token:  HuggingFace API token. Defaults to HF_TOKEN env var.
        model_url: Unused; kept for backwards-compatible signature.

    Returns:
        Summary string, or a descriptive fallback message.
    """
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        return "No AI token provided."

    clean_text = re.sub(r"<[^<]+?>", "", text).strip()
    if len(clean_text) < 50:
        return "Description too short for summary."

    for model_id in [DEFAULT_MODEL, FALLBACK_MODEL]:
        try:
            return _call_chat(clean_text, model_id, token)
        except RuntimeError as e:
            print(f"  [{model_id}] failed: {e}")
            if model_id != FALLBACK_MODEL:
                print(f"  Retrying with fallback: {FALLBACK_MODEL}...")

    return "AI summary unavailable."
