"""PR review comments -> lessons. Filter cheaply in code, distill in batches with a light model.

Filters follow what worked elsewhere (Snowflake "Experience Cards", 2026-08): drop bots, replies, praise/nits,
very short comments; keep comments that state a reason or a rule.
"""

from __future__ import annotations

import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewline.crew import adapters
from crewline.crew.models import Choice
from crewline.memory.store import Item, Memory

DISTILLER = Choice("agy", "gemini-3.8-flash-low")
TRIVIAL = re.compile(r"^\s*(lgtm|nit\b|thanks|thank you|done|\+1|good catch|ack|fixed|sgtm|ok\b|okay)",
                     re.I)
PROMPT = """Read comments.json: code review comments from a project, each with the code hunk it refers to.
For each comment, decide if it teaches something a future contributor to THIS FILE should know
(a pitfall, a project convention, a design decision and its reason). Skip style nits, questions without an
answer, praise, and anything only about this one PR. Write the lesson so it stands alone without the PR:
one or two sentences, concrete, naming the class/method/config involved.
Reply with JSON only: {"lessons": [{"id": <comment id>, "kind": "pitfall|convention|decision", "lesson": "..."}]}"""


def keep(c: dict) -> bool:
    body = c["body"].strip()
    return (not c["bot"] and not c["reply_to"] and c["path"] and len(body) >= 60 and not TRIVIAL.match(body)
            and "```suggestion" not in body[:20])


def distill(batch: list[dict], choice: Choice = DISTILLER) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="cl_mem_") as d:
        Path(d, "comments.json").write_text(json.dumps(
            [{"id": c["id"], "path": c["path"], "comment": c["body"][:1500], "hunk": c["hunk"]} for c in batch],
            indent=1), encoding="utf-8")
        res = adapters.run(choice, PROMPT, d, tier="light", purpose="memory.distill", timeout=600)
    if not res.ok:
        return []
    m = re.search(r"\{.*\}", res.text, re.S)
    try:
        return json.loads(m.group(0)).get("lessons", []) if m else []
    except ValueError:
        return []


def ingest(mem: Memory, scope: str, comments: list[dict], batch: int = 25, workers: int = 4) -> dict:
    fresh = [c for c in comments if keep(c) and not mem.seen(f"gh-review:{c['id']}")]
    by_id = {c["id"]: c for c in fresh}
    chunks = [fresh[i:i + batch] for i in range(0, len(fresh), batch)]
    added = 0
    with ThreadPoolExecutor(workers) as ex:
        for lessons in ex.map(distill, chunks):
            for les in lessons:
                c = by_id.get(les.get("id"))
                if not c or not les.get("lesson"):
                    continue
                added += mem.add(Item(scope, c["path"], les.get("kind", "pitfall"), les["lesson"].strip(),
                                      c["url"], f"gh-review:{c['id']}", c["created"]))
    return {"comments": len(comments), "kept": len(fresh), "lessons": added}
