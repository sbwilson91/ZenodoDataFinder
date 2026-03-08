"""
scraper/md_to_html_email.py
Called from GitHub Actions as: python scraper/md_to_html_email.py <input.md>
Writes: /tmp/digest_email.html  and  /tmp/digest_plain.txt
"""
import sys, re
from datetime import datetime
from pathlib import Path


def inline(t):
    t = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    return t


def parse(md):
    out, in_list = [], False

    def cl():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    for line in md.splitlines():
        s = line.strip()
        if s.startswith('# ') and not s.startswith('##'):
            cl(); out.append(f'<h1>{inline(s[2:])}</h1>')
        elif s.startswith('## ') and not s.startswith('###'):
            cl(); out.append(f'<h2>{inline(s[3:])}</h2>')
        elif s.startswith('### '):
            cl(); out.append(f'<h3>{inline(s[4:])}</h3>')
        elif s == '---':
            cl(); out.append('<hr>')
        elif s.startswith('> '):
            cl(); out.append(f'<blockquote>{inline(s[2:])}</blockquote>')
        elif s.startswith('- '):
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{inline(s[2:])}</li>')
        elif s == '':
            cl()
        else:
            cl()
            css = 'meta' if re.match(r'^\*\*[^*]+\*\*', s) else ''
            if s:
                out.append(f'<p class="{css}">{inline(s)}</p>')

    cl()
    return '\n'.join(out)


def build_html(md):
    date_str = datetime.now().strftime('%A, %-d %B %Y')
    body = parse(md)
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<style>'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{background:#f4f1ec;font-family:Georgia,serif;font-size:16px;line-height:1.7;color:#1a1a1a;padding:32px 16px 64px}'
        '.wrapper{max-width:700px;margin:0 auto}'
        '.masthead{border-top:4px solid #1a1a1a;border-bottom:1px solid #1a1a1a;padding:28px 0 20px;margin-bottom:40px}'
        '.label{font-family:"Courier New",monospace;font-size:10px;letter-spacing:.25em;text-transform:uppercase;color:#666;margin-bottom:8px}'
        '.title{font-family:"Courier New",monospace;font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:#444}'
        '.date{font-family:"Courier New",monospace;font-size:11px;color:#888;margin-top:6px}'
        'h1{font-size:28px;font-weight:normal;letter-spacing:-.02em;line-height:1.2;margin:48px 0 16px;padding-bottom:12px;border-bottom:2px solid #1a1a1a}'
        'h2{font-size:11px;font-family:"Courier New",monospace;font-weight:normal;letter-spacing:.2em;text-transform:uppercase;color:#fff;background:#1a1a1a;display:inline-block;padding:4px 12px;margin:40px 0 20px}'
        'h3{font-size:19px;font-weight:normal;line-height:1.35;color:#1a1a1a;margin:28px 0 10px}'
        'p{margin-bottom:10px;color:#2a2a2a}'
        'p.meta{font-family:"Courier New",monospace;font-size:12px;color:#555;margin:6px 0}'
        'blockquote{border-left:3px solid #c8b89a;margin:14px 0;padding:10px 16px;background:#faf8f5;font-style:italic;color:#3a3a3a;font-size:15px}'
        'ul{padding-left:0;list-style:none;margin:8px 0}'
        'ul li{font-family:"Courier New",monospace;font-size:12px;color:#444;padding:3px 0 3px 16px;position:relative}'
        'ul li::before{content:"\\2192";position:absolute;left:0;color:#c8b89a}'
        'a{color:#1a1a1a;text-decoration-color:#c8b89a}'
        'code{font-family:"Courier New",monospace;font-size:12px;background:#f0ede8;padding:1px 5px;border-radius:2px}'
        'hr{border:none;border-top:1px solid #ddd;margin:32px 0}'
        'strong{font-weight:600}'
        '.footer{margin-top:56px;padding-top:20px;border-top:1px solid #ccc;font-family:"Courier New",monospace;font-size:11px;color:#888}'
        '</style></head><body><div class="wrapper">'
        '<div class="masthead">'
        '<div class="label">Automated Research Intelligence</div>'
        f'<div class="title">Weekly Journal Digest</div>'
        f'<div class="date">{date_str}</div>'
        '</div>'
        + body +
        '<div class="footer">Generated automatically &middot; Nature &middot; Science &middot; Cell &middot; '
        'Cell Stem Cell &middot; Stem Cell Reports &middot; Nature Biotechnology &middot; '
        'Nature Methods &middot; Bioinformatics</div>'
        '</div></body></html>'
    )


if __name__ == '__main__':
    md = Path(sys.argv[1]).read_text(encoding='utf-8')
    Path('/tmp/digest_email.html').write_text(build_html(md), encoding='utf-8')
    Path('/tmp/digest_plain.txt').write_text(md[:50000], encoding='utf-8')
    print("HTML email written → /tmp/digest_email.html")
