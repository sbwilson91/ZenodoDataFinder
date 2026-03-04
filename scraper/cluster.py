# scraper/cluster.py
import re
from collections import Counter
from typing import Optional
from .feeds import Paper

# Words to ignore when auto-labelling clusters
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "to", "for", "with",
    "by", "from", "is", "are", "was", "were", "be", "been", "on",
    "at", "this", "that", "these", "those", "we", "our", "its",
    "using", "based", "via", "during", "after", "between", "into",
    "new", "study", "paper", "research", "analysis", "approach",
    "show", "shows", "reveal", "reveals", "found", "provide", "provides",
    "high", "low", "large", "small", "single", "multiple", "human",
    "cell", "cells", "gene", "genes", "protein", "proteins",
}


def _extract_keywords(text: str, top_n: int = 3) -> list[str]:
    """Pull the most frequent meaningful words from a block of text."""
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    counts = Counter(w for w in words if w not in _STOPWORDS)
    return [w for w, _ in counts.most_common(top_n)]


def _label_cluster(papers: list[Paper]) -> str:
    """Generate a human-readable label from the papers in a cluster."""
    # Prefer LLM-assigned categories if available
    all_cats = [c for p in papers for c in (p.categories or [])]
    if all_cats:
        top = Counter(all_cats).most_common(2)
        return " & ".join(t[0].title() for t in top)

    # Fall back to keyword extraction from titles
    combined = " ".join(p.title for p in papers)
    keywords = _extract_keywords(combined, top_n=2)
    return " & ".join(k.title() for k in keywords) if keywords else "General"


def cluster_papers(papers: list[Paper],
                   n_clusters: Optional[int] = None,
                   min_cluster_size: int = 2) -> list[Paper]:
    """
    E1 — Assign cluster_id and cluster_label to each paper using
    sentence embeddings + agglomerative clustering.

    Falls back gracefully to category-based grouping if
    sentence-transformers or scikit-learn are not installed.
    """
    if not papers:
        return papers

    # ── Try embedding-based clustering ────────────────────────────────────
    try:
        from sentence_transformers import SentenceTransformer
        from sklearn.cluster import AgglomerativeClustering
        import numpy as np

        print("  Loading embedding model (all-MiniLM-L6-v2)...")
        model = SentenceTransformer("all-MiniLM-L6-v2")

        texts = [f"{p.title}. {p.abstract[:300]}" for p in papers]
        embeddings = model.encode(texts, show_progress_bar=False,
                                  normalize_embeddings=True)

        # Auto-select number of clusters: roughly 1 per 8 papers, min 2, max 10
        k = n_clusters or max(2, min(10, len(papers) // 8))

        clustering = AgglomerativeClustering(
            n_clusters=k,
            metric="cosine",
            linkage="average",
        )
        labels = clustering.fit_predict(embeddings)

        # Assign cluster ids
        for paper, label in zip(papers, labels):
            paper.cluster_id = int(label)

        # Label each cluster
        from collections import defaultdict
        clusters: dict[int, list[Paper]] = defaultdict(list)
        for paper in papers:
            clusters[paper.cluster_id].append(paper)

        cluster_labels: dict[int, str] = {}
        for cid, members in clusters.items():
            cluster_labels[cid] = _label_cluster(members)

        for paper in papers:
            paper.cluster_label = cluster_labels[paper.cluster_id]

        print(f"  Clustered {len(papers)} papers into {k} groups: "
              f"{', '.join(sorted(set(cluster_labels.values())))}")

    # ── Fallback: group by first LLM category ─────────────────────────────
    except ImportError:
        print("  sentence-transformers/sklearn not found — "
              "falling back to category-based grouping.")
        _fallback_cluster(papers)

    except Exception as e:
        print(f"  Clustering failed ({e}) — falling back to category grouping.")
        _fallback_cluster(papers)

    return papers


def _fallback_cluster(papers: list[Paper]) -> None:
    """
    Group papers by their first LLM-assigned category.
    Used when sentence-transformers is unavailable.
    """
    from collections import defaultdict
    groups: dict[str, list[Paper]] = defaultdict(list)
    for paper in papers:
        label = paper.categories[0].title() if paper.categories else "General"
        groups[label].append(paper)

    for cid, (label, members) in enumerate(sorted(groups.items())):
        for paper in members:
            paper.cluster_id    = cid
            paper.cluster_label = label
