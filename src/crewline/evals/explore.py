"""Exploration cost on a large repo: does a codebase map make an agent find the right files cheaper?

Read-only task on Kafka eval tickets (created after the cutoff): the agent explores a snapshot of the repo and
lists the files the fix must modify. Each ticket runs twice, without and with codemap.md. Measured: recall of
the real fix's files, input tokens, seconds. No tests run, so no Docker is needed.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewline.config import data_dir
from crewline.crew import adapters
from crewline.crew.models import Choice
from crewline.evals import apache
from crewline.memory import codemap
from crewline.sources import git

AGENT = Choice("agy", "gemini-4-neon-medium")
PROMPT = """Read brief.md: a ticket for this repository. Explore the repository (read only, do not change anything)
and find the source files that must be MODIFIED to implement it (not tests).{map}
Reply with JSON only: {{"files": ["path/relative/to/repo/root", ...]}}, most likely first, at most 10."""
MAP_NOTE = (" codemap.md maps the repository (what each directory is for and which file to open first); "
            "use it to go straight to the right place instead of exploring broadly.")


def _norm(p: str, wt: Path) -> str:
    p = p.replace("\\", "/")
    root = str(wt).replace("\\", "/").rstrip("/") + "/"
    if p.lower().startswith(root.lower()):
        p = p[len(root):]
    return p.lstrip("./")


def _ask(wt: Path, brief_text: str, with_map: bool) -> dict:
    (wt / "brief.md").write_text(brief_text, encoding="utf-8")
    res = adapters.run(AGENT, PROMPT.format(map=MAP_NOTE if with_map else ""), wt, tier="explore",
                       purpose=f"eval.explore.{'map' if with_map else 'nomap'}", timeout=900)
    m = re.search(r"\{.*\}", res.text or "", re.S)
    try:
        files = json.loads(m.group(0)).get("files", []) if (res.ok and m) else []
    except ValueError:
        files = []
    return {"ok": res.ok, "files": [_norm(f, wt) for f in files], "tokens_in": res.tokens_in,
            "seconds": round(res.seconds, 1)}


def run(n: int = 20, seed: int = 11) -> dict:
    repo, out = apache.paths("kafka")
    snap = git.rev_before(repo, apache.CUTOFF)
    tickets = apache.split_rows(apache.load("kafka"), "eval")
    random.Random(seed).shuffle(tickets)
    tickets = tickets[:n]
    cmap = codemap.build(repo, snap)
    base = data_dir() / "explore"
    wts = {}
    for cond in ("nomap", "map"):     # two read-only worktrees so the two conditions can run side by side
        wt = base / f"kafka-{cond}"
        if wt.exists():
            subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)
            shutil.rmtree(wt, ignore_errors=True)
        git._git(repo, "worktree", "add", "-q", "--detach", str(wt), snap)
        if cond == "map":
            shutil.copyfile(cmap, wt / "codemap.md")
        wts[cond] = wt
    rows = []
    for t in tickets:
        text = f"# {t['key']}: {t['summary']}\n\n{t['description']}"
        with ThreadPoolExecutor(2) as ex:
            off, on = ex.map(lambda c, txt=text: _ask(wts[c], txt, c == "map"), ("nomap", "map"))
        row = {"key": t["key"], "gold": t["files"], "nomap": off, "map": on}
        rows.append(row)
        with open(base / "rows.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    for wt in wts.values():
        subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)], capture_output=True)

    def agg(cond: str) -> dict:
        ok = [r for r in rows if r[cond]["ok"]]
        return {
            "ok": len(ok),
            "recall@5": round(statistics.mean(apache.recall(r[cond]["files"], r["gold"], 5) for r in rows), 3),
            "recall@10": round(statistics.mean(apache.recall(r[cond]["files"], r["gold"], 10) for r in rows), 3),
            "median_tokens_in": int(statistics.median([r[cond]["tokens_in"] or 0 for r in ok])) if ok else None,
            "median_seconds": round(statistics.median([r[cond]["seconds"] for r in ok])) if ok else None,
        }

    result = {"benchmark": "kafka-explore-codemap", "date": time.strftime("%Y-%m-%d"), "n": len(rows),
              "agent": AGENT.model, "codemap_chars": len(cmap.read_text(encoding="utf-8")),
              "nomap": agg("nomap"), "map": agg("map")}
    res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
    (res_dir / f"kafka-explore-codemap-{result['date']}.json").write_text(json.dumps(result, indent=2))
    return result


def versus_locate(project: str, n: int = 30, seed: int = 11, workers: int = 2) -> dict:
    """Agent exploring the repo alone vs Crewline locate (fused, and fused + re-rank) on the same tickets.
    Agent answers are cached per ticket (resumable); locate numbers come from the benchmark caches."""
    repo, out = apache.paths(project)
    snap = git.rev_before(repo, apache.CUTOFF)
    tickets = apache.split_rows(apache.load(project), "eval")
    random.Random(seed).shuffle(tickets)
    tickets = tickets[:n]
    base = data_dir() / "explore"
    base.mkdir(parents=True, exist_ok=True)
    cache = base / f"{project}-agent.jsonl"
    done = {}
    if project == "kafka" and (base / "rows.jsonl").exists():   # reuse the codemap run's no-map answers
        for line in open(base / "rows.jsonl", encoding="utf-8"):
            r = json.loads(line)
            done[r["key"]] = r["nomap"]
    if cache.exists():
        for line in open(cache, encoding="utf-8"):
            r = json.loads(line)
            done[r["key"]] = r["agent"]
    todo = [t for t in tickets if t["key"] not in done]
    if todo:
        wts = []
        for i in range(workers):
            wt = base / f"{project}-wt{i}"
            if wt.exists():
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                               capture_output=True)
                shutil.rmtree(wt, ignore_errors=True)
            git._git(repo, "worktree", "add", "-q", "--detach", str(wt), snap)
            wts.append(wt)

        def one(i_t: tuple[int, dict]) -> None:
            i, t = i_t
            ans = _ask(wts[i % workers], f"# {t['key']}: {t['summary']}\n\n{t['description']}", False)
            with open(cache, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": t["key"], "agent": ans}) + "\n")
            done[t["key"]] = ans

        try:
            for start in range(0, len(todo), workers):   # one ticket per worktree at a time
                with ThreadPoolExecutor(workers) as ex:
                    list(ex.map(one, list(enumerate(todo[start:start + workers]))))
        finally:
            for wt in wts:
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)],
                               capture_output=True)

    from crewline.locate import baseline
    ranks = {r["key"]: r for r in apache.rankings(project, "eval")}
    rr_cache = {}
    rr_file = out / "rerank-gemini-4-neon-medium-pool60.jsonl"
    if rr_file.exists():
        for line in open(rr_file, encoding="utf-8"):
            d = json.loads(line)
            rr_cache[d["key"]] = d["ranked"]
    w = apache.FUSIONS["tuned"]
    agent, fused, rerank = [], [], []
    for t in tickets:
        g = t["files"]
        x = ranks[t["key"]]
        f = baseline.fuse(*[x[c] for c in w], weights=list(w.values()), k=60)
        agent.append(apache.recall(done[t["key"]]["files"], g, 10))
        fused.append(apache.recall(f, g, 10))
        rerank.append(apache.recall(rr_cache.get(t["key"], f), g, 10))
    ok = [done[t["key"]] for t in tickets if done[t["key"]]["ok"]]
    result = {
        "benchmark": f"{project}-agent-vs-locate", "date": time.strftime("%Y-%m-%d"), "n": len(tickets),
        "agent": AGENT.model,
        "agent_explore": {"recall@10": round(statistics.mean(agent), 3), "ok": len(ok),
                          "median_tokens_in": int(statistics.median([a["tokens_in"] or 0 for a in ok])) if ok else None,
                          "median_seconds": round(statistics.median([a["seconds"] for a in ok])) if ok else None},
        "locate_fused": {"recall@10": round(statistics.mean(fused), 3), "tokens_in": 0},
        "locate_rerank": {"recall@10": round(statistics.mean(rerank), 3),
                          "rerank_cached": sum(1 for t in tickets if t["key"] in rr_cache)},
        "locate_rerank_wins": sum(1 for a, r in zip(agent, rerank, strict=True) if r > a),
        "agent_wins": sum(1 for a, r in zip(agent, rerank, strict=True) if a > r),
    }
    res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
    (res_dir / f"{project}-agent-vs-locate-{result['date']}.json").write_text(json.dumps(result, indent=2))
    return result
