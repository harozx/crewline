---
name: delegate
description: Hand light or medium work to agy/Codex through the Crewline router instead of doing it in Claude Code. Use for summarising, converting, extracting, drafting code to a clear spec, writing tests, or second-opinion reviews.
---

Pick the tier from AGENTS.md, then:

```
uv run crewline crew run "<self-contained prompt>" --tier light|medium|heavy --cwd <dir> [--write] --purpose <label>
```

Rules:
- The prompt must stand alone: name the files, the expected output format, and the acceptance check.
- For code: give a task spec shaped like `docs/templates/task.json`, use `--write`, run in a worktree
  (`git worktree add ../crewline-wt/<task> -b task/<id>`), then review the diff yourself or at `heavy` tier
  with a reviewer from another vendor.
- For long inputs, let the agent read files in `--cwd`; do not paste them into the prompt.
- Only relay the short result back into your own context.
- Check `D:/crewline-data/ledger/calls.jsonl` for failures and rate limits before retrying.
