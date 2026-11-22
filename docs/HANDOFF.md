# HANDOFF: nhật ký bàn giao

Mục mới nhất ở trên cùng. Mỗi mục: đã làm gì, số đo, bước kế.

---

## 2026-11-22 (3) · TẠM DỪNG: P1 gần xong, P2 sửa lỗi gốc, P3 có 803 bài học

- **P1 định vị (eval, r@10):** rerank 60 ứng viên bằng Neon: Kafka **0.799**, HBase **0.882**, Hive **0.654**; Flink đang dở (297/358 ticket đã cache).
  - Dev: pool 30 → 60 tăng Kafka dev 0.650 → 0.730. Co-change làm tụt (0.586 → 0.441) → bỏ.
  - Dev phân tích: ~1/4 ticket sửa > 5 file (trúng thấp), ~1/3 ticket mô tả ngắn (trúng thấp) → cần comment/link/ảnh.
- **P2 đội agent** (`crewline crew solve`): chạy thử trên chính repo (brief `D:/crewline-data/briefs/self-001/brief.md`).
  - Lỗi gốc đã sửa: claude/codex là shim .cmd → cmd.exe cắt prompt ở dòng đầu → nay gửi prompt qua stdin.
  - Đã sửa thêm: preamble sub-agent (bỏ qua luật giao việc trong CLAUDE.md), tin `is_error` của Claude, gộp bằng cherry-pick (tránh CRLF), worker phải có diff thật.
  - Codex Terra làm worker qua cổng ruff+pytest ở 2 lượt trước; lượt 4 (sau khi sửa stdin) bị dừng giữa chừng.
  - Chấm "giải ticket" trên repo ngoài (click, pytest) cần chạy test của họ: auto mode chặn chạy trực tiếp; owner đang bật Docker.
- **P3 trí nhớ:** 9.773 comment review Kafka từ 05/2026 → lọc 2.519 → **803 bài học** (`D:/crewline-data/memory/kafka.sqlite`), ACL theo repo, test ACL có. Bài đo memory on/off (`crewline eval memory`) chưa chạy xong.

**Chạy tiếp:**
1. `uv run crewline crew solve D:/crewline-data/briefs/self-001/brief.md --repo D:/crewline --gate "uv run ruff check . && uv run pytest -q"`
2. `uv run crewline eval memory --n 60`
3. Flink: `POOL=60 uv run python scripts/rerank_probe.py flink eval 358 agy gemini-4-neon-medium` (dùng cache, chỉ gọi ~61 ticket còn lại)
4. Docker sẵn sàng → bộ chấm solve trên click/pytest trong container.

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
