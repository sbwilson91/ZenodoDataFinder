#!/usr/bin/env python3
"""
Strava Weekly Running Report Generator — with Claude AI Insights
Fetches recent activities via Strava API, processes metrics, calls Claude
for narrative analysis, and generates a detailed HTML report.
"""

import os
import json
import requests
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict


# ─── CONFIG ───────────────────────────────────────────────────────────────────

STRAVA_CLIENT_ID     = os.environ["STRAVA_CLIENT_ID"]
STRAVA_CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
STRAVA_REFRESH_TOKEN = os.environ["STRAVA_REFRESH_TOKEN"]
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]

HISTORY_WEEKS = 16
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "reports"))
OUTPUT_DIR.mkdir(exist_ok=True)


# ─── ATHLETE CONTEXT ──────────────────────────────────────────────────────────
# Fed to Claude as the system prompt on every run so insights are grounded
# in the full story, not just this week's numbers.

ATHLETE_CONTEXT = """
You are providing weekly running analysis for a specific athlete. Here is their
complete performance history and context so your insights are grounded and personal.

BACKGROUND
- Male runner, based in Copenhagen (recently moved to Barcelona)
- Runs with MRC (Monday Running Club) — Tuesday fartlek sessions are the
  cornerstone of speed work; also runs with a work crew on Wednesdays
- Completed an 884-day run streak (Oct 2023 to Mar 2026), ended the day after
  the Barcelona Marathon due to illness; back running within 4 days

CAREER BESTS (as of March 2026)
- Parkrun PB:     19:52  (Jan 2025, after a month of Australian heat training)
- 10km PB:        43:34  (Frost Cup, Feb 2024)
- Half marathon:  1:32:55 (Berlin, Apr 2025) — equalled 1:32:57 CPH Sep 2025
- Marathon PB:    3:30:45 (Copenhagen, May 2025) — calves gave out at km 37
- Longest race:   104.3km Kullamannen UTMB 100k (Nov 2024, 17:23)
- Ultra 2:        Ultravasan 90km (Aug 2025, 12:02)
- Superhalfs:     6/6 complete (Tromsø, Lisbon, Prague, CPH, Berlin, Valencia)

KEY PHYSIOLOGICAL BENCHMARKS
- Aerobic efficiency peak: 5:01/km at 130–145 bpm (Apr 2025, post-Kullamannen)
- Average HR Oct 2023: ~139 bpm
- Average HR at peak fitness (Feb 2025): ~120 bpm
- Average HR Feb 2026: ~129–131 bpm
- Cadence: rose from 152 spm to 163–170 spm after a deliberate experiment Nov 2023
- The Kullamannen 100km (Nov 2024) produced the biggest aerobic adaptation of
  the entire dataset — HR dropped ~10 bpm in the following two months

TRAINING PATTERNS
- Weekly average in peak phase (Dec 2024 – May 2025): ~250 km/month
- Peak week ever: 143.8 km
- Annual 2024: 3,001 km (actively chased as a specific target)
- Shoe rotation: Nike Vaporfly 3 (carbon racing), Novablast (daily), Speedgoat (trails)
- Has run in 17+ countries; streak survived Dubai heat, Indian rooftop loops,
  airport treadmills, sub-zero Copenhagen winters

KNOWN LIMITERS TO WATCH
- Calf endurance: gave out at km 37 in CPH Marathon — posterior chain S&C is the fix
- Cadence: currently 163–170 spm, still 5–7 below the 170–180 optimal range
- Vertical oscillation: ~92mm (target <80mm) — linked to cadence
- History of racing on heavy legs (marathon then HM 8 days later, etc.)
- Recurring heel issues; achilles warning during Kullamannen ultra taper

GOALS AS OF MARCH 2026
- Sub-1:30 half marathon (explicitly stated as target — "12 weeks to CPH half")
- Sub-3:20 marathon (physiologically supported by aerobic efficiency data)
- Sub-19:30 parkrun (fitness is there, just needs a dedicated parkrun block)
- New base in Barcelona — finding new routes, new running community
- Post-streak: returning to structured training without the daily pressure

TONE GUIDANCE
- Be specific and personal — reference actual PBs, actual race names, real patterns
- Be honest about regressions without being dramatic
- Note genuine milestones vs normal weekly variation
- Reference MRC sessions when they appear (Tuesday fartlek is the key quality day)
- The athlete writes personal notes on runs — they are self-aware and analytical
- Avoid generic advice like "make sure to rest" — be specific to this athlete's data
- Total insight length: ~400–550 words across all fields combined
- Write as a knowledgeable running coach who has studied this athlete's full history
"""


# ─── STRAVA AUTH ──────────────────────────────────────────────────────────────

def refresh_access_token():
    """Exchange refresh token for a fresh access token. Strava tokens expire after 6h."""
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id":     STRAVA_CLIENT_ID,
        "client_secret": STRAVA_CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": STRAVA_REFRESH_TOKEN,
    })
    resp.raise_for_status()
    data = resp.json()
    print(f"✓ Token refreshed, expires {datetime.fromtimestamp(data['expires_at'])}")
    return data["access_token"], data["refresh_token"]


