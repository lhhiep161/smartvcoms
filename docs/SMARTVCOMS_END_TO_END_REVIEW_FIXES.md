# SmartVCOMS - Kế hoạch chỉnh sửa sau rà soát end-to-end

Ngày lập: 05/06/2026  
Cập nhật gần nhất: 05/06/2026  
Phạm vi: SmartVCOMS trong repository `lhhiep161/smartvcoms`

Tài liệu này dùng để quản lý các chỉnh sửa sau khi rà soát luồng end-to-end SmartVCOMS. Mục tiêu là xử lý từng bước, hạn chế thay đổi lan rộng và dễ kiểm thử.

---

## 0. Trạng thái tổng hợp

| Bước | Nhóm việc | Mức độ | Trạng thái | Ghi chú |
|---:|---|---|---|---|
| 1 | Chuẩn hóa SQLite connection | HIGH | DONE / LOCAL TEST PASSED | Đã thêm helper `connect_vcoms_sqlite()` và thay các service chính sang dùng helper. Chưa test watcher Outlook thật do cần Windows + Outlook Classic + pywin32. |
| 2 | Tách API read-only cho room/officer status | HIGH | DONE / LOCAL TEST PASSED | Đã thêm `GET /api/vcoms/lookup/config`, frontend non-admin dùng `loadLookupConfig()` thay vì phụ thuộc `/admin/config`. |
| 3 | Chuẩn hóa quyền view tab Quản trị SmartVCOMS | MEDIUM/HIGH | DONE / LOCAL TEST PASSED | Chỉ `isAdmin` có quyền đương nhiên; user khác phải được cấp grant `SmartVCOMS.quan_tri_he_thong` trên Portal Admin. |
| 3A | Dọn runtime/cache artifact khỏi Git | MEDIUM | DONE / REPO CLEANED | Đã thêm `.gitignore`, bỏ tracking `__pycache__`, `*.pyc`, `runtime_data`, `*.db`, `*.sqlite`, `*.sqlite3`. Giữ `frontend/dist` trong Git do mô hình triển khai hiện tại cần dist có sẵn trên máy chủ không có Node.js. |
| 4 | Sửa audit/snapshot manual action để undo chính xác | MEDIUM | IMPLEMENTED / LOCAL TEST PASSED | Snapshot manual action đã lưu bằng JSON chuẩn, undo hỗ trợ cả JSON mới và audit cũ dạng `str(dict)`. Codex đã compile backend, test SQLite tạm cho `MANUAL_DONE`, `MANUAL_WAIT_DISBURSE`, audit cũ và schema thiếu cột optional, đồng thời smoke test backend `/api/health` + `/smart-vcoms` thành công. |
| 5 | Tách thời điểm web refresh và thời điểm dữ liệu sync thực tế | MEDIUM | DEFERRED / SKIPPED FOR NOW | Bước này chủ yếu làm rõ hiển thị, không ảnh hưởng luồng xử lý SmartVCOMS. Tạm bỏ qua ở vòng hiện tại, không xóa khỏi backlog. |
| 6 | Chuẩn hóa business date / ngày vận hành | MEDIUM | DEFERRED / SKIPPED FOR NOW | Hệ thống hiện vẫn vận hành bình thường nếu ngày/giờ máy chủ đúng. Tạm bỏ qua ở vòng hiện tại, không xóa khỏi backlog; sẽ xem xét sau khi có nhu cầu chạy lại dữ liệu theo ngày, debug ngày cũ hoặc chuẩn hóa ngày vận hành riêng. |
| 7 | Cleanup helper/CSS/import | LOW | DEFERRED / SKIPPED FOR NOW | Đây là cleanup nợ kỹ thuật, không ảnh hưởng nghiệp vụ hiện tại. Tạm bỏ qua để tránh rủi ro cleanup quá tay trước khi chạy thật; giữ trong backlog để xử lý sau khi hệ thống ổn định. |

---

## 1. Bước 1 - Chuẩn hóa SQLite connection cho SmartVCOMS

