# SmartVCOMS - Kế hoạch chỉnh sửa sau rà soát end-to-end

Ngày lập: 05/06/2026  
Phạm vi: SmartVCOMS trong repository `lhhiep161/smartvcoms`  
Mục tiêu: ghi nhận các vấn đề phát hiện sau khi rà soát luồng end-to-end, sau đó thực hiện từng bước theo mức độ ưu tiên.

Tài liệu này chỉ dùng để quản lý các chỉnh sửa tiếp theo. Không tự ý mở rộng sang module khác nếu không cần thiết.

---

## 0. Tóm tắt kết luận rà soát

Luồng chính hiện tại đã tương đối rõ và có thể chạy thử:

```text
start_smartvcoms.bat
-> FastAPI backend
-> Outlook watcher
-> đọc email VCOMS hôm nay
-> ghi SQLite
-> xử lý raw email
-> rebuild vcoms_case_state
-> /api/vcoms/cases
-> useSmartVCOMS.loadCases()
-> SmartVCOMSPage.vue
-> Kanban / KPI / Thống kê
```

Các vấn đề ưu tiên cần xử lý trước khi vận hành ổn định nhiều người:

```text
1. Chuẩn hóa SQLite connection để giảm rủi ro database is locked.
2. Tách API read-only cho phòng ban/cán bộ để tab Bàn điều phối và Thống kê không phụ thuộc quyền Quản trị.
3. Tách quyền thao tác thủ công khỏi quyền view Quản trị.
4. Sửa audit/snapshot của manual action để undo khôi phục đúng trạng thái cũ.
5. Trả thêm thời điểm đồng bộ dữ liệu thực tế, không chỉ thời điểm web fetch thành công.
6. Chuẩn hóa business date / ngày vận hành nếu cần xử lý dữ liệu ngoài ngày hiện tại.
7. Gom các helper trùng lặp và dọn cleanup UI/CSS sau các lần chỉnh giao diện.
```

---

## 1. Chuẩn hóa SQLite connection cho SmartVCOMS

Trạng thái: `TODO`  
Mức độ: `HIGH`  
Ưu tiên thực hiện: `1`

### Vấn đề

Một số nơi đã dùng helper `connect_sqlite()` với WAL, `busy_timeout`, `synchronous=NORMAL`, nhưng nhiều service vẫn mở SQLite trực tiếp bằng `sqlite3.connect(VCOMS_DB_PATH)`.

Khi hệ thống chạy thật, frontend đang refresh Kanban thường xuyên, trong khi Outlook watcher cũng ghi/rebuild SQLite định kỳ. Việc mở connection không đồng nhất có thể làm tăng rủi ro:

```text
- database is locked
- API cases/statistics/admin config trả lỗi ngắt quãng
- watcher rebuild chậm hoặc fail khi web đang đọc nhiều
```

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/store/sqlite_store.py
backend/modules/smartvcoms/services/kanban_service.py
backend/modules/smartvcoms/services/stats_service.py
backend/modules/smartvcoms/services/admin_service.py
backend/modules/smartvcoms/services/actions_service.py
backend/modules/smartvcoms/utils.py
```

### Hướng xử lý đề xuất

```text
- Tạo hoặc tái sử dụng helper connect_sqlite() cho toàn bộ SmartVCOMS service.
- Đảm bảo mọi connection dùng:
  - timeout phù hợp
  - PRAGMA journal_mode=WAL
  - PRAGMA synchronous=NORMAL
  - PRAGMA busy_timeout
  - row_factory nếu cần
- Không đổi schema, không đổi logic nghiệp vụ.
- Chỉ thay cách mở/đóng connection.
```

### Kiểm tra sau sửa

```text
python -m compileall backend
Chạy backend + watcher
Mở SmartVCOMS tab Bàn điều phối
Theo dõi API /api/vcoms/cases khi watcher rebuild
Không xuất hiện database is locked
```

---

## 2. Tách API read-only cho room/officer status

Trạng thái: `TODO`  
Mức độ: `HIGH`  
Ưu tiên thực hiện: `2`

### Vấn đề

Tab Thống kê cần danh sách phòng để hiển thị dropdown phòng ban. Khu vực KPI/cán bộ ở Bàn điều phối cũng cần trạng thái cán bộ Ready/Off/Biztrip.

Hiện frontend đang lấy các dữ liệu này thông qua `loadAdminConfig()` / `/api/vcoms/admin/config`, nhưng endpoint này yêu cầu quyền `quan_tri_he_thong`. Như vậy user chỉ có quyền Bàn điều phối hoặc Thống kê nhưng không có quyền Quản trị có thể gặp các vấn đề:

```text
- Dropdown phòng ở tab Thống kê rỗng.
- Khu vực trạng thái cán bộ không đủ danh sách/cấu hình.
- UI nghiệp vụ bị phụ thuộc quyền Quản trị không cần thiết.
```

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/router.py
backend/modules/smartvcoms/services/admin_service.py
frontend/src/modules/smart-vcoms/composables/useSmartVCOMS.js
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
frontend/src/modules/smart-vcoms/components/TabStatistics.vue
```

