# ResearchAssistants

Automated bots that monitor scientific data repositories and citation networks,
sending weekly email digests.

## Architecture

```
ResearchAssistants/
├── utils/               # Shared utilities (email, AI summarization)
│   ├── __init__.py
│   ├── email_logic.py   # Gmail SMTP email sending
│   └── ai_logic.py      # HuggingFace BART summarization
├── bots/                # Individual bot scripts
│   ├── zenodo_bot.py    # scRNA-seq dataset discovery on Zenodo
│   └── citation_bot.py  # Citation tracking via OpenAlex
├── .github/workflows/   # GitHub Actions schedules
│   ├── zenodo_run.yml
│   └── citation_run.yml
├── requirements.txt
└── README.md
```

## Active Bots

**Zenodo Bot** (`bots/zenodo_bot.py`) - Discovers new scRNA-seq datasets on Zenodo, extracts metadata (species, tissue, cell counts), generates AI summaries, and emails a weekly report.

**Citation Bot** (`bots/citation_bot.py`) - Uses the OpenAlex API to find papers citing your research (ORCID: 0000-0002-8994-0781), summarizes their abstracts, tags them as Microscopy/Transcriptomics, and sends a Citation Intelligence Report.

## Running Locally

```bash
# Set environment variables
export EMAIL_SENDER="you@gmail.com"
export EMAIL_RECEIVER="you@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export HF_TOKEN="hf_your_token"
export PYTHONPATH=.

pip install -r requirements.txt

# Run a bot
python bots/zenodo_bot.py
python bots/citation_bot.py
```

On Windows, use `set` instead of `export`:
```cmd
set PYTHONPATH=.
set EMAIL_SENDER=you@gmail.com
python bots/zenodo_bot.py
```

## Environment Variables

| Variable         | Required | Description                                |
|------------------|----------|--------------------------------------------|
| EMAIL_SENDER     | Yes      | Gmail address for sending reports          |
| EMAIL_RECEIVER   | Yes      | Recipient email address                    |
| EMAIL_PASSWORD   | Yes      | Gmail App Password                         |
| HF_TOKEN         | Yes      | HuggingFace API token                      |
| LOOKBACK_PERIOD  | No       | "week" (default), "month", or "6months"    |

## How to Add a New Bot

1. **Create the bot script** at `bots/your_bot.py`:

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
       # 4. Send the email
       html_content = "<h2>Your Report</h2>"
       # ... build html_content ...
       send_email(f"Your Report: {datetime.date.today()}", html_content)

   if __name__ == "__main__":
       run()
   ```

2. **Create a workflow file** at `.github/workflows/your_bot_run.yml`:

   ```yaml
   name: Your Bot Name
   on:
     schedule:
       - cron: '0 7 * * 1'    # Pick a time that doesn't overlap
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
             PYTHONPATH: .
             EMAIL_SENDER:   ${{ secrets.EMAIL_SENDER }}
             EMAIL_RECEIVER: ${{ secrets.EMAIL_RECEIVER }}
             EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
             HF_TOKEN:       ${{ secrets.HF_TOKEN }}
           run: python bots/your_bot.py
   ```

3. **Update `requirements.txt`** if your bot needs additional packages.

4. **Commit and push.** The workflow will run on schedule or via manual dispatch.
