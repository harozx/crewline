"""Calibrate locate on one repo by backtesting its own history, then keep only the signals that help there.

Why: what helps depends on the codebase (history added +10 points of recall@10 on Hive, +1.4 on HBase).
How:  past tickets with known fixes, oldest first -> tune fusion weights on the older 60% (dev) -> report on the
      newer 40% (test). Symbols come from a snapshot taken at the dev/test boundary, built in a separate worktree
      under the data dir: the user's working tree is never touched.
Ticket sources:
  keys    commits whose subject carries a key like PROJ-123 (ticket text from Jira when --jira is given,
          otherwise the commit subjects: shorter, and may name the fix -> optimistic)
  github  merged PRs that close an issue; the issue title+body is the ticket (needs `gh` access to the repo)
  commits every code commit, its message as the ticket (optimistic: messages are written after the fix)
Writes <data>/index/<repo>/calibration.json, which `locate` then uses.
"""

from __future__ import annotations

import itertools
import json
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from crewline.config import data_dir
from crewline.locate import baseline, symbols
from crewline.locate.symbols import SymbolIndex
from crewline.sources import git

SIGNALS = ("path", "history", "symbols", "mentions")
GRID = (0, 0.5, 1, 2, 3)
KS = (1, 5, 10)
KEY = r"\b[A-Z][A-Z0-9]+-\d+\b"


def _files(commits: list[git.Commit]) -> list[str]:
    return sorted({p for c in commits for s, p in c.files if s == "M" and baseline.is_code(p)})


def tickets_from_keys(repo: Path, since: str, jira_url: str | None = None) -> list[dict]:
    by = git.by_key(git.log(repo, "HEAD", since=since), KEY)
    out = []
    for key, commits in by.items():
        commits = sorted(commits, key=lambda c: c.date)
        files = _files(commits)
        if files:
            out.append({"key": key, "text": " ".join(c.subject for c in commits), "files": files,
                        "parent": commits[0].parent, "fixed_at": commits[0].date})
    if jira_url and out:
        from crewline.sources.jira import Jira
        jira, texts = Jira(jira_url), {}
        keys = [t["key"] for t in out]
        for i in range(0, len(keys), 50):
            for issue in jira.search(f"key in ({','.join(keys[i:i + 50])})", fields="summary,description"):
                f = issue["fields"]
                texts[issue["key"]] = f"{f.get('summary') or ''}\n{f.get('description') or ''}"
        for t in out:
            t["text"] = texts.get(t["key"], t["text"])
    return out


def tickets_from_github(repo: Path, slug: str, since: str, limit: int = 400) -> list[dict]:
    p = subprocess.run(["gh", "pr", "list", "-R", slug, "--state", "merged", "--limit", str(limit),
                        "--search", f"merged:>={since} linked:issue",
                        "--json", "number,mergeCommit,closingIssuesReferences"],
                       capture_output=True, text=True, encoding="utf-8")
    out = []
    for pr in json.loads(p.stdout or "[]"):
        issues = pr.get("closingIssuesReferences") or []
        if not issues or not pr.get("mergeCommit"):
            continue
        sha = pr["mergeCommit"]["oid"]
        try:
            parent = git._git(repo, "rev-parse", f"{sha}^1").strip()
            date = git._git(repo, "show", "-s", "--format=%cI", sha).strip()
            files = [f for f in git._git(repo, "diff", "--name-only", "--diff-filter=M", parent, sha).split()
                     if baseline.is_code(f)]
        except subprocess.CalledProcessError:
            continue   # merge commit not in the local clone
        iss = json.loads(subprocess.run(["gh", "api", f"repos/{slug}/issues/{issues[0]['number']}"],
                                        capture_output=True, text=True, encoding="utf-8").stdout or "{}")
        if files:
            out.append({"key": f"#{issues[0]['number']}", "text": f"{iss.get('title', '')}\n{iss.get('body') or ''}",
                        "files": files, "parent": parent, "fixed_at": date})
    return out


def tickets_from_commits(repo: Path, since: str) -> list[dict]:
    out = []
    for c in git.log(repo, "HEAD", since=since):
        files = _files([c])
        if files and len(c.subject) >= 20:
            out.append({"key": c.sha[:10], "text": c.subject, "files": files, "parent": c.parent,
                        "fixed_at": c.date})
    return out