### Hướng xử lý đề xuất

Tạo API read-only riêng, ví dụ:

```text
GET /api/vcoms/lookup/config
```

hoặc tách nhỏ:

```text
GET /api/vcoms/rooms
GET /api/vcoms/officers/status
```

Quyền truy cập:

```text
- Người có quyền xem Bàn điều phối được đọc officer status/rooms.
- Người có quyền xem Thống kê được đọc rooms.
- Không cần quyền Quản trị để đọc dữ liệu phục vụ hiển thị.
- Chỉ endpoint update config mới cần quyền Quản trị.
```

### Kiểm tra sau sửa

```text
- User chỉ có quyền Thống kê vẫn thấy dropdown phòng.
- User chỉ có quyền Bàn điều phối vẫn thấy trạng thái cán bộ.
- User không có quyền Quản trị không gọi được API update config.
- Tab Quản trị vẫn hoạt động như cũ.
```

---

## 3. Tách quyền thao tác thủ công khỏi quyền view Quản trị

Trạng thái: `TODO`  
Mức độ: `MEDIUM/HIGH`  
Ưu tiên thực hiện: `3`

### Vấn đề

Các endpoint thao tác thủ công hiện đang check quyền view của `quan_tri_he_thong`. Đây là thao tác ghi dữ liệu, không nên dùng chung với quyền xem.

Các thao tác liên quan:

```text
POST /api/vcoms/manual-action
DELETE /api/vcoms/manual-action/{case_key}
POST /api/vcoms/manual-override
DELETE /api/vcoms/manual-override/{case_key}/{field_name}
```

Rủi ro:

```text
- Người có quyền view Quản trị có thể thao tác ghi nếu không được kiểm soát riêng.
- Khó phân quyền riêng cho nhóm vận hành chỉ được manual action nhưng không được sửa cấu hình.
```

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/router.py
backend/core/portal_permission_engine.py
runtime_data/portal/portal.db hoặc seed permission nếu có
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
```

### Hướng xử lý đề xuất

```text
- Bổ sung permission action riêng, ví dụ:
  - manual_action
  - manual_override
  - edit_case
- Backend assert_permission theo action mới thay vì view của quan_tri_he_thong.
- Frontend chỉ hiện nút thao tác thủ công nếu user có quyền tương ứng.
- Không đổi logic manual action ở bước này nếu không cần.
```

### Kiểm tra sau sửa

```text
- User chỉ có quyền view không thao tác thủ công được.
- User được cấp quyền manual_action thao tác được.
- User admin vẫn thao tác được.
- UI ẩn/hiện nút đúng quyền.
```

---

## 4. Sửa audit/snapshot manual action để undo chính xác

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên thực hiện: `4`

### Vấn đề

Khi apply manual action, hệ thống chưa lưu đủ snapshot trạng thái cũ. Trong khi undo lại cố khôi phục nhiều field hơn. Điều này có thể làm undo không trả hồ sơ về đúng trạng thái trước manual action trong một số tình huống.

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/services/actions_service.py
backend/modules/smartvcoms/pipeline/state_machine.py
backend/modules/smartvcoms/store/sqlite_store.py
```

### Hướng xử lý đề xuất

Khi apply manual action, lưu snapshot đầy đủ vào `vcoms_case_audit.old_value`:

```text
current_stage_code
current_stage_label
current_status
completion_type
is_open
completed_time
manual_completed_time
manual_finish_time
sign_time
disbursed_time
updated_at
updated_by
```

Khi undo:

```text
- Đọc snapshot mới nhất.
- Khôi phục các field có trong snapshot.
- Deactivate manual action.
- Ghi audit undo nếu cần.
```

### Kiểm tra sau sửa

```text
- Manual chuyển WAIT_DISBURSE rồi undo: về đúng trạng thái cũ.
- Manual DONE rồi undo: không còn CLOSED nếu trước đó hồ sơ chưa closed.
- Rebuild watcher sau undo không tự áp lại manual action đã inactive.
- Không mất dữ liệu note/audit.
```

---

## 5. Tách thời điểm web refresh và thời điểm dữ liệu sync thực tế

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên thực hiện: `5`

### Vấn đề

`lastUpdate` hiện là thời điểm frontend gọi API thành công, không phải thời điểm Outlook watcher sync dữ liệu mới nhất.

Người dùng có thể hiểu nhầm:

```text
Cập nhật: 09:15:20
```

