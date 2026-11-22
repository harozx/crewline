# Crewline: rules for every agent and contributor

Crewline turns a ticket into a reviewed PR. It reads Jira, Confluence and GitHub (images and attachments
included), finds where in the code to fix, recalls what the team already learned there, and runs the local CLI
agents (Claude Code, Codex, agy) as a crew with one lead.

Read `docs/HANDOFF.md` (newest entry first) before working, and `docs/PLAN.md` for the roadmap.

## Decision rights
- The lead agent (Claude Code in this repo) decides design, libraries, refactors and phase order alone.
- Escalate to the owner only for: spending money (paid APIs, services), anything that writes to a company
  system (Jira, Confluence, GitHub of an employer), publishing the repo, license changes, deleting data,
  or a result that changes the plan (a phase's exit criterion fails).
- Record every non-obvious decision as an ADR in `docs/adr/` (template: `docs/templates/adr.md`).

## Model tiers (route work, don't guess)
| Tier | Use for | Default models |
|---|---|---|
| `light` | summarise, convert, classify, extract, format checks | agy `gemini-3.8-flash-low`, codex `gpt-5.6-luna` |
| `medium` | code to a clear spec, tests, fixing lint/test failures | codex `gpt-5.6-terra`, agy `claude-sonnet-5-5-medium` |
| `heavy` | planning, hard localisation, cross-review, final calls | Claude Code (Opus), agy `gemini-4-neon-high`, agy `claude-opus-5-5-high` |

- Start at the lowest tier that can do the job; escalate after two failed gate checks.
- Writer and reviewer come from different vendors.
- The routing table lives in `src/crewline/crew/models.py`; change it there from eval results, not by feel.
- Paid APIs are off by default. Subscriptions (Claude Code, agy, Codex/ChatGPT) go first.

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
