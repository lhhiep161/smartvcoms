# SmartVCOMS - Kế hoạch chỉnh sửa sau rà soát end-to-end

Ngày lập: 05/06/2026  
Cập nhật gần nhất: 05/06/2026  
Phạm vi: SmartVCOMS trong repository `lhhiep161/smartvcoms`

Tài liệu này dùng để quản lý các chỉnh sửa sau khi rà soát luồng end-to-end SmartVCOMS. Mục tiêu là xử lý từng bước, hạn chế thay đổi lan rộng và dễ kiểm thử.

---

## 0. Trạng thái tổng hợp

| Bước | Nhóm việc | Mức độ | Trạng thái | Ghi chú |
|---:|---|---|---|---|
| 1 | Chuẩn hóa SQLite connection | HIGH | DONE / LOCAL TEST PASSED | Đã thêm helper `connect_vcoms_sqlite()` và thay các service chính sang dùng helper. Codex đã compile/build/smoke test helper thành công trên Mac/Linux. Chưa test watcher Outlook thật do cần Windows + Outlook Classic + pywin32. |
| 2 | Tách API read-only cho room/officer status | HIGH | DONE / LOCAL TEST PASSED | Đã thêm `GET /api/vcoms/lookup/config`, frontend non-admin dùng `loadLookupConfig()` thay vì phụ thuộc `/admin/config`. Codex đã compile/build/backend/smoke test 401 chưa đăng nhập thành công. Chưa test từng nhóm quyền sau đăng nhập do môi trường CLI không có session/browser. |
| 3 | Chuẩn hóa quyền view tab Quản trị SmartVCOMS | MEDIUM/HIGH | DONE / LOCAL TEST PASSED | Đã bỏ hardcode LĐP HTTD / Trưởng phòng HTTD / DTLY khỏi quyền Quản trị SmartVCOMS. Từ nay chỉ `isAdmin` có quyền đương nhiên; user khác phải được cấp grant `SmartVCOMS.quan_tri_he_thong` trên Portal Admin. |
| 3A | Dọn runtime/cache artifact khỏi Git | MEDIUM | DONE / REPO CLEANED | Đã thêm `.gitignore`, bỏ tracking `__pycache__`, `*.pyc`, `runtime_data`, `*.db`, `*.sqlite`, `*.sqlite3`. Giữ `frontend/dist` trong Git do mô hình triển khai hiện tại cần dist có sẵn trên máy chủ không có Node.js. |
| 4 | Sửa audit/snapshot manual action để undo chính xác | MEDIUM | IMPLEMENTED / LOCAL TEST PASSED | Snapshot manual action đã lưu bằng JSON chuẩn, undo hỗ trợ cả JSON mới và audit cũ dạng `str(dict)`. Codex đã compile backend, test SQLite tạm cho `MANUAL_DONE`, `MANUAL_WAIT_DISBURSE`, audit cũ và schema thiếu cột optional, đồng thời smoke test backend `/api/health` + `/smart-vcoms` thành công. |
| 5 | Tách thời điểm web refresh và thời điểm dữ liệu sync thực tế | MEDIUM | TODO | Chưa thực hiện. |
| 6 | Chuẩn hóa business date / ngày vận hành | MEDIUM | TODO | Chưa thực hiện. |
| 7 | Cleanup helper/CSS/import | LOW | TODO | Thực hiện sau cùng. |

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

### Kết quả Codex đã báo cáo

```text
- git pull OK.
- python -m compileall backend OK.
- cd frontend && npm run build OK.
- Backend chạy được bằng python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000.
- /api/health trả 200 OK.
- /smart-vcoms trả 200 OK.
- Không có lỗi import.
- Không thấy lỗi database is locked trong smoke test.
- Smoke test helper xác nhận journal_mode=wal, busy_timeout=10000, foreign_keys=1.
```

### Giới hạn kiểm thử

Codex đang chạy trên môi trường không có Windows + Outlook Classic + pywin32 nên watcher thật fail ở bước Outlook COM reader. Vì vậy chưa xác nhận được end-to-end watcher thật với dữ liệu Outlook thực tế.

---

## 2. Bước 2 - Tách API read-only cho room/officer status

Trạng thái: `DONE / LOCAL TEST PASSED`  
Mức độ: `HIGH`  
Ưu tiên: `2`

### Vấn đề

Tab Thống kê cần danh sách phòng để hiển thị dropdown phòng ban. Khu vực KPI/cán bộ ở Bàn điều phối cũng cần trạng thái cán bộ Ready/Off/Biztrip.

Trước khi chỉnh, frontend dùng:

```text
GET /api/vcoms/admin/config
```