# ─── STRAVA FETCH ─────────────────────────────────────────────────────────────

def get_activities(token, after_ts, before_ts=None, per_page=100):
    """Fetch all activities in a time window, handling pagination."""
    headers = {"Authorization": f"Bearer {token}"}
    activities, page = [], 1
    while True:
        params = {"after": int(after_ts), "per_page": per_page, "page": page}
        if before_ts:
            params["before"] = int(before_ts)
        resp = requests.get("https://www.strava.com/api/v3/athlete/activities",
                            headers=headers, params=params)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return activities


# ─── METRICS ──────────────────────────────────────────────────────────────────

def pace_from_speed(speed_ms):
    if not speed_ms or speed_ms <= 0:
        return "–"
    p = 1000 / speed_ms / 60
    return f"{int(p)}:{int((p - int(p)) * 60):02d}"


def pace_val(speed_ms):
    if not speed_ms or speed_ms <= 0:
        return None
    return 1000 / speed_ms / 60


def fmt_duration(seconds):
    if not seconds:
        return "–"
    h, rem = divmod(int(seconds), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def is_parkrun(activity):
    if activity.get("type") != "Run":
        return False
    dist = activity.get("distance", 0) / 1000
    date = datetime.fromisoformat(activity["start_date_local"].replace("Z", ""))
    return date.weekday() == 5 and 4.8 <= dist <= 5.3


def compute_weekly_stats(activities):
    runs = [a for a in activities if a.get("type") == "Run"]
    if not runs:
        return None
    return {
        "runs":       len(runs),
        "dist_km":    round(sum(a.get("distance", 0) for a in runs) / 1000, 1),
        "time_s":     sum(a.get("moving_time", 0) for a in runs),
        "elev_m":     round(sum(a.get("total_elevation_gain", 0) for a in runs)),
        "avg_pace":   pace_from_speed(statistics.mean(
                          [a["average_speed"] for a in runs if a.get("average_speed")]
                      ) if any(a.get("average_speed") for a in runs) else 0),
        "avg_hr":     round(statistics.mean(
                          [a["average_heartrate"] for a in runs if a.get("average_heartrate")]
                      )) if any(a.get("average_heartrate") for a in runs) else None,
        "activities": runs,
    }


def compute_aerobic_efficiency(activities):
    speeds = [
        pace_val(a["average_speed"])
        for a in activities
        if a.get("type") == "Run"
        and a.get("average_heartrate")
        and a.get("average_speed")
        and 130 <= a["average_heartrate"] <= 145
        and 4 < pace_val(a["average_speed"]) < 9
    ]
    return round(statistics.mean(speeds), 2) if speeds else None


def find_parkruns(activities):
    prs = []
    for a in activities:
        if is_parkrun(a):
            t = a.get("moving_time", 0)
            prs.append({
                "date":     a["start_date_local"][:10],
                "time_s":   t,
                "time_min": round(t / 60, 2),
                "hr":       a.get("average_heartrate"),
                "name":     a.get("name", "Parkrun"),
            })
    return sorted(prs, key=lambda x: x["date"])


def find_notable(activities):
    keywords = {"marathon","half","ultra","race","parkrun","10k","10km","5k","5km",
                "runstreak","pb","fartlek","interval","tempo","mrc","sprint","intervals"}
    notable = []
    for a in activities:
        dist_km = a.get("distance", 0) / 1000
        if dist_km >= 15 or any(k in a.get("name","").lower() for k in keywords):
            desc = (a.get("description") or "").strip()
            notable.append({
                "name":    a.get("name","Run"),
                "date":    a["start_date_local"][:10],
                "dist_km": round(dist_km, 1),
                "time":    fmt_duration(a.get("moving_time")),
                "pace":    pace_from_speed(a.get("average_speed")),
                "hr":      a.get("average_heartrate"),
                "desc":    desc[:300] if desc else "",
                "type":    a.get("type","Run"),
            })
    return sorted(notable, key=lambda x: x["date"], reverse=True)


def detect_streak(activities):
    run_dates = sorted(set(
        datetime.fromisoformat(a["start_date_local"].replace("Z","")).date()
        for a in activities if a.get("type") == "Run"
    ))
    streak, check = 0, datetime.now(timezone.utc).date()
    for d in reversed(run_dates):
        if d >= check - timedelta(days=1):
            streak += 1
            check = d
        else:
            break
    return streak


# ─── CLAUDE AI INSIGHTS ───────────────────────────────────────────────────────

def build_insights_prompt(data):
    """Build the data payload sent to Claude."""
    tw        = data["this_week"] or {}
    aeff      = data["aero_eff_now"]
    aeff_prev = data["aero_eff_prev"]

    # Recent parkrun summary
    pr_lines = []
    for p in data["all_parkruns"][-5:]:
        m, s = int(p["time_min"]), int((p["time_min"] % 1) * 60)
        pr_lines.append(f"  {p['date']}: {m}:{s:02d}" +
                        (f", HR {p['hr']} bpm" if p["hr"] else ""))
    if data["best_parkrun"]:
        bp = data["best_parkrun"]
        bm, bs = int(bp["time_min"]), int((bp["time_min"] % 1) * 60)
        pr_lines.append(f"  All-time PB: {bm}:{bs:02d} ({bp['date']})")
    pr_block = "RECENT PARKRUNS:\n" + "\n".join(pr_lines) if pr_lines else ""

    # Notable activities with notes
    notable_lines = []
    for n in data["notable"][:8]:
        line = f"  {n['date']} — {n['name']} ({n['dist_km']}km, {n['pace']}/km"
        if n["hr"]:
            line += f", HR {n['hr']}"
        line += ")"
        if n["desc"]:
            line += f'\n    Athlete note: "{n["desc"][:200]}"'
        notable_lines.append(line)
    notable_block = ("NOTABLE ACTIVITIES THIS WEEK:\n" + "\n".join(notable_lines)
                     if notable_lines else "No notable activities logged this week.")

    # Weekly series
    wk_lines = [
        f"  {w['week']}: {w['dist_km']}km, {w['runs']} runs" +
        (f", HR {w['avg_hr']}" if w["avg_hr"] else "")
        for w in data["weekly_series"][-8:]
    ]
    wk_block = "WEEKLY VOLUME (last 8 weeks):\n" + "\n".join(wk_lines)

    # Aerobic efficiency
    aeff_block = ""
    if aeff:
        m, s = int(aeff), int((aeff % 1) * 60)
        aeff_block = f"AEROBIC EFFICIENCY (pace at 130–145 bpm, 8-wk avg): {m}:{s:02d}/km"
        if aeff_prev:
            diff_s = round((aeff_prev - aeff) * 60)
            aeff_block += f" — {abs(diff_s)}s/km {'faster' if diff_s > 0 else 'slower'} than prior 8 weeks"

    # Zone distribution
    total_z = sum(data["zone_dist"].values()) or 1
    zone_block = "HR ZONES THIS WEEK:\n" + "\n".join(
        f"  {z}: {round(v/total_z*100)}%"
        for z, v in data["zone_dist"].items() if v > 0
    )

    return f"""Here is this week's training data. Provide your analysis as instructed.

WEEK: {data['week_label']}

THIS WEEK:
  Distance:        {tw.get('dist_km', 0)} km
  Runs:            {tw.get('runs', 0)}
  Avg pace:        {tw.get('avg_pace', '–')}/km
  Avg HR:          {tw.get('avg_hr', '–')} bpm
  Elevation:       {tw.get('elev_m', 0)} m
  8-wk rolling avg:{data['rolling_avg_km']} km
  vs rolling avg:  {round(tw.get('dist_km', 0) - data['rolling_avg_km'], 1)} km
  Current streak:  {data['current_streak']} consecutive days

{wk_block}

{aeff_block}

{zone_block}

{pr_block}

{notable_block}

---

Respond with a single JSON object — no markdown fences, no extra text:

{{
  "headline": "One punchy sentence (max 15 words) that captures this week's story",
  "week_narrative": "2–3 paragraphs analysing the week in context. Reference specific sessions, athlete notes, and patterns visible in the data. Be direct and specific.",
  "key_signals": [
    {{"signal": "short label", "detail": "1–2 sentences of specific analysis", "type": "positive|warning|neutral"}},
    ... (3–5 signals total)
  ],
  "next_week_focus": "1–2 specific actionable sentences referencing this athlete's actual goals and limiters."
}}"""


def get_claude_insights(data):
    """Call Claude API and return parsed insights dict."""
    print("Calling Claude for insights…")
    prompt = build_insights_prompt(data)

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        json={
            "model":      "claude-sonnet-4-20250514",
            "max_tokens": 1200,
            "system":     ATHLETE_CONTEXT,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"].strip()

    # Strip markdown fences if Claude added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    insights = json.loads(raw)
    print(f'✓ Insights: "{insights.get("headline", "…")}"')
    return insights


# ─── REPORT DATA ASSEMBLY ─────────────────────────────────────────────────────

def build_report_data(token, now=None):
    if now is None:
        now = datetime.now(timezone.utc)

    days_since_monday = now.weekday()
    week_start = now - timedelta(
        days=days_since_monday, hours=now.hour,
        minutes=now.minute, seconds=now.second
    )
    week_end      = week_start + timedelta(days=7)
    history_start = week_start - timedelta(weeks=HISTORY_WEEKS)

    print(f"Fetching {history_start.date()} → {week_end.date()}…")
    all_activities = get_activities(token,
                                    after_ts=history_start.timestamp(),
                                    before_ts=week_end.timestamp())
    print(f"  → {len(all_activities)} activities")

    def activity_dt(a):
        return datetime.fromisoformat(a["start_date_local"].replace("Z", ""))

    this_week = [a for a in all_activities
                 if activity_dt(a) >= week_start.replace(tzinfo=None)]

    # Weekly buckets
    weekly_buckets = defaultdict(list)
    for a in all_activities:
        wkey = (activity_dt(a) - timedelta(days=activity_dt(a).weekday())).strftime("%Y-%m-%d")
        weekly_buckets[wkey].append(a)

    weekly_series = []
    for wk, acts in sorted(weekly_buckets.items()):
        runs = [a for a in acts if a.get("type") == "Run"]
        dist = sum(a.get("distance", 0) for a in runs) / 1000
        hrs  = [a["average_heartrate"] for a in runs if a.get("average_heartrate")]
        weekly_series.append({
            "week":    wk, "dist_km": round(dist, 1),
            "runs":    len(runs),
            "avg_hr":  round(statistics.mean(hrs)) if hrs else None,
        })

    past_8   = [w for w in weekly_series if w["week"] < week_start.strftime("%Y-%m-%d")][-8:]
    rolling  = round(statistics.mean(w["dist_km"] for w in past_8), 1) if past_8 else 0

    cutoff_8  = (week_start - timedelta(weeks=8)).replace(tzinfo=None)
    recent    = [a for a in all_activities if activity_dt(a) >= cutoff_8]
    older     = [a for a in all_activities if activity_dt(a) <  cutoff_8]

    all_prs   = find_parkruns(all_activities)
    best_pr   = min(all_prs, key=lambda x: x["time_s"]) if all_prs else None

    # HR zone distribution this week
    zones = {"Z1": 0, "Z2": 0, "Z3": 0, "Z4": 0, "Z5": 0}
    for a in [x for x in this_week if x.get("type") == "Run"]:
        hr = a.get("average_heartrate")
        if hr:
            pct = hr / 185 * 100
            z = "Z1" if pct < 60 else "Z2" if pct < 70 else "Z3" if pct < 80 else "Z4" if pct < 90 else "Z5"
            zones[z] += 1

    type_counts = defaultdict(int)
    for a in this_week:
        type_counts[a.get("type","Other")] += 1

    return {
        "generated_at":     now.strftime("%A %d %B %Y, %H:%M UTC"),
        "week_label":       week_start.strftime("w/c %d %B %Y"),
        "week_start":       week_start.strftime("%Y-%m-%d"),
        "this_week":        compute_weekly_stats(this_week),
        "rolling_avg_km":   rolling,
        "weekly_series":    weekly_series[-16:],
        "aero_eff_now":     compute_aerobic_efficiency(recent),
        "aero_eff_prev":    compute_aerobic_efficiency(older),
        "all_parkruns":     all_prs[-20:],
        "best_parkrun":     best_pr,
        "notable":          find_notable(this_week),
        "zone_dist":        zones,
        "type_counts":      dict(type_counts),
        "current_streak":   detect_streak(all_activities),
        "total_activities": len(all_activities),
    }


# ─── HTML REPORT ──────────────────────────────────────────────────────────────

def generate_html(data, insights):
    tw      = data["this_week"] or {}
    dist    = tw.get("dist_km", 0)
    runs    = tw.get("runs", 0)
    pace    = tw.get("avg_pace", "–")
    hr      = tw.get("avg_hr", "–")
    elev    = tw.get("elev_m", 0)
    rolling = data["rolling_avg_km"]
    vs_avg  = round(dist - rolling, 1)
    vs_str  = (f"+{vs_avg}" if vs_avg >= 0 else str(vs_avg)) + " km"

    w_labels = json.dumps([w["week"][5:] for w in data["weekly_series"]])
    w_dists  = json.dumps([w["dist_km"]  for w in data["weekly_series"]])
    w_hrs    = json.dumps([w["avg_hr"]   for w in data["weekly_series"]])
    r_line   = json.dumps([rolling]      * len(data["weekly_series"]))

    pr_labels = json.dumps([p["date"][5:] for p in data["all_parkruns"]])
    pr_times  = json.dumps([round(p["time_min"], 2) for p in data["all_parkruns"]])
    pr_hrs    = json.dumps([p["hr"] for p in data["all_parkruns"]])

    aeff     = data["aero_eff_now"]
    aeff_p   = data["aero_eff_prev"]
    aeff_str = f"{int(aeff)}:{int((aeff%1)*60):02d}/km" if aeff else "–"
    if aeff and aeff_p:
        diff_s           = round((aeff_p - aeff) * 60)
        aeff_delta       = f"{'↑' if diff_s > 0 else '↓'} {abs(diff_s)}s/km vs prior 8 wks"
        aeff_delta_color = "#22c55e" if diff_s > 0 else "#ef4444"
    else:
        aeff_delta, aeff_delta_color = "", "#4a5270"

    streak       = data["current_streak"]
    streak_color = "#22c55e" if streak > 7 else "#f97316" if streak > 0 else "#4a5270"

    bp = data["best_parkrun"]
    bp_str = ""
    if bp:
        bm, bs = int(bp["time_min"]), int((bp["time_min"] % 1) * 60)
        bp_str = f"{bm}:{bs:02d} ({bp['date']})"

    # Zone bars
    tz_total = sum(data["zone_dist"].values()) or 1
    z_pcts   = {z: round(v / tz_total * 100) for z, v in data["zone_dist"].items()}
    z_colors = {"Z1":"#60a5fa","Z2":"#14b8a6","Z3":"#f59e0b","Z4":"#f97316","Z5":"#ef4444"}
    z_names  = {"Z1":"Z1 Recovery","Z2":"Z2 Easy","Z3":"Z3 Aerobic","Z4":"Z4 Threshold","Z5":"Z5 Max"}
    zones_html = "".join(
        f'<div class="zr"><div class="zl">{z_names[z]}</div>'
        f'<div class="zb"><div class="zbi" style="width:{z_pcts[z]}%;background:{z_colors[z]};"></div></div>'
        f'<div class="zp">{z_pcts[z]}%</div></div>'
        for z in ["Z1","Z2","Z3","Z4","Z5"]
    )

    # Notable activity cards
    notable_html = ""
    for n in data["notable"][:8]:
        desc_html = (f'<div class="act-desc">&ldquo;{n["desc"]}&rdquo;</div>'
                     if n["desc"] else "")
        hr_span   = f'<span>♥ {n["hr"]} bpm</span>' if n["hr"] else ""
        notable_html += f"""
      <div class="act-card">
        <div class="act-meta">{n["date"]}</div>
        <div class="act-name">{n["name"]}</div>
        <div class="act-stats"><span>{n["dist_km"]} km</span><span>{n["time"]}</span><span>{n["pace"]}/km</span>{hr_span}</div>
        {desc_html}
      </div>"""
    if not notable_html:
        notable_html = '<p class="empty">No notable activities this week.</p>'

    # AI signals
    signals_html = ""
    sig_color = {"positive":"#22c55e","warning":"#ef4444","neutral":"#14b8a6"}
    sig_icon  = {"positive":"↑","warning":"⚠","neutral":"→"}
    sig_class = {"positive":"signal-positive","warning":"signal-warning","neutral":"signal-neutral"}
    for sig in insights.get("key_signals", []):
        t = sig.get("type","neutral")
        signals_html += f"""
      <div class="signal {sig_class.get(t,'signal-neutral')}">
        <div class="signal-header">
          <span class="signal-icon" style="color:{sig_color.get(t,'#14b8a6')}">{sig_icon.get(t,'→')}</span>
          <span class="signal-label">{sig.get('signal','')}</span>
        </div>
        <div class="signal-detail">{sig.get('detail','')}</div>
      </div>"""

    # AI narrative paragraphs
    narrative_html = "".join(
        f"<p>{para.strip()}</p>"
        for para in insights.get("week_narrative","").split("\n\n") if para.strip()
    )

    headline   = insights.get("headline", f"{data['week_label']} — {dist} km")
    next_focus = insights.get("next_week_focus","")

    # Colour the vs-avg chip
    vs_color = "#22c55e" if vs_avg >= 0 else "#ef4444"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Weekly Run Report — {data["week_label"]}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600&display=swap" rel="stylesheet">
<style>
  :root{{--o:#f97316;--a:#f59e0b;--t:#14b8a6;--r:#ef4444;--g:#22c55e;--p:#8b5cf6;
         --bg:#080b12;--sf:#0f1520;--card:#141926;--bdr:#1a2035;--tx:#dde2f0;--mu:#4a5270;--dim:#1e2540;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  html{{scroll-behavior:smooth;}}
  body{{background:var(--bg);color:var(--tx);font-family:'Source Serif 4',serif;font-weight:300;line-height:1.75;font-size:16px;}}
  .wrap{{max-width:940px;margin:0 auto;padding:0 32px;}}
  @media(max-width:600px){{.wrap{{padding:0 16px;}}}}

  .header{{background:linear-gradient(180deg,#0f1520 0%,#080b12 100%);border-bottom:3px solid var(--o);padding:44px 0 36px;position:relative;overflow:hidden;}}
  .header::before{{content:'';position:absolute;inset:0;background:radial-gradient(ellipse 80% 60% at 65% 30%,rgba(249,115,22,.07) 0%,transparent 70%);pointer-events:none;}}
  .header-inner{{position:relative;z-index:1;}}
  .tag{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.18em;color:var(--o);text-transform:uppercase;margin-bottom:8px;}}
  .report-title{{font-family:'Playfair Display',serif;font-size:clamp(28px,5vw,50px);font-weight:900;color:#fff;line-height:1;margin-bottom:6px;}}
  .report-title em{{color:var(--o);font-style:italic;}}
  .report-sub{{font-size:12px;color:var(--mu);font-family:'IBM Plex Mono',monospace;margin-top:6px;}}

  .ai-headline{{background:linear-gradient(135deg,#0a1a0a,#0f1520);border:1px solid rgba(34,197,94,.2);border-left:4px solid var(--g);border-radius:10px;padding:20px 24px;margin:24px 0 0;}}
  .ai-hl-tag{{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.16em;color:var(--g);text-transform:uppercase;margin-bottom:8px;display:flex;align-items:center;gap:6px;}}
  .ai-hl-tag::before{{content:'◆';font-size:8px;}}
  .ai-headline-text{{font-family:'Playfair Display',serif;font-size:clamp(18px,3vw,24px);font-style:italic;color:#ccd4e8;line-height:1.4;}}

  .hero{{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:10px;margin:24px 0;}}
  .hs{{background:var(--card);border:1px solid var(--bdr);border-radius:10px;padding:14px 16px;}}
  .hs-l{{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.12em;color:var(--mu);text-transform:uppercase;display:block;margin-bottom:4px;}}
  .hs-v{{font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:500;color:var(--o);display:block;line-height:1;}}
  .hs-v.g{{color:var(--g);}}.hs-v.t{{color:var(--t);}}.hs-v.a{{color:var(--a);}}.hs-v.r{{color:var(--r);}}.hs-v.m{{color:var(--mu);}}
  .hs-d{{font-size:11px;color:var(--mu);margin-top:3px;display:block;}}
  .hs-delta{{font-family:'IBM Plex Mono',monospace;font-size:11px;margin-top:3px;display:block;}}

  .section{{padding:40px 0 28px;border-top:1px solid var(--bdr);}}
  .sh{{font-family:'IBM Plex Mono',monospace;font-size:10px;letter-spacing:.16em;color:var(--o);text-transform:uppercase;margin-bottom:16px;display:flex;align-items:center;gap:10px;}}
  .sh::after{{content:'';flex:1;height:1px;background:var(--bdr);}}
  .ai-badge{{display:inline-flex;align-items:center;gap:4px;background:rgba(34,197,94,.08);border:1px solid rgba(34,197,94,.2);border-radius:4px;padding:2px 7px;font-size:9px;color:var(--g);letter-spacing:.06em;}}

  .narrative{{max-width:720px;}}
  .narrative p{{color:#8090b0;font-size:15px;line-height:1.9;margin-bottom:1.3em;}}
  .narrative p strong{{color:var(--tx);font-weight:600;}}

  .signals{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:10px;margin:20px 0;}}
  .signal{{background:var(--card);border:1px solid var(--bdr);border-radius:9px;padding:15px 17px;}}
  .signal-positive{{border-left:3px solid var(--g);}}.signal-warning{{border-left:3px solid var(--r);}}.signal-neutral{{border-left:3px solid var(--t);}}
  .signal-header{{display:flex;align-items:center;gap:8px;margin-bottom:6px;}}
  .signal-icon{{font-size:14px;font-weight:700;}}.signal-label{{font-size:13px;font-weight:600;color:var(--tx);}}
  .signal-detail{{font-size:13px;color:var(--mu);line-height:1.65;}}

  .next-focus{{background:linear-gradient(135deg,#0f0f1a,#0f1520);border:1px solid rgba(139,92,246,.25);border-left:4px solid var(--p);border-radius:10px;padding:18px 22px;margin-top:20px;}}
  .nf-tag{{font-family:'IBM Plex Mono',monospace;font-size:9px;letter-spacing:.14em;color:var(--p);text-transform:uppercase;margin-bottom:8px;}}
  .nf-body{{font-size:14px;color:#8090b0;line-height:1.75;}}

  .fig{{background:var(--card);border:1px solid var(--bdr);border-radius:12px;overflow:hidden;margin:18px 0;}}
  .fig-h{{padding:16px 20px 0;display:flex;justify-content:space-between;align-items:flex-start;}}
  .fig-title{{font-size:14px;font-weight:600;color:var(--tx);}}.fig-n{{font-family:'IBM Plex Mono',monospace;font-size:9px;color:var(--o);letter-spacing:.1em;text-transform:uppercase;}}
  .fig-body{{padding:14px 20px;}}.fig-cap{{padding:10px 20px 14px;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--mu);border-top:1px solid var(--bdr);line-height:1.6;}}
  canvas{{display:block;width:100%!important;}}

  .act-grid{{display:flex;flex-direction:column;gap:8px;}}
  .act-card{{background:var(--bg);border:1px solid var(--bdr);border-radius:8px;padding:12px 16px;}}
  .act-meta{{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--mu);}}
  .act-name{{font-size:14px;font-weight:600;color:var(--tx);margin:3px 0 6px;}}
  .act-stats{{display:flex;gap:14px;flex-wrap:wrap;font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--t);}}
  .act-desc{{font-size:12px;color:var(--mu);font-style:italic;margin-top:8px;border-left:2px solid var(--dim);padding-left:10px;line-height:1.6;}}
  .empty{{color:var(--mu);font-size:14px;padding:8px 0;}}

  .zones{{display:flex;flex-direction:column;gap:9px;}}
  .zr{{display:flex;align-items:center;gap:10px;}}
  .zl{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mu);width:90px;flex-shrink:0;}}
  .zb{{flex:1;height:6px;background:var(--dim);border-radius:3px;overflow:hidden;}}
  .zbi{{height:100%;border-radius:3px;opacity:.85;}}
  .zp{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--mu);width:30px;text-align:right;}}

  .footer{{border-top:1px solid var(--bdr);padding:32px 0 48px;margin-top:48px;}}
  .footer p{{font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--mu);line-height:1.9;}}
</style>
</head>
<body>

<div class="header">
  <div class="wrap header-inner">
    <div class="tag">Weekly Running Report · Strava + Claude AI</div>
    <div class="report-title">Week of <em>{data["week_label"].replace("w/c ","")}</em></div>
    <div class="report-sub">Generated {data["generated_at"]}</div>
    <div class="ai-headline">
      <div class="ai-hl-tag">Claude · Weekly Read</div>
      <div class="ai-headline-text">{headline}</div>
    </div>
  </div>
</div>

<div class="wrap">

  <div class="hero" style="margin-top:24px;">
    <div class="hs">
      <span class="hs-l">This Week</span>
      <span class="hs-v {"g" if vs_avg >= 0 else ""}">{dist} km</span>
      <span class="hs-delta" style="color:{vs_color}">{vs_str}</span>
    </div>
    <div class="hs"><span class="hs-l">Runs</span><span class="hs-v">{runs}</span></div>
    <div class="hs"><span class="hs-l">Avg Pace</span><span class="hs-v t">{pace}/km</span></div>
    <div class="hs"><span class="hs-l">Avg HR</span><span class="hs-v r">{hr}{" bpm" if hr != "–" else ""}</span></div>
    <div class="hs"><span class="hs-l">Elevation</span><span class="hs-v a">{elev} m</span></div>
    <div class="hs"><span class="hs-l">8-wk Avg</span><span class="hs-v m">{rolling} km</span></div>
    <div class="hs"><span class="hs-l">Streak</span><span class="hs-v" style="color:{streak_color}">{streak}d</span></div>
    <div class="hs">
      <span class="hs-l">Aero Eff.</span>
      <span class="hs-v t">{aeff_str}</span>
      <span class="hs-delta" style="color:{aeff_delta_color}">{aeff_delta}</span>
    </div>
  </div>

  <div class="section">
    <div class="sh">Analysis <span class="ai-badge">◆ Claude</span></div>
    <div class="narrative">{narrative_html}</div>
    <div class="signals">{signals_html}</div>
    <div class="next-focus">
      <div class="nf-tag">Focus for next week</div>
      <div class="nf-body">{next_focus}</div>
    </div>
  </div>

  <div class="section">
    <div class="sh">Volume — Last 16 Weeks</div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Weekly Distance & Rolling Average</span><span class="fig-n">Fig. 1</span></div>
      <div class="fig-body"><canvas id="chart-weekly" height="220"></canvas></div>
      <div class="fig-cap">Weekly distance (bars). Orange = this week. Teal dashed = 8-week rolling average. Above the line = above-average week.</div>
    </div>
  </div>

  <div class="section">
    <div class="sh">Notable Activities This Week</div>
    <div class="act-grid">{notable_html}</div>
  </div>

  <div class="section">
    <div class="sh">Heart Rate</div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Average HR per Week</span><span class="fig-n">Fig. 2</span></div>
      <div class="fig-body"><canvas id="chart-hr" height="200"></canvas></div>
      <div class="fig-cap">Sustained downward trend at maintained volume = improving aerobic fitness. Green dots = weeks below 126 bpm.</div>
    </div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">HR Zone Distribution — This Week</span><span class="fig-n">Fig. 3</span></div>
      <div class="fig-body"><div class="zones">{zones_html}</div></div>
      <div class="fig-cap">Estimated from avg HR vs max 185 bpm. Polarised training = high Z1–Z2, low Z3, moderate Z4–Z5.</div>
    </div>
  </div>

  <div class="section">
    <div class="sh">Aerobic Efficiency</div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Pace at 130–145 bpm — 8-Week Rolling</span><span class="fig-n">Fig. 4</span></div>
      <div class="fig-body" style="padding:20px 24px;">
        <div style="display:flex;align-items:flex-end;gap:32px;flex-wrap:wrap;">
          <div>
            <div style="font-family:'IBM Plex Mono',monospace;font-size:9px;color:var(--mu);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;">Current 8-week avg</div>
            <div style="font-family:'IBM Plex Mono',monospace;font-size:36px;font-weight:500;color:var(--t);">{aeff_str}</div>
          </div>
          {"<div><div style='font-family:IBM Plex Mono,monospace;font-size:9px;color:var(--mu);text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;'>vs prior 8 weeks</div><div style='font-family:IBM Plex Mono,monospace;font-size:22px;font-weight:500;color:" + aeff_delta_color + ";'>" + aeff_delta + "</div></div>" if aeff_delta else ""}
        </div>
        <div style="margin-top:14px;font-size:13px;color:var(--mu);line-height:1.65;">Holds cardiac effort constant (130–145 bpm) to isolate true running economy. Faster at the same HR = aerobic engine improving.</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="sh">Parkrun</div>
    {"<div style='background:var(--card);border:1px solid rgba(245,158,11,.3);border-left:3px solid var(--a);border-radius:8px;padding:13px 16px;margin-bottom:14px;'><div style='font-family:IBM Plex Mono,monospace;font-size:9px;color:var(--a);text-transform:uppercase;letter-spacing:.12em;'>All-Time PB</div><div style='font-family:IBM Plex Mono,monospace;font-size:22px;color:var(--a);margin-top:4px;'>" + bp_str + "</div></div>" if bp_str else ""}
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Parkrun Times & HR</span><span class="fig-n">Fig. 5</span></div>
      <div class="fig-body"><canvas id="chart-parkrun" height="230"></canvas></div>
      <div class="fig-cap">Finish time (bars, left axis). HR (line, right axis). Green = sub-20. Orange = sub-22. Faster time at same HR = fitness gained.</div>
    </div>
  </div>

  <div class="footer">
    <p>Weekly Running Report · GitHub Actions · {data["generated_at"]}<br>
    Data: Strava API · Insights: Claude (claude-sonnet-4-20250514)<br>
    {HISTORY_WEEKS}-week analysis window · {data["total_activities"]} activities</p>
  </div>

</div>

<script>
const GC='rgba(26,32,53,.9)',TC='#2a3050';
Chart.defaults.color='#4a5270';
Chart.defaults.font.family="'IBM Plex Mono',monospace";
Chart.defaults.font.size=11;

new Chart(document.getElementById('chart-weekly'),{{
  type:'bar',
  data:{{labels:{w_labels},datasets:[
    {{label:'Weekly km',data:{w_dists},backgroundColor:{w_dists}.map((_,i)=>i==={w_dists}.length-1?'#f97316':'rgba(249,115,22,.48)'),borderRadius:4,order:2}},
    {{type:'line',label:'8-wk avg',data:{r_line},borderColor:'rgba(20,184,166,.65)',borderWidth:1.5,borderDash:[6,4],pointRadius:0,tension:0,order:1}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:true,
    plugins:{{legend:{{labels:{{color:'#5a6280',boxWidth:12}}}},tooltip:{{callbacks:{{label:c=>` ${{c.parsed.y}} km`}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{color:TC,maxRotation:45,font:{{size:9}}}}}},y:{{grid:{{color:GC}},ticks:{{color:TC,callback:v=>v+'km'}}}}}}}}
}});

const hd={w_hrs};
new Chart(document.getElementById('chart-hr'),{{
  type:'line',
  data:{{labels:{w_labels},datasets:[{{label:'Avg HR',data:hd,borderColor:'#ef4444',backgroundColor:'rgba(239,68,68,.08)',borderWidth:2.5,pointRadius:4,pointBackgroundColor:hd.map(h=>h&&h<=126?'#22c55e':'#ef4444'),tension:.3,fill:true}}]}},
  options:{{responsive:true,maintainAspectRatio:true,
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:c=>`${{c.parsed.y}} bpm`}}}}}},
    scales:{{x:{{grid:{{color:GC}},ticks:{{color:TC,maxRotation:45,font:{{size:9}}}}}},y:{{grid:{{color:GC}},ticks:{{color:TC,callback:v=>v+' bpm'}}}}}}}}
}});

const prt={pr_times},prh={pr_hrs};
new Chart(document.getElementById('chart-parkrun'),{{
  type:'bar',
  data:{{labels:{pr_labels},datasets:[
    {{type:'bar',label:'Time (min)',data:prt,backgroundColor:prt.map(t=>t<20?'#22c55e':t<22?'#f97316':t>27?'#1e2540':'#3b82f6'),borderRadius:3,yAxisID:'y',order:2}},
    {{type:'line',label:'HR',data:prh,borderColor:'rgba(239,68,68,.6)',borderWidth:1.5,pointRadius:3,tension:.3,yAxisID:'y2',order:1}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:true,
    plugins:{{legend:{{labels:{{color:'#5a6280',boxWidth:12}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{color:TC,font:{{size:9}}}}}},
      y:{{grid:{{color:GC}},reverse:true,min:18,max:32,ticks:{{color:TC,callback:v=>`${{Math.floor(v)}}:${{String(Math.round((v-Math.floor(v))*60)).padStart(2,'0')}}`}}}},
      y2:{{grid:{{display:false}},min:110,max:190,position:'right',ticks:{{color:'#ef4444'}}}}}}}}
}});
</script>
</body>
</html>"""


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print("=== Strava Weekly Report + Claude Insights ===")

    access_token, new_refresh = refresh_access_token()
    if new_refresh != STRAVA_REFRESH_TOKEN:
        print("⚠  Refresh token rotated — writing new_refresh_token.txt")
        Path("new_refresh_token.txt").write_text(new_refresh)

    data = build_report_data(access_token)

    try:
        insights = get_claude_insights(data)
    except Exception as e:
        print(f"⚠  Claude error ({e}) — using fallback")
        insights = {
            "headline": f"{data['week_label']} — {(data['this_week'] or {}).get('dist_km','?')} km",
            "week_narrative": "AI insights unavailable this week. Check API key and logs.",
            "key_signals": [],
            "next_week_focus": "Review charts manually this week.",
        }

    html = generate_html(data, insights)

    dated  = OUTPUT_DIR / f"report_{datetime.now().strftime('%Y-%m-%d')}.html"
    latest = OUTPUT_DIR / "index.html"
    dated.write_text(html, encoding="utf-8")
    latest.write_text(html, encoding="utf-8")

    tw = data["this_week"] or {}
    print(f"\n✓ {dated.name} written")
    print(f"  {tw.get('dist_km','–')} km · {tw.get('runs','–')} runs · "
          f"{tw.get('avg_pace','–')}/km · {tw.get('avg_hr','–')} bpm")
    print(f"  Streak: {data['current_streak']} days")
    print(f'\n  Headline: "{insights["headline"]}"')


if __name__ == "__main__":
    main()