def _snapshot_index(repo: Path, sha: str, out_dir: Path) -> SymbolIndex:
    path = out_dir / f"symbols-{sha[:10]}.json"
    if not path.exists():
        wt = out_dir / "snapshot"
        if wt.exists():
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
        git._git(repo, "worktree", "add", "-q", "--detach", str(wt), sha)
        try:
            symbols.build(wt, path)
        finally:
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
    return SymbolIndex.load(path)


def _recall(ranked: list[str], gold: list[str], k: int) -> float:
    return len(set(ranked[:k]) & set(gold)) / len(gold)


def _score(rows: list[dict], weights: dict[str, float]) -> dict[str, float]:
    w = {k: v for k, v in weights.items() if v}
    per = {k: [] for k in KS}
    for r in rows:
        ranked = baseline.fuse(*[r[s] for s in w], weights=list(w.values())) if w else []
        for k in KS:
            per[k].append(_recall(ranked, r["gold"], k))
    return {f"recall@{k}": round(statistics.mean(v), 3) for k, v in per.items()}


def run(repo: Path, source: str = "keys", since: str = "2023-01-01", jira_url: str | None = None,
        slug: str | None = None, max_tickets: int = 400) -> dict:
    repo = repo.resolve()
    out_dir = data_dir() / "index" / repo.name
    out_dir.mkdir(parents=True, exist_ok=True)
    if source == "keys":
        tickets = tickets_from_keys(repo, since, jira_url)
    elif source == "github":
        tickets = tickets_from_github(repo, slug or "", since, max_tickets)
    else:
        tickets = tickets_from_commits(repo, since)
    tickets = sorted(tickets, key=lambda t: t["fixed_at"])[-max_tickets:]
    if len(tickets) < 30:
        return {"repo": str(repo), "source": source, "tickets": len(tickets),
                "verdict": "too little history to calibrate (need >= 30 tickets with known fixes)"}
    cut = int(len(tickets) * 0.6)
    boundary = tickets[cut]["parent"]
    sym = _snapshot_index(repo, boundary, out_dir)
    trees: dict[str, list[str]] = {}
    rows = []
    for i, t in enumerate(tickets):
        if t["parent"] not in trees:
            trees[t["parent"]] = [p for p in git.ls_tree(repo, t["parent"]) if baseline.is_code(p)]
        alive_list = trees[t["parent"]]
        alive = set(alive_list)
        history = [{"text": h["text"], "files": h["files"]} for h in tickets[:i] if h["fixed_at"] < t["fixed_at"]]
        rows.append({"gold": t["files"], "dev": i < cut,
                     "path": baseline.rank_paths(t["text"], alive_list),
                     "history": baseline.rank_history(t["text"], history, alive),
                     "symbols": sym.rank_bm25(t["text"], alive),
                     "mentions": sym.rank_mentions(t["text"], alive)})
    dev, test = [r for r in rows if r["dev"]], [r for r in rows if not r["dev"]]
    best, best_w = -1.0, {}
    for combo in itertools.product(GRID, repeat=len(SIGNALS)):
        if not any(combo):
            continue
        w = dict(zip(SIGNALS, combo, strict=True))
        s = _score(dev, w)
        val = s["recall@10"] + 0.5 * s["recall@5"]
        if val > best:
            best, best_w = val, w
    default = {"path": 0.5, "history": 3, "symbols": 0.5, "mentions": 3}
    result = {
        "repo": str(repo), "source": source, "date": time.strftime("%Y-%m-%d"),
        "tickets": len(tickets), "dev": len(dev), "test": len(test),
        "optimistic": source != "github" and not (source == "keys" and jira_url),
        "signals_alone_test": {s: _score(test, {s: 1})["recall@10"] for s in SIGNALS},
        "default_weights_test": _score(test, default),
        "calibrated_weights": best_w,
        "calibrated_test": _score(test, best_w),
        "disabled": [s for s, v in best_w.items() if not v],
    }
    (out_dir / "calibration.json").write_text(json.dumps(result, indent=2))
    return result


def weights_for(repo: Path) -> dict[str, float] | None:
    f = data_dir() / "index" / repo.resolve().name / "calibration.json"
    try:
        return json.loads(f.read_text()).get("calibrated_weights")
    except (OSError, ValueError):
        return None
