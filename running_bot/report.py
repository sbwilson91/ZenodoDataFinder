"""
running_bot/report.py — HTML report renderer.
Generates a self-contained HTML file with Chart.js visualisations.
"""

import json


def generate_html(data: dict, insights: dict, history_weeks: int = 16) -> str:
    tw      = data.get("this_week") or {}
    dist    = tw.get("dist_km", 0)
    runs    = tw.get("runs", 0)
    pace    = tw.get("avg_pace", "–")
    hr      = tw.get("avg_hr", "–")
    elev    = tw.get("elev_m", 0)
    rolling = data["rolling_avg_km"]
    vs_avg  = round(dist - rolling, 1)
    vs_str  = (f"+{vs_avg}" if vs_avg >= 0 else str(vs_avg)) + " km"
    vs_col  = "#22c55e" if vs_avg >= 0 else "#ef4444"

    ws = data.get("weekly_series", [])
    w_labels = json.dumps([w["week"][5:] for w in ws])
    w_dists  = json.dumps([w["dist_km"]  for w in ws])
    w_hrs    = json.dumps([w["avg_hr"]   for w in ws])
    r_line   = json.dumps([rolling]      * len(ws))
    last_idx = len(ws) - 1

    all_prs   = data.get("all_parkruns", [])
    pr_labels = json.dumps([p["date"][5:] for p in all_prs])
    pr_times  = json.dumps([round(p["time_min"], 2) for p in all_prs])
    pr_hrs    = json.dumps([p["hr"] for p in all_prs])

    aeff     = data.get("aero_eff_now")
    aeff_p   = data.get("aero_eff_prev")
    aeff_str = f"{int(aeff)}:{int((aeff%1)*60):02d}/km" if aeff else "–"
    if aeff and aeff_p:
        diff_s           = round((aeff_p - aeff) * 60)
        aeff_delta       = f"{'↑' if diff_s>0 else '↓'} {abs(diff_s)}s/km vs prior 8 wks"
        aeff_delta_color = "#22c55e" if diff_s > 0 else "#ef4444"
    else:
        aeff_delta, aeff_delta_color = "", "#4a5270"

    streak       = data.get("current_streak", 0)
    streak_color = "#22c55e" if streak > 7 else "#f97316" if streak > 0 else "#4a5270"

    bp = data.get("best_parkrun")
    bp_html = ""
    if bp:
        bm, bs = int(bp["time_min"]), int((bp["time_min"] % 1) * 60)
        bp_html = (
            f'<div style="background:var(--card);border:1px solid rgba(245,158,11,.3);'
            f'border-left:3px solid var(--a);border-radius:8px;padding:13px 16px;margin-bottom:14px;">'
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:var(--a);'
            f'text-transform:uppercase;letter-spacing:.12em;">All-Time PB</div>'
            f'<div style="font-family:IBM Plex Mono,monospace;font-size:22px;color:var(--a);'
            f'margin-top:4px;">{bm}:{bs:02d} ({bp["date"]})</div></div>'
        )

    # Zone bars
    zones  = data.get("zone_dist", {})
    tz_tot = sum(zones.values()) or 1
    z_pcts = {z: round(v/tz_tot*100) for z, v in zones.items()}
    z_col  = {"Z1":"#60a5fa","Z2":"#14b8a6","Z3":"#f59e0b","Z4":"#f97316","Z5":"#ef4444"}
    z_name = {"Z1":"Z1 Recovery","Z2":"Z2 Easy","Z3":"Z3 Aerobic","Z4":"Z4 Threshold","Z5":"Z5 Max"}
    zones_html = "".join(
        f'<div class="zr"><div class="zl">{z_name[z]}</div>'
        f'<div class="zb"><div class="zbi" style="width:{z_pcts[z]}%;background:{z_col[z]};"></div></div>'
        f'<div class="zp">{z_pcts[z]}%</div></div>'
        for z in ["Z1","Z2","Z3","Z4","Z5"]
    )

    # Notable activity cards
    notable_html = ""
    for n in data.get("notable", [])[:8]:
        hr_span   = f'<span>♥ {n["hr"]} bpm</span>' if n.get("hr") else ""
        desc_html = (f'<div class="act-desc">&ldquo;{n["desc"]}&rdquo;</div>'
                     if n.get("desc") else "")
        notable_html += (
            f'<div class="act-card">'
            f'<div class="act-meta">{n["date"]}</div>'
            f'<div class="act-name">{n["name"]}</div>'
            f'<div class="act-stats"><span>{n["dist_km"]} km</span>'
            f'<span>{n["time"]}</span><span>{n["pace"]}/km</span>{hr_span}</div>'
            f'{desc_html}</div>'
        )
    if not notable_html:
        notable_html = '<p class="empty">No notable activities this week.</p>'

    # AI signal cards
    sig_color = {"positive":"#22c55e","warning":"#ef4444","neutral":"#14b8a6"}
    sig_icon  = {"positive":"↑","warning":"⚠","neutral":"→"}
    signals_html = ""
    for sig in insights.get("key_signals", []):
        t = sig.get("type", "neutral")
        signals_html += (
            f'<div class="signal signal-{t}">'
            f'<div class="signal-header">'
            f'<span class="signal-icon" style="color:{sig_color.get(t,"#14b8a6")}">'
            f'{sig_icon.get(t,"→")}</span>'
            f'<span class="signal-label">{sig.get("signal","")}</span></div>'
            f'<div class="signal-detail">{sig.get("detail","")}</div></div>'
        )

    narrative_html = "".join(
        f"<p>{p.strip()}</p>"
        for p in insights.get("week_narrative","").split("\n\n") if p.strip()
    )

    headline    = insights.get("headline", f"{data['week_label']} — {dist} km")
    next_focus  = insights.get("next_week_focus", "")
    aeff_delta_html = (
        f'<div><div style="font-family:IBM Plex Mono,monospace;font-size:9px;color:var(--mu);'
        f'text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;">vs prior 8 weeks</div>'
        f'<div style="font-family:IBM Plex Mono,monospace;font-size:22px;font-weight:500;'
        f'color:{aeff_delta_color};">{aeff_delta}</div></div>'
        if aeff_delta else ""
    )

    hs_v_class = "g" if vs_avg >= 0 else ""

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
         --bg:#080b12;--card:#141926;--bdr:#1a2035;--tx:#dde2f0;--mu:#4a5270;--dim:#1e2540;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
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
    <div class="tag">ResearchAssistants_SBW · Running Bot · Strava + Claude</div>
    <div class="report-title">Week of <em>{data["week_label"].replace("w/c ","")}</em></div>
    <div class="report-sub">Generated {data["generated_at"]} · {data["total_activities"]} activities in window</div>
    <div class="ai-headline">
      <div class="ai-hl-tag">Claude · Weekly Read</div>
      <div class="ai-headline-text">{headline}</div>
    </div>
  </div>
