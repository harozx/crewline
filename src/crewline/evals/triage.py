"""Triage: which module does a ticket belong to? The zero-token use of locate (route tickets before any agent).

Module = the path prefix before "/src/" (a Maven/Gradle module, e.g. `clients`, `flink-runtime`), else the first
directory. A ticket's gold modules = modules of the files its fix modified. Locate's fused ranking (no model) is
turned into a module ranking by summing reciprocal ranks. Baselines: the most-changed module in earlier history,
and Jira's Component field mapped to the module it most often co-occurs with in earlier tickets.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from crewline.evals import apache
from crewline.locate import baseline


def module(path: str) -> str:
    return path.split("/src/", 1)[0] if "/src/" in path else path.split("/", 1)[0]


def rank_modules(files: list[str], c: int = 0, k: int = 20) -> list[str]:
    """Module ranking from a file ranking. Steep weights on the top files (c=0) over the first 20 so a module with
    many mediocre hits does not outvote the module holding the top file. Tuned on the dev split (Apache,
    2026-11-24: top-1 0.675 -> 0.743), never on eval."""
    acc: dict[str, float] = defaultdict(float)
    for i, f in enumerate(files[:k]):
        acc[module(f)] += 1 / (c + i + 1)
    return [m for m, _ in sorted(acc.items(), key=lambda x: -x[1])]


def run(projects: tuple[str, ...] = ("kafka", "flink", "hbase", "hive")) -> dict:
    out = {}
    for p in projects:
        tickets = {t["key"]: t for t in apache.load(p)}
        rows = apache.rankings(p, "eval")
        w = apache.FUSIONS["tuned"]
        hits = {"locate@1": [], "locate@3": [], "majority@1": [], "component@1": []}
        n_modules = set()
        for r in rows:
            t = tickets[r["key"]]
            gold = {module(f) for f in r["gold"]}
            n_modules |= gold
            fused = baseline.fuse(*[r[c] for c in w], weights=list(w.values()), k=60)
            ranked = rank_modules(fused)
            hits["locate@1"].append(bool(ranked[:1]) and ranked[0] in gold)
            hits["locate@3"].append(bool(set(ranked[:3]) & gold))
            history = [h for h in tickets.values() if h["files"] and h["fixed_at"] < t["created"]]
            counts = Counter(module(f) for h in history for f in h["files"])
            hits["majority@1"].append(bool(counts) and counts.most_common(1)[0][0] in gold)
            comp_map: dict[str, Counter] = defaultdict(Counter)
            for h in history:
                for comp in h.get("components") or []:
                    comp_map[comp].update(module(f) for f in h["files"])
            guess = None
            for comp in t.get("components") or []:
                if comp_map.get(comp):
                    guess = comp_map[comp].most_common(1)[0][0]
                    break
            hits["component@1"].append(guess in gold if guess else False)
        out[p] = {"tickets": len(rows), "modules_seen": len(n_modules),
                  "with_component": sum(1 for r in rows if tickets[r["key"]].get("components")),
                  **{k: round(statistics.mean(v), 3) for k, v in hits.items()}}
    total = sum(v["tickets"] for v in out.values())
    out["all"] = {k: round(sum(v[k] * v["tickets"] for v in out.values()) / total, 3)
                  for k in ("locate@1", "locate@3", "majority@1", "component@1")} | {"tickets": total}
    result = {"benchmark": "triage-module", "date": time.strftime("%Y-%m-%d"), "projects": out}
    res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
    (res_dir / f"triage-module-{result['date']}.json").write_text(__import__("json").dumps(result, indent=2))
    return result
