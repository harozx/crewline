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

**Versus an agent exploring the repo itself** (same tickets; the agent lists the files to modify, read-only):

| | Kafka (60) r@10 | tokens / time | Flink (40) r@10 | tokens / time |
|---|---|---|---|---|
| Agent alone (Gemini Neon Medium) | 0.804 | 66k / 63 s | **0.835** | 98k / 107 s |
| Crewline locate, no model | 0.686 | **0 / 0.5 s** | 0.536 | **0 / 0.5 s** |
| Crewline locate + re-rank | **0.811** | 18k / 40 s | 0.680 | 18k / 40 s |

Agents explore well. Crewline's edge is cost and speed: about the same recall as the agent on Kafka for a
quarter of the tokens, and a zero-token ranking in half a second, which is what you want when triaging or
routing hundreds of tickets before any agent runs. On a hard ticket in a large repo, let the agent explore
(giving it Crewline's list first saved ~15% tokens but did not raise recall).

**Per-repo calibration** (`crewline calibrate`): which signals help depends on the codebase. Kafka favours
symbols (recall@10 0.620 → 0.642 after calibration); sqlfluff favours paths and drops two signals
(0.702 → 0.763).

**Solving real issues** (16 pallets/click issues after 2026-07-01, hidden tests, Docker `--network none`):
one agent 7/16, crew 7/16 with identical per-issue outcomes; the crew reached that with a cheaper worker tier.

**Team memory** (803 lessons from Kafka reviews; does a reviewer catch what humans caught?): no gain measurable
beyond run-to-run noise yet, so memory is served as an optional checklist, never injected by default.
A generated codebase map did not help either (same recall, 8-40% more tokens on click and Kafka); it is off.

```
uv run crewline eval build --project kafka && uv run crewline eval locate --project kafka
uv run crewline eval solve-build --repo click && uv run crewline eval solve --mode crew
uv run crewline eval memory
```

Plan and decisions: `docs/PLAN.md` (Vietnamese), `docs/adr/`. License: Apache-2.0
