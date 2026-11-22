"""Re-rank the fused top-N with an agent: it sees the ticket and candidate paths with their declared symbols."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from crewline.crew import adapters
from crewline.crew.models import Choice

PROMPT = (
    "Read ticket.md and candidates.json in the current directory. The ticket describes a change to a codebase. "
    "candidates.json lists code files that might need to be modified, with the types and methods each declares. "
    "Pick the files most likely MODIFIED by the fix (not tests), best first, at most 10. "
    "Do not open other files. Reply with only a JSON array of paths copied exactly from candidates.json."
)


def rerank(ticket: str, candidates: list[str], symbols: dict[str, dict], choice: Choice,
           max_chars: int = 6000) -> list[str] | None:
    """Returns the re-ranked candidates (picked first, then the rest in original order), or None on failure."""
    with tempfile.TemporaryDirectory(prefix="cl_rr_") as d:
        Path(d, "ticket.md").write_text(ticket[:max_chars], encoding="utf-8")
        cands = [{"path": p, "types": symbols.get(p, {}).get("types", [])[:8],
                  "methods": symbols.get(p, {}).get("methods", [])[:25]} for p in candidates]
        Path(d, "candidates.json").write_text(json.dumps(cands, indent=1), encoding="utf-8")
        res = adapters.run(choice, PROMPT, d, tier="rerank", purpose="locate.rerank", timeout=600)
    if not res.ok:
        return None
    m = re.search(r"\[.*\]", res.text, re.S)
    try:
        picked = [p for p in json.loads(m.group(0)) if p in candidates] if m else []
    except ValueError:
        return None
    if not picked:
        return None
    return list(dict.fromkeys(picked + candidates))
