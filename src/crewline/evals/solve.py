"""Solve benchmark (SWE-bench style) on real GitHub issues: can solo / crew turn the issue into a fix?

Instance = a merged PR after CUTOFF that closes an issue and changes both src/ and tests/.
- The agent sees only the issue (title + body). The PR's test changes are hidden.
- Gate during work = the repo's existing test suite (no hidden tests), run in Docker with --network none.
- Score = hidden tests applied on the result: every FAIL_TO_PASS test passes and no PASS_TO_PASS test breaks.
Validation keeps only instances where the hidden tests fail at base and pass with the real fix.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from crewline.config import data_dir
from crewline.crew import team
from crewline.crew.models import Choice

CUTOFF = "2026-07-01"
IMAGE = "crewline-py312:1"
DOCKERFILE = "FROM python:3.12-slim\nRUN pip install --no-cache-dir pytest==8.3.5\n"
REPOS = {
    "click": {"slug": "pallets/click", "src": "src/", "tests": "tests/", "skip": ("tests/typing/",),
              "pythonpath": "src", "suite": "tests --ignore=tests/typing"},
}


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 900, stdin: str | None = None) -> tuple[int, str]:
    # bytes, not text mode: on Windows text-mode stdin turns "\n" into "\r\n" and patches stop applying
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, timeout=timeout,
                       input=stdin.encode("utf-8") if stdin is not None else None)
    return p.returncode, (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("utf-8", "replace")


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    code, out = _run(["git", "-C", str(repo), *args], stdin=stdin)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args[:3])}: {out[-400:]}")
    return out


def ensure_image() -> None:
    if _run(["docker", "image", "inspect", IMAGE])[0] == 0:
        return
    d = data_dir() / "docker"
    d.mkdir(exist_ok=True)
    (d / "Dockerfile").write_text(DOCKERFILE)
    code, out = _run(["docker", "build", "-t", IMAGE, str(d)], timeout=1800)
    if code != 0:
        raise RuntimeError(out[-800:])


def docker_pytest(wt: Path, pythonpath: str, targets: str, junit: bool = True) -> tuple[int, str]:
    """Run pytest inside a throwaway container with no network; the worktree is the only mount."""
    cmd = f"PYTHONPATH={pythonpath} python -m pytest -q -p no:cacheprovider {targets}"
    if junit:
        cmd += " --junitxml=.cl_junit.xml"
    return _run(["docker", "run", "--rm", "--network", "none", "--memory", "2g", "-v", f"{wt}:/repo", "-w", "/repo",
                 IMAGE, "sh", "-c", cmd], timeout=900)


def gate_command(name: str) -> str:
    cfg = REPOS[name]
    return (f'docker run --rm --network none --memory 2g -v "{{wt}}:/repo" -w /repo {IMAGE} '
            f'sh -c "PYTHONPATH={cfg["pythonpath"]} python -m pytest -q -x -p no:cacheprovider {cfg["suite"]}"')


def _results(wt: Path) -> dict[str, bool]:
    f = wt / ".cl_junit.xml"
    if not f.exists():
        return {}
    out = {}
    for tc in ET.parse(f).iter("testcase"):
        bad = any(ch.tag in ("failure", "error") for ch in tc)
        skipped = any(ch.tag == "skipped" for ch in tc)
        if not skipped:
            out[f'{tc.get("classname")}::{tc.get("name")}'] = not bad
    f.unlink()
    return out


def paths(name: str) -> tuple[Path, Path]:
    d = data_dir() / "datasets" / "solve" / name
    d.mkdir(parents=True, exist_ok=True)
    return data_dir() / "repos" / name, d


def _clone(name: str) -> Path:
    repo, _ = paths(name)
    if not repo.exists():
        _run(["git", "clone", "-q", "-c", "core.autocrlf=false", f"https://github.com/{REPOS[name]['slug']}.git",
              str(repo)], timeout=1800)
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "fetch", "-q", "origin")
    return repo


def _worktree(repo: Path, at: str, where: Path) -> Path:
    if where.exists():
        _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(where)])
        shutil.rmtree(where, ignore_errors=True)
    _git(repo, "worktree", "add", "-q", "--detach", str(where), at)
    return where


def build(name: str, limit: int = 80) -> dict:
    """Collect PRs, then validate each in Docker: hidden tests must fail at base and pass with the gold fix."""
    cfg = REPOS[name]
    repo = _clone(name)
    ensure_image()
    _, out = paths(name)
    code, raw = _run(["gh", "pr", "list", "-R", cfg["slug"], "--state", "merged", "--limit", str(limit),
                      "--search", f"merged:>={CUTOFF} linked:issue",
                      "--json", "number,title,mergeCommit,closingIssuesReferences,files"])
    prs = json.loads(raw) if code == 0 else []
    kept, seen = [], 0
    for pr in prs:
        files = [f["path"] for f in pr["files"]]
        src = [f for f in files if f.startswith(cfg["src"]) and f.endswith(".py")]
        tests = [f for f in files if f.startswith(cfg["tests"]) and f.endswith(".py")
                 and not f.startswith(cfg["skip"])]
        issues = pr.get("closingIssuesReferences") or []
        if not (src and tests and issues and pr.get("mergeCommit")):
            continue
        seen += 1
        merge = pr["mergeCommit"]["oid"]
        base = _git(repo, "rev-parse", f"{merge}^1").strip()
        test_patch = _git(repo, "diff", base, merge, "--", *tests)
        gold_patch = _git(repo, "diff", base, merge, "--", *src)
        wt = _worktree(repo, base, out / "wt-validate")
        _git(wt, "apply", "-", stdin=test_patch)
        docker_pytest(wt, cfg["pythonpath"], " ".join(tests))
        before = _results(wt)
        _git(wt, "apply", "-", stdin=gold_patch)
        docker_pytest(wt, cfg["pythonpath"], " ".join(tests))
        after = _results(wt)
        f2p = sorted(t for t, ok in after.items() if ok and before.get(t) is False or (ok and t not in before))
        p2p = sorted(t for t, ok in after.items() if ok and before.get(t) is True)
        if not f2p:
            continue
        iss = json.loads(_run(["gh", "api", f"repos/{cfg['slug']}/issues/{issues[0]['number']}"])[1])
        kept.append({"id": f"{name}-{pr['number']}", "pr": pr["number"], "issue": issues[0]["number"],
                     "title": iss.get("title", ""), "body": (iss.get("body") or "")[:6000], "base": base,
                     "merge": merge, "tests": tests, "src": src, "test_patch": test_patch,
                     "gold_patch": gold_patch, "FAIL_TO_PASS": f2p, "PASS_TO_PASS": p2p})
    _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(out / "wt-validate")])
    with open(out / "instances.jsonl", "w", encoding="utf-8") as fh:
        for k in kept:
            fh.write(json.dumps(k) + "\n")
    return {"repo": name, "candidates": seen, "valid": len(kept)}


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in open(paths(name)[1] / "instances.jsonl", encoding="utf-8")]


def score(name: str, inst: dict, result_ref: str) -> dict:
    """Apply hidden tests on top of the result (test files reset to base first) and check F2P / P2P."""
    repo, out = paths(name)
    wt = _worktree(repo, result_ref, out / f"wt-score-{inst['id']}")
    _git(wt, "checkout", "-q", inst["base"], "--", *[t for t in inst["tests"]
                                                     if _run(["git", "-C", str(wt), "cat-file", "-e",
                                                              f"{inst['base']}:{t}"])[0] == 0])
    applied = _run(["git", "-C", str(wt), "apply", "-"], stdin=inst["test_patch"])[0] == 0
    res: dict[str, bool] = {}
    if applied:
        docker_pytest(wt, REPOS[name]["pythonpath"], " ".join(inst["tests"]))
        res = _results(wt)
    _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(wt)])
    f2p = [res.get(t, False) for t in inst["FAIL_TO_PASS"]]
    p2p = [res.get(t, False) for t in inst["PASS_TO_PASS"]]
    return {"resolved": applied and all(f2p) and all(p2p), "f2p": f"{sum(f2p)}/{len(f2p)}",
            "p2p": f"{sum(p2p)}/{len(p2p)}", "tests_applied": applied}


def brief(inst: dict) -> str:
    body = re.sub(r"<!--.*?-->", "", inst["body"], flags=re.S).strip()
    return f"# Issue #{inst['issue']}: {inst['title']}\n\n{body}\n"


def run(name: str, mode: str, limit: int | None = None) -> dict:
    """mode: 'crew' or 'solo:<cli>:<model>'. Each instance runs in its own worktree at the instance base."""
    repo, out = paths(name)
    insts = load(name)[:limit]
    res_dir = out / "runs" / f"{mode.replace(':', '_')}-{time.strftime('%Y%m%d-%H%M')}"
    res_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for inst in insts:
        base_wt = _worktree(repo, inst["base"], out / f"wt-base-{inst['id']}")
        _git(base_wt, "checkout", "-q", "-B", f"solve/{inst['id']}")
        bf = res_dir / f"{inst['id']}.md"
        bf.write_text(brief(inst), encoding="utf-8")
        t0 = time.time()
        if mode == "crew":
            crew = team.Crew(base_wt, bf, gate_command(name))
            report = crew.run()
            crew.cleanup()
        else:
            _, cli, model = mode.split(":", 2)
            report = team.solo(base_wt, bf, gate_command(name), Choice(cli, model))  # type: ignore[arg-type]
        sc = score(name, inst, report.branch) if report.diff_files else {"resolved": False, "f2p": "-", "p2p": "-"}
        row = {"id": inst["id"], "mode": mode, "seconds": round(time.time() - t0), **sc,
               "files": report.diff_files, "gold_src": inst["src"],
               "steps": [asdict(s) for s in report.steps]}
        rows.append(row)
        (res_dir / "rows.jsonl").open("a", encoding="utf-8").write(json.dumps(row) + "\n")
        _run(["git", "-C", str(repo), "worktree", "remove", "--force", str(base_wt)])
    resolved = sum(r["resolved"] for r in rows)
    return {"repo": name, "mode": mode, "n": len(rows), "resolved": resolved,
            "rate": round(resolved / len(rows), 3) if rows else 0,
            "mean_seconds": round(sum(r["seconds"] for r in rows) / len(rows)) if rows else 0}
