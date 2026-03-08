"""Citation intelligence bot using OpenAlex API."""
import os
import datetime
import requests

from utils.email_logic import send_email
from utils.ai_logic import get_ai_summary

ORCID = "0000-0002-8994-0781"
LOOKBACK_PERIOD = os.environ.get("LOOKBACK_PERIOD", "week")
OPENALEX_BASE = "https://api.openalex.org"
OPENALEX_EMAIL = os.environ.get("EMAIL_SENDER", "")


def get_lookback_date(period):
    """Return ISO date string for the lookback window start."""
    days = {"week": 7, "month": 30, "6months": 180}.get(period, 7)
    return (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")


def reconstruct_abstract(inverted_index):
    """Reconstruct plain text from an OpenAlex abstract_inverted_index.

    The inverted index maps each word to a list of integer positions.
    Example: {"Directed": [0], "differentiation": [1], "of": [2, 13]}
    """
    if not inverted_index:
        return ""
    words = []
    for word, positions in inverted_index.items():
        for pos in positions:
            words.append((pos, word))
    words.sort(key=lambda x: x[0])
    return " ".join(w for _, w in words)


def get_author_work_ids():
    """Fetch all OpenAlex work IDs for the target ORCID.

    Returns:
        dict mapping OpenAlex work ID (e.g. "W3109860230") to display_name.
    """
    params = {
        "filter": f"author.orcid:{ORCID}",
        "select": "id,display_name",
        "per_page": 200,
        "mailto": OPENALEX_EMAIL,
    }
    try:
        res = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=20)
        res.raise_for_status()
        results = res.json().get("results", [])
    except Exception as e:
        print(f"OpenAlex author works query failed: {e}")
        return {}

    work_map = {}
    for work in results:
        full_id = work.get("id", "")
        short_id = full_id.split("/")[-1] if "/" in full_id else full_id
        work_map[short_id] = work.get("display_name", "Unknown")
    return work_map


def get_recent_citations(work_ids, since_date):
    """Fetch works that cite any of the given work IDs, published since since_date.

    Uses pipe-separated OR filter for efficient single-request batching.
    """
    if not work_ids:
        return []

    cites_filter = "|".join(work_ids)
    params = {
        "filter": f"cites:{cites_filter},from_publication_date:{since_date}",
        "select": "id,display_name,doi,publication_date,abstract_inverted_index,"
                  "concepts,topics,keywords,authorships",
        "per_page": 50,
        "sort": "publication_date:desc",
        "mailto": OPENALEX_EMAIL,
    }
    try:
        res = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
        res.raise_for_status()
        data = res.json()
        total = data.get("meta", {}).get("count", 0)
        print(f"Found {total} new citations since {since_date}")
        return data.get("results", [])
    except Exception as e:
        print(f"OpenAlex citations query failed: {e}")
        return []


def tag_work(work, abstract_text):
    """Assign domain tags (Microscopy / Transcriptomics) based on metadata.

    Checks concepts, topics, keywords, and the abstract text.
    """
    searchable_parts = [abstract_text.lower()]
    for concept in work.get("concepts", []):
        searchable_parts.append(concept.get("display_name", "").lower())
    for topic in work.get("topics", []):
        searchable_parts.append(topic.get("display_name", "").lower())
        for level in ("subfield", "field", "domain"):
            sub = topic.get(level, {})
            if sub:
                searchable_parts.append(sub.get("display_name", "").lower())
    for kw in work.get("keywords", []):
        searchable_parts.append(kw.get("display_name", "").lower())

    combined = " ".join(searchable_parts)

    tags = []
    if "microscopy" in combined or "microscope" in combined or "imaging" in combined:
        tags.append("Microscopy")
    if "transcriptom" in combined or "rna-seq" in combined or "single cell" in combined or "scrna" in combined:
        tags.append("Transcriptomics")

    return tags


def format_authors(authorships, max_authors=3):
    """Format a short author string from OpenAlex authorships."""
    names = []
    for auth in authorships[:max_authors]:
        name = auth.get("author", {}).get("display_name", "Unknown")
        names.append(name)
    author_str = ", ".join(names)
    if len(authorships) > max_authors:
        author_str += " et al."
    return author_str


def run():
    """Find recent citations of the author's works and send an intelligence report."""
    since_date = get_lookback_date(LOOKBACK_PERIOD)

    # Step 1: Get all works by the target author
    author_works = get_author_work_ids()
    if not author_works:
        print("No works found for the target ORCID.")
        return

    print(f"Tracking {len(author_works)} works by ORCID {ORCID}")

    # Step 2: Find recent citing works (single batched API call)
    work_ids = list(author_works.keys())
    citations = get_recent_citations(work_ids, since_date)

    if not citations:
        print("No new citations found.")
        return

    # Step 3: Build HTML report
    html_content = (
        f"<h2>Citation Intelligence Report</h2>"
        f"<p>New citations of your work since {since_date} "
        f"({len(citations)} found)</p>"
        f"<hr>"
    )

    for work in citations:
        title = work.get("display_name", "Untitled")
        doi = work.get("doi", "")
        doi_link = doi if doi else "#"
        pub_date = work.get("publication_date", "Unknown date")
        authors = format_authors(work.get("authorships", []))

        # Reconstruct abstract and summarize
        abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
        if abstract:
            summary = get_ai_summary(abstract)
        else:
            summary = "No abstract available."

        # Domain tagging
        tags = tag_work(work, abstract)
        tag_html = ""
        if tags:
            tag_badges = " ".join(
                f"<span style='background:#{'3498db' if t == 'Microscopy' else '27ae60'};"
                f"color:white;padding:2px 8px;border-radius:3px;font-size:12px;'>{t}</span>"
                for t in tags
            )
            tag_html = f"<p>{tag_badges}</p>"

        html_content += f"""
        <div style='border-bottom:1px solid #eee; padding:10px; margin-bottom:10px;'>
            <a href='{doi_link}'><h3>{title}</h3></a>
            <p style='color:#666;'>{authors} | {pub_date}</p>
            {tag_html}
            <p><b>AI Summary:</b> {summary}</p>
        </div>"""

    subject = f"Citation Intelligence Report: {datetime.date.today()}"
    send_email(subject, html_content)


if __name__ == "__main__":
    run()
