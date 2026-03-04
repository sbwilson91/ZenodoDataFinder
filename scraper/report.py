# scraper/report.py
from datetime import datetime, date
from .feeds import Paper
from collections import defaultdict
import re, os

def _matches_watchlist(paper: Paper, watchlist: list[str]) -> bool:
    """C1 — Return True if title or abstract contains any watchlist term."""
    haystack = (paper.title + " " + paper.abstract).lower()
    return any(term.lower() in haystack for term in watchlist)

def generate_report(papers: list[Paper], config: dict, output_path: str) -> None:
    """
    Build the markdown digest.
    Watchlist-matching papers appear first under ## ⭐ Featured Papers,
    then the rest follow in their usual category sections.
    """
    watchlist = config.get("watchlist", [])
    featured = [p for p in papers if _matches_watchlist(p, watchlist)]
    rest     = [p for p in papers if not _matches_watchlist(p, watchlist)]

    today = date.today().isoformat()
    lines = [f"# Weekly Journal Digest — {today}\n",
             f"**{len(papers)} new papers** across "
             f"{len({p.journal for p in papers})} journals.\n"]

    # --- Featured section (C1) ---
    if featured:
        lines.append("---\n## ⭐ Featured Papers\n")
        lines.append(
            f"> Matched watchlist terms: "
            f"{', '.join(f'`{t}`' for t in watchlist)}\n"
        )
        for paper in featured:
            lines.append(_format_paper(paper))

    # --- Remaining papers by category ---
    lines.append("---\n## All Papers\n")
    for paper in rest:
        lines.append(_format_paper(paper))

    return "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content)
    print(f"  Report written to {output_path}")


def _format_paper(paper: Paper) -> str:
    """Render a single paper entry — matches your existing digest format."""
    sig_icon = {"High": "🔴 **High impact**",
                "Medium": "🟡 Medium",
                "Low": "⚪ Routine"}.get(
        getattr(paper, "significance", "Medium"), "🟡 Medium"
    )
    repos_line = ""
    if paper.repos:
        links = " · ".join(f"[repo]({r})" for r in paper.repos)
        repos_line = f"\n**Code/Data:** {links}"

    topics_line = ""
    if paper.categories:
        topics_line = "\n**Topics:** " + " · ".join(
            f"`{c}`" for c in paper.categories
        )

    return (
        f"### {paper.title}\n"
        f"**{paper.journal}** | {paper.authors}  \n"
        f"*Published: {paper.published.strftime('%-d %b %Y')}* | {sig_icon}  \n"
        f"[Full paper]({paper.url})\n"
        f"\n> {paper.summary or 'Summary unavailable.'}\n"
        f"{topics_line}{repos_line}\n\n---\n"
    )


def update_archive_index(digest_path: str, paper_count: int) -> None:
    """
    C2 — Append a line to digests/index.md for the new digest.
    Creates the file with a header if it doesn't exist yet.
    """
    index_path = os.path.join(os.path.dirname(digest_path), "index.md")
    digest_name = os.path.basename(digest_path)
    today = date.today().isoformat()

    header = (
        "# Weekly Digest Archive\n\n"
        "| Date | Papers | File |\n"
        "|------|--------|------|\n"
    )

    new_row = f"| {today} | {paper_count} | [{digest_name}](./{digest_name}) |\n"

    if not os.path.isfile(index_path):
        with open(index_path, "w") as f:
            f.write(header)

    with open(index_path, "a") as f:
        f.write(new_row)

    print(f"  Archive index updated: {index_path}")


