# scraper/trends.py
import csv
import os
from collections import Counter
from datetime import date, datetime, timezone
from typing import Optional

import yaml

from .feeds import Paper


# ── helpers ──────────────────────────────────────────────────────────────────

def _get_tag_counts(papers: list[Paper], watchlist: list[str]) -> Counter:
    counts: Counter = Counter()
    for paper in papers:
        # LLM-assigned categories
        for tag in paper.categories:
            if tag:
                counts[tag.lower().strip()] += 1
        # Watchlist keyword hits
        haystack = (paper.title + " " + paper.abstract).lower()
        for term in watchlist:
            if term.lower() in haystack:
                counts[term.lower()] += 1
        # E1 — cluster labels
        if getattr(paper, "cluster_label", None):
            counts[f"cluster:{paper.cluster_label.lower()}"] += 1

    return counts


# ── public API ────────────────────────────────────────────────────────────────

TRENDS_DIR  = "trends"
COUNTS_FILE = os.path.join(TRENDS_DIR, "tag_counts.csv")


def log_tag_counts(papers: list[Paper], config: dict) -> None:
    """
    E2 — Append one row per tag to trends/tag_counts.csv.
    Called at the end of every run.
    """
    watchlist    = config.get("watchlist", [])
    counts       = _get_tag_counts(papers, watchlist)
    today        = date.today().isoformat()
    total_papers = len(papers)

    os.makedirs(TRENDS_DIR, exist_ok=True)
    file_exists = os.path.isfile(COUNTS_FILE)

    with open(COUNTS_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "tag", "count", "total_papers"])
        for tag, count in sorted(counts.items()):
            writer.writerow([today, tag, count, total_papers])

    print(f"  Trend data logged: {len(counts)} tags → {COUNTS_FILE}")


def maybe_write_monthly_report(config: dict) -> Optional[str]:
    """
    E2 — On the first run of a new month, read the last 5 weeks of
    tag_counts.csv and write a trends/YYYY-MM.md report.
    Returns the report path if written, else None.
    """
    if not os.path.isfile(COUNTS_FILE):
        return None

    try:
        import pandas as pd
    except ImportError:
        print("  pandas not installed — skipping monthly trend report")
        return None

    today     = date.today()
    report_path = os.path.join(TRENDS_DIR, f"{today.strftime('%Y-%m')}.md")

    # Only write once per month (skip if report already exists)
    if os.path.isfile(report_path):
        return None

    df = pd.read_csv(COUNTS_FILE, parse_dates=["date"])
    if df.empty:
        return None

    # Split into "this month" vs "previous month"
    this_month  = df[df["date"].dt.to_period("M") == pd.Period(today, "M")]
    prev_month  = df[df["date"].dt.to_period("M") == pd.Period(today, "M") - 1]

    if this_month.empty or prev_month.empty:
        return None

    this = this_month.groupby("tag")["count"].sum()
    prev = prev_month.groupby("tag")["count"].sum()

    # All tags seen in either month
    all_tags = set(this.index) | set(prev.index)

    deltas = {}
    for tag in all_tags:
        c = this.get(tag, 0)
        p = prev.get(tag, 0)
        if p == 0:
            pct = 100.0 if c > 0 else 0.0
        else:
            pct = ((c - p) / p) * 100
        deltas[tag] = {"this": int(c), "prev": int(p), "pct": round(pct, 1)}

    rising  = sorted([(t, d) for t, d in deltas.items() if d["pct"] >  15 and d["this"] >= 2],
                     key=lambda x: -x[1]["pct"])
    falling = sorted([(t, d) for t, d in deltas.items() if d["pct"] < -15 and d["prev"] >= 2],
                     key=lambda x:  x[1]["pct"])
    stable  = [(t, d) for t, d in deltas.items()
               if abs(d["pct"]) <= 15 and d["this"] >= 2]

    this_total = int(this_month["total_papers"].max()) if "total_papers" in this_month else "?"
    prev_total = int(prev_month["total_papers"].max()) if "total_papers" in prev_month else "?"

    lines = [
        f"# Trend Report — {today.strftime('%B %Y')}\n",
        f"Comparing **{today.strftime('%B')}** vs "
        f"**{(pd.Period(today, 'M') - 1).strftime('%B %Y')}**\n",
        f"Papers this month: ~{this_total} | Last month: ~{prev_total}\n",
        "---\n",
    ]

    if rising:
        lines.append("## Rising ↑\n")
        for tag, d in rising[:10]:
            arrow = f"+{d['pct']}%" if d['pct'] > 0 else f"{d['pct']}%"
            lines.append(f"- **{tag}**: {d['this']} mentions ({arrow} vs last month)\n")
        lines.append("\n")

    if falling:
        lines.append("## Falling ↓\n")
        for tag, d in falling[:10]:
            lines.append(f"- **{tag}**: {d['this']} mentions ({d['pct']}% vs last month)\n")
        lines.append("\n")

    if stable:
        lines.append("## Stable →\n")
        for tag, d in sorted(stable, key=lambda x: -x[1]["this"])[:10]:
            lines.append(f"- **{tag}**: {d['this']} mentions\n")
        lines.append("\n")

    os.makedirs(TRENDS_DIR, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"  Monthly trend report written: {report_path}")
    return report_path
