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


def pick(tier: Tier, avoid_vendor: str | None = None, blocked: set[Cli] = frozenset()) -> list[Choice]:
    """Choices for a tier in preference order, skipping blocked CLIs and (for reviewers) the writer's vendor."""
    out = [c for c in ROUTES[tier] if c.cli not in blocked and c.vendor != avoid_vendor]
    return out or [c for c in ROUTES[tier] if c.cli not in blocked]
