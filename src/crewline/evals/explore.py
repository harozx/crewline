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
