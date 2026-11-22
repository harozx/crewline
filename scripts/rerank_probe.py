"""Measure agent re-ranking of the fused top-30.

uv run python scripts/rerank_probe.py <project> <split> <n> <cli> <model>
"""

import json
import os
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor

from crewline.crew.models import Choice
from crewline.evals import apache
from crewline.locate import baseline, rerank

project, split, n, cli, model = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5]
W = apache.FUSIONS["tuned"]
POOL = int(os.environ.get("POOL", "30"))
rows = apache.rankings(project, split)[:n]
tickets = {t["key"]: t for t in apache.load(project)}
idx = json.load(open(next(apache.paths(project)[1].glob("symbols-*.json"))))
choice = Choice(cli, model, "low" if cli == "codex" else None)


def one(r):
    fused = baseline.fuse(*[r[c] for c in W], weights=list(W.values()), k=POOL)
    t = tickets[r["key"]]
    return fused, rerank.rerank(f'# {t["summary"]}\n\n{t["description"]}', fused, idx, choice), r["gold"]


with ThreadPoolExecutor(6) as ex:
    out = list(ex.map(one, rows))
fail = sum(1 for _, rr, _ in out if rr is None)
for k in (1, 5, 10):
    a = statistics.mean(apache.recall(f, g, k) for f, _, g in out)
    b = statistics.mean(apache.recall(rr or f, g, k) for f, rr, g in out)
    print(f"{project} pool={POOL} {model} {split} n={len(out)} fail={fail} r@{k}: fused {a:.3f} -> rerank {b:.3f}")
