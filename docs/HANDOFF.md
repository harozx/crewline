# HANDOFF: nhật ký bàn giao

Mục mới nhất ở trên cùng. Mỗi mục: đã làm gì, số đo, bước kế.

---

## 2026-11-22 (1) · Dựng dự án; P0 xong: dataset Kafka + baseline định vị

- **Đã làm:** repo, quy ước (`AGENTS.md`), kế hoạch (`docs/PLAN.md`), 4 skill (`handoff`, `eval`, `delegate`, `adr`), template ADR/task, CI.
  - Adapter cho 3 CLI + router theo tầng (fallback khi bị giới hạn quota, leo thang khi fail), ledger ở `D:/crewline-data/ledger/calls.jsonl`. Smoke test: agy flash/neon, codex luna, claude haiku đều trả lời đúng.
  - Codex CLI nâng lên 0.171; `gpt-5.6-sol` (mặc định trong config) không chạy với tài khoản ChatGPT → dùng `gpt-5.6-terra` / `gpt-5.6-luna`.
  - Dataset: clone blobless Kafka (77 MB), 3.932 ticket nối được commit từ 2023, **179 ticket kiểm tra** (tạo ≥ 2026-07-01).
- **Số đo** (`evals/results/kafka-locate-baseline-2026-11-22.json`):

  | Cách | r@5 | r@10 | r@20 |
  |---|---|---|---|
  | BM25 đường dẫn | 0.313 | 0.417 | 0.502 |
  | Ticket lịch sử tương tự | 0.393 | 0.452 | 0.538 |
  | Gộp (RRF) | 0.444 | **0.580** | 0.699 |

- **Quyết định:** ADR-0001 (điều khiển CLI trên máy, không dùng API trả tiền).

**Bước kế:** P1 định vị: thêm symbol (tên class/method trong nội dung file), parse stack trace, re-rank top 30 bằng model medium → mục tiêu r@10 ≥ 0.70.
