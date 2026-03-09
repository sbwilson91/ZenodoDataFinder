"""bioRxiv preprint digest bot.

Fetches recent bioRxiv preprints, filters by a user-defined watchlist,
generates AI summaries, writes a Markdown digest, and converts it to HTML
for email delivery via GitHub Actions.
"""
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from fetcher import fetch_recent, filter_by_watchlist
from utils.ai_logic import get_ai_summary

DIGESTS_DIR  = Path("digests")
WATCHLIST    = Path("watchlist.txt")
DAYS_BACK    = int(os.environ.get("DAYS_BACK", 7))


def load_watchlist(path=WATCHLIST) -> list:
    """Read watchlist file; skip blank lines and # comments."""
    if not path.exists():
        print(f"Warning: {path} not found. Using empty watchlist.")
        return []
    topics = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            topics.append(stripped)
    return topics


def _format_paper(p) -> str:
    """Format a single Preprint as a Markdown paper card."""
    date_str = p.date.strftime("%Y-%m-%d") if p.date.year > 1970 else "Date unknown"
    title_link = f"[{p.title}]({p.url})" if p.url else p.title
    authors_short = p.authors[:120] + "..." if len(p.authors) > 120 else p.authors
    category = p.category.title() if p.category else "Preprint"
    summary = p.summary if p.summary else "Summary unavailable."

    return (
        f"### {title_link}\n"
        f"**{authors_short}** | {category} | {date_str}\n\n"
        f"> {summary}\n"
    )


def build_digest(matched: dict, today: str, total_fetched: int) -> str:
    """Build a full Markdown digest string from matched preprints."""
    total_matched = sum(len(ps) for ps in matched.values())
    topic_count = len(matched)

    lines = [
        f"# Preprint Digest — {today}",
        f"_{total_matched} paper{'s' if total_matched != 1 else ''} matched "
        f"across {topic_count} topic{'s' if topic_count != 1 else ''} "
        f"({total_fetched} preprints scanned)_",
        "",
        "---",
        "",
    ]

    for topic, papers in matched.items():
        lines.append(f"## {topic}")
        lines.append("")
        for p in papers:
            lines.append(_format_paper(p))
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def run():
    topics = load_watchlist()
    if not topics:
        print("No topics in watchlist. Exiting.")
        return

    print(f"Watchlist: {topics}")

    # Fetch and filter
    preprints = fetch_recent(days_back=DAYS_BACK)
    matched   = filter_by_watchlist(preprints, topics)

    if not matched:
        print("No preprints matched any watchlist topic.")
        # Write a brief digest so the commit step doesn't fail silently
        today = date.today().isoformat()
        content = (
            f"# Preprint Digest — {today}\n\n"
            f"_No preprints matched any watchlist topic this week "
            f"({len(preprints)} scanned)._\n"
        )
    else:
        total_matched = sum(len(ps) for ps in matched.values())
        print(f"Matched {total_matched} preprints across {len(matched)} topics. Summarising...")

        hf_token = os.environ.get("HF_TOKEN")
        for topic, papers in matched.items():
            for p in papers:
                if len(p.abstract) >= 50:
                    p.summary = get_ai_summary(p.abstract, hf_token=hf_token)

        today   = date.today().isoformat()
        content = build_digest(matched, today, len(preprints))

    # Save Markdown digest
    DIGESTS_DIR.mkdir(exist_ok=True)
    digest_path = DIGESTS_DIR / f"{today}-preprint-digest.md"
    digest_path.write_text(content, encoding="utf-8")
    print(f"Digest saved → {digest_path}")

    # Convert to HTML for email
    html_script = Path(__file__).parent / "utils" / "md_to_html_email.py"
    result = subprocess.run(
        [sys.executable, str(html_script), str(digest_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"HTML conversion failed: {result.stderr}")
    else:
        print(result.stdout.strip())


if __name__ == "__main__":
    run()
