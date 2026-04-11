"""
running_bot/insights.py — Claude AI insight generation.
Includes speed session interval data in the prompt for detailed analysis.
"""

import os
import json
import requests


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-sonnet-4-20250514"


def get_claude_insights(data: dict, athlete_context: str) -> dict:
    system_prompt = (
        "You are providing weekly running analysis for a specific athlete. "
        "Use the following context to make your insights specific and personal:\n\n"
        + athlete_context
    )

    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            "x-api-key":         os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      MODEL,
            "max_tokens": 1800,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": _build_prompt(data)}],
        },
        timeout=45,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"].strip()

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    insights = json.loads(raw)
    print(f'✓ Insights: "{insights.get("headline","…")}"')
    return insights


def _fmt_pace(ms):
    if not ms or ms <= 0:
        return "–"
    p = 1000 / ms / 60
    return f"{int(p)}:{int((p - int(p)) * 60):02d}"


def _speed_session_block(sessions: list[dict]) -> str:
    if not sessions:
        return "No speed sessions detected this week (no Tuesday/Thursday runs or keyword-matched sessions)."

    lines = []
    for s in sessions:
        lines.append(f"\n### {s['date']} — {s['name']} ({s['dist_km']} km)")
        if s.get("session_avg_hr"):
            lines.append(f"Session avg HR: {s['session_avg_hr']} bpm  |  "
                         f"Peak HR: {s.get('session_peak_hr','–')} bpm")
        lines.append(f"Best effort pace: {s['best_pace']}/km  |  "
                     f"Avg effort pace: {s['avg_effort_pace']}/km  |  "
                     f"Intervals detected: {s['n_intervals']}")

        for i, iv in enumerate(s["intervals"], 1):
            dur  = f"{iv['duration_s']//60}:{iv['duration_s']%60:02d}"
            hr   = f", HR {iv['mean_hr']} bpm" if iv.get("mean_hr") else ""
            cad  = f", {iv['mean_cad']} spm" if iv.get("mean_cad") else ""
            lines.append(
                f"  Interval {i}: {dur} @ {iv['mean_pace']}/km avg "
                f"(peak {iv['peak_pace']}/km){hr}{cad}"
            )

        for i, rec in enumerate(s.get("recoveries", []), 1):
            if rec.get("mean_ms"):
                dur = f"{rec['duration_s']//60}:{rec['duration_s']%60:02d}"
                hr  = f", HR {rec['mean_hr']} bpm" if rec.get("mean_hr") else ""
                lines.append(
                    f"  Recovery {i}: {dur} @ {_fmt_pace(rec['mean_ms'])}/km{hr}"
                )

    return "\n".join(lines)


def _build_prompt(data: dict) -> str:
    tw        = data.get("this_week") or {}
    aeff      = data.get("aero_eff_now")
    aeff_prev = data.get("aero_eff_prev")

    # Parkruns
    pr_lines = []
    for p in data.get("all_parkruns", [])[-5:]:
        m, s = int(p["time_min"]), int((p["time_min"] % 1) * 60)
        pr_lines.append(f"  {p['date']}: {m}:{s:02d}" +
                        (f", HR {p['hr']} bpm" if p["hr"] else ""))
    bp = data.get("best_parkrun")
    if bp:
        bm, bs = int(bp["time_min"]), int((bp["time_min"] % 1) * 60)
        pr_lines.append(f"  All-time PB: {bm}:{bs:02d} ({bp['date']})")

    # Notable activities with athlete notes
    notable_lines = []
    for n in data.get("notable", [])[:8]:
        line = f"  {n['date']} — {n['name']} ({n['dist_km']}km, {n['pace']}/km"
        if n.get("hr"):
            line += f", HR {n['hr']}"
        line += ")"
        if n.get("desc"):
            line += f'\n    Athlete note: "{n["desc"][:200]}"'
        notable_lines.append(line)

    # Weekly volume
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

    # Speed sessions
    speed_block = _speed_session_block(data.get("speed_sessions", []))

    return f"""WEEK: {data['week_label']}

THIS WEEK SUMMARY:
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

PARKRUNS:
{chr(10).join(pr_lines) if pr_lines else "  None this week"}

NOTABLE ACTIVITIES:
{chr(10).join(notable_lines) if notable_lines else "  None"}

━━━ SPEED SESSION ANALYSIS ━━━
{speed_block}

---

Respond with a single JSON object — no markdown, no fences:

{{
  "headline": "One punchy sentence (max 15 words) capturing this week's story",
  "week_narrative": "2–3 paragraphs. Analyse the week in context of recent history. Reference specific sessions, athlete notes, visible patterns. Be direct and personal.",
  "speed_analysis": "2–3 paragraphs specifically on the speed/quality sessions this week. If interval data is available: comment on the paces achieved relative to this athlete's capability (sub-20 parkrun = ~3:58/km, HM PB = 4:24/km avg, 10km PB = 4:21/km), recovery quality, HR response, cadence if notable, and what this means for near-term targets. If no speed sessions: note what quality work was or wasn't present. Be specific — name the sessions, quote the paces.",
  "key_signals": [
    {{"signal": "short label", "detail": "1–2 sentences of specific analysis", "type": "positive|warning|neutral"}},
    ... (3–5 signals, at least one must reference speed session data if available)
  ],
  "next_week_focus": "1–2 specific actionable sentences referencing this athlete's actual goals and limiters."
}}"""
