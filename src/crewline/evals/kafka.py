"""Apache Kafka localisation benchmark: public Jira + git history, tickets linked to fixes by `KAFKA-nnnn`.

Eval tickets are Fixed and created on/after CUTOFF (contamination guard). Gold = existing non-test code files
the fix commits modified. History = every linked ticket whose fix landed before the eval ticket was created.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from crewline.config import data_dir
from crewline.locate import baseline, symbols
from crewline.locate.symbols import SymbolIndex
from crewline.sources import git
from crewline.sources.jira import Jira, flatten

JIRA = "https://issues.apache.org/jira"
CUTOFF = "2026-07-01"
HISTORY_SINCE = "2023-01-01"
DEV_FROM = "2026-01-01"
KS = (1, 5, 10, 20)


def paths() -> tuple[Path, Path]:
    d = data_dir() / "datasets" / "kafka"
    d.mkdir(parents=True, exist_ok=True)
    return data_dir() / "repos" / "kafka", d


def build() -> dict:
    repo, out = paths()
    commits = git.log(repo, "HEAD", since=HISTORY_SINCE)
    keymap = git.by_key(commits, r"KAFKA-\d+")
    jira = Jira(JIRA)
    jql = f'project = KAFKA AND resolution = Fixed AND resolved >= "{HISTORY_SINCE}" ORDER BY created ASC'
    rows = []
    for issue in jira.search(jql, fields="summary,description,created,resolutiondate,issuetype,components"):
        t = flatten(issue)
        fixes = sorted(keymap.get(t["key"], []), key=lambda c: c.date)
        if not fixes:
            continue
        modified = sorted({p for c in fixes for s, p in c.files if s == "M" and baseline.is_code(p)})
        t.update(fix_shas=[c.sha for c in fixes], parent=fixes[0].parent, fixed_at=fixes[0].date,
                 files=modified, eval=t["created"] >= CUTOFF)
        rows.append(t)
    with open(out / "tickets.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_eval = sum(1 for r in rows if r["eval"] and r["files"])
    return {"linked_tickets": len(rows), "eval_tickets": n_eval, "commits_scanned": len(commits)}


def load() -> list[dict]:
    _, out = paths()
    return [json.loads(line) for line in open(out / "tickets.jsonl", encoding="utf-8")]


def recall(ranked: list[str], gold: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(gold)) / len(gold)


def symbol_index() -> SymbolIndex:
    """Symbols from the repo checked out at the last commit before CUTOFF (no leakage from later fixes)."""
    repo, out = paths()
    snap = git.rev_before(repo, CUTOFF)
    path = out / f"symbols-{snap[:10]}.json"
    if not path.exists():
        if git.head(repo) != snap:
            raise RuntimeError(f"check out {snap} in {repo} first (git checkout {snap})")
        symbols.build(repo, path)
    return SymbolIndex.load(path)


def rankings(split: str = "eval", limit: int | None = None) -> list[dict]:
    """Per-ticket rankings from every component, cached so fusion can be tuned without recomputing."""
    repo, out = paths()
    cache = out / f"rankings-{split}.jsonl"
    if cache.exists() and limit is None:
        return [json.loads(line) for line in open(cache, encoding="utf-8")]
    rows = load()
    if split == "eval":
        chosen = [r for r in rows if r["eval"] and r["files"]]
    else:  # dev: tuning set, the six months before the cutoff
        chosen = [r for r in rows if DEV_FROM <= r["created"] < CUTOFF and r["files"]]
    chosen = chosen[:limit]
    sym = symbol_index()
    tree_cache: dict[str, list[str]] = {}
    result = []
    for t in chosen:
        if t["parent"] not in tree_cache:
            tree_cache[t["parent"]] = [p for p in git.ls_tree(repo, t["parent"]) if baseline.is_code(p)]
        alive_list = tree_cache[t["parent"]]
        alive = set(alive_list)
        query = f'{t["summary"]}\n{t["description"]}'
        history = [{"text": f'{h["summary"]}\n{h["description"]}', "files": h["files"]}
                   for h in rows if h["files"] and h["fixed_at"] < t["created"] and h["key"] != t["key"]]
        result.append({
            "key": t["key"], "gold": t["files"],
            "path": baseline.rank_paths(query, alive_list),
            "history": baseline.rank_history(query, history, alive),
            "symbols": sym.rank_bm25(query, alive),
            "mentions": sym.rank_mentions(query, alive),
        })
    if limit is None:
        with open(cache, "w", encoding="utf-8") as fh:
            for r in result:
                fh.write(json.dumps(r) + "\n")
    return result


FUSIONS = {
    "baseline": {"path": 1, "history": 1},
    "all": {"path": 1, "history": 1, "symbols": 1, "mentions": 1},
    # grid-searched on the dev split (2026-01..06), never on eval
    "tuned": {"path": 0.5, "history": 3, "symbols": 0.5, "mentions": 3},
}


def score(rows: list[dict], fusions: dict[str, dict[str, float]]) -> dict:
    methods = {m: {m: 1.0} for m in ("path", "history", "symbols", "mentions")} | fusions
    out = {}
    for name, weights in methods.items():
        per = {k: [] for k in KS}
        for r in rows:
            ranked = baseline.fuse(*[r[c] for c in weights], weights=list(weights.values()))
            for k in KS:
                per[k].append(recall(ranked, r["gold"], k))
        out[name] = {f"recall@{k}": round(statistics.mean(v), 3) for k, v in per.items()}
    return out


def evaluate(limit: int | None = None, split: str = "eval", tag: str = "p1") -> dict:
    rows = rankings(split, limit)
    result = {"benchmark": "kafka-locate", "split": split, "cutoff": CUTOFF, "n": len(rows),
              "date": time.strftime("%Y-%m-%d"), "methods": score(rows, FUSIONS)}
    if limit is None:
        res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
        res_dir.mkdir(parents=True, exist_ok=True)
        (res_dir / f"kafka-locate-{split}-{tag}-{result['date']}.json").write_text(json.dumps(result, indent=2))
    return result
