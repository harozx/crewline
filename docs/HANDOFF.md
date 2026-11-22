# HANDOFF: nhật ký bàn giao

Mục mới nhất ở trên cùng. Mỗi mục: đã làm gì, số đo, bước kế.

---

## 2026-11-22 (2) · P1 định vị: Kafka đạt 0.728; benchmark 4 dự án; brief đọc ảnh

- **Đã làm:**
  - Chỉ mục symbol (class/method/config key) dựng từ code tại mốc 01/07 → không lộ đáp án. Bộ dò "ticket nhắc tới gì" (CamelCase, Class#method, stack frame, config key).
  - Tách dev (01–06/2026, để dò) và eval (≥ 07/2026, chỉ để báo cáo). Trọng số gộp dò trên dev Kafka.
  - Model sắp xếp lại top 30 (chỉ đưa đường dẫn + symbol, không đưa nội dung file).
  - Benchmark tổng quát `evals/apache.py`: Kafka, Flink, HBase, Hive (710 ticket eval).
  - `crewline brief KEY`: ticket → markdown, ảnh tải về và được mô tả ngay tại chỗ (agy flash), wiki markup + ADF.
- **Số đo (eval):**

  | Dự án | baseline r@10 | gộp đã dò r@10 | + Neon rerank r@10 |
  |---|---|---|---|
  | Kafka (179) | 0.580 | 0.673 | **0.728** (r@1 0.549) |
  | HBase (61) | 0.640 | 0.783 | chưa chạy |
  | Hive (112) | 0.426 | 0.533 | chưa chạy |

  - Dev 40 ticket, rerank: Neon 0.650 > Flash 0.639 > Codex Luna 0.595 (gộp 0.565).
  - Lưu ý: model có thể đã biết cấu trúc code Kafka → trên code riêng của công ty mức tăng từ rerank có thể thấp hơn. Cần đo trên repo model chưa thấy (pilot).
- **Quyết định:** ADR-0002 (định vị thị trường).

**Bước kế:** Flink xong → bảng 4 dự án; xem Hive trượt ở đâu (trên dev); rerank cho HBase/Hive; đưa rerank thành lệnh `crewline locate`.

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
