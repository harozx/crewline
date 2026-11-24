# Hướng dẫn sử dụng Crewline

Crewline chạy hoàn toàn trên máy bạn, chỉ **đọc** Jira/GitHub, không bao giờ ghi ngược lên. Có ba cách dùng:

1. **Bản đồ thay đổi** (một file HTML): xem việc nào rơi vào đâu, lan tới đâu, ai đang làm gì, việc nào làm trước.
2. **MCP** cho agent (Claude Code, Codex, Cursor…): agent hỏi Crewline "ticket này sửa ở file nào" trước khi tự đọc code.
3. **Crew**: các CLI agent trên máy (agy, tùy chọn claude/codex) chia việc: lead lập kế hoạch, worker viết code, reviewer khác hãng kiểm tra.

## 1. Cài đặt

Cần Python 3.11 và [uv](https://docs.astral.sh/uv/), git, và repo code của bạn đã clone về máy.

```
git clone <repo crewline> && cd crewline
uv sync
```

Biến môi trường (tự đặt trong shell của bạn, Crewline không lưu token):

| Biến | Ý nghĩa |
|---|---|
| `JIRA_URL` | ví dụ `https://jira.congty.vn` |
| `JIRA_TOKEN` | Jira Data Center: Personal Access Token. Jira Cloud: API token, kèm `JIRA_USER` = email |
| `CREWLINE_DATA` | thư mục cache, chỉ mục, bản đồ (mặc định trong thư mục người dùng) |
| `CREWLINE_CLIS` | CLI agent Crewline được phép chạy, mặc định `agy`. Thêm `claude,codex` nếu bạn có tài khoản riêng |

## 2. Thiết lập cho một repo (một lệnh)

```
uv run crewline setup --repo D:/code/du-an --jira %JIRA_URL% ^
  --jql "project = ABC AND resolution = Unresolved ORDER BY priority DESC"
```

Lệnh này:

1. Đọc lịch sử ticket đã sửa (khóa `ABC-123` trong commit), lấy nội dung ticket từ Jira.
2. **Tự đo** trên chính repo của bạn: với ticket cũ, Crewline có đoán đúng file cần sửa không (recall@10), và bật hoặc tắt từng tín hiệu theo kết quả. Con số này nói bạn nên tin Crewline tới đâu trên repo này.
3. Dựng chỉ mục và bản đồ `<CREWLINE_DATA>/maps/<repo>.html`.
4. In cấu hình MCP để dán vào agent.

Chỉ dựng lại bản đồ (ví dụ mỗi sáng):

```
uv run crewline map --repo D:/code/du-an --jira %JIRA_URL% --jql "project = ABC AND resolution = Unresolved"
```

Lần đầu mất vài phút (Kafka 60 ticket khoảng 5 phút). Những lần sau nhanh hơn vì cấu trúc repo và embedding ticket được cache.

## 3. Đọc bản đồ

Mở file HTML bằng trình duyệt. Sau khi dựng lại, nhấn **Ctrl+F5** để không xem bản cũ trong cache.

**Thanh trên:** số việc đang mở, số việc quá hạn hoặc sắp hạn, số cặp việc sửa cùng file, và việc nên làm trước.

**Cột trái: các tab**

| Tab | Dùng để |
|---|---|
| Việc cần làm | Ticket xếp theo điểm ưu tiên 0–100. Lọc: Bug, Có hạn, Có va chạm, **Chưa giao**, **Người làm chưa từng sửa vùng này** |
| Epic / task cha | Mỗi epic: các task con, module bị đụng, task con gấp nhất, va chạm với việc ngoài epic |
| Người làm | Mỗi assignee: số việc, điểm, số việc quá hạn, và **bao nhiêu việc nằm đúng vùng code họ từng sửa**. Bấm vào một người để lọc việc của họ |
| Đâm nhau | Cặp ticket sửa cùng file. Cặp cùng task cha được đánh dấu riêng, không báo động |
| Module | Các module của repo: người nắm code, bus factor, điểm nóng |

**Nhãn người làm trên mỗi ticket:**
- `✓ Tên` (xanh lá): trong một năm qua, người được giao đã **viết hoặc review** chính các file này, hoặc đã sửa module này ít nhất 3 lần. Review được lấy từ dòng `Reviewers:` trong commit.
- `~ Tên` (xanh dương): họ từng đụng module này hoặc module bên cạnh, nhưng ít.
- `? Tên` (cam): chưa thấy họ đụng vùng này. Có thể là người mới đang làm quen, hoặc giao nhầm. Nên hỏi thêm những người trong ô "Người nắm phần code này".
- `chưa giao ai`: ticket chưa có assignee.

Đây là gợi ý từ git, **không phải đánh giá người**. Tên Jira và tên git được so khớp dù khác dấu, gạch nối hay thứ tự. Tên viết bằng chữ khác (ví dụ tên Hàn) có thể không khớp. Commit sửa hàng loạt (trên 100 file, như thêm license hoặc annotation) không được tính là "đã sửa code".

**Bên phải: hai góc nhìn**
- **Đồ thị:** module là vòng tròn. To = nhiều ticket, đỏ = nhiều bug. Bấm một ticket thì module nó rơi vào sáng đỏ, vùng bị lan sáng cam, và chỉ hiện đường nối liên quan. **Bấm lại lần nữa, hoặc bấm vào chỗ trống, để bỏ chọn.**
- **Sơ đồ logic:** đọc từ trái sang phải. Ticket → module và file cần sửa → vùng lan ảnh hưởng (kèm lý do). Với module: được dùng bởi → module → phụ thuộc vào → hay sửa cùng. Với epic: epic → task con → module → vùng lan.

**Chi tiết ticket:** lý do của điểm ưu tiên, file có khả năng phải sửa (kèm số file import nó, số commit một năm), người nắm code, task cha và anh em, việc đâm cùng file, ticket cũ tương tự, và **ghi chú Jira** dạng wiki markup có nút sao chép. Crewline không tự đăng ghi chú này lên Jira.

**Link thẳng:** `du-an.html#ABC-123` mở một ticket, `#ABC-123/logic` mở sơ đồ logic của nó, `#module:core` mở một module. Có thể dán link này vào Jira hoặc Slack.

**Điểm ưu tiên** = 40% Jira (priority, bug, đang chặn việc khác, release) + 40% code (lan rộng bao nhiêu, module nhiều bug không, đâm cùng file) + 20% thời gian (hạn, ngày release, lâu không ai đụng). Con số chưa được kiểm chứng với kết quả thực tế: hãy đọc lý do, đừng chỉ nhìn số.

## 4. Dùng qua MCP

```
claude mcp add crewline -- uv --directory /duong-dan/toi/crewline run crewline mcp
codex mcp add crewline -- uv --directory /duong-dan/toi/crewline run crewline mcp
```

| Tool | Trả về |
|---|---|
| `ticket_brief(key)` | Ticket Jira dạng markdown, ảnh được mô tả tại chỗ |
| `locate_files(ticket, repo)` | File có khả năng phải sửa, kèm bằng chứng |
| `triage_ticket(ticket, repo)` | Module nào, file nào mở trước, CODEOWNERS. Không tốn token |
| `ticket_impact(ticket, repo)` | Ticket rơi vào đâu, lan tới đâu, vì sao |
| `rank_tickets(repo, jql)` | Danh sách ưu tiên và các va chạm |
| `team_memory(paths)` | Bài học từ review cũ của các file đó (tùy chọn, chưa đo được lợi ích) |

Ví dụ câu hỏi cho agent: *"Dùng crewline ticket_impact cho ABC-123 rồi sửa nó."*

## 5. Crew (agent chia việc)

```
uv run crewline crew solve --repo D:/code/du-an --gate "mvn -q test" --impact "nội dung ticket…"
```

Lead lập kế hoạch, mỗi worker làm trong git worktree riêng, cổng kiểm tra (`--gate`) phải qua, reviewer khác hãng duyệt, rồi tích hợp bằng cherry-pick. Crew **không push và không tạo PR**: bạn xem kết quả rồi tự quyết định.

## 6. Dự án nhiều repo

Hiện mỗi bản đồ ứng với một repo. Với một dự án Jira trải trên nhiều repo, hãy dựng một bản đồ cho mỗi repo, cùng một JQL. Mỗi ticket sẽ hiện ở repo mà nó rơi vào. Bản đồ gộp nhiều repo vào một trang đang nằm trong kế hoạch: module đặt tên theo dạng `repo/module`, và liên kết giữa các repo được suy ra từ cùng mã ticket trong commit, thư viện nội bộ dùng chung, và proto/API/topic dùng chung.

## 7. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Bản đồ trông như cũ | Nhấn Ctrl+F5 |
| 401/403 từ Jira | Kiểm tra `JIRA_TOKEN`. Cloud cần thêm `JIRA_USER` |
| Không có ticket lịch sử | Commit phải chứa mã ticket (`ABC-123`), hoặc dùng `--since` sớm hơn |
| Recall khi `setup` thấp | Ticket ít chữ hoặc tên trong code khác hẳn với mô tả. Dùng thêm agent re-rank, hoặc để agent tự khám phá code |
| CLI agent bị hết quota | Crewline tự bỏ qua CLI đó tới khi hết hạn (`ledger/quota_blocked.json`) |
