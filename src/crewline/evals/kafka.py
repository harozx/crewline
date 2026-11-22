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
from crewline.locate import baseline
from crewline.sources import git
from crewline.sources.jira import Jira, flatten

JIRA = "https://issues.apache.org/jira"
CUTOFF = "2026-07-01"
HISTORY_SINCE = "2023-01-01"
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


def evaluate(limit: int | None = None) -> dict:
    repo, _ = paths()
    rows = load()
    evals = [r for r in rows if r["eval"] and r["files"]][:limit]
    per: dict[str, dict[int, list[float]]] = {m: {k: [] for k in KS} for m in ("path", "history", "fused")}
    tree_cache: dict[str, list[str]] = {}
    for t in evals:
        if t["parent"] not in tree_cache:
            tree_cache[t["parent"]] = [p for p in git.ls_tree(repo, t["parent"]) if baseline.is_code(p)]
        alive = tree_cache[t["parent"]]
        query = f'{t["summary"]}\n{t["description"]}'
        history = [{"text": f'{h["summary"]}\n{h["description"]}', "files": h["files"]}
                   for h in rows if h["files"] and h["fixed_at"] < t["created"] and h["key"] != t["key"]]
        r_path = baseline.rank_paths(query, alive)
        r_hist = baseline.rank_history(query, history, set(alive))
        ranked = {"path": r_path, "history": r_hist, "fused": baseline.fuse(r_path, r_hist)}
        for m, r in ranked.items():
            for k in KS:
                per[m][k].append(recall(r, t["files"], k))
    summary = {m: {f"recall@{k}": round(statistics.mean(v[k]), 3) for k in KS} for m, v in per.items()}
    result = {"benchmark": "kafka-locate", "cutoff": CUTOFF, "n": len(evals),
              "date": time.strftime("%Y-%m-%d"), "methods": summary}
    res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
    res_dir.mkdir(parents=True, exist_ok=True)
    (res_dir / f"kafka-locate-baseline-{result['date']}.json").write_text(json.dumps(result, indent=2))
    return result
