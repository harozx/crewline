# Crewline: kế hoạch chi tiết

## Mục tiêu
Từ một ticket, Crewline gom đủ ngữ cảnh (ticket, ảnh, file đính kèm, Confluence, code, lịch sử PR, trí nhớ team),
chỉ ra **sửa ở đâu**, rồi điều một đội CLI agent trên máy (Claude Code, Codex, agy) làm ra **PR qua test và
review chéo**, chờ người duyệt.

### Thước đo (đo bằng số, không bằng cảm giác)
| Chỉ số | Cách đo | Mục tiêu v1 |
|---|---|---|
| Định vị file | recall@5, recall@10 file trong PR thật | recall@10 ≥ 0.70 |
| Giải ticket | test xanh trên tập ticket có test | đội > 1 agent đơn |
| Chi phí | token + giây mỗi ticket, theo tầng | giảm khi dùng phân tầng |
| Trí nhớ | lỗi reviewer từng bắt mà agent lặp lại | có trí nhớ < không có |

## Định vị (ADR-0002)
Không đánh vào chỗ đã có người lớn chiếm (Copilot/Rovo cho Jira Cloud, các bảng điều phối agent).
Crewline là **lớp ngữ cảnh + định vị + trí nhớ có đo đạc**, cắm vào agent nào cũng được qua MCP, ưu tiên
**Jira Data Center / chạy tại chỗ**, đọc cả ảnh/đính kèm, và công bố **benchmark định vị trên Jira** đầu tiên.

## Nguyên tắc
1. Đo trước, xây sau: mỗi giai đoạn có mốc so sánh và điều kiện qua.
2. Việc nhẹ cho model nhẹ, việc nặng cho model thinking (bảng tầng ở `AGENTS.md`).
3. Chỉ đọc hệ thống công ty; ghi ngược là tính năng phải bật riêng.
4. Trí nhớ thừa hưởng quyền của nguồn (GitHub role, Confluence space, Jira security level).
5. Bộ kiểm tra chỉ dùng ticket tạo sau 2026-07-01 để tránh model đã học thuộc lời giải.

## Kiến trúc
```
sources/  jira (Cloud + DC, REST v2), github (code, PR, review, CODEOWNERS, team), confluence, sessions
reader/   ticket → brief: ADF/wiki → markdown, ảnh nhúng + đính kèm, link Confluence/Figma, comment mới nhất
index/    ticket↔commit↔PR, symbol (tree-sitter), stack trace → file, BM25 + embedding
locate/   xếp hạng repo/file nghi vấn kèm bằng chứng
memory/   mẩu nhớ gắn file/service, nguồn, ACL, phát hiện nhớ cũ
crew/     adapter CLI, router theo tầng + quota, lead/worker/reviewer, worktree, cổng test
mcp/      server MCP: get_brief, locate, recall, run_crew
evals/    dataset + chấm điểm: locate, solve, solo vs crew, memory on/off
```
Dữ liệu và cache ở `D:/crewline-data`, không vào repo.

## Các giai đoạn

### P0 · Dữ liệu và mốc (tuần 1)
- [x] Repo, quy ước, skill, template, CI.
- [x] Adapter CLI (claude, agy, codex) + bảng tầng + ledger.
- [x] Dataset Kafka: ticket Fixed tạo ≥ 2026-07-01, nối commit qua `KAFKA-xxxx`, danh sách file sửa (bỏ file test để chấm riêng).
- [x] Baseline định vị: BM25 trên đường dẫn + tên symbol; ticket cũ tương tự → file đã sửa.
- [x] `crewline eval locate` ra recall@k, lưu `evals/results/*.json`.
- **Qua khi:** dataset ≥ 150 ticket, baseline có số, chạy lại bằng một lệnh.

### P1 · Đọc ticket + định vị (tuần 2–3)
- Mở rộng benchmark sang 3–5 dự án Apache (Flink, Cassandra, HBase, Hadoop...) để số đo không phụ thuộc một repo.
- Reader: ADF và wiki markup → markdown, tải ảnh/đính kèm có xác thực, docx/xlsx/pdf → markdown, giữ chỗ ảnh trong văn bản.
- Định vị v1: parse stack trace/log, bản đồ lịch sử (ticket tương tự → file), symbol khớp từ khóa, embedding (tầng light).
- Re-rank top 30 bằng model tầng medium/heavy đọc brief + đoạn code.
- **Qua khi:** recall@10 tăng rõ so với baseline (mục tiêu ≥ 0.70).

