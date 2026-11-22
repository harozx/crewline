# Crewline: rules for every agent and contributor

Crewline turns a ticket into a reviewed PR. It reads Jira, Confluence and GitHub (images and attachments
included), finds where in the code to fix, recalls what the team already learned there, and runs the local CLI
agents (Claude Code, Codex, agy) as a crew with one lead.

Read `docs/HANDOFF.md` (newest entry first) before working, and `docs/PLAN.md` for the roadmap.

## Sub-agents
A prompt that starts with `[Crewline sub-agent]` is one step of a crew run: skip delegation, handoff and
ADR rules and answer exactly what the prompt asks.

## Decision rights
- The lead agent (Claude Code in this repo) decides design, libraries, refactors and phase order alone.
- Escalate to the owner only for: spending money (paid APIs, services), anything that writes to a company
  system (Jira, Confluence, GitHub of an employer), publishing the repo, license changes, deleting data,
  or a result that changes the plan (a phase's exit criterion fails).
- Record every non-obvious decision as an ADR in `docs/adr/` (template: `docs/templates/adr.md`).

## Model tiers (route work, don't guess)
| Tier | Use for | Default route (agy) |
|---|---|---|
| `light` | summarise, convert, classify, extract, format checks | `gemini-3.8-flash-low` |
| `medium` | code to a clear spec, tests, fixing lint/test failures | `claude-sonnet-5-5-medium`, `gemini-4-neon-medium` |
| `heavy` | planning, hard localisation, cross-review, final calls | `claude-opus-5-5-high`, `gemini-4-neon-high` |

- Only enabled CLIs are used: `CREWLINE_CLIS` or `<data>/config.json` `{"clis": [...]}`; default `agy` only.
  Claude Code and Codex CLIs spend the user's personal quota: enable them only for users who linked their own
  account. (2026-11-22: benchmark runs exhausted Codex for a month and hit Claude's 5-hour limit.)
- Start at the lowest tier that can do the job; escalate after two failed gate checks.
- Writer and reviewer come from different vendors (Claude vs Gemini both reachable through agy).
- A CLI that hits a usage limit is blocked in `<data>/ledger/quota_blocked.json` until it resets.
- The routing table lives in `src/crewline/crew/models.py`; change it there from eval results, not by feel.
- Paid APIs are off by default.
- Heavy evals run one at a time (16 GB machine; parallel runs got reaped for memory).

## Code
- Python 3.11, `uv`. Run `uv run ruff check . && uv run pytest` before every commit.
- `src/crewline/<area>/` per module: `sources`, `reader`, `index`, `locate`, `memory`, `crew`, `mcp`, `evals`.
- Code, identifiers, commit messages, README: English. Owner-facing notes (`docs/PLAN.md`, `docs/HANDOFF.md`): Vietnamese.
- Small modules, plain functions, dataclasses. No framework for orchestration: subprocess + files.
- Agents talk through files with a schema (task spec, result report, diff), never free chat.
- Tests only for logic that can silently go wrong (ranking, linking, ACL, routing). No tests for plumbing.

## Data and safety
- Datasets and caches go to `D:/crewline-data` (`CREWLINE_DATA`), never into the repo.
- Never store secrets, tokens or raw transcripts in the repo, the memory store or a ledger.
- Every memory item keeps its source link and inherits the source's ACL; queries run with the user's token.
- Company systems are read-only unless the owner turns writing on for that system.
- Eval sets for models only use tickets created after `2026-07-01` (contamination guard).

## Git
- Branch per change off `main`; small commits; message `area: what changed` + why in the body.
- Plain `git commit` (identity already configured).
- Every merged phase updates `docs/HANDOFF.md` with: what changed, numbers, next step.
