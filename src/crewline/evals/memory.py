"""Does team memory help an agent catch what a human reviewer caught?

Eval items: review comments on Kafka made on/after EVAL_FROM, on files that already have lessons from earlier
reviews. The agent reviews the same diff hunk twice, without and with recalled lessons (only lessons created
before the comment). A light judge decides whether the agent raised the reviewer's point.
"""

from __future__ import annotations

import json
import random
import re
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewline.config import data_dir
from crewline.crew import adapters
from crewline.crew.models import Choice
from crewline.memory.extract import keep
from crewline.memory.store import Memory

EVAL_FROM = "2026-10-01"
REVIEWER = Choice("agy", "gemini-4-neon-medium")
JUDGE = Choice("agy", "gemini-3.8-flash-low")

REVIEW = """You are reviewing a pull request to Apache Kafka. change.md has the file path and the diff hunk under
review (the last lines of the hunk are the ones being reviewed).{mem}
List the concrete problems a senior Kafka reviewer would raise about the last lines of the hunk, most important
first, at most 5. Reply with JSON only: {{"issues": ["..."]}}"""
MEM_NOTE = "\nlessons.md has lessons the team learned from earlier reviews of this code; use them if relevant."
JUDGE_PROMPT = """cases.json has items, each with a human reviewer's comment and a list of issues an AI raised on
the same code. For each item decide if ANY AI issue makes substantially the same point as the human comment.
Reply with JSON only: {"verdicts": [{"id": <id>, "hit": true|false}]}"""


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def items(n: int, seed: int = 7) -> tuple[list[dict], Memory]:
    d = data_dir() / "datasets" / "kafka"
    mem = Memory(data_dir() / "memory" / "kafka.sqlite")
    cs = [json.loads(line) for line in open(d / "review_comments.jsonl", encoding="utf-8")]
    pool = [c for c in cs if c["created"] >= EVAL_FROM and keep(c)
            and mem.recall([c["path"]], lambda s: True, before=c["created"], limit=1)]
    random.Random(seed).shuffle(pool)
    return pool[:n], mem


def review(c: dict, lessons: list[str]) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="cl_rv_") as d:
        Path(d, "change.md").write_text(f"File: {c['path']}\n\n```diff\n{c['hunk']}\n```\n", encoding="utf-8")
        if lessons:
            Path(d, "lessons.md").write_text("\n".join(f"- {x}" for x in lessons), encoding="utf-8")
        res = adapters.run(REVIEWER, REVIEW.format(mem=MEM_NOTE if lessons else ""), d, tier="review",
                           purpose="eval.memory.review", timeout=600)
    return _json(res.text).get("issues", []) if res.ok else []


def judge(cases: list[dict]) -> dict[int, bool]:
    with tempfile.TemporaryDirectory(prefix="cl_jd_") as d:
        Path(d, "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
        res = adapters.run(JUDGE, JUDGE_PROMPT, d, tier="light", purpose="eval.memory.judge", timeout=600)
    return {v["id"]: bool(v.get("hit")) for v in _json(res.text).get("verdicts", []) if "id" in v}


def run(n: int = 60, workers: int = 6) -> dict:
    evs, mem = items(n)

    def one(c: dict) -> dict:
        lessons = [i.lesson for i in mem.recall([c["path"]], lambda s: True, before=c["created"], limit=8)]
        return {"c": c, "lessons": len(lessons), "off": review(c, []), "on": review(c, lessons)}

    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, evs))
    hits: dict[str, list[bool]] = {"off": [], "on": []}
    for cond in ("off", "on"):
        cases = [{"id": i, "human": r["c"]["body"][:1200], "ai": r[cond]} for i, r in enumerate(rows)]
        verdicts: dict[int, bool] = {}
        for i in range(0, len(cases), 20):
            verdicts |= judge(cases[i:i + 20])
        hits[cond] = [verdicts.get(i, False) for i in range(len(rows))]
    result = {"benchmark": "kafka-review-memory", "eval_from": EVAL_FROM, "n": len(rows),
              "date": time.strftime("%Y-%m-%d"), "reviewer": REVIEWER.model,
              "hit_rate_no_memory": round(statistics.mean(hits["off"]), 3) if rows else 0,
              "hit_rate_memory": round(statistics.mean(hits["on"]), 3) if rows else 0,
              "mean_lessons": round(statistics.mean(r["lessons"] for r in rows), 1) if rows else 0,
              "only_with_memory": sum(1 for a, b in zip(hits["off"], hits["on"], strict=True) if b and not a),
              "only_without_memory": sum(1 for a, b in zip(hits["off"], hits["on"], strict=True) if a and not b)}
    res_dir = Path(__file__).resolve().parents[3] / "evals" / "results"
    (res_dir / f"kafka-review-memory-{result['date']}.json").write_text(json.dumps(result, indent=2))
    return result
