import requests
import datetime
import smtplib
import re
import os
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration from Environment Variables
HF_TOKEN = os.environ.get("HF_TOKEN")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
LOOKBACK_PERIOD = os.environ.get("LOOKBACK_PERIOD", "week")

def get_date_query(period):
    days = {'week': 7, 'month': 30, '6months': 180}.get(period, 7)
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    return f"[{start_date} TO *]"

def get_ai_summary(text):
    if not HF_TOKEN: return "No AI Token provided."
    API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    clean_text = re.sub('<[^<]+?>', '', text).strip()[:1024]

    if len(clean_text) < 50:
        return "Description too short for summary."

    for attempt in range(3):
        try:
            response = requests.post(API_URL, headers=headers, json={"inputs": clean_text}, timeout=30)
            try:
                res_json = response.json()
            except ValueError:
                print(f"HuggingFace returned non-JSON (status {response.status_code})")
                return "AI Summary unavailable."
            if isinstance(res_json, list) and len(res_json) > 0:
                return res_json[0].get('summary_text', "Summary content missing.")
            elif isinstance(res_json, dict) and "estimated_time" in res_json:
                wait = min(res_json['estimated_time'], 30)
                print(f"Model loading, waiting {wait:.0f}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            elif isinstance(res_json, dict) and "error" in res_json:
                print(f"HuggingFace error: {res_json['error']}")
                return "AI Summary unavailable."
        except Exception as e:
            print(f"HuggingFace request failed: {e}")
    return "AI Summary unavailable."

def get_quick_stats(meta, files):
    """Extract species, tissue, cell counts from Zenodo metadata fields."""
    stats = []
    desc = re.sub('<[^<]+?>', '', meta.get('description', '')).lower()
    keywords = [k.lower() for k in meta.get('keywords', [])]

    # Species detection
    species_patterns = {
        'Human': r'\b(human|homo sapiens|patient|hg38|grch38|pbmc)\b',
        'Mouse': r'\b(mouse|mus musculus|murine|mm10|mm39)\b',
        'Zebrafish': r'\b(zebrafish|danio rerio)\b',
        'Drosophila': r'\b(drosophila|fruit fly)\b',
        'Rat': r'\b(rat|rattus)\b',
    }
    for species, pattern in species_patterns.items():
        if re.search(pattern, desc) or any(re.search(pattern, k) for k in keywords):
            stats.append(f"Species: {species}")
            break

    # Cell/nuclei count from description
    cell_match = re.search(r'([\d,\.]+)\s*(million|thousand|k)?\s*(cells|nuclei|transcriptomes|samples)', desc)
    if cell_match:
        stats.append(f"Scale: ~{cell_match.group(0).strip()}")

    # Tissue detection
    tissues = ['bone marrow', 'brain', 'lung', 'liver', 'kidney', 'blood',
               'tumor', 'skin', 'heart', 'intestine', 'pbmc', 'retina',
               'pancreas', 'spleen', 'thymus', 'colon', 'breast', 'ovary']
    for tissue in tissues:
        if tissue in desc or tissue in ' '.join(keywords):
            stats.append(f"Tissue: {tissue.title()}")
            break

    # File type summary
    extensions = {}
    for f in files:
        ext = '.' + f.get('key', '').rsplit('.', 1)[-1] if '.' in f.get('key', '') else 'other'
        extensions[ext] = extensions.get(ext, 0) + 1
    if extensions:
        file_summary = ', '.join(f"{count}x {ext}" for ext, count in sorted(extensions.items(), key=lambda x: -x[1]))
        stats.append(f"Files: {file_summary}")

    # Keywords
    raw_keywords = meta.get('keywords', [])
    if raw_keywords:
        stats.append(f"Tags: {', '.join(raw_keywords[:5])}")

    return ' | '.join(stats) if stats else "No metadata stats found."

def run():
    date_range = get_date_query(LOOKBACK_PERIOD)
    query = f'q=single cell RNA AND publication_date:{date_range} AND type:dataset'

    try:
        res = requests.get(f"https://zenodo.org/api/records?{query}&sort=mostrecent&size=10", timeout=20)
        res.raise_for_status()
        content_type = res.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            print(f"Zenodo returned non-JSON response (Content-Type: {content_type})")
            return
        hits = res.json().get('hits', {}).get('hits', [])
    except Exception as e:
        print(f"Zenodo API connection error: {e}")
        return

    if not hits:
        print("No new datasets found.")
        return

    html_content = f"<h2>scRNA-seq Zenodo Report ({LOOKBACK_PERIOD})</h2>"
    for hit in hits:
        meta = hit.get('metadata', {})
        links = hit.get('links', {})
        files = hit.get('files', [])

        # SAFE ACCESS: Use .get() to avoid KeyError
        record_url = links.get('html', f"https://zenodo.org/records/{hit.get('id', '')}")
        title = meta.get('title', 'Untitled Dataset')
        stats = get_quick_stats(meta, files)
        summary = get_ai_summary(meta.get('description', ""))
        total_size = sum(f.get('size', 0) for f in files) / 1e6

        html_content += f"""
        <div style='border-bottom:1px solid #eee; padding:10px; margin-bottom:10px;'>
            <a href='{record_url}'><h3>{title}</h3></a>
            <p><b>AI Summary:</b> {summary}</p>
            <p><b>Quick Stats:</b> {stats}</p>
            <p><b>Details:</b> {len(files)} files | Total Size: {total_size:.1f} MB</p>
        </div>"""

    # Email Logic
    msg = MIMEMultipart()
    msg['Subject'] = f"scRNA-seq Data Alert: {datetime.date.today()}"
    msg['To'] = EMAIL_RECEIVER
    msg['From'] = EMAIL_SENDER
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_SENDER, EMAIL_PASSWORD)
            s.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        print("Report sent successfully!")
    except Exception as e:
        print(f"Email failed to send: {e}")

if __name__ == "__main__":
    run()
