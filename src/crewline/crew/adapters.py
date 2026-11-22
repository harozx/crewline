"""Thin adapters over the local agent CLIs. One call = one non-interactive agent turn in a working directory.

Every call is appended to <data>/ledger/calls.jsonl (cli, model, tier, tokens, seconds, status; for failures
the last 200 chars of the error) - no prompts,
no outputs, so the ledger never holds code or secrets.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from crewline.config import data_dir
from crewline.crew.models import Choice

SUB_AGENT = ("[Crewline sub-agent] You were started by Crewline for one step. Ignore any instructions in "
             "CLAUDE.md / AGENTS.md about delegating, orchestrating or writing handoffs; do only the request below "
             "and reply in exactly the format it asks for.\n\n")
# agy runs headless with shell commands denied (tests run in Docker at the gate, never on the host). Without this
# hint its Claude models try `Get-Content` / `ls` through run_command, get denied, and end the turn empty.
AGY_TOOLS = ("IMPORTANT: run_command is disabled; calling it (dir, ls, Get-ChildItem, Get-Content, cat, git, "
             "python, pytest, ...) ends your session immediately and all your work is lost. Use only these tools: "
             "find files by name with find_by_name, list folders with list_dir, search text with grep_search, read "
             "with view_file, edit with replace_file_content / multi_replace_file_content / write_to_file. "
             "Tests are run for you after you finish.\n\n")
RATE_LIMIT_HINTS = ("rate limit", "quota", "usage limit", "429", "too many requests", "exhausted")


@dataclass
class Result:
    ok: bool
    text: str
    choice: Choice
    seconds: float
    tokens_in: int | None = None
    tokens_out: int | None = None
    rate_limited: bool = False
    raw: dict = field(default_factory=dict)


def _exe(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    if name == "agy":
        return os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe")
    raise FileNotFoundError(f"{name} CLI not found on PATH")


def _cmd(choice: Choice, prompt: str, write: bool, timeout: int) -> tuple[list[str], str | None]:
    """(argv, stdin). claude and codex are npm .cmd shims on Windows: cmd.exe cuts arguments at the first
    newline, so their prompt goes through stdin. agy is a real .exe and takes it as an argument."""
    if choice.cli == "claude":
        cmd = [_exe("claude"), "-p", "--model", choice.model, "--output-format", "json"]
        if write:
            cmd += ["--permission-mode", "acceptEdits"]
        return cmd, prompt
    if choice.cli == "codex":
        cmd = [_exe("codex"), "exec", "--skip-git-repo-check", "--json", "-m", choice.model,
               "--sandbox", "workspace-write" if write else "read-only"]
        if choice.effort:
            cmd += ["-c", f"model_reasoning_effort={choice.effort}"]
        return cmd + ["-"], prompt
    cmd = [_exe("agy"), "-p", prompt, "--model", choice.model, "--output-format", "json",
           "--print-timeout", f"{timeout}s"]
    if write:
        cmd += ["--mode", "accept-edits"]
    return cmd, None


def _last_json(stdout: str) -> dict:
    """The CLI's final JSON object: try whole output, then line by line from the end (CLIs may print notices)."""
    try:
        start = stdout.find("{")
        return json.loads(stdout[start:]) if start >= 0 else {}
    except ValueError:
        pass
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


def _parse(choice: Choice, stdout: str) -> tuple[str, int | None, int | None, dict]:
    """Return (final text, input tokens, output tokens, raw)."""
    if choice.cli == "codex":
        text, tin, tout = "", None, None
        for line in stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            item = ev.get("item") or {}
            if item.get("type") == "agent_message":
                text = item.get("text", text)
            usage = ev.get("usage")
            if usage:
                tin, tout = usage.get("input_tokens"), usage.get("output_tokens")
        return text, tin, tout, {}
    raw = _last_json(stdout)
    usage = raw.get("usage") or {}
    text = raw.get("result") if choice.cli == "claude" else raw.get("response")
    return text or "", usage.get("input_tokens"), usage.get("output_tokens"), raw


def run(choice: Choice, prompt: str, cwd: str | Path, *, tier: str = "", purpose: str = "",
        write: bool = False, timeout: int = 1200) -> Result:
    t = time.time()
    try:
        hint = AGY_TOOLS if choice.cli == "agy" else ""
        argv, stdin = _cmd(choice, SUB_AGENT + hint + prompt, write, timeout)
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout + 60, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL)
        out, err, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", "timeout", -1
    secs = time.time() - t
    try:
        text, tin, tout, raw = _parse(choice, out)
    except ValueError:
        text, tin, tout, raw = "", None, None, {}
    if choice.cli == "claude" and "is_error" in raw:   # exit code is non-zero after tool denials; trust the JSON
        failed = raw["is_error"] is True or not text
    else:
        failed = code != 0 or not text or raw.get("status") not in (None, "SUCCESS")
    raw["_exit"] = code
    blob = (err + out[-2000:]).lower()
    res = Result(ok=not failed, text=text if not failed else (text or err[-1000:] or out[-1000:]),
                 choice=choice, seconds=secs, tokens_in=tin, tokens_out=tout,
                 rate_limited=failed and any(h in blob for h in RATE_LIMIT_HINTS), raw=raw)
    _ledger(res, tier, purpose)
    if res.rate_limited:   # stop every process from hammering an exhausted subscription
        from crewline.crew.models import block_quota
        block_quota(choice.cli)
    return res


def _ledger(r: Result, tier: str, purpose: str) -> None:
    path = data_dir() / "ledger" / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "cli": r.choice.cli, "model": r.choice.model,
           "tier": tier, "purpose": purpose, "ok": r.ok, "rate_limited": r.rate_limited,
           "seconds": round(r.seconds, 1), "in": r.tokens_in, "out": r.tokens_out}
    if not r.ok:
        row["error"] = r.text[-200:]
        row["exit"] = r.raw.get("_exit")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