Endpoint này yêu cầu quyền `quan_tri_he_thong`, dẫn tới rủi ro:

```text
- User chỉ có quyền Thống kê có thể không thấy danh sách phòng.
- User chỉ có quyền Bàn điều phối có thể không thấy đủ trạng thái cán bộ.
- UI nghiệp vụ bị phụ thuộc quyền Quản trị không cần thiết.
```

### Đã thực hiện

#### Backend

File:

```text
backend/modules/smartvcoms/router.py
```

Đã thêm endpoint read-only:

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

Endpoint này gọi lại `load_admin_config()` để trả dữ liệu read-only phục vụ UI:

```text
cb_config
ld_config
sla_config
room_config
```

Lưu ý: các endpoint update cấu hình vẫn giữ nguyên quyền `quan_tri_he_thong`.

#### Frontend

Đã thêm `loadLookupConfig()` trong:

```text
frontend/src/modules/smart-vcoms/composables/useSmartVCOMS.js
```

và đổi các nơi non-admin cần dữ liệu lookup sang dùng endpoint read-only, gồm:

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

### Kết quả Codex đã báo cáo

```text
- python -m compileall backend OK.
- cd frontend && npm run build OK.
- Backend chạy OK bằng python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000.
- /api/health trả 200 OK.
- /smart-vcoms trả 200 OK.
- GET /api/vcoms/lookup/config khi chưa đăng nhập trả 401 đúng kỳ vọng.
- GET /api/vcoms/admin/config khi chưa đăng nhập trả 401 đúng kỳ vọng.
```

### Giới hạn kiểm thử

Codex chưa kiểm tra trực tiếp theo từng nhóm user sau đăng nhập vì môi trường CLI không có browser/session auth tương tác.

---

## 3. Bước 3 - Chuẩn hóa quyền view tab Quản trị SmartVCOMS

Trạng thái: `DONE / LOCAL TEST PASSED`  
Mức độ: `MEDIUM/HIGH`  
Ưu tiên: `3`

### Mục tiêu

Giữ nguyên việc manual action/manual override đi theo quyền view tab Quản trị SmartVCOMS, nhưng bỏ hardcode LĐP HTTD / Trưởng phòng HTTD / DTLY khỏi rule mặc định.

### Quy tắc mới

Từ nay quyền:

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

Nếu muốn cấp quyền cho LĐP HTTD / Trưởng phòng HTTD / DTLY hoặc bất kỳ user nào khác, phải thêm grant trong Portal Admin:

```text
username = user cần cấp quyền
section_key = SmartVCOMS.quan_tri_he_thong
can_view = 1
is_active = 1
```

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

Đã kiểm tra trực tiếp code trên `origin/main`:

```text
- portal_permission_engine.py có SMARTVCOMS_ADMIN_GRANT_SECTION = "SmartVCOMS.quan_tri_he_thong".
- can() rẽ riêng khi page_id == "SmartVCOMS" và part_id == "quan_tri_he_thong".
- _smartvcoms_admin_allows() chỉ cho isAdmin hoặc named grant SmartVCOMS.quan_tri_he_thong.
- PortalAdminRole level 1 chỉ tự động cấp quyền PortalAdmin, không tự động cấp SmartVCOMS Quản trị.
- _smartvcoms_admin_rule() mặc định chỉ còn isAdmin.
- seed page_permissions.json chỉ còn isAdmin cho parts.quan_tri_he_thong.view.
- PortalAdminPage.vue có thêm option grant SmartVCOMS.quan_tri_he_thong.
```

Codex đã báo cáo test giả lập:

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

### Manual action/manual override

Manual action/manual override **vẫn** dùng đúng quyền view của tab Quản trị SmartVCOMS, không tách thành quyền riêng:

```text
POST /api/vcoms/manual-action
DELETE /api/vcoms/manual-action/{case_key}
POST /api/vcoms/manual-override
DELETE /api/vcoms/manual-override/{case_key}/{field_name}
```

Các endpoint này vẫn check:

```text
SmartVCOMS / quan_tri_he_thong / view
```

---

## 3A. Dọn repo runtime/cache artifact trước khi sang bước tiếp theo

Trạng thái: `DONE / REPO CLEANED`  
Mức độ: `MEDIUM`  
Ưu tiên: `3A`

### Lý do

Repo trước đó đã tracking một số file runtime/cache/build trung gian, gồm `__pycache__`, `*.pyc`, `runtime_data`, `*.db`. Các file này không nên version control vì dễ gây conflict, phình repo và có thể chứa dữ liệu runtime/test.

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

Đã bỏ tracking các nhóm file:

