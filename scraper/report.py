# scraper/report.py
from datetime import datetime
from .feeds import Paper
from collections import defaultdict

def generate_report(papers: list[Paper], output_path: str) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Sort: High significance first, then by journal, then by title
    sig_order = {"High": 0, "Medium": 1, "Low": 2}
    papers.sort(key=lambda p: (
        sig_order.get(getattr(p, "_significance", "Medium"), 1),
        p.journal,
        p.title
    ))

    # Group papers by their broad categories for the table of contents
    by_category = defaultdict(list)
    for paper in papers:
        primary = paper.categories[0] if paper.categories else "Uncategorised"
        by_category[primary].append(paper)

    lines = [
        f"# Weekly Journal Digest — {today}",
        f"\n**{len(papers)} new papers** across {len(set(p.journal for p in papers))} journals.\n",
        "---\n",
        "## Table of Contents\n",
    ]

    # Build TOC
    for cat in sorted(by_category.keys()):
        anchor = cat.lower().replace(" ", "-").replace("/", "")
        lines.append(f"- [{cat}](#{anchor}) ({len(by_category[cat])} papers)")

    lines.append("\n---\n")

    # Build each section
    for cat in sorted(by_category.keys()):
        lines.append(f"## {cat}\n")
        for paper in by_category[cat]:
            sig = getattr(paper, "_significance", "")
            sig_badge = {"High": "🔴 **High impact**", "Medium": "🟡 Medium", 
                        "Low": "⚪ Routine"}.get(sig, "")
            
            lines.append(f"### {paper.title}")
            lines.append(f"**{paper.journal}** | {paper.authors}  ")
            lines.append(f"*Published: {paper.published.strftime('%d %b %Y')}* | {sig_badge}  ")
            lines.append(f"[Full paper]({paper.url})")
            if paper.doi:
                lines.append(f" | DOI: `{paper.doi}`")
            lines.append("\n")
            
            if paper.summary:
                lines.append(f"> {paper.summary}\n")
            
            if paper.categories:
                lines.append(f"**Topics:** {' · '.join(f'`{c}`' for c in paper.categories)}  ")
            if paper.keywords:
                lines.append(f"**Key terms:** {', '.join(paper.keywords)}  ")
            if paper.repos:
                lines.append("\n**Code & Data:**")
                for repo in paper.repos:
                    lines.append(f"- {repo}")
            lines.append("\n---\n")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report written to {output_path}")