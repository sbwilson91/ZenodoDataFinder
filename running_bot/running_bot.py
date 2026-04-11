#!/usr/bin/env python3
"""
running_bot/running_bot.py

Weekly running report bot for ResearchAssistants_SBW.
Entry point called by .github/workflows/running_bot_run.yml.
"""

import os
import datetime
from pathlib import Path

import yaml

from strava import refresh_access_token, build_report_data
from speed_sessions import get_speed_sessions
from insights import get_claude_insights
from report import generate_html
from utils.email_logic import send_email


def load_config():
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_athlete_context():
    ctx_path = Path(__file__).parent / "athlete_context.md"
    return ctx_path.read_text(encoding="utf-8")


def run():
    print(f"=== Running Bot — {datetime.date.today()} ===")

    cfg         = load_config()
    history_wks = cfg.get("history_weeks", 16)
    output_dir  = Path(__file__).parent / cfg.get("output_dir", "reports")
    output_dir.mkdir(exist_ok=True)
    send_email_report = cfg.get("send_email", True)

    athlete_context = load_athlete_context()

    # 1. Strava auth
    access_token, new_refresh = refresh_access_token()
    if new_refresh:
        Path("new_refresh_token.txt").write_text(new_refresh)
        print("⚠  Refresh token rotated")

    # 2. Weekly metrics
    data = build_report_data(access_token, history_weeks=history_wks)

    # 3. Speed session deep-dive (fetches streams for Tue/Thu/MRC/Mikkeler runs)
    print("\nAnalysing speed sessions…")
    speed_sessions = get_speed_sessions(access_token, data.get("this_week_all", []))
    data["speed_sessions"] = speed_sessions

    # 4. Claude insights (now includes speed session data)
    try:
        insights = get_claude_insights(data, athlete_context)
    except Exception as e:
        print(f"⚠  Claude error: {e} — using fallback")
        tw = data.get("this_week") or {}
        insights = {
            "headline":        f"{data['week_label']} — {tw.get('dist_km','?')} km",
            "week_narrative":  "AI insights unavailable this week.",
            "speed_analysis":  "",
            "key_signals":     [],
            "next_week_focus": "Review the charts below.",
        }

    # 5. Render HTML
    html = generate_html(data, insights, history_weeks=history_wks)

    # 6. Save
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    dated    = output_dir / f"report_{date_str}.html"
    latest   = output_dir / "index.html"
    dated.write_text(html, encoding="utf-8")
    latest.write_text(html, encoding="utf-8")
    print(f"\n✓ {dated}")

    # 7. Email
    if send_email_report:
        try:
            tw      = data.get("this_week") or {}
            subject = (f"🏃 Weekly Run Report — {data['week_label']} — "
                       f"{tw.get('dist_km','?')} km")
            send_email(subject, html)
            print("✓ Email sent")
        except Exception as e:
            print(f"⚠  Email failed: {e}")

    # 8. Summary to Actions log
    tw = data.get("this_week") or {}
    print(f"\n── {data['week_label']} ──────────────────────")
    print(f"  {tw.get('dist_km','–')} km · {tw.get('runs','–')} runs · "
          f"{tw.get('avg_pace','–')}/km · {tw.get('avg_hr','–')} bpm")
    print(f"  Speed sessions: {len(speed_sessions)}")
    for s in speed_sessions:
        print(f"    {s['date']} {s['name'][:40]} — "
              f"{s['n_intervals']} intervals, best {s['best_pace']}/km")
    print(f'\n  "{insights["headline"]}"')


if __name__ == "__main__":
    run()
