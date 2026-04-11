"""
running_bot/insights.py — Claude AI insight generation.

Analogous to utils/ai_logic.py in other bots, but uses the Anthropic API
rather than HuggingFace (the running report needs nuanced narrative analysis,
not extractive summarisation). Requires ANTHROPIC_API_KEY secret.
"""

import os
import json
import requests


def get_claude_insights(data: dict, athlete_context: str) -> dict:
    """
    Call Claude with this week's metrics + full athlete history context.
    Returns a dict with: headline, week_narrative, key_signals, next_week_focus.

    Args:
        data:            output of strava.build_report_data()
        athlete_context: content of running_bot/athlete_context.md
    """
    system_prompt = (
        "You are providing weekly running analysis for a specific athlete. "
        "Use the following context to make your insights specific and personal:\n\n"
        + athlete_context
    )

    prompt = _build_prompt(data)

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 1200,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"].strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    insights = json.loads(raw)
    print(f'✓ Claude insights: "{insights.get("headline","…")}"')
    return insights


def _build_prompt(data: dict) -> str:
    tw        = data.get("this_week") or {}
    aeff      = data.get("aero_eff_now")
    aeff_prev = data.get("aero_eff_prev")

    # Recent parkruns
    pr_lines = []
    for p in data.get("all_parkruns", [])[-5:]:
        m, s = int(p["time_min"]), int((p["time_min"] % 1) * 60)
        pr_lines.append(f"  {p['date']}: {m}:{s:02d}" + (f", HR {p['hr']} bpm" if p["hr"] else ""))
    bp = data.get("best_parkrun")
    if bp:
        bm, bs = int(bp["time_min"]), int((bp["time_min"] % 1) * 60)
        pr_lines.append(f"  All-time PB: {bm}:{bs:02d} ({bp['date']})")
    pr_block = ("RECENT PARKRUNS:\n" + "\n".join(pr_lines)) if pr_lines else ""

    # Notable activities with athlete's own notes
    notable_lines = []
    for n in data.get("notable", [])[:8]:
        line = f"  {n['date']} — {n['name']} ({n['dist_km']}km, {n['pace']}/km"
        if n.get("hr"):
            line += f", HR {n['hr']}"
        line += ")"
        if n.get("desc"):
            line += f'\n    Athlete note: "{n["desc"][:200]}"'
        notable_lines.append(line)
    notable_block = ("NOTABLE ACTIVITIES:\n" + "\n".join(notable_lines)
                     if notable_lines else "No notable activities this week.")

    # Weekly volume trend
    wk_lines = [
        f"  {w['week']}: {w['dist_km']}km, {w['runs']} runs"
        + (f", HR {w['avg_hr']}" if w.get("avg_hr") else "")
        for w in data.get("weekly_series", [])[-8:]
    ]

    # Aerobic efficiency
    aeff_line = ""
    if aeff:
        m, s = int(aeff), int((aeff % 1) * 60)
        aeff_line = f"Aerobic efficiency (130–145 bpm): {m}:{s:02d}/km"
        if aeff_prev:
            diff_s = round((aeff_prev - aeff) * 60)
            aeff_line += f" — {abs(diff_s)}s/km {'faster' if diff_s > 0 else 'slower'} than prior 8 weeks"

    # HR zones
    zones   = data.get("zone_dist", {})
    tz_tot  = sum(zones.values()) or 1
    z_lines = [f"  {z}: {round(v/tz_tot*100)}%" for z, v in zones.items() if v > 0]

    return f"""WEEK: {data['week_label']}

THIS WEEK:
  Distance:         {tw.get('dist_km', 0)} km
  Runs:             {tw.get('runs', 0)}
  Avg pace:         {tw.get('avg_pace', '–')}/km
  Avg HR:           {tw.get('avg_hr', '–')} bpm
  Elevation:        {tw.get('elev_m', 0)} m
  8-wk rolling avg: {data['rolling_avg_km']} km/wk
  vs rolling avg:   {round(tw.get('dist_km', 0) - data['rolling_avg_km'], 1)} km
  Current streak:   {data['current_streak']} consecutive days

WEEKLY VOLUME (last 8 weeks):
{chr(10).join(wk_lines)}

{aeff_line}

HR ZONES:
{chr(10).join(z_lines)}

{pr_block}

{notable_block}

---

Respond with a single JSON object — no markdown fences, no extra text:

{{
  "headline": "One punchy sentence (max 15 words) capturing this week's story",
  "week_narrative": "2–3 paragraphs. What happened this week in the context of recent history. Reference specific sessions, athlete notes, visible patterns. Be direct and personal.",
  "key_signals": [
    {{"signal": "short label", "detail": "1–2 sentences of specific analysis", "type": "positive|warning|neutral"}},
    ... (3–5 signals)
  ],
  "next_week_focus": "1–2 specific actionable sentences referencing this athlete's actual goals and limiters."
}}"""
