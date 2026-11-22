---
name: handoff
description: Write the end-of-session entry in docs/HANDOFF.md (Vietnamese, newest on top) - what changed, numbers, next step. Use at the end of any work session or phase in this repo.
---

1. Collect facts only from this session: commits (`git log --oneline` since last entry), eval results in
   `evals/results/`, decisions (ADRs added).
2. Insert a new entry right under the header of `docs/HANDOFF.md`:
   ```
   ## YYYY-MM-DD (N) · <tiêu đề ngắn>
   - **Đã làm:** ...
   - **Số đo:** bảng hoặc gạch đầu dòng, kèm tên file kết quả
   - **Quyết định:** ADR-NNNN nếu có
   **Bước kế:** một việc cụ thể
   ```
3. Tick finished items in `docs/PLAN.md`. Keep it short: facts and numbers, no narration.
