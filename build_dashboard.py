#!/usr/bin/env python3
"""
build_dashboard.py  (repo root)

Reads the latest output from every bot and generates docs/index.html —
a unified hub page served via GitHub Pages.

Run by .github/workflows/build_dashboard.yml after any bot completes.
Also called locally with: python build_dashboard.py
"""

import re
import json
import glob
import shutil
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT  = Path(__file__).parent
DOCS       = REPO_ROOT / "docs"
DOCS.mkdir(exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def fmt_age(date_str: str) -> tuple[str, str]:
    """Return (human label, css colour) for a YYYY-MM-DD date string."""
    try:
        d   = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        days = (now - d).days
        if   days == 0: return "today",            "#22c55e"
        elif days == 1: return "yesterday",         "#22c55e"
        elif days <= 7: return f"{days} days ago",  "#22c55e"
        elif days <= 14: return f"{days} days ago", "#f59e0b"
        else:            return f"{days} days ago", "#ef4444"
    except Exception:
        return date_str, "#64748b"


def strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


# ── per-bot extractors ────────────────────────────────────────────────────────

def extract_running_bot() -> dict:
    reports = sorted(
        (REPO_ROOT / "running_bot" / "reports").glob("report_*.html"),
        reverse=True
    )
    if not reports:
        return {"available": False}

    f    = reports[0]
    date = f.stem.replace("report_", "")
    text = f.read_text(encoding="utf-8")

    headline = ""
    m = re.search(r'class="ai-headline-text"[^>]*>(.*?)</div>', text, re.DOTALL)
    if m:
        headline = strip_tags(m.group(1))

    stats = {}
    for hm in re.finditer(
        r'class="hs-l"[^>]*>(.*?)</span>.*?class="hs-v[^"]*"[^>]*>(.*?)</span>',
        text, re.DOTALL
    ):
        k = strip_tags(hm.group(1))
        v = strip_tags(hm.group(2))
        if k and v and k not in stats:
            stats[k] = v

    # Copy latest report to docs/ for Pages serving
    dest = DOCS / "running.html"
    shutil.copy(f, dest)

    # Also copy archive
    archive_dir = DOCS / "running_archive"
    archive_dir.mkdir(exist_ok=True)
    shutil.copy(f, archive_dir / f.name)

    # Build archive list
    archive = [
        {"date": p.stem.replace("report_", ""), "file": f"running_archive/{p.name}"}
        for p in sorted(reports, reverse=True)[:12]
    ]

    return {
        "available": True,
        "date":      date,
        "headline":  headline,
        "stats":     stats,
        "link":      "running.html",
        "archive":   archive,
    }


def extract_journal_digest() -> dict:
    digests = sorted(
        (REPO_ROOT / "journal_digest" / "digests").glob("*.md"),
        reverse=True
    )
    if not digests:
        return {"available": False}

    f    = digests[0]
    date = f.stem[:10] if len(f.stem) >= 10 else f.stem
    text = f.read_text(encoding="utf-8")

    # Count papers (## headings that look like paper titles)
    paper_count = len(re.findall(r"^## ", text, re.MULTILINE))

    # First H1 or first non-empty line as title
    title_m = re.search(r"^# (.+)$", text, re.MULTILINE)
    title   = title_m.group(1).strip() if title_m else "Weekly Digest"

    # Extract first meaningful paragraph as preview
    paras   = [p.strip() for p in text.split("\n\n") if p.strip() and not p.startswith("#")]
    preview = paras[0][:200] + "…" if paras else ""

    # Copy latest HTML if it exists in docs/
    html_src = DOCS / "index.html"   # existing Pages output from digest
    dest     = DOCS / "journal.html"
    if html_src.exists() and html_src != dest:
        shutil.copy(html_src, dest)

    # Archive list
    archive = [
        {"date": p.stem[:10], "file": f"journal_digests/{p.name}"}
        for p in sorted(digests, reverse=True)[:12]
    ]

    # Copy markdown files for archive browsing
    arc_dir = DOCS / "journal_digests"
    arc_dir.mkdir(exist_ok=True)
    for d in digests[:12]:
        shutil.copy(d, arc_dir / d.name)

    return {
        "available":   True,
        "date":        date,
        "title":       title,
        "paper_count": paper_count,
        "preview":     preview,
        "link":        "journal.html",
        "archive":     archive,
    }


def extract_preprint_digest() -> dict:
    digests = sorted(
        (REPO_ROOT / "preprint_digest").glob("*.md"),
        reverse=True
    )
    if not digests:
        # Check for any other output format
        digests = sorted(
            (REPO_ROOT / "preprint_digest").glob("*.html"),
            reverse=True
        )
    if not digests:
        return {"available": False}

    f    = digests[0]
    date = f.stem[:10] if len(f.stem) >= 10 else f.stem
    text = f.read_text(encoding="utf-8")

    paper_count = len(re.findall(r"^## ", text, re.MULTILINE))
    title_m     = re.search(r"^# (.+)$", text, re.MULTILINE)
    title       = title_m.group(1).strip() if title_m else "Preprint Digest"

    return {
        "available":   True,
        "date":        date,
        "title":       title,
        "paper_count": paper_count,
        "link":        None,   # email only unless HTML output found
    }


def read_status_file(bot_name: str) -> dict:
    """Read the simple status JSON each bot writes on success."""
    status_file = DOCS / "status.json"
    if status_file.exists():
        try:
            status = json.loads(status_file.read_text())
            return status.get(bot_name, {})
        except Exception:
            pass
    return {}


# ── dashboard HTML ─────────────────────────────────────────────────────────────

def bot_card(
    icon: str,
    title: str,
    schedule: str,
    date: str,
    content_html: str,
    link: str | None,
    accent: str,
    archive_html: str = "",
) -> str:
    age_label, age_color = fmt_age(date) if date else ("never", "#ef4444")

    link_btn = (
        f'<a href="{link}" class="card-btn">View latest report →</a>'
        if link else
        '<span class="card-btn-disabled">Email delivery only</span>'
    )

    return f"""
    <div class="card" style="--accent:{accent}">
      <div class="card-header">
        <div class="card-icon">{icon}</div>
        <div>
          <div class="card-title">{title}</div>
          <div class="card-schedule">{schedule}</div>
        </div>
        <div class="card-badge" style="color:{age_color}">{age_label}</div>
      </div>
      <div class="card-body">{content_html}</div>
      <div class="card-footer">
        {link_btn}
        {archive_html}
      </div>
    </div>"""


def archive_dropdown(items: list[dict], label: str = "Archive") -> str:
    if not items:
        return ""
    opts = "\n".join(
        f'<option value="{i["file"]}">{i["date"]}</option>'
        for i in items
    )
    return f"""
    <select class="archive-select" onchange="if(this.value)window.open(this.value,'_blank')">
      <option value="">{label} ▾</option>
      {opts}
    </select>"""


def build_html(running: dict, journal: dict, preprint: dict, generated_at: str) -> str:

    # ── Running Bot card ─────────────────────────────────────────
    if running["available"]:
        stats_html = "".join(
            f'<div class="stat"><span class="stat-k">{k}</span>'
            f'<span class="stat-v">{v}</span></div>'
            for k, v in list(running["stats"].items())[:6]
        )
        r_content = f"""
        <div class="headline">"{running['headline']}"</div>
        <div class="stats-row">{stats_html}</div>"""
        r_archive = archive_dropdown(running.get("archive", []), "Past reports")
        r_card = bot_card("🏃", "Running Bot", "Monday · Strava + Claude",
                          running["date"], r_content, running["link"],
                          "#f97316", r_archive)
    else:
        r_card = bot_card("🏃", "Running Bot", "Monday · Strava + Claude",
                          "", "<p class='no-data'>No reports yet.</p>",
                          None, "#f97316")

    # ── Journal Digest card ───────────────────────────────────────
    if journal["available"]:
        j_content = f"""
        <div class="digest-title">{journal['title']}</div>
        <div class="paper-count">{journal['paper_count']} papers summarised</div>
        <div class="preview">{journal['preview']}</div>"""
        j_archive = archive_dropdown(journal.get("archive", []), "Past digests")
        j_card = bot_card("📰", "Journal Digest", "Friday · Nature, Science, Cell + more",
                          journal["date"], j_content, journal.get("link"),
                          "#14b8a6", j_archive)
    else:
        j_card = bot_card("📰", "Journal Digest", "Friday · RSS feeds + Gemini",
                          "", "<p class='no-data'>No digests yet.</p>",
                          None, "#14b8a6")

    # ── Preprint Digest card ─────────────────────────────────────
    if preprint["available"]:
        p_content = f"""
        <div class="digest-title">{preprint['title']}</div>
        <div class="paper-count">{preprint['paper_count']} preprints reviewed</div>"""
        p_card = bot_card("📄", "Preprint Digest", "Thursday · bioRxiv + arXiv",
                          preprint["date"], p_content, preprint.get("link"),
                          "#8b5cf6")
    else:
        p_card = bot_card("📄", "Preprint Digest", "Thursday · bioRxiv + arXiv",
                          "", "<p class='no-data'>No digests yet.</p>",
                          None, "#8b5cf6")

    # ── Email-only bots ──────────────────────────────────────────
    zenodo_status  = read_status_file("zenodo_bot")
    citation_status = read_status_file("citation_bot")

    z_date = zenodo_status.get("last_run", "")
    c_date = citation_status.get("last_run", "")

    z_content = f"""
    <div class="email-note">Queries Zenodo for new scRNA-seq datasets published this week.
    Generates AI summaries and sends a formatted HTML report by email.</div>
    {"<div class='last-run'>Last run: "+z_date+"</div>" if z_date else ""}"""

    c_content = f"""
    <div class="email-note">Tracks papers citing your research via OpenAlex
    (ORCID 0000-0002-8994-0781). Tags by Microscopy / Transcriptomics and sends by email.</div>
    {"<div class='last-run'>Last run: "+c_date+"</div>" if c_date else ""}"""

    z_card = bot_card("🔬", "Zenodo Bot", "Monday · Zenodo API + Gemini",
                      z_date, z_content, None, "#3b82f6")
    c_card = bot_card("📚", "Citation Bot", "Wednesday · OpenAlex + Gemini",
                      c_date, c_content, None, "#f59e0b")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ResearchAssistants_SBW · Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600&display=swap" rel="stylesheet">
<style>
  :root{{--bg:#080b12;--sf:#0f1520;--card:#141926;--bdr:#1a2035;--tx:#dde2f0;--mu:#4a5270;--dim:#1e2540;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--tx);font-family:'Source Serif 4',serif;font-weight:300;min-height:100vh;}}

  /* HEADER */
  .header{{background:linear-gradient(180deg,#0f1520 0%,#080b12 100%);border-bottom:3px solid #f97316;padding:44px 40px 36px;position:relative;overflow:hidden;}}
  .header::before{{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 60% 30%,rgba(249,115,22,.07) 0%,transparent 70%);pointer-events:none;}}
  .header-inner{{position:relative;max-width:1100px;margin:0 auto;}}
  .tag{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.18em;color:#f97316;text-transform:uppercase;margin-bottom:8px;}}
  h1{{font-family:'Playfair Display',serif;font-size:clamp(28px,5vw,48px);font-weight:700;color:#fff;line-height:1;margin-bottom:6px;}}
  h1 em{{color:#f97316;font-style:italic;}}
  .generated{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mu);margin-top:8px;}}

  /* SCHEDULE BAR */
  .schedule-bar{{max-width:1100px;margin:24px auto 0;display:flex;gap:8px;flex-wrap:wrap;}}
  .sched-item{{background:var(--card);border:1px solid var(--bdr);border-radius:6px;padding:6px 12px;font-family:'IBM Plex Mono',monospace;font-size:11px;}}
  .sched-day{{color:#f97316;margin-right:6px;}}
  .sched-bot{{color:var(--mu);}}

  /* GRID */
  .grid{{max-width:1100px;margin:32px auto;padding:0 40px 64px;display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;}}
  @media(max-width:600px){{.grid{{padding:0 16px 48px;}}}}

  /* CARDS */
  .card{{background:var(--card);border:1px solid var(--bdr);border-radius:14px;overflow:hidden;display:flex;flex-direction:column;border-top:3px solid var(--accent,#f97316);}}
  .card-header{{padding:18px 20px 14px;display:flex;align-items:flex-start;gap:12px;border-bottom:1px solid var(--bdr);}}
  .card-icon{{font-size:22px;flex-shrink:0;margin-top:2px;}}
  .card-title{{font-family:'Source Serif 4',serif;font-size:16px;font-weight:600;color:var(--tx);}}
  .card-schedule{{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--mu);margin-top:3px;}}
  .card-badge{{font-family:'IBM Plex Mono',monospace;font-size:11px;margin-left:auto;flex-shrink:0;}}
  .card-body{{padding:18px 20px;flex:1;}}
  .card-footer{{padding:12px 20px 16px;border-top:1px solid var(--bdr);display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}

  /* CARD CONTENT */
  .headline{{font-family:'Playfair Display',serif;font-style:italic;font-size:14px;color:#ccd4e8;line-height:1.5;margin-bottom:14px;}}
  .stats-row{{display:flex;flex-wrap:wrap;gap:6px;}}
  .stat{{background:var(--bg);border:1px solid var(--bdr);border-radius:6px;padding:6px 10px;}}
  .stat-k{{font-family:'IBM Plex Mono',monospace;font-size:9px;color:var(--mu);text-transform:uppercase;letter-spacing:.08em;display:block;}}
  .stat-v{{font-family:'IBM Plex Mono',monospace;font-size:14px;font-weight:500;color:var(--accent,#f97316);}}
  .digest-title{{font-size:14px;font-weight:600;color:var(--tx);margin-bottom:6px;}}
  .paper-count{{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--accent,#14b8a6);margin-bottom:10px;}}
  .preview{{font-size:13px;color:var(--mu);line-height:1.65;}}
  .email-note{{font-size:13px;color:var(--mu);line-height:1.65;margin-bottom:8px;}}
  .last-run{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mu);}}
  .no-data{{font-size:13px;color:var(--mu);font-style:italic;}}

  /* FOOTER ELEMENTS */
  .card-btn{{background:rgba(249,115,22,.1);border:1px solid rgba(249,115,22,.3);color:#f97316;padding:6px 14px;border-radius:6px;font-family:'IBM Plex Mono',monospace;font-size:11px;text-decoration:none;transition:background .15s;}}
  .card-btn:hover{{background:rgba(249,115,22,.2);}}
  .card-btn-disabled{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mu);}}
  .archive-select{{background:var(--bg);border:1px solid var(--bdr);color:var(--mu);padding:5px 10px;border-radius:6px;font-family:'IBM Plex Mono',monospace;font-size:11px;cursor:pointer;}}
  .archive-select:hover{{border-color:var(--mu);}}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div class="tag">ResearchAssistants_SBW · Automated Intelligence Hub</div>
    <h1>Research <em>Dashboard</em></h1>
    <div class="schedule-bar">
      <div class="sched-item"><span class="sched-day">MON</span><span class="sched-bot">Zenodo · Running</span></div>
      <div class="sched-item"><span class="sched-day">WED</span><span class="sched-bot">Citation</span></div>
      <div class="sched-item"><span class="sched-day">THU</span><span class="sched-bot">Preprint</span></div>
      <div class="sched-item"><span class="sched-day">FRI</span><span class="sched-bot">Journal Digest</span></div>
      <div class="sched-item"><span class="sched-day">1st</span><span class="sched-bot">Athlete Context Update</span></div>
    </div>
    <div class="generated">Dashboard generated {generated_at}</div>
  </div>
</div>

<div class="grid">
  {r_card}
  {j_card}
  {p_card}
  {z_card}
  {c_card}
</div>

</body>
</html>"""


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"=== Building Dashboard — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} ===")

    running  = extract_running_bot()
    journal  = extract_journal_digest()
    preprint = extract_preprint_digest()

    print(f"  Running bot:      {'✓ ' + running['date'] if running['available'] else '✗ no reports'}")
    print(f"  Journal digest:   {'✓ ' + journal['date'] if journal['available'] else '✗ no digests'}")
    print(f"  Preprint digest:  {'✓ ' + preprint['date'] if preprint['available'] else '✗ no digests'}")

    generated_at = datetime.now(timezone.utc).strftime("%A %d %B %Y, %H:%M UTC")
    html = build_html(running, journal, preprint, generated_at)

    out = DOCS / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"\n✓ docs/index.html written ({len(html):,} chars)")


if __name__ == "__main__":
    main()
