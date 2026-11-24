"""`crewline setup`: get a repo ready in one command and say how well Crewline works on it.

1. Pick the ticket source: Jira keys in commits, else GitHub PRs that close issues (from the `origin` remote),
   else commit messages (optimistic, flagged).
2. Calibrate on the repo's own history (or fall back to default weights and say why).
3. Pre-build the indexes `locate` needs (symbols; embeddings only if calibration switched them on).
4. Print the numbers and ready-to-paste MCP config for Claude Code, Codex and Cursor.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from crewline.config import data_dir
from crewline.locate import calibrate, engine
from crewline.sources import git

KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _github_slug(repo: Path) -> str | None:
    p = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", p.stdout.strip())
    return m.group(1) if m else None


def pick_source(repo: Path, since: str, jira_url: str | None) -> tuple[str, str | None, str]:
    subjects = [c.subject for c in git.log(repo, "HEAD", since=since)]
    keyed = sum(1 for s in subjects if KEY.search(s))
    if keyed >= 30:
        return "keys", None, f"{keyed} commits carry ticket keys" + (" (ticket text from Jira)" if jira_url else "")
    slug = _github_slug(repo)
    if slug:
        return "github", slug, f"GitHub repo {slug}: merged PRs that close issues"
    return "commits", None, "no ticket keys and no GitHub remote: commit messages stand in for tickets (optimistic)"


def run(repo: Path, since: str = "2024-01-01", jira_url: str | None = None, max_tickets: int = 400,
        jql: str | None = None, open_n: int = 60) -> dict:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"{repo} is not a git checkout")
    t0 = time.time()
    source, slug, why = pick_source(repo, since, jira_url)
    cal = calibrate.run(repo, source, since, jira_url, slug, max_tickets)
    calibrated = "calibrated_weights" in cal
    sym, raw = engine._index(repo)   # symbol index at HEAD, cached per commit
    if calibrated and cal["calibrated_weights"].get("semantic"):
        from crewline.locate import semantic
        emb = data_dir() / "index" / repo.name / f"semantic-{git.head(repo)[:10]}.npz"
        if not emb.exists():
            semantic.build(repo, raw, emb)
    summary = {
        "repo": str(repo), "source": source, "source_reason": why, "tickets": cal.get("tickets", 0),
        "calibrated": calibrated, "verdict": cal.get("verdict"),
        "files_top10": cal.get("calibrated_test", {}).get("recall@10"),
        "file_top1": cal.get("calibrated_test", {}).get("recall@1"),
        "module_top1": cal.get("triage_test", {}).get("top1"),
        "module_top3": cal.get("triage_test", {}).get("top3"),
        "signals_on": [k for k, v in cal.get("calibrated_weights", {}).items() if v],
        "optimistic": cal.get("optimistic", False),
    }
    # Change map from the same history and the same ticket source (open work placed on it).
    from crewline.map import build as cmap
    from crewline.map import render
    if jira_url and jql:
        opened = cmap.open_tickets_jira(jira_url, jql, open_n)
    elif source == "github" and slug:
        opened = cmap.open_tickets_github(slug, open_n)
    else:
        opened = []
    page = data_dir() / "maps" / f"{repo.name}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    data = cmap.build(repo, cmap.load_history(repo, jira_url), opened, repo.name)
    render.render(data, page)
    summary.update(map=str(page), open_tickets=len(opened), modules=len(data["modules"]),
                   seconds=round(time.time() - t0))
    (data_dir() / "index" / repo.name / "setup.json").write_text(json.dumps(summary, indent=2))
    return summary


def mcp_config(crewline_dir: Path) -> dict[str, str]:
    d = str(crewline_dir).replace("\\", "/")
    server = {"command": "uv", "args": ["--directory", d, "run", "crewline", "mcp"]}
    return {
        "Claude Code": f"claude mcp add crewline -- uv --directory {d} run crewline mcp",
        "Codex": f"codex mcp add crewline -- uv --directory {d} run crewline mcp",
        "Cursor (.cursor/mcp.json)": json.dumps({"mcpServers": {"crewline": server}}, indent=2),
    }


def report(s: dict) -> str:
    pct = lambda v: f"{v * 100:.0f}%" if isinstance(v, (int, float)) else "n/a"  # noqa: E731
    lines = [f"Crewline setup: {s['repo']}  ({s['seconds']} s)",
             f"  ticket source : {s['source']} - {s['source_reason']}"]
    if s["calibrated"]:
        lines += [f"  history used  : {s['tickets']} tickets (tuned on the older 60%, scored on the newer 40%)",
                  f"  right file    : in the top 10 for {pct(s['files_top10'])}, "
                  f"ranked first for {pct(s['file_top1'])}",
                  f"  right module  : first for {pct(s['module_top1'])}, top 3 for {pct(s['module_top3'])}",
                  f"  signals on    : {', '.join(s['signals_on'])}"]
        if s["optimistic"]:
            lines.append("  note          : scored on commit messages written after the fix -> optimistic")
    else:
        lines.append(f"  calibration   : skipped ({s['verdict']}); default weights will be used")
    if s.get("map"):
        lines.append(f"  change map    : {s['map']}  ({s['modules']} modules, {s['open_tickets']} open tickets placed)")
    lines.append("")
    lines.append("Add the MCP server to your agent:")
    for name, cfg in mcp_config(Path(__file__).resolve().parents[2]).items():
        lines.append(f"  {name}:")
        lines += [f"    {line}" for line in cfg.splitlines()]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(run(Path(sys.argv[1]))))
