# ADR-0001: Drive local CLI agents, not model APIs

- Date: 2026-11-22
- Status: accepted

## Context
The owner has subscriptions for Claude Code, Google (agy: Gemini 4, Claude Opus/Sonnet) and ChatGPT (Codex).
Paid API spend is to be avoided. Each CLI is already a full coding agent with file and shell tools.

## Decision
Crewline orchestrates `claude -p`, `codex exec` and `agy -p` as subprocesses behind one adapter interface
(`crewline.crew.adapters`). Agents exchange files with a schema (task spec, result, diff), not chat.
Every call is written to a ledger (model, tier, tokens, seconds, status) so routing can be tuned from data.

## Consequences
- No API keys needed; cost is subscription quota, tracked in the ledger.
- CLIs change flags and model names (Codex `gpt-5.6-sol` fails on a ChatGPT account, 2026-11-22): adapters
  must stay thin and model names live in one table.
- Calls are slow (seconds to minutes): run independent tasks in parallel.
