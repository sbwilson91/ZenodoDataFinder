"""
scraper/summarise.py
────────────────────
Summarisation via HuggingFace Inference API.
Default model: mistralai/Mistral-7B-Instruct-v0.3

Drop-in replacement for the previous Anthropic-based module — the
public interface (summarise_papers) is identical, so nothing else
in the pipeline needs to change.

Environment variables expected:
  HF_API_TOKEN   — your HuggingFace access token
  HF_MODEL       — (optional) override the default model ID
"""

import os
import re
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional

from .feeds import Paper  # relative import — adjust if running standalone

# ── Model configuration ────────────────────────────────────────────────────────

DEFAULT_MODEL   = "mistralai/Mistral-7B-Instruct-v0.3"
HF_API_BASE     = "https://api-inference.huggingface.co/models"

# Fallback model tried automatically if the primary returns an error.
# Zephyr is also free-tier and has strong instruction-following.
FALLBACK_MODEL  = "HuggingFaceH4/zephyr-7b-beta"

# How long to wait (seconds) if HF returns a 503 "model loading" response.
MODEL_LOAD_WAIT = 25
MAX_RETRIES     = 3

# ── Prompt templates ───────────────────────────────────────────────────────────
# Mistral-Instruct uses [INST] ... [/INST] chat tokens.
# Zephyr uses <|system|> / <|user|> / <|assistant|>.
# We detect which format to use from the model name.

SYSTEM_CONTENT = (
    "You are a scientific literature analyst helping researchers stay current "
    "with recent publications. You are precise, use domain-appropriate language, "
    "and never invent information not present in the abstract."
)

def _build_user_content(papers: list["Paper"]) -> str:
    """Build the user-facing part of the prompt for a batch of papers."""
    papers_text = ""
    for i, p in enumerate(papers, 1):
        repo_str = ", ".join(p.repos)  if p.repos    else "None found"
        kw_str   = ", ".join(p.keywords) if p.keywords else "Not provided"
        papers_text += (
            f"\n--- PAPER {i} ---\n"
            f"Title: {p.title}\n"
            f"Authors: {p.authors}\n"
            f"Journal: {p.journal}\n"
            f"Author Keywords: {kw_str}\n"
            f"Code/Data Repositories: {repo_str}\n"
            f"Abstract: {p.abstract[:1500]}\n"   # cap to manage token budget
        )

    return (
        f"Below are {len(papers)} recent scientific papers.\n"
        f"For EACH paper return a JSON object with exactly these fields:\n"
        f'  "summary"      : 3-4 sentence plain-English summary of the key finding and its significance\n'
        f'  "categories"   : list of 2-4 broad topic tags (e.g. "single-cell genomics", "CRISPR",\n'
        f'                   "machine learning", "organoids", "epigenetics", "protein structure")\n'
        f'  "key_terms"    : list of 4-6 important technical terms from the paper\n'
        f'  "significance" : one of "High", "Medium", or "Low" — your assessment of novelty/impact\n'
        f'  "repos"        : list of any code/data repository URLs mentioned (copy from above, never invent)\n\n'
        f"Return ONLY a valid JSON array containing exactly {len(papers)} objects. "
        f"No explanation, no markdown fences, no other text.\n"
        f"{papers_text}"
    )


def _format_prompt_mistral(system: str, user: str) -> str:
    """Mistral-Instruct chat format."""
    return f"<s>[INST] {system}\n\n{user} [/INST]"


def _format_prompt_zephyr(system: str, user: str) -> str:
    """Zephyr / ChatML-style format."""
    return (
        f"<|system|>\n{system}</s>\n"
        f"<|user|>\n{user}</s>\n"
        f"<|assistant|>\n"
    )


def _build_prompt(model_id: str, system: str, user: str) -> str:
    if "zephyr" in model_id.lower():
        return _format_prompt_zephyr(system, user)
    # Default: Mistral-style [INST] tokens — also works for Llama-3-instruct
    return _format_prompt_mistral(system, user)


# ── HF Inference API call ──────────────────────────────────────────────────────

