"""Locate on a real repo: ticket text -> ranked files with evidence.

History comes from git alone (commits whose subject carries a ticket key, e.g. PROJ-123); the commit subject
stands in for the ticket text when Jira is not available. Settings are the benchmark winners: tuned fusion,
then an agent re-ranks the top 60 (ADR/HANDOFF 2026-11-22).
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from crewline.config import data_dir
from crewline.crew.models import Choice
from crewline.locate import baseline, rerank, symbols
from crewline.locate.symbols import SymbolIndex
from crewline.sources import git

WEIGHTS = {"path": 0.5, "history": 3, "symbols": 0.5, "mentions": 3}
POOL = 60
RERANKERS = [Choice("agy", "gemini-4-neon-medium"), Choice("agy", "gemini-3.8-flash-low")]
KEY = r"\b[A-Z][A-Z0-9]+-\d+\b"


@dataclass
class Hit:
    path: str
    rank: int
    found_by: list[str] = field(default_factory=list)
    similar_tickets: list[str] = field(default_factory=list)


def _index(repo: Path) -> tuple[SymbolIndex, dict]:
    sha = git.head(repo)
    d = data_dir() / "index" / repo.resolve().name
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"symbols-{sha[:10]}.json"
    if not path.exists():
        symbols.build(repo, path)
    raw = json.loads(path.read_text())
    return SymbolIndex(raw), raw


def _history(repo: Path, since: str) -> list[dict]:
    by = git.by_key(git.log(repo, "HEAD", since=since), KEY)
    out = []
    for key, commits in by.items():
        files = sorted({p for c in commits for s, p in c.files if s == "M" and baseline.is_code(p)})
        if files:
            out.append({"key": key, "text": " ".join(c.subject for c in commits), "files": files})
    return out


def locate(repo: Path, ticket: str, *, top: int = 10, use_agent: bool = True,
           since: str = "2023-01-01") -> list[Hit]:
    sym, raw = _index(repo)
    alive_list = [p for p in git.ls_tree(repo, "HEAD") if baseline.is_code(p)]
    alive = set(alive_list)
    history = _history(repo, since)
    ranked = {
        "path": baseline.rank_paths(ticket, alive_list),
        "history": baseline.rank_history(ticket, history, alive),
        "symbols": sym.rank_bm25(ticket, alive),
        "mentions": sym.rank_mentions(ticket, alive),
    }
    fused = baseline.fuse(*ranked.values(), weights=list(WEIGHTS.values()), k=POOL)
    final = fused
    if use_agent:
        for choice in RERANKERS:
            rr = rerank.rerank(ticket, fused, raw, choice)
            if rr:
                final = rr
                break
    similar = _similar(ticket, history)
    hits = []
    for i, p in enumerate(final[:top]):
        hits.append(Hit(p, i + 1, [c for c, r in ranked.items() if p in r[:20]],
                        [h["key"] for h in similar if p in h["files"]][:3]))
    return hits


def _similar(ticket: str, history: list[dict], n: int = 20) -> list[dict]:
    if not history:
        return []
    from rank_bm25 import BM25Okapi

    from crewline.locate.text import tokens
    bm = BM25Okapi([tokens(h["text"]) for h in history])
    scores = bm.get_scores(tokens(ticket))
    return [history[i] for i in sorted(range(len(history)), key=lambda i: -scores[i])[:n] if scores[i] > 0]


def to_markdown(hits: list[Hit]) -> str:
    lines = ["| # | File | Found by | Similar past tickets |", "|---|---|---|---|"]
    for h in hits:
        lines.append(f"| {h.rank} | `{h.path}` | {', '.join(h.found_by) or 'agent'} | "
                     f"{', '.join(h.similar_tickets) or '-'} |")
    return "\n".join(lines)


def to_json(hits: list[Hit]) -> str:
    return json.dumps([asdict(h) for h in hits], indent=2)


def ticket_text(arg: str) -> str:
    """A path to brief.md / any text file, or the ticket text itself."""
    p = Path(arg)
    if len(arg) < 260 and p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"\s+", " ", arg)
