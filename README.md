# ResearchAssistants_SBW

Automated bots that monitor scientific data repositories, citation networks, and journal feeds —
sending weekly email digests and publishing a GitHub Pages digest site.

## Architecture

Each bot lives in its own self-contained folder alongside everything it needs to run.
GitHub Actions workflows trigger each bot on a Monday morning schedule.

```
ResearchAssistants_SBW/
├── zenodo_bot/                  # Bot 1 — Zenodo scRNA-seq dataset discovery
│   ├── zenodo_bot.py
│   └── utils/
│       ├── email_logic.py       # Gmail SMTP sending
│       └── ai_logic.py          # HuggingFace BART summarisation
│
├── citation_bot/                # Bot 2 — Citation tracking via OpenAlex
│   ├── citation_bot.py
│   └── utils/
│       ├── email_logic.py
│       └── ai_logic.py
│
├── journal_digest/              # Bot 3 — Weekly journal RSS digest
│   ├── scraper/
│   │   ├── main.py              # Orchestrator
│   │   ├── feeds.py             # RSS feed parsing
│   │   ├── extract_repos.py     # Code/data repo link extraction
│   │   ├── summarise.py         # AI summarisation (HuggingFace)
│   │   ├── cluster.py           # Semantic clustering by topic
│   │   ├── report.py            # Markdown digest generation
│   │   ├── trends.py            # Tag frequency trend tracking
│   │   ├── manifest.py          # JSON metadata manifest
│   │   └── md_to_html_email.py  # Markdown → styled HTML email
│   ├── config.yaml              # Journal RSS feeds + watchlist terms
│   ├── digests/                 # Output: weekly markdown digests (committed)
│   └── trends/                  # Output: tag_counts.csv + monthly reports (committed)
│
├── docs/                        # GitHub Pages output (committed by workflow)
├── .github/workflows/
│   ├── zenodo_run.yml           # Mon 05:00 UTC
│   ├── citation_run.yml         # Mon 06:00 UTC
│   └── weekly_digest.yml        # Mon 07:00 UTC
├── requirements.txt
├── .gitignore
└── README.md
```

## Active Bots

### Zenodo Bot (`zenodo_bot/`)
Queries the Zenodo API for new single-cell RNA-seq datasets published in the past week.
Extracts metadata (species, tissue, cell counts), generates AI summaries via HuggingFace,
and emails a formatted HTML report.

### Citation Bot (`citation_bot/`)
Uses the OpenAlex API to find papers citing your research (ORCID: 0000-0002-8994-0781).
Summarises abstracts, tags papers as Microscopy/Transcriptomics, and sends a
Citation Intelligence Report.

### Journal Digest (`journal_digest/`)
Fetches papers from RSS feeds across Nature, Science, Cell, and related journals.
Extracts repository links, generates AI summaries, clusters papers by topic, tracks keyword
trends over time, and publishes a styled weekly digest via email and GitHub Pages.

Configured via `journal_digest/config.yaml` — edit journals and watchlist terms there.

## Schedule

| Bot | Workflow | Time (UTC) |
|---|---|---|
| Zenodo Bot | `zenodo_run.yml` | Monday 05:00 |
| Citation Bot | `citation_run.yml` | Monday 06:00 |
| Journal Digest | `weekly_digest.yml` | Monday 07:00 |

All workflows can also be triggered manually via **Actions → workflow → Run workflow**.

## Running Locally

```bash
pip install -r requirements.txt

# Zenodo Bot
export PYTHONPATH=zenodo_bot
export EMAIL_SENDER="you@gmail.com"
export EMAIL_RECEIVER="you@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export HF_TOKEN="hf_your_token"
python zenodo_bot/zenodo_bot.py

# Citation Bot
export PYTHONPATH=citation_bot
python citation_bot/citation_bot.py

# Journal Digest (runs from journal_digest/ as working directory)
cd journal_digest
export HF_API_TOKEN="hf_your_token"
python -m scraper.main
```

On Windows, use `set` instead of `export`.

## Environment Variables

| Variable | Used By | Description |
|---|---|---|
| `EMAIL_SENDER` | zenodo, citation | Gmail address for sending |
| `EMAIL_RECEIVER` | zenodo, citation, digest | Recipient email address |
| `EMAIL_PASSWORD` | zenodo, citation, digest | Gmail App Password |
| `HF_TOKEN` | zenodo, citation | HuggingFace API token |
| `HF_API_TOKEN` | journal digest | HuggingFace API token (mapped from `HF_TOKEN` in workflow) |
| `LOOKBACK_PERIOD` | zenodo, citation | `week` (default), `month`, or `6months` |

All secrets are stored in **GitHub repo Settings → Secrets and variables → Actions**.

## Adding a New Bot

1. **Create a folder** at the repo root: `your_bot/`

2. **Add the bot script** `your_bot/your_bot.py`:

   ```python
   """Description of what your bot does."""
   import os
   import datetime
   import requests
   from utils.email_logic import send_email
   from utils.ai_logic import get_ai_summary

   def run():
       # 1. Query your data source API
       # 2. Process each result (optionally use get_ai_summary())
       # 3. Build HTML content string
       # 4. Call send_email()
       html_content = "<h2>Your Report</h2>"
       send_email(f"Your Report: {datetime.date.today()}", html_content)

   if __name__ == "__main__":
       run()
   ```

3. **Copy `utils/`** from an existing bot into `your_bot/utils/`:

   ```bash
   cp -r zenodo_bot/utils/ your_bot/utils/
   ```

4. **Create a workflow** at `.github/workflows/your_bot_run.yml`:

   ```yaml
   name: Your Bot Name
   on:
     schedule:
       - cron: '0 8 * * 1'    # Pick a time that doesn't overlap
     workflow_dispatch:
   jobs:
     your-bot:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.11'
         - run: pip install -r requirements.txt
         - name: Run bot
           env:
             PYTHONPATH: your_bot
             EMAIL_SENDER:   ${{ secrets.EMAIL_SENDER }}
             EMAIL_RECEIVER: ${{ secrets.EMAIL_RECEIVER }}
             EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
             HF_TOKEN:       ${{ secrets.HF_TOKEN }}
           run: python your_bot/your_bot.py
   ```

5. **Update `requirements.txt`** if your bot needs additional packages, then commit and push.
