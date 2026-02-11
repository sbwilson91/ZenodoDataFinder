import requests
import datetime
import smtplib
import re
import os
import anndata
import fsspec
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
    clean_text = re.sub('<[^<]+?>', '', text)[:1024]

    for _ in range(3): # Retry 3 times if model is loading
        try:
            response = requests.post(API_URL, headers=headers, json={"inputs": clean_text}, timeout=20)
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type:
                print(f"HuggingFace returned non-JSON response (Content-Type: {content_type})")
                return "AI Summary unavailable."
            res_json = response.json()
            if isinstance(res_json, list) and len(res_json) > 0:
                return res_json[0].get('summary_text', "Summary content missing.")
            elif isinstance(res_json, dict) and "estimated_time" in res_json:
                time.sleep(res_json['estimated_time'])
                continue
        except Exception:
            pass
    return "AI Summary unavailable."

def peek_data(files):
    # Safe check for H5AD
    h5ad = next((f for f in files if f.get('key', '').endswith('.h5ad')), None)
    if h5ad and h5ad.get('links', {}).get('self'):
        try:
            with fsspec.open(h5ad['links']['self'], mode='rb') as f:
                ad = anndata.read_h5ad(f, backed='r')
                return f"Peeked H5AD: {ad.n_obs} cells, {ad.n_vars} genes"
        except: pass

    # Safe check for Metadata CSV/TSV
    meta_file = next((f for f in files if any(k in f.get('key', '').lower() for k in ['meta', 'sample', 'cell'])
                     and f.get('key', '').endswith(('.csv', '.tsv'))), None)
    if meta_file and meta_file.get('links', {}).get('self'):
        try:
            r = requests.get(meta_file['links']['self'], headers={"Range": "bytes=0-500"}, timeout=5)
            return f"Metadata Header: {r.text.splitlines()[0][:100]}..."
        except: pass

    return "No automated stats found."

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
        stats = peek_data(files)
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
