"""Ticket -> brief: one markdown file an agent can act on, with images described in place.

Attachments are downloaded with the user's own Jira credentials. Images are described by a light vision model
(agy reads local image files); documents are listed for now (docx/xlsx/pdf conversion comes next).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewline.crew import adapters
from crewline.crew.models import Choice
from crewline.reader.markup import adf_to_md, wiki_to_md
from crewline.sources.jira import Jira

IMAGE = re.compile(r"\.(png|jpe?g|gif|webp|bmp)$", re.I)
VISION = Choice("agy", "gemini-3.8-flash-low")
DESCRIBE = ("Describe {name} for a developer who will change the code. Transcribe every visible label, field, "
            "error message, number and annotation (arrows, red boxes). Say what the screen or diagram shows. "
            "Plain text, at most 12 lines.")


def _text(value, media: dict[str, str]) -> str:
    return adf_to_md(value, media) if isinstance(value, dict) else wiki_to_md(value or "")


def describe_image(path: Path, choice: Choice = VISION) -> str:
    res = adapters.run(choice, DESCRIBE.format(name=path.name), path.parent, tier="light",
                       purpose="reader.image", timeout=300)
    return res.text.strip() if res.ok else f"(could not read image: {path.name})"


def build(jira: Jira, key: str, workdir: Path, max_comments: int = 15, vision: bool = True) -> Path:
    issue = jira.issue(key, fields="summary,description,issuetype,status,priority,components,attachment,"
                                   "issuelinks,comment,labels")
    f = issue["fields"]
    att = f.get("attachment") or []
    media = {a.get("id", ""): a["filename"] for a in att}
    workdir.mkdir(parents=True, exist_ok=True)
    files_dir = workdir / "attachments"
    files_dir.mkdir(exist_ok=True)

    local: dict[str, Path] = {}
    for a in att:
        dst = files_dir / a["filename"]
        if not dst.exists():
            r = jira.http.get(a["content"])
            if r.status_code == 200:
                dst.write_bytes(r.content)
        if dst.exists():
            local[a["filename"]] = dst

    images = [p for name, p in local.items() if IMAGE.search(name)]
    described: dict[str, str] = {}
    if vision and images:
        with ThreadPoolExecutor(4) as ex:
            described = dict(zip([p.name for p in images], ex.map(describe_image, images), strict=True))

    referenced: set[str] = set()

    def fill(md: str) -> str:
        def sub(m: re.Match) -> str:
            name = m.group(1)
            referenced.add(name)
            desc = described.get(name)
            return f"\n> **[Image {name}]**\n" + "".join(f"> {line}\n" for line in desc.splitlines()) if desc \
                else m.group(0)
        return re.sub(r"!\[image: ([^\]]+)\]\(attachment:[^)]+\)", sub, md)

    parts = [f"# {key}: {f.get('summary', '')}", "",
             f"- Type: {(f.get('issuetype') or {}).get('name')} · Status: {(f.get('status') or {}).get('name')}"
             f" · Priority: {(f.get('priority') or {}).get('name')}",
             f"- Components: {', '.join(c['name'] for c in f.get('components') or []) or '-'}"
             f" · Labels: {', '.join(f.get('labels') or []) or '-'}"]
    links = [(lk.get("type", {}).get("outward") if "outwardIssue" in lk else lk.get("type", {}).get("inward"),
              (lk.get("outwardIssue") or lk.get("inwardIssue") or {}).get("key")) for lk in f.get("issuelinks") or []]
    if links:
        parts.append("- Links: " + "; ".join(f"{rel} {k}" for rel, k in links))
    parts += ["", "## Description", fill(_text(f.get("description"), media)) or "(empty)"]

    extra = [n for n in described if n not in referenced]
    if extra:
        parts += ["", "## Images not referenced in the text"]
        for n in extra:
            parts += [f"### {n}", described[n]]
    docs = [n for n in local if not IMAGE.search(n)]
    if docs:
        parts += ["", "## Other attachments", *[f"- {n} (`attachments/{n}`)" for n in docs]]

    comments = (f.get("comment") or {}).get("comments", [])[-max_comments:]
    if comments:
        parts += ["", f"## Latest comments ({len(comments)} shown, newest last)"]
        for c in comments:
            who = (c.get("author") or {}).get("displayName", "?")
            parts += [f"**{who}** · {c.get('created', '')[:10]}", fill(_text(c.get("body"), media)), ""]

    out = workdir / "brief.md"
    out.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    return out
