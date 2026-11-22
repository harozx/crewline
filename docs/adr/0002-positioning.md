# ADR-0002: Positioning - the measured context layer for self-hosted Jira teams

- Date: 2026-11-22
- Status: accepted

## Context (market scan 2026-11-22)
- Jira → PR is taken on Cloud: GitHub Copilot coding agent for Jira (preview since 2026-03, needs Jira Cloud +
  Rovo + paid Copilot; uses title, description, labels, comments, custom fields), Atlassian Rovo Dev / Jira
  Coding Agent (Rovo credits, Teamwork Graph as context layer).
- Multi-CLI orchestrators are crowded: Vibe Kanban, Claude Squad, Emdash, Bernstein, maestro, multiagents.
  They run agents in parallel; none understands the ticket or where to fix.
- Team context: Unblocked (commercial, ~$29/user/mo), Slack pushing conversations as agent context,
  repo-memory tools Kage (GPL) and TeamBrain (Apache). Snowflake "Experience Cards" (2026-08): review memory
  helps recall but can also hurt; more context lowered accuracy in a 2026 study.
- Localisation research (LocAgent, MULocBench, CodeScout, A^2Agent) uses GitHub/SWE-bench issues. No
  Jira-based localisation benchmark found.

## Decision
1. Product core = **brief + locate + recall over MCP**, usable by any agent (Claude Code, Codex, Copilot,
   Vibe Kanban...). The crew runner stays, but as a reference consumer, not the headline.
2. **Jira Data Center/Server and on-prem first-class**: data stays on the machine, uses subscriptions the team
   already pays for. This is where Copilot-for-Jira and Rovo do not go.
3. **Read what others skip:** screenshots, mockups, attachments, linked Confluence; ops tickets enriched with
   stack traces and similar past incidents.
4. **Measured memory:** every memory source ships with an on/off eval; ACL inherited from the source.
5. **Publish a public Jira localisation benchmark** (several Apache projects, post-cutoff tickets) with a
   leaderboard. Owner approval needed before publishing.

## Consequences
- Do not build a kanban/terminal UI; integrate with existing orchestrators instead.
- P1 adds more Apache projects to the benchmark; attachment/image reading moves up.
- Measure: benchmark wins vs plain agent search, and a pilot on a Data Center instance.
