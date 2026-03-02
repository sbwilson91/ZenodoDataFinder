"""
scraper/summarise.py
"""

import os
import re
import json
import time
import requests
from typing import Optional

from .feeds import Paper

HF_CHAT_URL    = "https://router.huggingface.co/hf-inference/v1/chat/completions"
DEFAULT_MODEL  = "Qwen/Qwen2.5-7B-Instruct"
FALLBACK_MODEL = "microsoft/Phi-3.5-mini-instruct"
MAX_RETRIES    = 3

SYSTEM_PROMPT = (
    "You are a scientific literature analyst helping researchers stay current "
    "with recent publications. You are precise, use domain-appropriate language, "
    "and never invent information not present in the abstract."
)

def _build_user_prompt(papers):
    papers_text = ""
    for i, p in enumerate(papers, 1):
        repo_str = ", ".join(p.repos)    if p.repos    else "None found"
        kw_str   = ", ".join(p.keywords) if p.keywords else "Not provided"
        papers_text += (
            f"\n--- PAPER {i} ---\n"
            f"Title: {p.title}\n"
            f"Authors: {p.authors}\n"
            f"Journal: {p.journal}\n"
            f"Author Keywords: {kw_str}\n"
            f"Repositories: {repo_str}\n"
            f"Abstract: {p.abstract[:1500]}\n"
        )
    return (
        f"Below are {len(papers)} recent scientific papers.\n"
        f"Return a JSON array with exactly {len(papers)} objects, each containing:\n"
        f'  "summary"      : 3-4 sentence plain-English summary of key finding and significance\n'
        f'  "categories"   : list of 2-4 broad topic tags (e.g. "single-cell genomics", "CRISPR",\n'
        f'                   "machine learning", "organoids", "epigenetics", "protein structure")\n'
        f'  "key_terms"    : list of 4-6 important technical terms\n'
        f'  "significance" : one of "High", "Medium", or "Low"\n'
        f'  "repos"        : list of any repository URLs mentioned (copy exactly, never invent)\n\n'
        f"Return ONLY a valid JSON array. No explanation, no markdown fences, no other text.\n"
        f"{papers_text}"
    )

def _call_hf_chat(user_prompt, model_id, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": 2048,
        "temperature": 0.2,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.post(HF_CHAT_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]
        elif resp.status_code == 503:
            wait = 25 * attempt
            print(f"    Model loading — waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(wait)
        elif resp.status_code == 429:
            wait = 60 * attempt
            print(f"    Rate limited — waiting {wait}s...")
            time.sleep(wait)
        else:
            raise RuntimeError(
                f"HF API error {resp.status_code} for model '{model_id}': {resp.text[:300]}"
            )
    raise RuntimeError(f"HF API failed after {MAX_RETRIES} attempts.")

def _extract_json(raw):
    raw = re.sub(r"```(?:json)?", "", raw).strip()
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array in response. Got: {raw[:200]}")
    return json.loads(raw[start:end + 1])

def _empty_result():
    return {
        "summary": "Summary unavailable.",
        "categories": [],
        "key_terms": [],
        "significance": "Medium",
        "repos": [],
    }

def summarise_papers(papers, hf_token, model_id=None, batch_size=5):
    model = model_id or os.environ.get("HF_MODEL", DEFAULT_MODEL)
    print(f"  Using model: {model}")

    for batch_start in range(0, len(papers), batch_size):
        batch = papers[batch_start:batch_start + batch_size]
        label = f"{batch_start + 1}–{batch_start + len(batch)}"
        print(f"  Summarising papers {label} of {len(papers)}...")

        user_prompt = _build_user_prompt(batch)
        results = None

        for attempt_model in [model, FALLBACK_MODEL]:
            try:
                raw     = _call_hf_chat(user_prompt, attempt_model, hf_token)
                results = _extract_json(raw)
                while len(results) < len(batch):
                    results.append(_empty_result())
                results = results[:len(batch)]
                break
            except (RuntimeError, ValueError, json.JSONDecodeError) as e:
                print(f"    Error with {attempt_model}: {e}")
                if attempt_model == FALLBACK_MODEL:
                    results = [_empty_result() for _ in batch]
                else:
                    print(f"    Retrying with fallback: {FALLBACK_MODEL}...")

        for paper, result in zip(batch, results):
            paper.summary       = result.get("summary", "")
            paper.categories    = result.get("categories", [])
            paper.keywords      = result.get("key_terms", paper.keywords)
            paper.repos         = sorted(set(paper.repos + result.get("repos", [])))
            paper._significance = result.get("significance", "Medium")

        if batch_start + batch_size < len(papers):
            time.sleep(3)

    return papers
