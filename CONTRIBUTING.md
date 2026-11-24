# Contributing

1. `uv sync`, then `uv run ruff check . && uv run pytest` must pass before every commit (CI runs the same).
2. Read [AGENTS.md](AGENTS.md): code style, model tiers, data and safety rules apply to people too.
3. A change that claims to improve localisation, triage or the crew needs a number: run the matching
   `crewline eval ...` command and put the before/after in the PR. Results go to `evals/results/`.
4. Tests only for logic that can silently go wrong (ranking, linking, ACL, routing).
5. Never commit tokens, company tickets or transcripts. Datasets and caches live in `$CREWLINE_DATA`.

Commit messages: `area: what changed`, with the why in the body.
