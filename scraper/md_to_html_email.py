"""
scraper/md_to_html_email.py
Converts the weekly digest .md into a styled HTML email.
Run as: python -m scraper.md_to_html_email <input.md> <output.html>
"""
import sys, re
from datetime import datetime
from pathlib import Path

def inline(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text

def parse_markdown(md):
    lines = md.splitlines()
    out, in_list = [], False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    for line in lines:
        s = line.strip()
        if s.startswith('# ') and not s.startswith('##'):
            close_list(); out.append(f'<h1>{inline(s[2:])}</h1>')
        elif s.startswith('## ') and not s.startswith('###'):
            close_list(); out.append(f'<h2>{inline(s[3:])}</h2>')
        elif s.startswith('### '):
            close_list(); out.append(f'<h3>{inline(s[4:])}</h3>')
        elif s == '---':
            close_list(); out.append('<hr>')
        elif s.startswith('> '):
            close_list(); out.append(f'<blockquote>{inline(s[2:])}</blockquote>')
        elif s.startswith('- '):
            if not in_list: out.append('<ul>'); in_list = True
            out.append(f'<li>{inline(s[2:])}</li>')
        elif s == '':
            close_list()
        else:
            close_list()
            css = 'meta' if re.match(r'^\*\*[^*]+\*\*', s) else ''
            if s: out.append(f'<p class="{css}">{inline(s)}</p>')

    close_list()
    return '\n'.join(out)

def build_html(body, date_str):
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#f4f1ec;font-family:Georgia,'Times New Roman',serif;font-size:16px;line-height:1.7;color:#1a1a1a;padding:32px 16px 64px}}
.wrapper{{max-width:700px;margin:0 auto}}
.masthead{{border-top:4px solid #1a1a1a;border-bottom:1px solid #1a1a1a;padding:28px 0 20px;margin-bottom:40px}}
.masthead .label{{font-family:'Courier New',monospace;font-size:10px;letter-spacing:.25em;text-transform:uppercase;color:#666;margin-bottom:8px}}
.masthead .title{{font-family:'Courier New',monospace;font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#444}}
.masthead .date{{font-family:'Courier New',monospace;font-size:11px;color:#888;margin-top:6px}}
h1{{font-size:28px;font-weight:normal;letter-spacing:-.02em;line-height:1.2;margin:48px 0 16px;padding-bottom:12px;border-bottom:2px solid #1a1a1a}}
h2{{font-size:11px;font-family:'Courier New',monospace;font-weight:normal;letter-spacing:.2em;text-transform:uppercase;color:#fff;background:#1a1a1a;display:inline-block;padding:4px 12px;margin:40px 0 20px}}
h3{{font-size:19px;font-weight:normal;line-height:1.35;color:#1a1a1a;margin:28px 0 10px;letter-spacing:-.01em}}
p{{margin-bottom:10px;color:#2a2a2a}}
p.meta{{font-family:'Courier New',monospace;font-size:12px;color:#555;margin:6px 0;line-height:1.5}}
blockquote{{border-left:3px solid #c8b89a;margin:14px 0;padding:10px 16px;background:#faf8f5;font-style:italic;color:#3a3a3a;font-size:15px;line-height:1.65}}
ul{{padding-left:0;list-style:none;margin:8px 0}}
ul li{{font-family:'Courier New',monospace;font-size:12px;color:#444;padding:3px 0 3px 16px;position:relative}}
ul li::before{{content:'→';position:absolute;left:0;color:#c8b89a}}
a{{color:#1a1a1a;text-decoration:underline;text-decoration-color:#c8b89a;text-underline-offset:2px}}
code{{font-family:'Courier New',monospace;font-size:12px;background:#f0ede8;padding:1px 5px;border-radius:2px;color:#444}}
hr{{border:none;border-top:1px solid #ddd;margin:32px 0}}
strong{{font-weight:600}}
.footer{{margin-top:56px;padding-top:20px;border-top:1px solid #ccc;font-family:'Courier New',monospace;font-size:11px;color:#888;letter-spacing:.05em}}
</style></head><body>
<div class="wrapper">
<div class="masthead">
  <div class="label">Automated Research Intelligence</div>
  <div class="title">Weekly Journal Digest</div>
  <div class="date">{date_str}</div>
</div>
{body}
<div class="footer">Generated automatically · Nature · Science · Cell · Cell Stem Cell · Stem Cell Reports · Nature Biotechnology · Nature Methods · Bioinformatics</div>
</div></body></html>"""

def convert(md_path, html_path):
    md   = Path(md_path).read_text(encoding='utf-8')
    body = parse_markdown(md)
    date = datetime.now().strftime('%A, %-d %B %Y')
    Path(html_path).write_text(build_html(body, date), encoding='utf-8')
    print(f"  HTML email written → {html_path}")

if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
