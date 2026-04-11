#!/usr/bin/env python3
"""
running_bot/running_bot.py

Weekly running report bot for ResearchAssistants_SBW.
Follows the same pattern as zenodo_bot/zenodo_bot.py and citation_bot/citation_bot.py:
  - self-contained in this folder
  - entry point is this file
  - workflow sets PYTHONPATH=running_bot and runs: python running_bot/running_bot.py

Fetches Strava activity data, processes running metrics, calls Claude for
AI-powered weekly insights, generates a styled HTML report, and commits it
to running_bot/reports/. Optionally emails the report via Gmail.

Secrets required (GitHub repo Settings → Secrets and variables → Actions):
  STRAVA_CLIENT_ID      — from strava.com/settings/api
  STRAVA_CLIENT_SECRET  — from strava.com/settings/api
  STRAVA_REFRESH_TOKEN  — from one-time get_tokens.py script
  ANTHROPIC_API_KEY     — from console.anthropic.com (new — not used by other bots)
  EMAIL_SENDER          — Gmail address (already present from other bots)
  EMAIL_RECEIVER        — recipient address (already present)
  EMAIL_PASSWORD        — Gmail App Password (already present)
"""

import os
import datetime
from pathlib import Path

import yaml

from strava import refresh_access_token, build_report_data
from insights import get_claude_insights
from report import generate_html
from utils.email_logic import send_email


# ─── CONFIG ───────────────────────────────────────────────────────────────────

def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_athlete_context():
    ctx_path = Path(__file__).parent / "athlete_context.md"
    return ctx_path.read_text(encoding="utf-8")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    print(f"=== Running Bot — {datetime.date.today()} ===")

    cfg          = load_config()
    history_wks  = cfg.get("history_weeks", 16)
    output_dir   = Path(__file__).parent / cfg.get("output_dir", "reports")
    output_dir.mkdir(exist_ok=True)
    send_email_report = cfg.get("send_email", True)

    # Athlete context is plain markdown — edit athlete_context.md to update PBs/goals
    athlete_context = load_athlete_context()

    # 1. Strava auth (token auto-rotates — workflow captures and updates secret)
    access_token, new_refresh = refresh_access_token()
    if new_refresh:
        Path("new_refresh_token.txt").write_text(new_refresh)
        print("⚠  Refresh token rotated — workflow will update secret")

    # 2. Fetch and process data
    data = build_report_data(access_token, history_weeks=history_wks)

    # 3. Claude AI insights
    try:
        insights = get_claude_insights(data, athlete_context)
    except Exception as e:
        print(f"⚠  Claude error: {e} — using fallback insights")
        tw = data.get("this_week") or {}
        insights = {
            "headline":        f"{data['week_label']} — {tw.get('dist_km','?')} km",
            "week_narrative":  "AI insights unavailable this week.",
            "key_signals":     [],
            "next_week_focus": "Review the charts below.",
        }

    # 4. Generate HTML
    html = generate_html(data, insights, history_weeks=history_wks)

    # 5. Save to running_bot/reports/
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    dated    = output_dir / f"report_{date_str}.html"
    latest   = output_dir / "index.html"
    dated.write_text(html, encoding="utf-8")
    latest.write_text(html, encoding="utf-8")
    print(f"✓ {dated}")
    print(f"✓ {latest}")

    # 6. Email report (optional — set send_email: false in config.yaml to disable)
    if send_email_report:
        try:
            tw = data.get("this_week") or {}
            subject = (
                f"🏃 Weekly Run Report — {data['week_label']} — "
                f"{tw.get('dist_km','?')} km"
            )
            send_email(subject, html)
            print("✓ Email sent")
        except Exception as e:
            print(f"⚠  Email failed: {e}")

    # 7. Stdout summary visible in Actions log
    tw = data.get("this_week") or {}
    print(f"\n── {data['week_label']} ──────────────────────")
    print(f"  {tw.get('dist_km','–')} km · {tw.get('runs','–')} runs · "
          f"{tw.get('avg_pace','–')}/km · {tw.get('avg_hr','–')} bpm")
    print(f"  Streak: {data['current_streak']} days")
    print(f'  "{insights["headline"]}"')


if __name__ == "__main__":
    run()
