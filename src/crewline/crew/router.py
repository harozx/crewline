"""Run a prompt at a tier: try choices in order, skip rate-limited CLIs, escalate a tier if a gate keeps failing."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from crewline.crew import adapters
from crewline.crew.models import ESCALATE, Cli, Tier, pick

Gate = Callable[[adapters.Result], bool]


def ask(prompt: str, cwd: str | Path, tier: Tier = "light", *, purpose: str = "", write: bool = False,
        gate: Gate | None = None, avoid_vendor: str | None = None, tries_per_tier: int = 2,
        escalate: bool = True) -> adapters.Result:
    blocked: set[Cli] = set()
    last: adapters.Result | None = None
    current: Tier | None = tier
    while current:
        failures = 0
        for choice in pick(current, avoid_vendor, blocked):
            res = adapters.run(choice, prompt, cwd, tier=current, purpose=purpose, write=write)
            last = res
            if res.rate_limited:
                blocked.add(choice.cli)
                continue
            if res.ok and (gate is None or gate(res)):
                return res
            failures += 1
            if failures >= tries_per_tier:
                break
        current = ESCALATE[current] if escalate else None
    if last is None:
        raise RuntimeError(f"no CLI available for tier {tier}")
    return last
