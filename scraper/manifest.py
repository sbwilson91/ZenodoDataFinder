# scraper/manifest.py
import json
import os
import re
from datetime import date
from .feeds import Paper

MANIFEST_PATH = "docs/manifest.json"


def update_manifest(papers: list[Paper], digest_html_name: str, config: dict) -> None:
    """
    E3 — Append metadata for this week's digest to docs/manifest.json.
    Creates the file if it doesn't exist.
    """
    watchlist = config.get("watchlist", [])
    today     = date.today().isoformat()

    # Build per-paper metadata — only fields needed by the dashboard
    paper_entries = []
    for p in papers:
        haystack = (p.title + " " + p.abstract).lower()
        watchlist_match = any(t.lower() in haystack for t in watchlist)
        paper_entries.append({
            "title":          p.title,
            "journal":        p.journal,
            "authors":        p.authors,
            "url":            p.url,
            "doi":            p.doi,
            "published":      p.published.isoformat() if p.published else None,
            "significance":   getattr(p, "significance", "Medium"),
            "summary":        p.summary or "",
            "categories":     p.categories,
            "watchlist_match": watchlist_match,
            "cluster_label": getattr(p, "cluster_label", None),
        })

    entry = {
        "date":         today,
        "html_file":    digest_html_name,
        "paper_count":  len(papers),
        "high_count":   sum(1 for p in papers if getattr(p, "significance", "") == "High"),
        "featured_count": sum(1 for p in paper_entries if p["watchlist_match"]),
        "papers":       paper_entries,
    }

    # Load existing manifest or start fresh
    if os.path.isfile(MANIFEST_PATH):
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = []

    # Replace entry for today if re-running, otherwise append
    manifest = [m for m in manifest if m["date"] != today]
    manifest.append(entry)
    manifest.sort(key=lambda x: x["date"], reverse=True)

    os.makedirs("docs", exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"  Manifest updated: {MANIFEST_PATH} ({len(manifest)} digests)")
