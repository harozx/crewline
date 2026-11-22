---
name: eval
description: Run Crewline benchmarks and compare against the last result before claiming an improvement. Use whenever a change touches locate/, index/, reader/, memory/ or crew/ routing.
---

1. Dataset missing or stale? `uv run crewline eval build-kafka` (data goes to `D:/crewline-data`).
2. Quick check while iterating: `uv run crewline eval locate --limit 40`. Final number: full run, no limit.
3. Compare with the newest file in `evals/results/` for the same method. Report the delta per metric.
4. An improvement counts only on the full set. A change that lowers recall@10 by more than 0.02 is reverted
   or justified in an ADR.
5. Never tune on eval tickets by hand (no reading their gold files to craft rules). Inspect failures only on
   tickets created before the cutoff.
6. Commit the result JSON with the change that produced it.
