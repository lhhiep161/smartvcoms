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
| 3 | Tách quyền manual action/manual override | MEDIUM/HIGH | TODO | Chưa thực hiện. Cần cân nhắc thiết kế permission trước khi sửa vì ảnh hưởng quyền ghi dữ liệu. |
| 4 | Sửa audit/snapshot manual action để undo chính xác | MEDIUM | TODO | Chưa thực hiện. |
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

Kết luận hiện tại:

```text
Bước 1 đạt về mặt mã nguồn và kiểm thử kỹ thuật cơ bản.
```

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

#### Frontend composable

File:

```text
frontend/src/modules/smart-vcoms/composables/useSmartVCOMS.js
```

Đã thêm:

```text
loadLookupConfig()
```

Hàm này gọi:

```text
GET /api/vcoms/lookup/config
```

và ghi dữ liệu vào `adminConfig` dùng chung cho UI.

#### SmartVCOMSPage

File:

```text
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
```

Đã đổi luồng load:

```text
- Nếu user có quyền Bàn điều phối / Thống kê / Quản trị: gọi loadLookupConfig().
- Nếu user có quyền Quản trị: vẫn gọi loadRules() khi cần.
- Khi vào tab Quản trị: gọi loadAdminConfig() như cũ để lấy cấu hình quản trị.
- Khi vào tab Rule Engine: dùng lookup config nếu chưa có cb_config.
```

#### TabStatistics

File:

```text
frontend/src/modules/smart-vcoms/components/TabStatistics.vue
```

Đã đổi từ:

```text
loadAdminConfig()
```

sang:

```text
loadLookupConfig()
```

để user có quyền Thống kê nhưng không có quyền Quản trị vẫn có thể tải danh sách phòng.

### Commit liên quan

```text
75466e3 feat: add read-only SmartVCOMS lookup config API
0ab616e feat: load SmartVCOMS lookup config for non-admin views
ba3d486 feat: use lookup config on SmartVCOMS non-admin tabs
df6912d feat: use lookup config in statistics tab
```

### Kết quả Codex đã báo cáo

```text
- git pull OK.
- Rà soát diff OK.
- GET /api/vcoms/lookup/config đã tồn tại.
- Endpoint lookup/config cho phép user có view của ban_dieu_phoi / thong_ke / quan_tri_he_thong.
- GET /api/vcoms/admin/config vẫn yêu cầu quan_tri_he_thong.
- Frontend đã thêm loadLookupConfig().
- SmartVCOMSPage.vue đã dùng loadLookupConfig() cho non-admin views.
- TabStatistics.vue không còn gọi loadAdminConfig().
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

Các điểm chưa xác nhận trực tiếp:

```text
- User chỉ có quyền thong_ke có dropdown phòng.
- User chỉ có quyền ban_dieu_phoi thấy officer status.
- Admin vẫn vào Quản trị / Rule Engine bằng browser thật.
```

Kết luận hiện tại:

```text
Bước 2 đạt về mặt code + compile/build + smoke test chưa đăng nhập.
Có thể chuyển sang Bước 3, nhưng Bước 3 cần cẩn trọng vì ảnh hưởng permission ghi dữ liệu.
```

---

## 3. Bước 3 - Tách quyền thao tác thủ công khỏi quyền view Quản trị

Trạng thái: `TODO`  
Mức độ: `MEDIUM/HIGH`  
Ưu tiên: `3`

Các endpoint thao tác thủ công hiện vẫn đang dùng quyền view của `quan_tri_he_thong`:

```text
POST /api/vcoms/manual-action
DELETE /api/vcoms/manual-action/{case_key}
POST /api/vcoms/manual-override
DELETE /api/vcoms/manual-override/{case_key}/{field_name}
```

Hướng xử lý dự kiến:

```text
- Tạo permission action riêng: manual_action / manual_override hoặc edit_case.
- Backend assert quyền mới.
- Frontend ẩn/hiện nút thao tác theo quyền mới.
```

Lưu ý trước khi thực hiện:

```text
- Cần đọc kỹ cơ chế permission hiện tại.
- Không nên tự ý thêm schema mới nếu permission engine hiện tại đã hỗ trợ action `edit`.
- Cần đảm bảo admin hiện tại không bị mất quyền thao tác.
```

---

## 4. Bước 4 - Sửa audit/snapshot manual action để undo chính xác

Trạng thái: `TODO`  
Mức độ: `MEDIUM`  
Ưu tiên: `4`

Cần lưu snapshot đầy đủ trước khi manual action để undo trả đúng trạng thái cũ.

Các field dự kiến cần lưu:

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
[ ] Backend compile OK.
[ ] Frontend build OK.
[ ] Backend chạy OK.
[ ] /api/health OK.
[ ] /smart-vcoms OK.
[ ] /api/vcoms/lookup/config đúng quyền.
[ ] /api/vcoms/admin/config vẫn chỉ admin truy cập được.
[ ] Bàn điều phối hiển thị KPI/cán bộ đúng với user có quyền.
[ ] Tab Thống kê có dropdown phòng với user có quyền thống kê.
[ ] Tab Quản trị admin hoạt động.
[ ] Rule Engine admin hoạt động.
[ ] Không có database is locked trong smoke test.
[ ] Không có lỗi build do Vue template/script.
```
