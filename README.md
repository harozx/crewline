# Crewline

The context layer for coding agents on Jira teams, including self-hosted Jira Data Center. Crewline reads the
ticket the way a senior would (text, screenshots, attachments, comments, links), finds where in the codebase to
fix, and recalls what the team already learned there, with the source's permissions. Any agent can use it over
MCP: Claude Code, Codex, Cursor, Copilot, agy. It also ships a reference crew runner (a lead plans, workers write
in git worktrees, a reviewer from another vendor checks, tests gate).

Everything runs on your machine with subscriptions you already have. Nothing writes back to Jira or GitHub.

## Use it from your agent (MCP)

```
uv sync
claude mcp add crewline -- uv --directory /path/to/crewline run crewline mcp     # Claude Code
codex mcp add crewline -- uv --directory /path/to/crewline run crewline mcp      # Codex
```
Cursor / other clients: command `uv`, args `--directory /path/to/crewline run crewline mcp`.

| Tool | What it returns |
|---|---|
| `ticket_brief(key)` | Markdown brief of a Jira ticket; images and screenshots described where they appear |
| `locate_files(ticket, repo)` | Files most likely to change, with evidence (signals, similar past tickets) |
| `team_memory(paths)` | Lessons from past code reviews of those files, filtered by your repo access |

Environment: `JIRA_URL`, `JIRA_TOKEN` (Data Center PAT, or Cloud API token with `JIRA_USER`), `CREWLINE_DATA`
(cache folder), `CREWLINE_CLIS` (which agent CLIs Crewline itself may drive; default `agy`).

## Benchmarks

**File localisation on public Apache Jira** (tickets fixed and created after 2026-07-01, gold = non-test files
the fix modified; weights tuned on a separate earlier split):

| Project | Tickets | Path+history baseline | Fused signals | + agent re-rank (top 60) |
|---|---|---|---|---|
| Kafka | 179 | 0.580 | 0.673 | **0.799** |
| HBase | 61 | 0.640 | 0.783 | **0.882** |
| Flink | 358 | 0.484 | 0.581 | **0.704** |
| Hive | 112 | 0.426 | 0.533 | **0.654** |
| All (weighted) | 710 | | | **0.735** |

recall@10. Re-ranking uses a model that may have seen these public codebases; private code may gain less.

**Solving real issues** (16 pallets/click issues after 2026-07-01, hidden tests, Docker `--network none`):
one agent 7/16, crew 7/16 with identical per-issue outcomes; the crew reached that with a cheaper worker tier.

**Team memory** (803 lessons from Kafka reviews; does a reviewer catch what humans caught?): no gain measurable
beyond run-to-run noise yet, so memory is served as an optional checklist, never injected by default.

```
uv run crewline eval build --project kafka && uv run crewline eval locate --project kafka
uv run crewline eval solve-build --repo click && uv run crewline eval solve --mode crew
uv run crewline eval memory
```

Plan and decisions: `docs/PLAN.md` (Vietnamese), `docs/adr/`. License: Apache-2.0
