"""P0 baselines for "which files does this ticket touch":

- path:    BM25 of the ticket text against file paths (tokens of dirs, class names).
- history: BM25 of the ticket against earlier tickets; their fixed files inherit the similarity.
- fused:   reciprocal-rank fusion of both.
"""

from __future__ import annotations

import re
from collections import defaultdict

from rank_bm25 import BM25Okapi

from crewline.locate.text import tokens

CODE_EXT = (".java", ".scala", ".py", ".kt", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs")
TEST_NAME = re.compile(r"(^test|_tests?\.\w+$|\.test\.\w+$|\.spec\.\w+$|Tests?\.\w+$)")


def is_code(path: str) -> bool:
    return path.endswith(CODE_EXT) and not path.endswith(".d.ts") and not is_test(path)


def is_test(path: str) -> bool:
    p = "/" + path.lower()
    name = path.rsplit("/", 1)[-1]
    return (any(d in p for d in ("/test/", "/tests/", "/__tests__/", "/spec/", "/testing/fixtures/"))
            or bool(TEST_NAME.search(name)) or name.lower().startswith("test"))


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


def fuse(*rankings: list[str], weights: list[float] | None = None, k: int = 50, c: int = 60) -> list[str]:
    """Weighted reciprocal-rank fusion."""
    acc: dict[str, float] = defaultdict(float)
    for r, w in zip(rankings, weights or [1.0] * len(rankings), strict=True):
        for i, f in enumerate(r):
            acc[f] += w / (c + i + 1)
    return [f for f, _ in sorted(acc.items(), key=lambda x: -x[1])[:k]]