</div>
<div class="wrap">
  <div class="hero" style="margin-top:24px;">
    <div class="hs"><span class="hs-l">This Week</span><span class="hs-v {hs_v_class}">{dist} km</span><span class="hs-delta" style="color:{vs_col}">{vs_str}</span></div>
    <div class="hs"><span class="hs-l">Runs</span><span class="hs-v">{runs}</span></div>
    <div class="hs"><span class="hs-l">Avg Pace</span><span class="hs-v t">{pace}/km</span></div>
    <div class="hs"><span class="hs-l">Avg HR</span><span class="hs-v r">{hr}{" bpm" if hr != "–" else ""}</span></div>
    <div class="hs"><span class="hs-l">Elevation</span><span class="hs-v a">{elev} m</span></div>
    <div class="hs"><span class="hs-l">8-wk Avg</span><span class="hs-v m">{rolling} km</span></div>
    <div class="hs"><span class="hs-l">Streak</span><span class="hs-v" style="color:{streak_color}">{streak}d</span></div>
    <div class="hs"><span class="hs-l">Aero Eff.</span><span class="hs-v t">{aeff_str}</span><span class="hs-delta" style="color:{aeff_delta_color}">{aeff_delta}</span></div>
  </div>
  <div class="section">
    <div class="sh">Analysis <span class="ai-badge">◆ Claude</span></div>
    <div class="narrative">{narrative_html}</div>
    <div class="signals">{signals_html}</div>
    <div class="next-focus"><div class="nf-tag">Focus for next week</div><div class="nf-body">{next_focus}</div></div>
  </div>
  <div class="section">
    <div class="sh">Volume — Last {history_weeks} Weeks</div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Weekly Distance & Rolling Average</span><span class="fig-n">Fig. 1</span></div>
      <div class="fig-body"><canvas id="chart-weekly" height="220"></canvas></div>
      <div class="fig-cap">Weekly distance (bars). Orange = this week. Teal dashed = 8-week rolling average.</div>
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
      <div class="fig-cap">Sustained downward trend at maintained volume = improving aerobic fitness.</div>
    </div>
    <div class="fig">
      <div class="fig-h"><span class="fig-title">HR Zone Distribution — This Week</span><span class="fig-n">Fig. 3</span></div>
      <div class="fig-body"><div class="zones">{zones_html}</div></div>
      <div class="fig-cap">Estimated from avg HR vs max 185 bpm. Polarised = high Z1–Z2, low Z3.</div>
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
          {aeff_delta_html}
        </div>
        <div style="margin-top:14px;font-size:13px;color:var(--mu);">Holds cardiac effort constant. Faster at same HR = aerobic engine improving.</div>
      </div>
    </div>
  </div>
  <div class="section">
    <div class="sh">Parkrun</div>
    {bp_html}
    <div class="fig">
      <div class="fig-h"><span class="fig-title">Parkrun Times & HR</span><span class="fig-n">Fig. 5</span></div>
      <div class="fig-body"><canvas id="chart-parkrun" height="230"></canvas></div>
      <div class="fig-cap">Finish time (bars, left). HR (line, right). Green = sub-20. Orange = sub-22.</div>
    </div>
  </div>
  <div class="footer">
    <p>ResearchAssistants_SBW · running_bot · {data["generated_at"]}<br>
    Data: Strava API · Insights: Claude (claude-sonnet-4-20250514)<br>
    {history_weeks}-week window · {data["total_activities"]} activities</p>
  </div>
</div>
<script>
const GC='rgba(26,32,53,.9)',TC='#2a3050';
Chart.defaults.color='#4a5270';
Chart.defaults.font.family="'IBM Plex Mono',monospace";
Chart.defaults.font.size=11;
const wd={w_dists};
new Chart(document.getElementById('chart-weekly'),{{
  type:'bar',
  data:{{labels:{w_labels},datasets:[
    {{label:'Weekly km',data:wd,backgroundColor:wd.map((_,i)=>i==={last_idx}?'#f97316':'rgba(249,115,22,.48)'),borderRadius:4,order:2}},
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
    {{type:'bar',label:'Time',data:prt,backgroundColor:prt.map(t=>t<20?'#22c55e':t<22?'#f97316':t>27?'#1e2540':'#3b82f6'),borderRadius:3,yAxisID:'y',order:2}},
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
