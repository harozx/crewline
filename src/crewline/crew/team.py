"""The crew: a lead plans, workers change code in their own git worktrees, a gate runs, a reviewer from another
vendor checks the diff, results are integrated on one branch. Nothing is pushed; a human merges.

Flow per run:
  plan (heavy, read-only) -> waves of tasks (parallel inside a wave) -> per task:
  worker (task tier, write) -> gate -> on failure retry once with the failure, then escalate a tier
  -> review (heavy, other vendor) -> one fix round if changes requested -> integrate -> final gate.
A run with one task is the "solo" baseline with the same plumbing.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from crewline.config import data_dir
from crewline.crew import adapters
from crewline.crew.models import ESCALATE, Choice, Tier, pick

PLAN_PROMPT = """You are the lead engineer. Read brief.md (the ticket) and locate.md (files most likely involved).
You may read the repository but must not change it. Plan the change as JSON only:
{{"tasks": [{{"id": "T1", "title": "...", "tier": "light|medium|heavy", "files": ["paths the task may change"],
  "depends_on": [], "instructions": "precise, self-contained instructions for the worker"}}]}}
Rules: use ONE task unless the work splits into independent parts touching different files; at most {max_tasks}
tasks. Tier: light = mechanical edit, medium = normal code change with clear spec, heavy = tricky logic.
Do not plan test-only tasks unless the ticket asks for tests."""

WORK_PROMPT = """You are a worker on a team. Read brief.md for the ticket. Your task:
{title}
{instructions}
Only change these files unless strictly necessary: {files}
Make the change directly in the repository. Keep it minimal and in the project's style. Do not commit.
{feedback}"""

REVIEW_PROMPT = """Review the change in review.diff against the ticket in brief.md. You may read the repository.
Reply with JSON only: {{"verdict": "approve" | "changes", "issues": ["concrete problem and where"]}}.
Approve unless there is a real bug, a missed requirement, or a change outside the ticket's scope."""


@dataclass
class Task:
    id: str
    title: str
    tier: Tier = "medium"
    files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    instructions: str = ""


@dataclass
class Step:
    task: str
    role: str
    cli: str
    model: str
    ok: bool
    seconds: float
    note: str = ""


@dataclass
class RunReport:
    run_id: str
    mode: str
    branch: str = ""
    tasks: list[Task] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    gate_passed: bool = False
    gate_tail: str = ""
    seconds: float = 0.0
    diff_files: list[str] = field(default_factory=list)


def _sh(cmd: list[str] | str, cwd: Path, timeout: int = 1800) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, shell=isinstance(cmd, str))
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "gate timed out"


def _git(cwd: Path, *args: str) -> str:
    code, out = _sh(["git", *args], cwd)
    if code != 0:
        raise RuntimeError(f"git {' '.join(args)}: {out[-500:]}")
    return out