Trạng thái: `DONE / LOCAL TEST PASSED`  
Mức độ: `HIGH`  
Ưu tiên: `1`

### Mục tiêu

Giảm rủi ro `database is locked` khi backend đọc dữ liệu SmartVCOMS song song với Outlook watcher đang ghi/rebuild SQLite.

### Đã thực hiện

Thêm helper trong:

```text
backend/modules/smartvcoms/utils.py
```

Helper:

```text
connect_vcoms_sqlite()
```

Cấu hình connection:

```text
timeout=10.0
PRAGMA journal_mode=WAL
PRAGMA synchronous=NORMAL
PRAGMA busy_timeout=10000
PRAGMA foreign_keys=ON
```

Các file đã chuyển sang dùng helper:

```text
backend/modules/smartvcoms/utils.py
backend/modules/smartvcoms/services/kanban_service.py
backend/modules/smartvcoms/services/stats_service.py
backend/modules/smartvcoms/services/admin_service.py
backend/modules/smartvcoms/services/actions_service.py
```

### Commit liên quan

```text
ccfe371 fix: standardize SmartVCOMS sqlite connection helper
a0a0d05 fix: use SmartVCOMS sqlite helper in actions service
2fc263f fix: use SmartVCOMS sqlite helper in stats service
698b989 fix: use SmartVCOMS sqlite helper in admin service
cd03326 fix: use SmartVCOMS sqlite helper in kanban service
```

### Kết quả kiểm thử

```text
- python -m compileall backend OK.
- cd frontend && npm run build OK.
- Backend chạy được bằng python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000.
- /api/health trả 200 OK.
- /smart-vcoms trả 200 OK.
- Smoke test helper xác nhận journal_mode=wal, busy_timeout=10000, foreign_keys=1.
```

### Giới hạn kiểm thử

Codex đang chạy trên môi trường không có Windows + Outlook Classic + pywin32 nên watcher thật chưa được xác nhận end-to-end với dữ liệu Outlook thực tế.

---

## 2. Bước 2 - Tách API read-only cho room/officer status

Trạng thái: `DONE / LOCAL TEST PASSED`  
Mức độ: `HIGH`  
Ưu tiên: `2`

### Vấn đề

Tab Thống kê cần danh sách phòng để hiển thị dropdown phòng ban. Khu vực KPI/cán bộ ở Bàn điều phối cũng cần trạng thái cán bộ Ready/Off/Biztrip. Trước khi chỉnh, frontend dùng `GET /api/vcoms/admin/config`, khiến UI nghiệp vụ bị phụ thuộc quyền Quản trị không cần thiết.

### Đã thực hiện

Backend thêm endpoint read-only:

```text
GET /api/vcoms/lookup/config
```

Quyền đọc lookup config:

```text
Cho phép nếu user có ít nhất 1 quyền view trong các part:
- ban_dieu_phoi
- thong_ke
- quan_tri_he_thong
```

Frontend thêm `loadLookupConfig()` trong:

```text
frontend/src/modules/smart-vcoms/composables/useSmartVCOMS.js
```

và đổi các nơi non-admin cần dữ liệu lookup sang dùng endpoint read-only:

```text
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
frontend/src/modules/smart-vcoms/components/TabStatistics.vue
```

### Commit liên quan

```text
75466e3 feat: add read-only SmartVCOMS lookup config API
0ab616e feat: load SmartVCOMS lookup config for non-admin views
ba3d486 feat: use lookup config on SmartVCOMS non-admin tabs
df6912d feat: use lookup config in statistics tab
```

### Kết quả kiểm thử

```text
- python -m compileall backend OK.
- cd frontend && npm run build OK.
- Backend chạy OK.
- /api/health trả 200 OK.
- /smart-vcoms trả 200 OK.
- GET /api/vcoms/lookup/config khi chưa đăng nhập trả 401 đúng kỳ vọng.
- GET /api/vcoms/admin/config khi chưa đăng nhập trả 401 đúng kỳ vọng.
```

