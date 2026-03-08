# scraper/feeds.py
import feedparser
import yaml
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class Paper:
    title: str
    authors: str
    journal: str
    url: str
    abstract: str
    published: datetime
    doi: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    # These get filled in later by the LLM and repo extractor
    summary: Optional[str] = None
    categories: list[str] = field(default_factory=list)
    repos: list[str] = field(default_factory=list)
    # E1 — filled in by cluster.py after summarisation
    cluster_id:    Optional[int] = None
    cluster_label: Optional[str] = None

def load_config(path="config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)

def fetch_papers(config: dict) -> list[Paper]:
    """
    Fetch all papers published in the last `lookback_days` from every journal
    in the config. feedparser handles both RSS and Atom formats transparently.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=config["lookback_days"])
    all_papers = []

    for journal in config["journals"]:
        print(f"  Fetching: {journal['name']}...")
        try:
            feed = feedparser.parse(journal["rss"])
            # feedparser is lenient, but we still check for failures
            if feed.bozo and not feed.entries:
                print(f"    Warning: feed parse issue for {journal['name']}")
                continue

            for entry in feed.entries:
                pub_date = parse_date(entry)
                if pub_date is None or pub_date < cutoff:
                    continue  # Skip old entries

                abstract = extract_abstract(entry)
                if not abstract:
                    continue  # Papers without abstracts are usually editorials

                paper = Paper(
                    title=entry.get("title", "No title").strip(),
                    authors=format_authors(entry),
                    journal=journal["name"],
                    url=entry.get("link", ""),
                    abstract=abstract,
                    published=pub_date,
                    doi=extract_doi(entry),
                    keywords=extract_keywords(entry),
                )
                all_papers.append(paper)

            # Be polite to journal servers — small delay between requests
            time.sleep(1)

        except Exception as e:
            print(f"    Error fetching {journal['name']}: {e}")

    print(f"\n  Found {len(all_papers)} new papers across all journals.")
    return all_papers

def parse_date(entry) -> Optional[datetime]:
    """feedparser gives us a time.struct_time; convert to timezone-aware datetime."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None

def extract_abstract(entry) -> str:
    """Abstracts can live in summary, content, or description depending on the journal."""
    for attr in ("summary", "content"):
        val = getattr(entry, attr, None)
        if val:
            # content is a list of dicts for Atom feeds
            if isinstance(val, list):
                val = val[0].get("value", "")
            # Strip basic HTML tags that sometimes appear in RSS abstracts
            import re
            val = re.sub(r"<[^>]+>", " ", val).strip()
            if len(val) > 100:  # Ignore very short summaries (likely just titles)
                return val
    return ""

def extract_doi(entry) -> Optional[str]:
    import re
    # DOIs often appear in the link or a dedicated field
    for field in (entry.get("id", ""), entry.get("link", "")):
        match = re.search(r"10\.\d{4,}/\S+", field)
        if match:
            return match.group(0).rstrip(".")
    return None

def extract_keywords(entry) -> list[str]:
    """Some feeds include <category> tags which map to keywords."""
    tags = getattr(entry, "tags", [])
    return [t.get("term", "") for t in tags if t.get("term")]

def format_authors(entry) -> str:
    authors = getattr(entry, "authors", [])
    if not authors:
        return entry.get("author", "Unknown authors")
    names = [a.get("name", "") for a in authors[:5]]  # Cap at 5 for readability
    result = ", ".join(n for n in names if n)
    if len(authors) > 5:
        result += f" et al. (+{len(authors)-5} more)"

    return result or "Unknown authors"