def _call_hf_api(prompt: str, model_id: str, token: str) -> str:
    """
    POST to the HuggingFace Inference API and return the generated text.
    Handles:
      - 503  model loading → waits MODEL_LOAD_WAIT seconds, retries
      - 429  rate limit    → backs off exponentially
      - non-200 errors     → raises RuntimeError
    """
    url     = f"{HF_API_BASE}/{model_id}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 1024,
            "temperature": 0.2,          # Low temp = deterministic, structured output
            "return_full_text": False,   # Only return the completion, not the prompt
            "do_sample": True,
        },
        "options": {
            "wait_for_model": True,      # Block until model is loaded (avoids 503 loops)
            "use_cache": False,          # We want fresh summaries each run
        }
    }

    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(url, headers=headers, json=payload, timeout=120)

        if resp.status_code == 200:
            data = resp.json()
            # HF returns a list of dicts: [{"generated_text": "..."}]
            if isinstance(data, list) and data:
                return data[0].get("generated_text", "")
            raise RuntimeError(f"Unexpected response shape: {data}")

        elif resp.status_code == 503:
            # Model is warming up — HF usually loads within 20-30s
            wait = MODEL_LOAD_WAIT * attempt
            print(f"    Model loading (503) — waiting {wait}s before retry {attempt}/{MAX_RETRIES}...")
            time.sleep(wait)

        elif resp.status_code == 429:
            wait = 60 * attempt   # Rate limited — back off more aggressively
            print(f"    Rate limited (429) — waiting {wait}s...")
            time.sleep(wait)

        else:
            raise RuntimeError(
                f"HF API error {resp.status_code} for model '{model_id}': {resp.text[:300]}"
            )

    raise RuntimeError(f"HF API failed after {MAX_RETRIES} attempts for model '{model_id}'.")


# ── JSON extraction ────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> list[dict]:
    """
    LLMs sometimes wrap JSON in markdown fences or add a preamble sentence.
    This function strips all of that and returns a parsed list.
    """
    # Strip markdown fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip()

    # Find the first [ ... ] block
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No JSON array found in model output.")

    return json.loads(raw[start:end + 1])


def _empty_result() -> dict:
    return {
        "summary": "Summary unavailable.",
        "categories": [],
        "key_terms": [],
        "significance": "Medium",
        "repos": [],
    }


# ── Public API ─────────────────────────────────────────────────────────────────

def summarise_papers(
    papers: list["Paper"],
    hf_token: str,
    model_id: Optional[str] = None,
    batch_size: int = 5,          # Smaller batches than Anthropic — HF context windows vary
) -> list["Paper"]:
    """
    Summarise a list of Paper objects using the HuggingFace Inference API.

    Parameters
    ----------
    papers     : list of Paper dataclasses (mutated in-place)
    hf_token   : HuggingFace access token (os.environ["HF_API_TOKEN"])
    model_id   : HF model repo ID. Defaults to DEFAULT_MODEL or HF_MODEL env var.
    batch_size : Papers per API call. Keep ≤5 for 7B models to avoid truncation.

    Returns
    -------
    The same list of Paper objects with .summary, .categories, .keywords,
    .repos, and ._significance populated.
    """
    model = model_id or os.environ.get("HF_MODEL", DEFAULT_MODEL)
    print(f"  Using model: {model}")

    for batch_start in range(0, len(papers), batch_size):
        batch = papers[batch_start:batch_start + batch_size]
        label = f"{batch_start + 1}–{batch_start + len(batch)}"
        print(f"  Summarising papers {label} of {len(papers)}...")

        user_content = _build_user_content(batch)
        prompt       = _build_prompt(model, SYSTEM_CONTENT, user_content)

        results = None
        for attempt_model in [model, FALLBACK_MODEL]:
            try:
                raw     = _call_hf_api(prompt, attempt_model, hf_token)
                results = _extract_json(raw)
                if len(results) != len(batch):
                    # Model returned wrong number of items — pad or trim
                    print(f"    Warning: got {len(results)} results for {len(batch)} papers. Padding.")
                    while len(results) < len(batch):
                        results.append(_empty_result())
                    results = results[:len(batch)]
                break   # Success — no need to try fallback

            except (RuntimeError, ValueError, json.JSONDecodeError) as e:
                print(f"    Error with {attempt_model}: {e}")
                if attempt_model == FALLBACK_MODEL:
                    # Both models failed — fill with empty results so run continues
                    results = [_empty_result() for _ in batch]
                else:
                    print(f"    Retrying with fallback model: {FALLBACK_MODEL}...")
                    prompt = _build_prompt(FALLBACK_MODEL, SYSTEM_CONTENT, user_content)

        # Apply results back onto Paper objects
        for paper, result in zip(batch, results):
            paper.summary    = result.get("summary", "")
            paper.categories = result.get("categories", [])
            paper.keywords   = result.get("key_terms", paper.keywords)
            # Merge any repo URLs the LLM found with those already extracted by regex
            paper.repos      = sorted(set(paper.repos + result.get("repos", [])))
            paper._significance = result.get("significance", "Medium")

        # Courteous delay between batches — HF free tier is rate-limited
        if batch_start + batch_size < len(papers):
            time.sleep(3)

    return papers
