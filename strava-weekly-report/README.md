# Strava Weekly Running Report

Automatically generates a detailed personal running report every Monday morning using your Strava data. Deploys to GitHub Pages so you always have a live URL to check.

---

## What it produces

Every Monday at 08:00 UTC, a report is generated covering:

- **This week vs rolling average** — distance, runs, pace, HR, elevation
- **Weekly volume chart** — 16-week bar chart with rolling average line
- **Heart rate trend** — weekly avg HR over time (the primary fitness signal)
- **HR zone distribution** — how hard you actually trained
- **Aerobic efficiency** — pace at 130–145 bpm (8-week rolling, vs prior 8 weeks)
- **Notable activities** — races, long runs, named sessions with your own notes
- **Parkrun tracker** — all recent parkruns with times and HR overlay
- **Current run streak** — consecutive days with at least one run

The report is committed to the repo as `reports/YYYY-MM-DD.html` and the latest version is always at `reports/index.html`, which is served via GitHub Pages.

---

## Setup (15 minutes)

### 1. Create a Strava API app

Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api) and create an app:

- **Application Name**: anything (e.g. "Weekly Report")
- **Category**: Data Importer
- **Club**: leave blank
- **Website**: your GitHub Pages URL (or `http://localhost` for now)
- **Authorization Callback Domain**: `localhost`

Note your **Client ID** and **Client Secret**.

### 2. Get your refresh token (run once, locally)

```bash
# Clone this repo
git clone https://github.com/YOUR_USERNAME/strava-weekly-report
cd strava-weekly-report

# Install the one dependency
pip install requests

# Run the setup script — it will open a browser for Strava OAuth
python scripts/get_tokens.py
```

Follow the prompts. At the end it will print three values to copy.

### 3. Add secrets to GitHub

Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these three secrets:

| Secret name | Value |
|---|---|
| `STRAVA_CLIENT_ID` | your numeric client ID |
| `STRAVA_CLIENT_SECRET` | your client secret string |
| `STRAVA_REFRESH_TOKEN` | the refresh token from step 2 |
| `ANTHROPIC_API_KEY` | your Anthropic API key — get one at console.anthropic.com |

> **Note on token rotation:** Strava refreshes the token on every API call. The workflow automatically captures the new token and updates the `STRAVA_REFRESH_TOKEN` secret using the GitHub CLI, so you never have to rotate it manually.

### 4. Enable GitHub Pages

Go to your repo → **Settings → Pages**

- **Source**: GitHub Actions

That's it. After the first workflow run, your report will be live at:
`https://YOUR_USERNAME.github.io/strava-weekly-report/`

### 5. Run it manually to test

Go to **Actions → Weekly Running Report → Run workflow**

Check the run logs — it will print a summary to stdout even without looking at the HTML.

---

## Customisation

### Change the schedule

Edit `.github/workflows/weekly_report.yml`:

```yaml
schedule:
  - cron: "0 8 * * 1"   # Monday 08:00 UTC
```

Cron format: `minute hour day month weekday`. To run Sunday evening instead:
```yaml
  - cron: "0 20 * * 0"   # Sunday 20:00 UTC
```

### Adjust history window

In `scripts/generate_report.py`:

```python
HISTORY_WEEKS = 16   # how many weeks of data to pull and chart
```

### Adjust parkrun detection

The script detects parkruns as Saturday runs between 4.8–5.3 km. If you do a different 5k event on another day, adjust in `generate_report.py`:

```python
def is_parkrun(activity):
    dist = activity.get("distance", 0) / 1000
    date = datetime.fromisoformat(activity["start_date_local"])
    return date.weekday() == 5 and 4.8 <= dist <= 5.3
    # weekday(): 0=Mon, 5=Sat, 6=Sun
```

### Estimated max HR

The HR zone calculation uses 185 bpm as estimated max. Update in `generate_report.py`:

```python
pct = hr / 185 * 100   # replace 185 with your actual max HR
```

---

## File structure

```
strava-weekly-report/
├── .github/
│   └── workflows/
│       └── weekly_report.yml      # GitHub Actions schedule + deploy
├── scripts/
│   ├── generate_report.py         # main analysis + HTML generation
│   └── get_tokens.py              # one-time OAuth setup script
├── reports/
│   ├── index.html                 # latest report (served by Pages)
│   └── YYYY-MM-DD.html            # dated archive
└── README.md
```

---

## Strava API limits

The free Strava API allows **100 requests per 15 minutes** and **1,000 per day**. This script makes roughly 1–3 requests per run (more if you have many recent activities triggering pagination). A weekly run is well within limits.

If you want to add per-activity stream data (HR/cadence by the second), each activity costs one extra request. With 30+ runs a month that's 30 extra requests — still fine, but worth knowing.

---

## Troubleshooting

**"Token expired" errors**: The refresh token should auto-rotate. If the workflow fails on auth, re-run `scripts/get_tokens.py` and update the `STRAVA_REFRESH_TOKEN` secret manually.

**"No activities found"**: Check your Strava privacy settings — activities set to "Only you" are still visible to your own API app, but double-check the scope includes `activity:read_all`.

**Charts not rendering**: The report uses Chart.js from cdnjs. If you're viewing the HTML file locally (file://) some browsers block CDN requests. Just open it via a local server or push to Pages.