---

## 3. Bước 3 - Chuẩn hóa quyền view tab Quản trị SmartVCOMS

Trạng thái: `DONE / LOCAL TEST PASSED`  
Mức độ: `MEDIUM/HIGH`  
Ưu tiên: `3`

### Quy tắc mới

Quyền:

```text
SmartVCOMS / quan_tri_he_thong / view
```

được xác định như sau:

```text
- isAdmin = True  -> có quyền đương nhiên.
- user khác       -> chỉ có quyền nếu được cấp Portal Admin grant:
  section_key = SmartVCOMS.quan_tri_he_thong
  can_view = 1
  is_active = 1
```

### Đã thực hiện

Đã bỏ khỏi rule mặc định:

```text
- {"flags": ["isLanhDaoPhong"], "rooms": ["18"]}
- {"flags": ["isTruongPhong"], "rooms": ["18"]}
- {"users": ["DTLY"]}
```

Nếu muốn cấp quyền cho LĐP HTTD / Trưởng phòng HTTD / DTLY hoặc bất kỳ user nào khác, phải thêm grant trong Portal Admin.

### File đã sửa

```text
backend/core/portal_permission_engine.py
backend/core/portal_permissions.py
package_config/seed/page_permissions.json
frontend/src/modules/portal-admin/pages/PortalAdminPage.vue
docs/SMARTVCOMS_END_TO_END_REVIEW_FIXES.md
```

### Commit liên quan

```text
9d3439e Chuan hoa quyen tab quan tri SmartVCOMS
```

### Kết quả kiểm tra

```text
Admin -> True
LĐP HTTD chưa grant -> False
Trưởng phòng HTTD chưa grant -> False
DTLY chưa grant -> False
User thường có grant SmartVCOMS.quan_tri_he_thong + can_view=1 -> True
grant can_view=0 -> False
grant inactive -> False
PortalAdminRole level 1 vẫn vào PortalAdmin overview được nhưng không tự động có SmartVCOMS.quan_tri_he_thong
```

Manual action/manual override vẫn dùng đúng quyền view của tab Quản trị SmartVCOMS, không tách thành quyền riêng.

---

## 3A. Dọn repo runtime/cache artifact trước khi sang bước tiếp theo

Trạng thái: `DONE / REPO CLEANED`  
Mức độ: `MEDIUM`  
Ưu tiên: `3A`

### Đã thực hiện

Đã thêm `.gitignore` với các rule chính:

```text
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
venv/
env/
.DS_Store
runtime_data/
*.db
*.sqlite
*.sqlite3
frontend/node_modules/
```

Đã bỏ tracking:

```text
backend/**/__pycache__/*.pyc
runtime_data/.DS_Store
runtime_data/portal/portal.db
runtime_data/smartvcoms/vcoms.db
```

Giữ `frontend/dist` trong Git ở giai đoạn hiện tại vì backend đang serve trực tiếp từ `frontend/dist`, launcher không chạy npm build và máy chủ triển khai dự kiến không có Node.js. Khi sửa frontend source, cần build ở máy dev có Node.js rồi commit cả source frontend và `frontend/dist`.

### Commit liên quan

```text
27faf2b chore: ignore runtime and cache artifacts
```

---

## 4. Bước 4 - Sửa audit/snapshot manual action để undo chính xác

Trạng thái: `IMPLEMENTED / LOCAL TEST PASSED`  
Mức độ: `MEDIUM`  
Ưu tiên: `4`

### File đã sửa

```text
backend/modules/smartvcoms/services/actions_service.py
```

### Đã thực hiện

Trong commit code gốc:

```text
82fe8e83da49b99f2baf2c065935e07461852c41
fix: store full SmartVCOMS manual action snapshots
```

Đã bổ sung:

```text
- MANUAL_ACTION_SNAPSHOT_FIELDS.
- apply_manual_action() đọc snapshot đầy đủ trước khi update.
- old_value / new_value audit ghi bằng JSON chuẩn.
- remove_manual_action() parse JSON mới bằng json.loads.
- fallback audit cũ bằng ast.literal_eval cho dạng str(dict).
- chỉ restore các cột thực sự tồn tại trong vcoms_case_state.
```