def _json(text: str) -> dict:
    """First JSON object in an agent reply (fenced or bare); {} when there is none."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    return {}


class Crew:
    def __init__(self, repo: Path, brief: Path, gate: str | None, locate_md: str = "", max_tasks: int = 4,
                 lead: Choice | None = None, picker=pick):
        self.repo = repo.resolve()
        self.brief_text = brief.read_text(encoding="utf-8")
        self.locate_md = locate_md
        self.gate_cmd = gate
        self.max_tasks = max_tasks
        self.lead = lead
        self.pick = picker
        self.run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.root = data_dir() / "runs" / self.run_id
        self.root.mkdir(parents=True)
        self.base = _git(self.repo, "rev-parse", "HEAD").strip()
        self.report = RunReport(self.run_id, "crew")

    # -- helpers ---------------------------------------------------------------------------------------------
    def _seed(self, wt: Path) -> None:
        (wt / "brief.md").write_text(self.brief_text, encoding="utf-8")
        if self.locate_md:
            (wt / "locate.md").write_text(self.locate_md, encoding="utf-8")

    def _unseed(self, wt: Path) -> None:
        for name in ("brief.md", "locate.md", "review.diff"):
            (wt / name).unlink(missing_ok=True)

    def _worktree(self, name: str, start: str) -> Path:
        wt = self.root / "wt" / name
        _git(self.repo, "worktree", "add", "-q", "-b", f"crewline/{self.run_id}/{name}", str(wt), start)
        return wt

    def _diff(self, wt: Path) -> str:
        self._unseed(wt)
        _git(wt, "add", "-A")
        return _git(wt, "diff", "--cached", self.base)

    def _gate(self, wt: Path) -> tuple[bool, str]:
        if not self.gate_cmd:
            return True, ""
        self._unseed(wt)
        code, out = _sh(self.gate_cmd.replace("{wt}", str(wt)), wt)   # {wt}: e.g. a Docker volume mount
        return code == 0, out[-3000:]

    def _call(self, task: str, role: str, choice: Choice, prompt: str, cwd: Path, write: bool,
              timeout: int = 1200) -> adapters.Result:
        res = adapters.run(choice, prompt, cwd, tier=role, purpose=f"crew.{role}", write=write, timeout=timeout)
        self.report.steps.append(Step(task, role, choice.cli, choice.model, res.ok, round(res.seconds, 1),
                                      "rate-limited" if res.rate_limited else ""))
        return res

    # -- phases ----------------------------------------------------------------------------------------------
    def plan(self) -> list[Task]:
        self._seed(self.repo)
        try:
            for choice in ([self.lead] if self.lead else self.pick("heavy")):
                res = self._call("-", "lead", choice, PLAN_PROMPT.format(max_tasks=self.max_tasks), self.repo, False)
                try:
                    tasks = [Task(**{k: v for k, v in t.items() if k in Task.__dataclass_fields__})
                             for t in _json(res.text).get("tasks", [])]
                except (ValueError, TypeError):
                    tasks = []
                if tasks:
                    return tasks[: self.max_tasks]
        finally:
            self._unseed(self.repo)
        return [Task("T1", "Implement the ticket", "heavy", instructions="Implement what brief.md asks.")]

    def work(self, task: Task, start: str) -> tuple[Path, bool, str]:
        wt = self._worktree(task.id, start)
        feedback, tier, tries = "", task.tier, 0
        writer_vendor = ""
        while tier:
            for choice in self.pick(tier):
                self._seed(wt)
                prompt = WORK_PROMPT.format(title=task.title, instructions=task.instructions,
                                            files=", ".join(task.files) or "as needed", feedback=feedback)
                res = self._call(task.id, f"worker:{tier}", choice, prompt, wt, True)
                if res.rate_limited:
                    continue   # quota hit: same attempt on the next CLI, not a failed try
                writer_vendor = choice.vendor
                changed = bool(self._diff(wt).strip())
                passed, tail = self._gate(wt) if changed else (False, "")
                if res.ok and changed and passed:
                    return wt, True, writer_vendor
                feedback = ("Your previous attempt did not pass. Gate output (tail):\n" + tail) if tail else \
                    "Your previous attempt failed to produce a change."
                break      # one attempt per try; retry / escalate below
            else:
                if not self.pick(tier):   # every CLI for this tier is out of quota
                    return wt, False, writer_vendor
            tries += 1
            if tries >= 2:
                tier, tries = ESCALATE[tier], 0
        return wt, False, writer_vendor

    def review(self, task: Task, wt: Path, writer_vendor: str) -> None:
        diff = self._diff(wt)
        if not diff.strip():
            return
        self._seed(wt)
        (wt / "review.diff").write_text(diff, encoding="utf-8")
        verdict: dict = {}
        for choice in self.pick("heavy", avoid_vendor=writer_vendor)[:2]:   # a stuck reviewer must not stall the run
            res = self._call(task.id, "review", choice, REVIEW_PROMPT, wt, False, timeout=300)
            verdict = _json(res.text) if res.ok else {}
            if verdict.get("verdict"):
                break
        self._unseed(wt)
        if verdict.get("verdict") == "changes" and verdict.get("issues"):
            fix = Task(task.id, task.title, task.tier, task.files, instructions=task.instructions +
                       "\nA reviewer asked for these changes:\n- " + "\n- ".join(verdict["issues"]))
            self._seed(wt)
            res = self._call(task.id, f"fix:{task.tier}", self.pick(task.tier)[0],
                             WORK_PROMPT.format(title=fix.title, instructions=fix.instructions,
                                                files=", ".join(fix.files) or "as needed", feedback=""), wt, True)
            if not res.ok or not self._gate(wt)[0]:
                _git(wt, "checkout", "-q", "--", ".")   # fix broke the gate: keep the reviewed version
                _git(wt, "add", "-A")

    def run(self, review: bool = True) -> RunReport:
        t0 = time.time()
        tasks = self.plan()
        self.report.tasks = tasks
        integ = self._worktree("integration", self.base)
        done: set[str] = set()
        pending = list(tasks)
        while pending:
            wave = [t for t in pending if set(t.depends_on) <= done] or pending[:1]
            start = _git(integ, "rev-parse", "HEAD").strip()
            with ThreadPoolExecutor(len(wave)) as ex:
                results = list(ex.map(lambda t, s=start: (t, *self.work(t, s)), wave))
            for task, wt, _ok, vendor in results:
                if review:
                    self.review(task, wt, vendor)
                if self._diff(wt).strip():
                    _git(wt, "commit", "-q", "-m", f"crewline {task.id}: {task.title}")
                    code, out = _sh(["git", "cherry-pick", "--allow-empty", f"crewline/{self.run_id}/{task.id}"], integ)
                    if code != 0:
                        _sh(["git", "cherry-pick", "--abort"], integ)
                        self.report.steps.append(Step(task.id, "integrate", "-", "-", False, 0, out[-300:]))
                done.add(task.id)
                pending.remove(task)
        self.report.gate_passed, self.report.gate_tail = self._gate(integ)
        self.report.branch = f"crewline/{self.run_id}/integration"
        self.report.diff_files = [f for f in _git(integ, "diff", "--name-only", self.base).split() if f]
        self.report.seconds = round(time.time() - t0, 1)
        (self.root / "report.json").write_text(json.dumps(asdict(self.report), indent=2), encoding="utf-8")
        return self.report

    def cleanup(self) -> None:
        """Remove worktrees but keep branches (the result lives on the integration branch)."""
        for wt in (self.root / "wt").glob("*"):
            _sh(["git", "worktree", "remove", "--force", str(wt)], self.repo)
        shutil.rmtree(self.root / "wt", ignore_errors=True)


def solo(repo: Path, brief: Path, gate: str | None, choice: Choice) -> RunReport:
    """Baseline: one agent, one attempt + one retry with gate feedback, no plan, no review."""
    crew = Crew(repo, brief, gate, picker=lambda tier, avoid_vendor=None, blocked=frozenset(): [choice])
    task = Task("T1", "Implement the ticket", "heavy", instructions="Implement what brief.md asks.")
    crew.plan = lambda: [task]  # type: ignore[method-assign]
    report = crew.run(review=False)
    report.mode = f"solo:{choice.cli}:{choice.model}"
    (crew.root / "report.json").write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    crew.cleanup()   # worktrees go, the result stays on its branch
    return report
