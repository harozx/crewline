"""Git history as data: which commits mention which ticket keys, and which files they modified."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SEP = "\x1f"


@dataclass
class Commit:
    sha: str
    parent: str | None
    date: str
    subject: str
    files: list[tuple[str, str]]  # (status, path)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True,
                          encoding="utf-8", errors="replace").stdout


def log(repo: Path, ref: str = "HEAD", since: str | None = None) -> list[Commit]:
    args = ["log", ref, "--no-merges", "--no-renames", "--name-status", f"--format=@@{SEP}%H{SEP}%P{SEP}%cI{SEP}%s"]
    if since:
        args.append(f"--since={since}")
    commits: list[Commit] = []
    for line in _git(repo, *args).splitlines():
        if line.startswith("@@" + SEP):
            _, sha, parents, date, subject = line.split(SEP, 4)
            commits.append(Commit(sha, parents.split()[0] if parents else None, date, subject, []))
        elif line.strip() and commits:
            parts = line.split("\t")
            commits[-1].files.append((parts[0][0], parts[-1]))
    return commits


def by_key(commits: list[Commit], pattern: str) -> dict[str, list[Commit]]:
    rx = re.compile(pattern)
    out: dict[str, list[Commit]] = {}
    for c in commits:
        for key in set(rx.findall(c.subject)):
            out.setdefault(key, []).append(c)
    return out


def ls_tree(repo: Path, sha: str) -> list[str]:
    return _git(repo, "ls-tree", "-r", "--name-only", sha).splitlines()