```text
backend/**/__pycache__/*.pyc
runtime_data/.DS_Store
runtime_data/portal/portal.db
runtime_data/smartvcoms/vcoms.db
```

### Quyết định về frontend/dist

Giữ `frontend/dist` trong Git ở giai đoạn hiện tại.

Lý do:

```text
- backend/main.py đang serve frontend trực tiếp từ frontend/dist.
- launchers/start_smartvcoms.bat chỉ chạy backend và Outlook watcher, không chạy npm build.
- start_frontend.bat ghi rõ frontend đã được build sẵn và serve trực tiếp từ backend.
- Máy chủ triển khai thực tế dự kiến không có Node.js.
```

Vì vậy repo hiện tại là source repo kiêm gói triển khai nội bộ. Khi sửa frontend source, cần build ở máy dev có Node.js rồi commit cả source frontend và `frontend/dist`.

### Commit liên quan

```text
27faf2b chore: ignore runtime and cache artifacts
```

### Kết quả kiểm tra

```text
- python -m compileall backend OK.
- git ls-files không còn match __pycache__ / *.pyc / runtime_data / *.db / *.sqlite / *.sqlite3.
- frontend/dist vẫn được giữ tracking.
- Không thay đổi logic backend/frontend.
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
- MANUAL_ACTION_SNAPSHOT_FIELDS
- apply_manual_action() đọc snapshot đầy đủ trước khi update
- old_value / new_value audit ghi bằng JSON chuẩn
- remove_manual_action() parse JSON mới bằng json.loads
- fallback audit cũ bằng ast.literal_eval cho dạng str(dict)
- chỉ restore các cột thực sự tồn tại trong vcoms_case_state
```

Backward-compatible vẫn giữ:

```text
- Audit cũ chỉ có current_stage_code vẫn undo được
- current_stage_label được fallback theo mapping stage cũ
- current_status = OPEN
- completion_type = ""
- is_open = 1
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
- Test SQLite tạm cho MANUAL_DONE OK:
  apply -> DONE/CLOSED/is_open=0, audit old_value là JSON parse được.
  undo  -> restore đúng WAIT_SIGN, current_status, completion_type,
           is_open, completed_time/manual_completed_time/manual_finish_time,
           sign_time, updated_at, updated_by.

- Test SQLite tạm cho MANUAL_WAIT_DISBURSE OK:
  apply -> WAIT_DISBURSE / OPEN / is_open=1.
  undo  -> restore đúng PROCESSING / Đang xử lý / OPEN / completion_type=""
           / is_open=1 / updated_by gốc.

- Test backward-compatible audit cũ OK:
  old_value = \"{'current_stage_code': 'PROCESSING'}\"
  remove_manual_action() không lỗi và restore đúng:
  current_stage_code=PROCESSING, current_stage_label=Đang xử lý,
  current_status=OPEN, completion_type=\"\", is_open=1.

- Test schema thiếu cột optional OK:
  Bảng thiếu sign_time/disbursed_time vẫn apply/undo thành công,
  không phát sinh SQL error khi snapshot chứa field không tồn tại.

- Smoke backend OK:
  GET /api/health -> 200
  GET /smart-vcoms -> 200
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
Sẽ được ghi bằng commit docs sau khi cập nhật tài liệu này.
```

---

## 5. Bước 5 - Tách thời điểm web refresh và thời điểm dữ liệu sync thực tế

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên: `5`

Hiện `lastUpdate` là thời điểm frontend gọi API thành công, chưa phải thời điểm Outlook watcher sync dữ liệu thật.

Hướng xử lý dự kiến:

```text
/api/vcoms/cases trả thêm meta:
- web_generated_at
- last_sync_at
- last_sync_status
- last_sync_message
```

Frontend hiển thị rõ:

```text
Web: HH:MM:SS
Dữ liệu: HH:MM:SS SUCCESS/WARN/FAILED
```

---

## 6. Bước 6 - Chuẩn hóa business date / ngày vận hành

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên: `6`

Hiện Kanban/Statistics lọc hôm nay theo ngày server. Cần chuẩn hóa helper `operational_date`/`business_date`, trước mắt trả meta để dễ debug. Nếu cần sau này mới thêm selector ngày cho Bàn điều phối.

---

## 7. Bước 7 - Cleanup helper/CSS/import

Trạng thái: `TODO`  
Mức độ: `LOW/CLEANUP`  
Ưu tiên: `7`

Thực hiện cuối cùng:

```text
- Gom helper backend trùng lặp.
- Dọn import không dùng.
- Dọn CSS/class không dùng sau nhiều vòng chỉnh UI.
- Không đổi output API.
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
```
