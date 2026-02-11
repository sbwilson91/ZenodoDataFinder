import requests
import datetime
import smtplib
import re
import os
import anndata
import fsspec
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuration from Environment Variables (Secrets)
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
    if not HF_TOKEN: return "No AI Token."
    API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    clean_text = re.sub('<[^<]+?>', '', text)[:1024]
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": clean_text}, timeout=10)
        return response.json()[0]['summary_text']
    except:
        return "AI Summary unavailable."

def peek_data(files):
    """Try to get stats via H5AD lazy-load or CSV metadata sidecars."""
    h5ad = next((f for f in files if f['key'].endswith('.h5ad')), None)
    if h5ad:
        try:
            with fsspec.open(h5ad['links']['self'], mode='rb') as f:
                ad = anndata.read_h5ad(f, backed='r')
                return f"Peeked H5AD: {ad.n_obs} cells, {ad.n_vars} genes"
        except: pass

    # Fallback: Look for CSV/TSV metadata
    meta_file = next((f for f in files if any(k in f['key'].lower() for k in ['meta', 'sample', 'cell']) 
                     and f['key'].endswith(('.csv', '.tsv'))), None)
    if meta_file:
        try:
            r = requests.get(meta_file['links']['self'], headers={"Range": "bytes=0-500"}, timeout=5)
            return f"Metadata Header: {r.text.splitlines()[0][:100]}..."
        except: pass
    
    return "No scRNA stats found (likely raw data or RDS)."

def run():
    date_range = get_date_query(LOOKBACK_PERIOD)
    query = f'q=single cell RNA AND publication_date:{date_range} AND type:dataset'
    res = requests.get(f"https://zenodo.org/api/records?{query}&sort=mostrecent&size=10")
    hits = res.json().get('hits', {}).get('hits', [])

    if not hits: return print("No new data.")

    html_content = f"<h2>scRNA-seq Zenodo Report ({LOOKBACK_PERIOD})</h2>"
    for hit in hits:
        meta = hit['metadata']
        files = hit.get('files', [])
        stats = peek_data(files)
        summary = get_ai_summary(meta.get('description', ""))
        
        html_content += f"""
        <div style='border-bottom:1px solid #eee; padding:10px;'>
            <a href='{hit['links']['html']}'><h3>{meta['title']}</h3></a>
            <p><b>Summary:</b> {summary}</p>
            <p><b>Stats:</b> {stats}</p>
            <p><b>Size:</b> {sum(f['size'] for f in files)/1e6:.1f} MB</p>
        </div>"""

    msg = MIMEMultipart(); msg['Subject'] = f"scRNA-seq Zenodo Update"; msg['To'] = EMAIL_RECEIVER; msg['From'] = EMAIL_SENDER
    msg.attach(MIMEText(html_content, 'html'))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(EMAIL_SENDER, EMAIL_PASSWORD)
        s.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())

if __name__ == "__main__": run()