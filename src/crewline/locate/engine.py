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


_HISTORY_MEMO: dict[tuple, list[dict]] = {}


def _history(repo: Path, since: str) -> list[dict]:
    """Past tickets with the files their fix changed. Prefer what `calibrate`/`setup` fetched (Jira text or
    GitHub issues), so locate uses the same history it was calibrated on; else ticket keys in commit subjects.
    Memoised per source version: a map build locates 60 tickets and used to reload it 60 times (69 s)."""
    cached = sorted((data_dir() / "index" / repo.resolve().name).glob("tickets-*.json"),
                    key=lambda p: p.stat().st_mtime)
    if cached:
        memo: tuple = (str(repo.resolve()), since, str(cached[-1]), cached[-1].stat().st_mtime)
    else:
        memo = (str(repo.resolve()), since, git.head(repo))
    if memo not in _HISTORY_MEMO:
        _HISTORY_MEMO[memo] = _load_history(repo, since, cached)
    return _HISTORY_MEMO[memo]


def _load_history(repo: Path, since: str, cached: list[Path]) -> list[dict]:
    if cached:
        tickets = json.loads(cached[-1].read_text(encoding="utf-8"))
        out = [{"key": t["key"], "text": t["text"], "files": [f for f in t["files"] if baseline.is_code(f)]}
               for t in tickets]
        return [t for t in out if t["files"]]
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
    # a ticket is never its own precedent (it is in the cached history once its fix has merged)
    history = [h for h in _history(repo, since) if h["text"].strip() != ticket.strip()]
    ranked = {
        "path": baseline.rank_paths(ticket, alive_list),
        "history": baseline.rank_history(ticket, history, alive),
        "symbols": sym.rank_bm25(ticket, alive),
        "mentions": sym.rank_mentions(ticket, alive),
    }
    from crewline.locate.calibrate import weights_for
    w = {k: v for k, v in (weights_for(repo) or WEIGHTS).items() if v}   # per-repo calibration when present
    if "semantic" in w:   # only built when calibration found it useful for this repo
        from crewline.locate import semantic
        emb = data_dir() / "index" / repo.resolve().name / f"semantic-{git.head(repo)[:10]}.npz"
        if not emb.exists():
            semantic.build(repo, raw, emb)
        ranked["semantic"] = semantic.SemanticIndex(emb).rank(ticket, alive)
    fused = baseline.fuse(*[ranked[k] for k in w], weights=list(w.values()), k=POOL)
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


def _codeowners(repo: Path) -> list[tuple[str, str]]:
    """(pattern, owners) from CODEOWNERS, last match wins as in GitHub. Simple prefix/glob-free matching."""
    for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        f = repo / p
        if f.exists():
            rules = []
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split("#", 1)[0].split()
                if len(parts) >= 2:
                    rules.append((parts[0].strip("/").rstrip("*").rstrip("/"), " ".join(parts[1:])))
            return rules
    return []


def triage(repo: Path, ticket: str, top_modules: int = 3) -> str:
    """Zero-token routing: which module(s) the ticket belongs to, the file to open first in each, and owners.
    Benchmark (710 Apache tickets): right module first 69% of the time, within the top 3 92%."""
    from crewline.evals.triage import module, rank_modules

    hits = locate(repo, ticket, top=60, use_agent=False)
    files = [h.path for h in hits]
    mods = rank_modules(files)[:top_modules]
    rules = _codeowners(repo)
    lines = ["| # | Module | Open first | Owners |", "|---|---|---|---|"]
    for i, m in enumerate(mods, 1):
        first = next((f for f in files if module(f) == m), "")
        owners = "-"
        for pat, who in rules:
            if pat and (first.startswith(pat) or m.startswith(pat)):
                owners = who
        lines.append(f"| {i} | `{m}` | `{first}` | {owners} |")
    return "\n".join(lines)


def ticket_text(arg: str) -> str:
    """A path to brief.md / any text file, or the ticket text itself."""
    p = Path(arg)
    if len(arg) < 260 and p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return re.sub(r"\s+", " ", arg)
