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
# agy first everywhere: one subscription reaches both Gemini and Claude, so writer and reviewer can still come
# from different vendors. claude / codex are only used when the user enabled them (their own linked account).
ROUTES: dict[Tier, list[Choice]] = {
    "light": [
        Choice("agy", "gemini-3.8-flash-low"),
        Choice("codex", "gpt-5.6-luna", "low"),
        Choice("claude", "haiku"),
    ],
    "medium": [
        Choice("agy", "claude-sonnet-5-5-medium"),
        Choice("agy", "gemini-4-neon-medium"),
        Choice("codex", "gpt-5.6-terra", "medium"),
        Choice("claude", "sonnet"),
    ],
    "heavy": [
        Choice("agy", "claude-opus-5-5-high"),
        Choice("agy", "gemini-4-neon-high"),
        Choice("claude", "opus"),
        Choice("codex", "gpt-5.6-terra", "high"),
    ],
}
DEFAULT_CLIS = ("agy",)


def enabled_clis() -> set[str]:
    """CLIs this install may drive: env CREWLINE_CLIS="agy,claude,codex" or <data>/config.json {"clis": [...]}.
    Default agy only - other CLIs spend the user's own personal quota and must be opted into."""
    import json
    import os
    env = os.environ.get("CREWLINE_CLIS")
    if env:
        return {c.strip() for c in env.split(",") if c.strip()}
    from crewline.config import data_dir
    try:
        return set(json.loads((data_dir() / "config.json").read_text()).get("clis", DEFAULT_CLIS))
    except (OSError, ValueError):
        return set(DEFAULT_CLIS)

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
    blocked = set(blocked) | quota_blocked() | ({"claude", "codex", "agy"} - enabled_clis())
    out = [c for c in ROUTES[tier] if c.cli not in blocked and c.vendor != avoid_vendor]
    return out or [c for c in ROUTES[tier] if c.cli not in blocked]
