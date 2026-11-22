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


def _cmd(choice: Choice, prompt: str, write: bool, timeout: int) -> list[str]:
    if choice.cli == "claude":
        cmd = [_exe("claude"), "-p", prompt, "--model", choice.model, "--output-format", "json"]
        if write:
            cmd += ["--permission-mode", "acceptEdits"]
        return cmd
    if choice.cli == "codex":
        cmd = [_exe("codex"), "exec", "--skip-git-repo-check", "--json", "-m", choice.model,
               "--sandbox", "workspace-write" if write else "read-only"]
        if choice.effort:
            cmd += ["-c", f"model_reasoning_effort={choice.effort}"]
        return cmd + [prompt]
    cmd = [_exe("agy"), "-p", prompt, "--model", choice.model, "--output-format", "json",
           "--print-timeout", f"{timeout}s"]
    if write:
        cmd += ["--mode", "accept-edits"]
    return cmd


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
        p = subprocess.run(_cmd(choice, prompt, write, timeout), cwd=str(cwd), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout + 60, stdin=subprocess.DEVNULL)
        out, err, code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, code = "", "timeout", -1
    secs = time.time() - t
    try:
        text, tin, tout, raw = _parse(choice, out)
    except ValueError:
        text, tin, tout, raw = "", None, None, {}
    failed = code != 0 or not text or raw.get("status") not in (None, "SUCCESS") or raw.get("is_error") is True
    blob = (err + out[-2000:]).lower()
    res = Result(ok=not failed, text=text if not failed else (text or err[-1000:] or out[-1000:]),
                 choice=choice, seconds=secs, tokens_in=tin, tokens_out=tout,
                 rate_limited=failed and any(h in blob for h in RATE_LIMIT_HINTS), raw=raw)
    _ledger(res, tier, purpose)
    return res


def _ledger(r: Result, tier: str, purpose: str) -> None:
    path = data_dir() / "ledger" / "calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "cli": r.choice.cli, "model": r.choice.model,
           "tier": tier, "purpose": purpose, "ok": r.ok, "rate_limited": r.rate_limited,
           "seconds": round(r.seconds, 1), "in": r.tokens_in, "out": r.tokens_out}
    if not r.ok:
        row["error"] = r.text[-200:]
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
