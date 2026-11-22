@AGENTS.md

## Claude Code specifics
- You are the lead. Delegate light/medium work through `uv run crewline crew run` (or the `delegate` skill)
  instead of doing it yourself; keep your own context for planning, review and decisions.
- Project skills live in `.claude/skills/`: `handoff`, `eval`, `delegate`, `adr`.
