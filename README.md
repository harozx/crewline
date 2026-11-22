# Crewline

Ticket in, reviewed PR out. Crewline reads the ticket the way a senior would (text, screenshots, attachments,
linked Confluence pages), finds where in the codebase to fix, recalls what the team already learned there
(PR reviews, postmortems, past agent sessions, with the source's permissions), and runs the coding CLIs you
already have (Claude Code, Codex, agy) as a crew: a thinking model leads, light models do light work, a
different vendor reviews, tests gate.

Status: P0, benchmark and baselines. See `docs/PLAN.md` (Vietnamese) and `evals/results/`.

## Benchmark: Kafka file localisation
179 Apache Kafka tickets fixed and created after 2026-07-01, gold = non-test files the fix modified.

| Method | recall@5 | recall@10 | recall@20 |
|---|---|---|---|
| BM25 over paths | 0.313 | 0.417 | 0.502 |
| Similar past tickets → their files | 0.393 | 0.452 | 0.538 |
| Fused | 0.444 | 0.580 | 0.699 |

```
uv sync
uv run crewline eval build-kafka   # data to $CREWLINE_DATA (default D:/crewline-data)
uv run crewline eval locate
```

License: Apache-2.0
