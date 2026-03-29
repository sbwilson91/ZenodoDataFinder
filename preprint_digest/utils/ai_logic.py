"""Local Ollama AI summarization utility (OpenAI-compatible API)."""
import re
import time
import requests

OLLAMA_URL    = "http://localhost:11434/v1/chat/completions"
DEFAULT_MODEL = "llama3.1"
MAX_RETRIES   = 3

SYSTEM_PROMPT = (
    "You are a scientific literature analyst. "
    "Summarize the provided abstract in 2-3 plain-English sentences, "
    "focusing on the key finding and its significance. "
    "Never invent information not present in the abstract."
)


def _call_chat(text, model_id):
    headers = {"Content-Type": "application/json"}
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
        try:
            resp = requests.post(OLLAMA_URL, headers=headers, json=payload, timeout=120)
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Ollama is not running — start it with: ollama serve")
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        elif resp.status_code == 429:
            wait = 30 * attempt
            print(f"Ollama busy — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
        else:
            raise RuntimeError(
                f"Ollama error {resp.status_code} for model '{model_id}': {resp.text[:200]}"
            )
    raise RuntimeError(f"Ollama failed after {MAX_RETRIES} attempts.")


def get_ai_summary(text, hf_token=None, model_url=None):
    """Summarize text using local Ollama (llama3.1).

    Args:
        text:      Raw text (HTML tags will be stripped). Truncated to 1500 chars.
        hf_token:  Ignored (kept for backwards-compatible signature).
        model_url: Ignored (kept for backwards-compatible signature).

    Returns:
        Summary string, or a descriptive fallback message.
    """
    clean_text = re.sub(r"<[^<]+?>", "", text).strip()
    if len(clean_text) < 50:
        return "Description too short for summary."

    try:
        return _call_chat(clean_text, DEFAULT_MODEL)
    except RuntimeError as e:
        print(f"  Ollama summary failed: {e}")

    return "AI summary unavailable."
