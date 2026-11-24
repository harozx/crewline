# ADR-0003: Position on cost and coverage, not on beating the agent at finding files

- Date: 2026-11-24
- Status: accepted (refines ADR-0002)

## Context
Measured on the same tickets (read-only task: list the files the fix must modify):

| | Kafka 60 r@10 | tokens / s | Flink 40 r@10 | tokens / s |
|---|---|---|---|---|
| Agent (Gemini Neon Medium via agy) exploring alone | 0.804 | 66k / 63 | 0.835 | 98k / 107 |
| Crewline locate, fused signals, no model | 0.686 | 0 / 0.5 | 0.536 | 0 / 0.5 |
| Crewline locate + re-rank | 0.811 | ~18k / ~40 | 0.680 | ~18k / ~40 |
| Agent given locate's top 10 first | 0.798 | 56k / 57 | 0.821 | 78k / 81 |

Other results: crew vs single agent 7/16 vs 7/16 on click; review-lesson memory and codebase maps gave no
measurable gain; ticket-to-code history helps locate by +1.4 to +10 points depending on the repo.

## Decision
- Do not claim locate "finds files better than agents". Modern agents explore well.
- Claim what holds: comparable recall on Kafka at 3.6x fewer tokens; zero-token fused ranking in 0.5 s;
  per-repo calibration with numbers on the user's own history.
- Lead use cases: triage and routing of many tickets (which service/team/files, before any agent runs),
  scope estimates, environments where models cannot run on the code, and cheap first guesses that an agent
  can verify. For fixing one hard ticket, let the agent explore.
- Keep ticket reading (images, attachments, comments) and Jira Data Center support as the other pillars.

Triage (added 2026-11-24): module top-1 / top-3 over 710 tickets with zero tokens: locate 0.768 / 0.934
(aggregation tuned on dev; was 0.689 / 0.920),
Jira Component mapping 0.544, most-changed module 0.299.

## Consequences
- README leads with cost/coverage numbers and shows the agent comparison honestly.
- Next measurements: triage accuracy at the service/module level across many tickets (where 0-token ranking
  matters), and a pilot on private code.