Backward-compatible vẫn giữ:

```text
- Audit cũ chỉ có current_stage_code vẫn undo được.
- current_stage_label được fallback theo mapping stage cũ.
- current_status = OPEN.
- completion_type = "".
- is_open = 1.
```

### Snapshot mới dùng JSON chuẩn

Các field snapshot chính:

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

### Kết quả test local của Codex

```text
- python -m compileall backend OK.
- Test SQLite tạm cho MANUAL_DONE OK.
- Test SQLite tạm cho MANUAL_WAIT_DISBURSE OK.
- Test backward-compatible audit cũ OK.
- Test schema thiếu cột optional OK.
- Smoke backend OK: GET /api/health -> 200, GET /smart-vcoms -> 200.
```

### Phạm vi không đổi

```text
- Không đổi permission.
- Không đổi router/API contract.
- Không đổi Kanban.
- Không đổi SLA.
- Không đổi statistics.
- Không đổi frontend.
- Không đổi manual override cb_httd ngoài phần import/helper phục vụ service hiện có.
```

### Commit docs/test sau kiểm thử

```text
6889b03490c94c6c2c0f43830de02f88e83c87e3
docs: mark SmartVCOMS manual action snapshot fix tested
```

### Commit sửa tài liệu sau kiểm tra

```text
1ab62726eef9330c4ce4ebd7117e51a399c49ac3
docs: record SmartVCOMS manual action test commit
```

---

## 5. Bước 5 - Tách thời điểm web refresh và thời điểm dữ liệu sync thực tế

Trạng thái: `DEFERRED / SKIPPED FOR NOW`  
Mức độ: `MEDIUM`  
Ưu tiên: `5`

### Ghi chú bỏ qua ở vòng hiện tại

Bước này chủ yếu làm rõ hiển thị/truyền thông trạng thái dữ liệu, không thay đổi luồng xử lý chính của SmartVCOMS. Tạm thời bỏ qua Bước 5 trong vòng xử lý hiện tại, không xóa khỏi backlog. Có thể quay lại sau nếu cần tăng tính minh bạch trạng thái dữ liệu cho người dùng.

### Hướng xử lý khi quay lại sau

Nếu thực hiện sau này, backend `/api/vcoms/cases` có thể trả thêm meta:

```text
meta: {
  web_generated_at,
  last_sync_at,
  last_sync_status,
  last_sync_message
}
```

Frontend hiển thị tách bạch:

```text
Web: HH:MM:SS
Dữ liệu: HH:MM:SS SUCCESS/WARN/FAILED
```

Nguồn dữ liệu sync ưu tiên:

```text
outlook_reader_state
outlook_reader_runs
```

---

## 6. Bước 6 - Chuẩn hóa business date / ngày vận hành

Trạng thái: `DEFERRED / SKIPPED FOR NOW`  
Mức độ: `MEDIUM`  
Ưu tiên: `6`

### Ghi chú bỏ qua ở vòng hiện tại

Bước này có liên quan đến cách xác định "hôm nay/ngày vận hành" cho Kanban và Statistics, nhưng hiện tại hệ thống vẫn vận hành bình thường nếu ngày/giờ máy chủ đúng.

Hiện Kanban và Statistics đang dùng ngày server tại thời điểm gọi API:

```text
operational_date = datetime.now().date()
```

Không chỉnh Bước 6 ở vòng hiện tại không ảnh hưởng ngay đến:

```text
- Cách đọc Outlook.
- Cách rebuild vcoms_case_state.
- Cách phân loại hồ sơ.
- Cách tính SLA.
- Cách lọc Kanban trong điều kiện vận hành bình thường.
- Cách phân quyền.
- Manual action/manual override.
```

Tạm thời bỏ qua Bước 6 trong vòng xử lý hiện tại, không xóa khỏi backlog. Sẽ xem xét xử lý sau khi có nhu cầu:

```text
- chạy lại dữ liệu theo ngày,
- debug/đối soát dữ liệu ngày cũ,
- hoặc chuẩn hóa ngày vận hành riêng khác ngày hệ thống.
```

### Hướng xử lý khi quay lại sau

```text
- Thêm helper get_operational_date() hoặc resolve_operational_date().
- Mặc định vẫn trả datetime.now().date() để không đổi hành vi hiện tại.
- Kanban dùng helper thay vì gọi trực tiếp datetime.now().date().
- Statistics mode=today dùng cùng helper.
- Có thể thêm env var debug SMARTVCOMS_OPERATIONAL_DATE=YYYY-MM-DD nếu thật sự cần.
```

---

## 7. Bước 7 - Cleanup helper/CSS/import

Trạng thái: `DEFERRED / SKIPPED FOR NOW`  
Mức độ: `LOW/CLEANUP`  
Ưu tiên: `7`

### Ghi chú bỏ qua ở vòng hiện tại

Bước này chỉ là cleanup nợ kỹ thuật:

```text
- Gom helper backend trùng lặp.
- Dọn import không dùng.
- Dọn CSS/class không dùng sau nhiều vòng chỉnh UI.
```

Không thực hiện Bước 7 không ảnh hưởng đến nghiệp vụ/vận hành hiện tại. Ngược lại, cleanup quá tay trước khi chạy thật có thể tạo rủi ro làm lệch UI hoặc thay đổi hành vi ngoài ý muốn.

Vì vậy, tạm thời bỏ qua Bước 7 trong vòng xử lý hiện tại, không xóa khỏi backlog. Sẽ xem xét sau khi hệ thống đã chạy ổn trên máy thật hoặc khi có thời gian test kỹ.

### Hướng xử lý khi quay lại sau

```text
- Chỉ dọn import không dùng.
- Chỉ gom helper nếu trùng lặp rõ ràng và có test.
- Không đổi output API.
- Không đổi CSS/layout SmartVCOMS nếu không có ảnh chụp kiểm chứng trước/sau.
- Không đổi permission/SLA/Kanban/manual action/statistics.
```

---

## 8. Checklist nghiệm thu chung

```text
[x] Backend compile OK ở các bước đã hoàn tất.
[x] Frontend build OK ở các bước đã hoàn tất.
[x] Backend chạy OK ở smoke test các bước đã hoàn tất.
[x] /api/health OK ở smoke test các bước đã hoàn tất.
[x] /smart-vcoms OK ở smoke test các bước đã hoàn tất.
[x] /api/vcoms/lookup/config đã có endpoint read-only và trả 401 khi chưa đăng nhập.
[x] /api/vcoms/admin/config vẫn yêu cầu quyền quan_tri_he_thong và trả 401 khi chưa đăng nhập.
[ ] Bàn điều phối hiển thị KPI/cán bộ đúng với user có quyền trên browser thật.
[ ] Tab Thống kê có dropdown phòng với user có quyền thống kê trên browser thật.
[ ] Tab Quản trị admin hoạt động trên browser thật.
[ ] Rule Engine admin hoạt động trên browser thật.
[x] Quyền thao tác thủ công đi đúng theo quyền view tab Quản trị SmartVCOMS.
[x] Runtime/cache artifact đã được bỏ tracking khỏi Git.
[x] frontend/dist được giữ trong Git theo mô hình triển khai hiện tại.
[x] Không có database is locked trong smoke test helper.
[x] Không có lỗi build do Vue template/script ở các bước đã hoàn tất.
[-] Bước 5 tạm bỏ qua, giữ trong backlog để xem xét sau.
[-] Bước 6 tạm bỏ qua, giữ trong backlog để xem xét sau.
[-] Bước 7 tạm bỏ qua, giữ trong backlog để xem xét sau.
[ ] Kiểm thử end-to-end trên máy thật Windows + Outlook + dữ liệu thực tế.
```