### P2 · Đội agent (tuần 3–5)
- Lead (heavy) đọc brief → kế hoạch JSON: các task với phạm vi file, tầng, phụ thuộc.
- Worker mỗi task một git worktree; reviewer khác nhà cung cấp; cổng = build + test liên quan.
- Router: tầng thấp trước, leo thang sau 2 lần fail; theo dõi quota, chuyển nhà cung cấp khi bị giới hạn.
- Eval trên tập ticket Kafka có test nhanh: **1 agent vs đội**, tỉ lệ giải, token, thời gian.
- **Qua khi:** đội thắng agent đơn, hoặc biết rõ thua ở đâu và vì sao (ghi ADR).

### P3 · Trí nhớ team (tuần 5–6)
- Đào review PR → mẩu nhớ gắn file; postmortem, Confluence theo link.
- Hook cuối phiên Claude/Codex trích bài học, dev duyệt rồi mới chia sẻ.
- ACL theo nguồn, truy vấn bằng token người dùng; đánh dấu nhớ cũ khi code đổi.
- Eval memory on/off: agent có tránh được lỗi reviewer từng bắt không.

### P4 · Pilot + phát hành (tuần 7–8)
- Pilot chỉ đọc ở công ty owner (cần owner duyệt: đây là việc phải báo).
- [x] MCP server (`crewline mcp`: ticket_brief, locate_files, team_memory).
- [x] `crewline calibrate`: hiệu chỉnh theo lịch sử của từng repo.
- [x] Bản đồ codebase trên repo nhỏ (click): không lợi (+24% thời gian) → tắt mặc định.
- [x] Bản đồ codebase trên repo lớn (Kafka): cùng recall, +40% token → tắt. ở 60 ticket: `locate`+rerank 0.811 ≈ agent tự mò 0.804, ít token hơn ~3.6x (con số 20 ticket là may).
- [ ] Xác nhận `locate` vs agent tự mò trên mẫu lớn hơn (Kafka + Flink).
- [ ] Tài liệu, README tiếng Việt, công bố benchmark.
- [ ] Mở public (cần owner duyệt).

### Sau P4 · Đóng gói và hiệu năng (chỉ khi cần)
- Giữ Python cho lõi và bộ đo: >95% thời gian là chờ model (gộp tín hiệu ~0.5 s/ticket; rerank 30–60 s; worker 6–10 phút).
- Bước rẻ trước: thay `rank_bm25` bằng thư viện có lõi native (`bm25s` hoặc tantivy-py) khi repo > ~50k file.
- Chỉ khi phân phối public cần một file thực thi duy nhất, hoặc repo cực lớn: viết lại **lõi chỉ mục** bằng Rust
  (git history, tree-sitter, tantivy), gọi từ Python qua PyO3; điều phối agent và bộ đo vẫn là Python.
- Thêm bộ trích symbol cho TS/JS, Go, C# theo repo mục tiêu (ngôn ngữ công cụ ≠ ngôn ngữ repo).

## Bản đồ: việc kế
- **Nhiều repo một dự án:** workspace liệt kê các repo, module đặt tên `repo/module`. Liên kết giữa các repo lấy từ:
  cùng mã ticket trong commit của nhiều repo, thư viện nội bộ dùng chung (pom.xml/package.json), và
  proto/OpenAPI/topic dùng chung. Mỗi ticket rơi vào repo nào thì hiện ở repo đó.
- Kiểm chứng điểm ưu tiên trên lịch sử: ticket điểm cao có thật sự được làm sớm, hay gây nhiều bug, hơn không?
- Pilot trên Jira công ty: chỉ đọc, owner tự đặt token, cần owner đồng ý.

## Rủi ro
| Rủi ro | Xử lý |
|---|---|
| Model đã học thuộc Kafka | chỉ ticket ≥ 2026-07-01; thêm repo nhỏ làm bộ phụ |
| Test Kafka nặng | chỉ module test nhanh; bộ phụ Python |
| Đội agent không đáng tiền | lead chỉ chia khi song song có lợi; benchmark trả lời |
| Dữ liệu công ty | chỉ đọc, token cá nhân, che dữ liệu cá nhân, không lưu transcript |
| Quota subscription | router theo dõi giới hạn, giảm tầng hoặc chờ |
| Codex `gpt-5.6-sol` không chạy với tài khoản ChatGPT | dùng `gpt-5.6-terra` / `gpt-5.6-luna` |
