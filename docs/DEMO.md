# Demo: a real issue on code the models have not seen

Repo: [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) (created 2026-09, after the models' training
data). Issue #1493, fixed 2026-11-15; the fix modified `laya/hooks.py`. Outputs below are copied from real runs
on 2026-11-24, misses included.

## 1. Set up the repo (once, about a minute)

```
$ uv run crewline setup --repo path/to/laya --since 2026-06-01
Crewline setup: .../repos/laya
  ticket source : github - GitHub repo NandhaKishorM/laya: merged PRs that close issues
  history used  : 87 tickets (tuned on the older 60%, scored on the newer 40%)
  right file    : in the top 10 for 81%, ranked first for 53%
  right module  : first for 66%, top 3 for 94%
  signals on    : path, history, symbols, mentions, semantic

Add the MCP server to your agent:
  Claude Code:
    claude mcp add crewline -- uv --directory /path/to/crewline run crewline mcp
  ...
```

The numbers are Crewline measured on this repo's own history, before you rely on it.

## 2. The ticket

> **[bug]: OptionStabilityHook counts the original question twice when choice keys are already A, B, ...**
> When a `choice` question's keys are already `A`, `B`, ... the `letters` rename probe renders exactly the
> original options again. `make_variants` de-duplicates on `(order, relabel)` ...

## 3. Triage (`triage_ticket`, no model, ~1 s)

| # | Module | Open first |
|---|---|---|
| 1 | `laya-ts` | `laya-ts/src/option-stability.ts` |
| 2 | `examples` | `examples/05_choice_criteria_design.py` |
| 3 | `laya` | `laya/hooks.py` ✅ |

Right module at #3 here (the TypeScript port has the same feature name). Across 710 Apache tickets the right
module is first 77% of the time and in the top 3 93%.

## 4. Locate (`locate_files`)

No model, 0.3 s:

| # | File | Found by | Similar past tickets |
|---|---|---|---|
| 1 | `laya-ts/src/option-stability.ts` | path, symbols, mentions, semantic | - |
| 2 | `laya/hooks.py` ✅ | path, history, symbols, mentions | #1285, #1288, #1312 |
| 3 | `examples/05_choice_criteria_design.py` | path, semantic | - |

With a model re-ranking the top 60 (agy Gemini Neon, ~40 s, ~18k tokens):

| # | File | Found by | Similar past tickets |
|---|---|---|---|
| 1 | `laya/hooks.py` ✅ | path, history, symbols, mentions | #1285, #1288, #1312 |
| 2 | `laya-ts/src/option-stability.ts` | path, symbols, mentions, semantic | - |

The "similar past tickets" are earlier issues whose fixes also changed `laya/hooks.py`: the evidence an agent or
a reviewer can check.

## 5. What to expect

- Small and medium repos: the right file in the top 10 for roughly 80% of tickets with no model at all.
- Large, sprawling repos: 30-45% without a model, 45-60% with re-ranking.
- An agent exploring on its own finds files about as well or better on hard repos, at 3-5x the tokens. Use
  Crewline for triage, routing and cheap first guesses; let the agent explore when a single hard fix needs it.
