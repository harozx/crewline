"""Codebase map: a short, cached markdown map of a repo so agents stop re-exploring it on every task.

Built cheaply: file list + declared symbols (no file contents) -> a light model writes one or two lines of purpose
per directory; README / build files -> how to build, test and the main conventions. Cached per commit.
Measured by what it should save: worker tokens and time at equal quality (evals.solve "+map" modes).
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from crewline.config import data_dir
from crewline.crew import adapters
from crewline.crew.models import Choice
from crewline.locate import symbols
from crewline.locate.baseline import is_code
from crewline.sources import git

WRITER = Choice("agy", "gemini-3.8-flash-low")
BUILD_FILES = ("README.md", "README.rst", "CONTRIBUTING.md", "CONTRIBUTING.rst", "pyproject.toml", "setup.cfg",
               "tox.ini", "Makefile", "package.json", "build.gradle", "pom.xml", "Cargo.toml", "go.mod")
DIRS_PROMPT = """dirs.json lists directories of a code repository, each with its files and the main types and
functions they declare. For EVERY directory write one or two plain sentences: what it is responsible for, and which
file to open first for common changes. Reply with JSON only: {"dirs": {"<dir>": "<summary>"}}"""
REPO_PROMPT = """The files here are a repository's README and build/config files. In at most 15 short lines of
markdown bullet points, state: what the project is, how to install it for development, how to run the tests (exact
commands, including how to run one test file), code style/lint tools, and any layout rule a contributor must know.
Only facts present in the files. Reply with the bullet points only."""


def _symbols_by_dir(repo: Path, sha: str) -> dict[str, list[tuple[str, list[str]]]]:
    by: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for path in git.ls_tree(repo, sha):
        if not is_code(path):
            continue
        try:
            text = git._git(repo, "show", f"{sha}:{path}")
        except Exception:  # noqa: BLE001 - unreadable blob: skip the file, keep the map
            continue
        s = symbols.extract(text)
        names = s["types"][:6] + [m for m in s["methods"] if not m.startswith("_")][:10]
        d, _, name = path.rpartition("/")
        by[d or "."].append((name, names))
    return by


def _describe_dirs(by: dict[str, list[tuple[str, list[str]]]], batch: int = 15) -> dict[str, str]:
    dirs = sorted(by)
    chunks = [dirs[i:i + batch] for i in range(0, len(dirs), batch)]

    def one(chunk: list[str]) -> dict[str, str]:
        payload = {d: [{"file": f, "declares": n[:12]} for f, n in by[d][:25]] for d in chunk}
        with tempfile.TemporaryDirectory(prefix="cl_map_") as tmp:
            Path(tmp, "dirs.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
            res = adapters.run(WRITER, DIRS_PROMPT, tmp, tier="light", purpose="memory.codemap", timeout=600)
        m = re.search(r"\{.*\}", res.text or "", re.S)
        try:
            return json.loads(m.group(0)).get("dirs", {}) if (res.ok and m) else {}
        except ValueError:
            return {}

    out: dict[str, str] = {}
    with ThreadPoolExecutor(3) as ex:
        for part in ex.map(one, chunks):
            out |= part
    return out


def _describe_repo(repo: Path, sha: str) -> str:
    with tempfile.TemporaryDirectory(prefix="cl_map_") as tmp:
        found = 0
        for name in BUILD_FILES:
            try:
                Path(tmp, name).write_text(git._git(repo, "show", f"{sha}:{name}")[:20000], encoding="utf-8")
                found += 1
            except Exception:  # noqa: BLE001 - file absent at this commit
                continue
        if not found:
            return ""
        res = adapters.run(WRITER, REPO_PROMPT, tmp, tier="light", purpose="memory.codemap", timeout=600)
    return res.text.strip() if res.ok else ""


def build(repo: Path, sha: str | None = None) -> Path:
    repo = repo.resolve()
    sha = sha or git.head(repo)
    out = data_dir() / "index" / repo.name / f"codemap-{sha[:10]}.md"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    by = _symbols_by_dir(repo, sha)
    summaries = _describe_dirs(by)
    lines = [f"# Code map of {repo.name} @ {sha[:10]}", "",
             "Use this map to find where things live before opening files.", ""]
    dev = _describe_repo(repo, sha)
    if dev:
        lines += ["## Develop and test", dev, ""]
    lines += ["## Directories", ""]
    for d in sorted(by):
        lines.append(f"### {d}/")
        if summaries.get(d):
            lines.append(summaries[d])
        files = sorted(by[d])
        for name, names in files[:15]:   # keep big-repo maps skimmable; the summary names the file to open
            lines.append(f"- `{name}`" + (f": {', '.join(names[:6])}" if names else ""))
        if len(files) > 15:
            lines.append(f"- ... {len(files) - 15} more files")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def copy_into(repo: Path, sha: str, dest: Path) -> None:
    shutil.copyfile(build(repo, sha), dest / "codemap.md")
