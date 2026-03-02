# scraper/extract_repos.py
import re
from .feeds import Paper

# Patterns to catch GitHub, GitLab, Zenodo, Figshare, Bitbucket, and
# Software Heritage links — all common in methods papers
REPO_PATTERNS = [
    r"https?://github\.com/[\w\-\.]+/[\w\-\.]+",
    r"https?://gitlab\.com/[\w\-\.]+/[\w\-\.]+",
    r"https?://zenodo\.org/(?:record|doi)/[\d\.]+",
    r"https?://figshare\.com/[\w/\-]+",
    r"https?://bitbucket\.org/[\w\-\.]+/[\w\-\.]+",
    r"https?://sourceforge\.net/projects/[\w\-]+",
    r"https?://(?:www\.)?huggingface\.co/[\w\-]+(?:/[\w\-]+)?",
    r"https?://(?:www\.)?bioconductor\.org/packages/[\w\.]+",
    r"https?://pypi\.org/project/[\w\-]+",
]

COMPILED = [re.compile(p, re.IGNORECASE) for p in REPO_PATTERNS]

def find_repos(text: str) -> list[str]:
    found = set()
    for pattern in COMPILED:
        for match in pattern.finditer(text):
            url = match.group(0).rstrip(".,);")
            found.add(url)
    return sorted(found)

def extract_all_repos(papers: list[Paper]) -> None:
    """Mutates papers in-place, adding any found repository links."""
    for paper in papers:
        paper.repos = find_repos(paper.abstract + " " + paper.url)