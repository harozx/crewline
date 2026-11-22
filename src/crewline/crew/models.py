"""Model routing table: tier -> ordered (cli, model) choices. Tune from eval results, not by feel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["light", "medium", "heavy"]
Cli = Literal["claude", "codex", "agy"]


@dataclass(frozen=True)
class Choice:
    cli: Cli
    model: str
    effort: str | None = None

    @property
    def vendor(self) -> str:
        m = self.model.lower()
        if m.startswith("claude") or self.cli == "claude":
            return "anthropic"
        if m.startswith("gemini"):
            return "google"
        return "openai"


# First entry is preferred; later entries are fallbacks when a CLI is rate-limited or fails.
ROUTES: dict[Tier, list[Choice]] = {
    "light": [
        Choice("agy", "gemini-3.8-flash-low"),
        Choice("codex", "gpt-5.6-luna", "low"),
        Choice("claude", "haiku"),
    ],
    "medium": [
        Choice("codex", "gpt-5.6-terra", "medium"),
        Choice("agy", "claude-sonnet-5-5-medium"),
        Choice("claude", "sonnet"),
    ],
    "heavy": [
        Choice("claude", "opus"),
        Choice("agy", "gemini-4-neon-high"),
        Choice("agy", "claude-opus-5-5-high"),
        Choice("codex", "gpt-5.6-terra", "high"),
    ],
}

ESCALATE: dict[Tier, Tier | None] = {"light": "medium", "medium": "heavy", "heavy": None}


QUOTA_BLOCK_HOURS = 5.0


def _quota_file():
    from crewline.config import data_dir
    return data_dir() / "ledger" / "quota_blocked.json"


def quota_blocked() -> set[Cli]:
    """CLIs that hit a usage limit and are still inside their block window (shared by every process)."""
    import json
    import time
    f = _quota_file()
    try:
        until = json.loads(f.read_text())
    except (OSError, ValueError):
        return set()
    return {cli for cli, t in until.items() if t > time.time()}


def block_quota(cli: Cli, hours: float = QUOTA_BLOCK_HOURS) -> None:
    import json
    import time
    f = _quota_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        until = json.loads(f.read_text())
    except (OSError, ValueError):
        until = {}
    until[cli] = max(until.get(cli, 0), time.time() + hours * 3600)
    f.write_text(json.dumps(until))


def pick(tier: Tier, avoid_vendor: str | None = None, blocked: set[Cli] = frozenset()) -> list[Choice]:
    """Choices for a tier in preference order, skipping blocked or quota-exhausted CLIs and (for reviewers)
    the writer's vendor."""
    blocked = set(blocked) | quota_blocked()
    out = [c for c in ROUTES[tier] if c.cli not in blocked and c.vendor != avoid_vendor]
    return out or [c for c in ROUTES[tier] if c.cli not in blocked]
