"""Read-only GitHub access through the user's own `gh` login (so ACL = what that user can see)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator


def _api(path: str, paginate: bool = False) -> list | dict:
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        cmd.insert(2, "--paginate")
        cmd += ["--jq", ".[]"]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(f"gh api {path}: {p.stderr[-300:]}")
    if paginate:
        return [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    return json.loads(p.stdout or "null")


def can_read(repo: str) -> bool:
    """True when the current gh user can read the repo. Memory from a repo is only served to such users."""
    try:
        return bool(_api(f"repos/{repo}"))
    except RuntimeError:
        return False


def review_comments(repo: str, since: str) -> Iterator[dict]:
    """Inline review comments across all PRs of a repo, oldest first."""
    for c in _api(f"repos/{repo}/pulls/comments?since={since}T00:00:00Z&sort=created&direction=asc&per_page=100",
                  paginate=True):
        yield {
            "id": c["id"], "pr": int(c["pull_request_url"].rsplit("/", 1)[-1]), "path": c.get("path"),
            "line": c.get("line") or c.get("original_line"), "body": c.get("body") or "",
            "hunk": (c.get("diff_hunk") or "")[-1200:], "author": (c.get("user") or {}).get("login"),
            "bot": (c.get("user") or {}).get("type") == "Bot", "created": c.get("created_at"),
            "url": c.get("html_url"), "reply_to": c.get("in_reply_to_id"),
        }