là dữ liệu Outlook vừa đồng bộ lúc 09:15:20, trong khi thực tế chỉ là web vừa fetch lại API.

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/services/kanban_service.py
backend/modules/smartvcoms/store/outlook_store.py
frontend/src/modules/smart-vcoms/composables/useSmartVCOMS.js
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
```

### Hướng xử lý đề xuất

Backend `/api/vcoms/cases` trả thêm metadata:

```json
{
  "status": "success",
  "data": [],
  "meta": {
    "web_generated_at": "...",
    "last_sync_at": "...",
    "last_sync_status": "SUCCESS",
    "last_sync_message": "..."
  }
}
```

Frontend hiển thị rõ hơn:

```text
Web: 09:15:20
Dữ liệu: 09:15:05 SUCCESS
```

### Kiểm tra sau sửa

```text
- Khi web refresh mỗi giây, Web time thay đổi.
- Khi watcher chưa sync mới, Data sync time không đổi.
- Nếu watcher lỗi, UI có cảnh báo nhẹ.
```

---

## 6. Chuẩn hóa business date / ngày vận hành

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên thực hiện: `6`

### Vấn đề

Kanban và Thống kê đang lọc dữ liệu hôm nay theo ngày hiện tại của server. Điều này phù hợp vận hành bình thường, nhưng có rủi ro trong các tình huống:

```text
- Chạy kiểm tra sau 0h nhưng còn hồ sơ ngày trước.
- Dữ liệu Outlook có received_time lệch format/ngày.
- Máy chủ sai ngày giờ.
- Cần xem lại dữ liệu ngày trước trên Bàn điều phối.
```

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/services/kanban_service.py
backend/modules/smartvcoms/services/stats_service.py
backend/modules/smartvcoms/pipeline/state_machine.py
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
```

### Hướng xử lý đề xuất

Giai đoạn 1, chưa cần làm UI chọn ngày cho Bàn điều phối nếu chưa cần. Trước mắt:

```text
- Gom helper resolve_record_date/business_date dùng chung.
- Backend trả meta operational_date.
- Log rõ khi không có hồ sơ của ngày hiện tại.
```

Giai đoạn 2 nếu cần:

```text
- Cho phép query /api/vcoms/cases?date=YYYY-MM-DD.
- UI Bàn điều phối có selector ngày nhỏ, mặc định hôm nay.
```

### Kiểm tra sau sửa

```text
- Dữ liệu hôm nay vẫn hiển thị như cũ.
- API không bị lẫn ngày hôm trước.
- Có thể debug rõ operational_date.
```

---

## 7. Cleanup helper trùng lặp và CSS/UI còn chồng chéo

Trạng thái: `TODO`  
Mức độ: `LOW/CLEANUP`  
Ưu tiên thực hiện: `7`

### Vấn đề

Một số helper đang bị lặp giữa nhiều service:

```text
_get_record_date
_shorten_room
_load_room_display_map
_load_sla_cfg_map
```

Ngoài ra, sau nhiều vòng chỉnh UI, có thể còn:

```text
- class CSS không dùng
- inline style cũ
- import asset logo không còn dùng
- style chồng chéo giữa SmartVCOMSPage.vue và TabStatistics.vue
```

### File cần rà soát/chỉnh

```text
backend/modules/smartvcoms/services/kanban_service.py
backend/modules/smartvcoms/services/stats_service.py
backend/modules/smartvcoms/services/admin_service.py
backend/modules/smartvcoms/utils.py
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
frontend/src/modules/smart-vcoms/components/TabStatistics.vue
frontend/src/app/AppShell.vue
frontend/src/assets/style.css
```

### Hướng xử lý đề xuất

```text
- Gom helper backend trùng lặp vào utils hoặc module common riêng.
- Không đổi output API.
- Dọn import không dùng.
- Dọn CSS class không còn được dùng.
- Hạn chế chỉnh lại UI nếu không có lỗi.
```

### Kiểm tra sau sửa

```text
cd frontend && npm run build
python -m compileall backend
Mở lại Bàn điều phối / Thống kê / Quản trị / Rule Engine
Không vỡ UI
Không đổi dữ liệu hiển thị
```

---

## 8. Thứ tự triển khai đề xuất

```text
Bước 1: Chuẩn hóa SQLite connection.
Bước 2: Tách API read-only cho room/officer status.
Bước 3: Tách quyền manual action/manual override.
Bước 4: Sửa snapshot undo manual action.
Bước 5: Bổ sung metadata last_sync_at cho /api/vcoms/cases.
Bước 6: Chuẩn hóa operational_date/business_date.
Bước 7: Cleanup helper/CSS/import.
```

Không nên làm tất cả trong một lần để tránh khó kiểm thử. Mỗi bước nên có commit riêng.

---

## 9. Checklist nghiệm thu chung sau khi hoàn tất

```text
[ ] Backend khởi động được.
[ ] Frontend build thành công.
[ ] Outlook watcher chạy được.
[ ] /api/health thành công.
[ ] /api/vcoms/cases trả dữ liệu hôm nay.
[ ] /api/vcoms/statistics?mode=today trả dữ liệu.
[ ] Bàn điều phối hiển thị đủ 4 nhóm Kanban.
[ ] Tab Thống kê có dropdown phòng và segmented control hoạt động.
[ ] User không có quyền Quản trị vẫn xem được dữ liệu cần thiết nếu được cấp quyền Bàn điều phối/Thống kê.
[ ] Manual action đúng quyền.
[ ] Undo manual action trả đúng trạng thái cũ.
[ ] Không còn database is locked khi watcher chạy song song với web.
[ ] Không có horizontal scroll do UI.
[ ] Sidebar mở/thu gọn không làm vỡ SmartVCOMS.
```
