"""P0 baselines for "which files does this ticket touch":

- path:    BM25 of the ticket text against file paths (tokens of dirs, class names).
- history: BM25 of the ticket against earlier tickets; their fixed files inherit the similarity.
- fused:   reciprocal-rank fusion of both.
"""

from __future__ import annotations

from collections import defaultdict

from rank_bm25 import BM25Okapi

from crewline.locate.text import tokens


def is_code(path: str) -> bool:
    return path.endswith((".java", ".scala", ".py", ".kt", ".go", ".ts", ".js")) and not is_test(path)


def is_test(path: str) -> bool:
    p = path.lower()
    return "/test/" in p or "/tests/" in p or p.split("/")[-1].startswith("test") or "test." in p.split("/")[-1]


def rank_paths(query: str, paths: list[str], k: int = 50) -> list[str]:
    docs = [tokens(p) for p in paths]
    bm = BM25Okapi(docs)
    scores = bm.get_scores(tokens(query))
    order = sorted(range(len(paths)), key=lambda i: -scores[i])
    return [paths[i] for i in order[:k] if scores[i] > 0]


def rank_history(query: str, history: list[dict], alive: set[str], k: int = 50, top_tickets: int = 30) -> list[str]:
    """history: [{"text": ..., "files": [...]}] from tickets resolved before this one."""
    if not history:
        return []
    bm = BM25Okapi([tokens(h["text"]) for h in history])
    scores = bm.get_scores(tokens(query))
    best = sorted(range(len(history)), key=lambda i: -scores[i])[:top_tickets]
    acc: dict[str, float] = defaultdict(float)
    for i in best:
        if scores[i] <= 0:
            continue
        files = [f for f in history[i]["files"] if f in alive]
        for f in files:
            acc[f] += scores[i] / len(files) ** 0.5
    return [f for f, _ in sorted(acc.items(), key=lambda x: -x[1])[:k]]


def fuse(*rankings: list[str], k: int = 50, c: int = 60) -> list[str]:
    acc: dict[str, float] = defaultdict(float)
    for r in rankings:
        for i, f in enumerate(r):
            acc[f] += 1 / (c + i + 1)
    return [f for f, _ in sorted(acc.items(), key=lambda x: -x[1])[:k]]
