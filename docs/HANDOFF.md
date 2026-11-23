# HANDOFF: nhật ký bàn giao

Mục mới nhất ở trên cùng. Mỗi mục: đã làm gì, số đo, bước kế.

---

## 2026-11-23 (7) · `crewline calibrate`: mỗi repo một cấu hình, tự đo trên lịch sử của chính nó

- Backtest theo thời gian (dò 60% cũ, chấm 40% mới), symbol từ worktree snapshot trong thư mục dữ liệu (không đụng working tree người dùng); `locate`/MCP tự dùng `calibration.json`.
- **Kafka** (keys + Jira, 400 ticket): nguồn mạnh nhất symbol 0.56; r@10 0.620 → 0.642.
- **sqlfluff** (issue GitHub, 277 ticket): nguồn mạnh nhất đường dẫn 0.76; hiệu chỉnh **tắt** symbol + mentions; r@10 0.702 → 0.763, r@1 0.348 → 0.475.
- Repo riêng của owner (media-judge, viet-lyricist, TradingAgents) quá nhỏ / không có mã ticket → không hiệu chỉnh được (công cụ trả "không đủ lịch sử").

**Bước kế:** bản đồ codebase (đo token/thời gian worker có/không có); hiệu chỉnh thêm nguồn trí nhớ "tại sao" theo từng repo; pilot chỉ đọc ở công ty (cần owner duyệt).

---

## 2026-11-23 (6) · P2 chốt 7/16 = 7/16; P4 bắt đầu: MCP server chạy được

- **P2 chốt:** đội 7/16, solo Neon High 7/16, trùng kết quả cả 16 issue; đội dùng worker rẻ hơn, chậm ~16% (495 s vs 427 s).
- **P4:** `crewline mcp` (mcp 2.3, `MCPServer`): `ticket_brief`, `locate_files`, `team_memory`. Đã gọi thật qua client stdio (`scripts/mcp_smoke.py`): locate đưa `PartitionChangeBuilder.java` lên #1 cho KAFKA-21597; memory trả bài học kèm link; brief đọc Jira công khai.
- README viết lại theo định vị ADR-0002 + bảng benchmark trung thực (cả phần chưa đạt).

**Bước kế:** thử `locate_files` trên repo riêng (đo khi model chưa từng thấy code); đọc thêm comment + issue liên kết cho ticket mô tả ngắn (chỗ trượt lớn của Hive/Flink); pilot chỉ đọc ở công ty owner (cần owner duyệt).

---

## 2026-11-23 (5) · P2: đội = solo về chất lượng, worker rẻ hơn, chậm hơn ~14%

- **Chỉ dùng agy** (Codex/Claude CLI là tùy chọn khi người dùng tự liên kết tài khoản).
- Claude qua agy headless liên tục gọi `run_command` (bị chặn) → không làm worker được; Gemini Neon dùng đúng tool file → worker. Claude qua agy làm review ổn (15/15).
- **click solve, 16 issue, test ẩn, Docker:** solo Neon High 7/16 (0.438); đội 7/15 (dừng trước click-3637 vì máy thiếu RAM). Trên 15 cặp: **cùng kết quả từng issue**; đội dùng worker Neon Medium/Flash, trung bình 485 s so với 427 s.
- Kết quả: `evals/results/click-solve-solo-vs-crew-2026-11-23.json`.
- Kết luận P2: chưa thắng về tỉ lệ giải; lợi thế đo được là chạy bằng tầng model rẻ hơn với cùng chất lượng. Chia nhiều task không xảy ra (lead luôn chọn 1 task cho issue cỡ này).

**Bước kế:** chạy nốt click-3637 cho đội (`uv run crewline eval solve --repo click --mode crew`, tự tiếp tục); đo token để chốt "rẻ hơn"; sau đó P4 (MCP server + đóng gói định vị, phần đã đạt).

---

## 2026-11-22 (4) · P1 xong; P2 bị chặn vì hết quota; P3 chưa có lợi ích đo được

- **P1 (xong, đạt):** rerank 60 ứng viên bằng Neon, r@10 eval: Kafka 0.799, HBase 0.882, Flink 0.704, Hive 0.654 → trung bình có trọng số **0.735** trên 710 ticket (mục tiêu 0.70).
- **P2:**
  - Đội agent chạy trọn vòng lần đầu trên repo này (lead Claude → worker Codex → review Claude, cổng xanh) và đã merge (`crewline eval rerank`).
  - Bộ chấm solve (`evals/solve.py`): 16 issue click sau 07/2026, test ẩn, Docker `--network none`, đã cài click trong container, image có `less`; cổng xanh trên bản gốc của cả 16; chấm bản sửa thật ra resolved.
  - Lượt so solo/đội **không dùng được**: Claude chạm giới hạn 5 giờ (mở lại 23:30 22/11), **Codex hết hạn mức tới 22/12/2026** ("Upgrade to Plus"). Mỗi lượt worker Codex đọc ~450–500k token.
  - Đã sửa: CLI hết quota ghi vào `ledger/quota_blocked.json` và bị router bỏ qua cho tới hạn; worker chuyển sang CLI kế tiếp khi gặp quota thay vì tính là thất bại.
- **P3:** 803 bài học. Đo review 60 comment: lượt 1 không nhớ 0.517 / nhét prompt 0.383; lượt 2 không nhớ 0.467 / nhét prompt 0.483 / cộng thêm 0.467. → Nhiễu giữa hai lượt (~5 điểm) lớn hơn hiệu ứng; **chưa có lợi ích đo được**. Kiểu cộng thêm không gây hại.

**Bước kế (cần owner quyết):** chạy so solo/đội chỉ bằng agy (Gemini + Claude qua agy), tuần tự, ít song song; hoặc chờ quota.

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
