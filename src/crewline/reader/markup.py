"""Jira text -> markdown. Server/DC uses wiki markup; Cloud uses ADF (JSON). Images stay where they were,
as `![image: name](attachment:name)` placeholders the brief later fills with a description."""

from __future__ import annotations

import re


def wiki_to_md(text: str) -> str:
    if not text:
        return ""
    blocks: list[str] = []

    def keep(m: re.Match) -> str:
        lang = (m.group(2) or "").lstrip(":").split("|")[0]
        blocks.append(f"```{lang}\n{m.group(3).strip()}\n```")
        return f"\x00{len(blocks) - 1}\x00"

    t = re.sub(r"\{(code|noformat)(:[^}]*)?\}(.*?)\{\1\}", keep, text, flags=re.S)
    t = re.sub(r"^h([1-6])\.\s*", lambda m: "#" * int(m.group(1)) + " ", t, flags=re.M)
    t = re.sub(r"!([^!|\n]+?\.(?:png|jpe?g|gif|webp|bmp))(\|[^!]*)?!", r"![image: \1](attachment:\1)", t, flags=re.I)
    t = re.sub(r"\[([^|\]]+)\|([^\]]+)\]", r"[\1](\2)", t)
    t = re.sub(r"\[~([^\]]+)\]", r"@\1", t)
    t = re.sub(r"\{\{(.+?)\}\}", r"`\1`", t)
    t = re.sub(r"(?<![\w*])\*(\S[^*\n]*?\S|\S)\*(?![\w*])", r"**\1**", t)
    t = re.sub(r"^\s*#\s+", "1. ", t, flags=re.M)
    t = re.sub(r"\{quote\}(.*?)\{quote\}", lambda m: "\n".join("> " + x for x in m.group(1).strip().splitlines()),
               t, flags=re.S)
    return re.sub(r"\x00(\d+)\x00", lambda m: blocks[int(m.group(1))], t).strip()


def adf_to_md(node: dict | None, media: dict[str, str] | None = None) -> str:
    """Atlassian Document Format (Cloud) -> markdown. `media` maps media ids to attachment filenames."""
    if not node:
        return ""
    media = media or {}
    kind = node.get("type")
    kids = node.get("content") or []

    def inner(sep: str = "") -> str:
        return sep.join(adf_to_md(k, media) for k in kids)

    if kind == "text":
        s = node.get("text", "")
        for mark in node.get("marks") or []:
            mt = mark.get("type")
            if mt == "code":
                s = f"`{s}`"
            elif mt == "strong":
                s = f"**{s}**"
            elif mt == "em":
                s = f"*{s}*"
            elif mt == "link":
                s = f"[{s}]({mark.get('attrs', {}).get('href', '')})"
        return s
    if kind == "heading":
        return "#" * node.get("attrs", {}).get("level", 1) + " " + inner() + "\n\n"
    if kind == "paragraph":
        return inner() + "\n\n"
    if kind == "codeBlock":
        return f"```{node.get('attrs', {}).get('language', '')}\n{inner()}\n```\n\n"
    if kind in ("bulletList", "orderedList"):
        mark = "- " if kind == "bulletList" else "1. "
        return "".join(mark + adf_to_md(k, media).strip() + "\n" for k in kids) + "\n"
    if kind == "blockquote":
        return "".join("> " + line + "\n" for line in inner().strip().splitlines()) + "\n"
    if kind == "media":
        a = node.get("attrs", {})
        name = media.get(a.get("id", ""), a.get("alt") or a.get("id", "media"))
        return f"![image: {name}](attachment:{name})"
    if kind == "hardBreak":
        return "\n"
    if kind == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@")
    if kind == "inlineCard":
        return node.get("attrs", {}).get("url", "")
    return inner()
