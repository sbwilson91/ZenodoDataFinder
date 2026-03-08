"""HuggingFace AI summarization utility."""
import os
import re
import time
import requests

DEFAULT_MODEL_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"


def get_ai_summary(text, hf_token=None, model_url=None):
    """Summarize text using HuggingFace Inference API (BART-large-CNN).

    Args:
        text:      Raw text (HTML tags will be stripped). Truncated to 1024 chars.
        hf_token:  HuggingFace API token. Defaults to HF_TOKEN env var.
        model_url: Override the model endpoint URL.

    Returns:
        Summary string, or a descriptive fallback message.
    """
    token = hf_token or os.environ.get("HF_TOKEN")
    if not token:
        return "No AI Token provided."

    api_url = model_url or DEFAULT_MODEL_URL
    headers = {"Authorization": f"Bearer {token}"}
    clean_text = re.sub(r"<[^<]+?>", "", text).strip()[:1024]

    if len(clean_text) < 50:
        return "Description too short for summary."

    for attempt in range(3):
        try:
            response = requests.post(
                api_url, headers=headers,
                json={"inputs": clean_text}, timeout=30
            )
            try:
                res_json = response.json()
            except ValueError:
                print(f"HuggingFace returned non-JSON (status {response.status_code})")
                return "AI Summary unavailable."

            if isinstance(res_json, list) and len(res_json) > 0:
                return res_json[0].get("summary_text", "Summary content missing.")
            elif isinstance(res_json, dict) and "estimated_time" in res_json:
                wait = min(res_json["estimated_time"], 30)
                print(f"Model loading, waiting {wait:.0f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            elif isinstance(res_json, dict) and "error" in res_json:
                print(f"HuggingFace error: {res_json['error']}")
                return "AI Summary unavailable."
        except Exception as e:
            print(f"HuggingFace request failed: {e}")

    return "AI Summary unavailable."
