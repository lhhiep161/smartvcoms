# SmartVCOMS - Tổng hợp các điểm cần chỉnh sửa

Ngày lập: 04/06/2026  
Cập nhật gần nhất: 04/06/2026  
Phạm vi: SmartVCOMS trong repository `lhhiep161/smartvcoms`

Tài liệu này tổng hợp các nội dung cần chỉnh sửa đã chốt và trạng thái triển khai mới nhất. Mục tiêu là sửa đúng phạm vi yêu cầu, không mở rộng sang các logic nghiệp vụ khác nếu không cần thiết.

---

## 0. Trạng thái triển khai

| Nhóm việc | Trạng thái | Ghi chú |
|---|---:|---|
| Rule Engine - chọn Cán bộ trong bảng Assignment | DONE | Đã đổi sang select native, lưu ID_CB, bổ sung GET `/api/vcoms/admin/rules`. Khi test local nếu vẫn thấy UI cũ cần build/restart frontend/backend và hard refresh. |
| Tab Quản trị - tự load mặc định bảng Phân bổ SLA | DONE | Đã thêm `ensure_default_sla_config()`, tự ghi key thiếu vào SQLite, không overwrite giá trị cũ, bảng Phân bổ SLA đã có dữ liệu sau reload. |
| Chuẩn hóa ID_CB/Tên CB | DONE | Đã chuẩn hóa logic nội bộ dùng ID_CB, bỏ cộng trùng ID_CB + Tên cán bộ, assignment trả ID_CB, manual override lưu ID_CB, Kanban tách `cb_id` và tên hiển thị. |
| Đồng nhất `sla_minutes` và cấu hình thời gian làm việc/SLA | DONE | Đã có hàm tính calendar dùng chung, tách WORK/SLA calendar, fallback `sla_minutes` không còn tính raw `sla_deadline - arrival_time`, Kanban/Stats dùng calendar phù hợp. |
| Quy định lại `arrival_time` | DONE | `arrival_time` chỉ set khi hồ sơ chuyển `WAIT_ACCEPT` / `Chờ T.Nhận`; LC_REQUEST giữ logic cũ; backfill ARRIVAL chỉ relink event, không còn set `arrival_time`. |
| Giảm giãn cách dòng Bàn điều phối | TODO | Chỉ chỉnh CSS/density, không đổi logic dữ liệu. |
| Nghiệm thu tổng hợp | TODO | Chạy cuối cùng. |

---

## 1. Rule Engine - chọn Cán bộ trong bảng Assignment

Trạng thái: `DONE`

Đã xử lý:

```text
- Đổi custom dropdown Cán bộ sang select native.
- option value = ID_CB.
- label = ID_CB - Tên Cán bộ.
- Không lưu tên cán bộ vào rule.
- Bổ sung GET /api/vcoms/admin/rules.
- Sau khi lưu, tab Rule Engine có thể load lại rule đã lưu.
```

Lưu ý test local:

```text
- Nếu chạy Vite dev server: mở đúng http://localhost:5173 và hard refresh.
- Nếu xem bản build static qua backend: cần npm run build lại frontend, restart backend, rồi hard refresh.
```

---

## 2. Tab Quản trị - tự load mặc định bảng Phân bổ SLA

Trạng thái: `DONE`

Đã xử lý:

```text
- Thêm ensure_default_sla_config() để ghi key thiếu vào bảng sla_config trong SQLite.
- GET /api/vcoms/admin/config gọi ensure trước khi trả dữ liệu.
- Không overwrite giá trị cũ nếu DB đã có.
- Bảng Phân bổ SLA có empty-state nếu lỗi bất thường.
- Không thêm nút Thêm vì backend tự tạo đủ dòng mặc định.
```

Các key mặc định cần có:

```text
O1
O2
O3
O5
O6
LC_SLA
BL_SLA
DN_PREFIX
WORK_MORNING_START
WORK_MORNING_END
WORK_AFTERNOON_START
WORK_AFTERNOON_END
SLA_MORNING_START
SLA_MORNING_END
SLA_AFTERNOON_START
SLA_AFTERNOON_END
```

Giá trị giờ mặc định:

```text
*_MORNING_START = 08:00
*_MORNING_END = 12:00
*_AFTERNOON_START = 13:00
*_AFTERNOON_END = 19:30
```

---

## 3. Chuẩn hóa ID_CB và Tên CB

Trạng thái: `DONE`

Đã xử lý:

```text
- Tên CB đọc từ email được normalize sang ID_CB trước khi gán assigned_officer.
- assigned_officer lưu ID_CB.
- assign_officer() trả ID_CB, không trả tên CB.
- recalculate_config_load() hỗ trợ dashboard schema: CB HTTD + Thời gian SLA.
- recalculate_config_load() hỗ trợ internal schema: assigned_officer + sla_minutes.
- Officer column đều normalize qua _normalize_cb_id() rồi group theo ID_CB.
- update_last_assigned() match theo ID_CB.
- sync_config_cb_load_from_case_state() normalize dữ liệu cũ theo tên sang ID_CB nếu map chắc chắn, rồi chỉ group/tính theo ID_CB.
- admin_service.py tính Đang xử lý, Tổng phút SLA, Điểm Phân Giao chỉ theo ID_CB.
- manual override nhập tên hoặc ID đều normalize và lưu ID_CB vào assigned_officer.
- Kanban giữ cb_id = ID_CB, cb_httd là tên hiển thị nếu map được.
- Filter trạng thái Ready dùng strip + lower trong assign_officer() và _evaluate_assignment().
```

SQL/test nhanh:

```sql
SELECT assigned_officer, COUNT(*) AS so_hoso, COALESCE(SUM(sla_minutes), 0) AS tong_sla
FROM vcoms_case_state
WHERE business_date = date('now')
GROUP BY assigned_officer
ORDER BY assigned_officer;
```

```sql
SELECT id_cb, ten_can_bo, dang_xu_ly, tong_phut_sla, diem_phan_giao
FROM config_cb_full
ORDER BY id_cb;
```

```sql
SELECT s.assigned_officer, c.id_cb, c.ten_can_bo
FROM vcoms_case_state s
JOIN config_cb_full c
  ON UPPER(TRIM(s.assigned_officer)) = UPPER(TRIM(c.ten_can_bo))
WHERE s.business_date = date('now');
```

Kỳ vọng query cuối giảm về 0 hoặc chỉ còn các tên không map được.

---

## 4. Đồng nhất `sla_minutes` và cấu hình thời gian làm việc/SLA

Trạng thái: `DONE`

Đã xử lý trong commit:

```text
090020e fix: Đồng nhất sla_minutes + calendar cấu hình
```

### 4.1. Hàm dùng chung

Đã bổ sung trong:

```text
backend/modules/smartvcoms/utils.py
```

Các hàm chính:

```text
calc_calendar_elapsed_mins(...)
calc_real_elapsed_mins(...)
calc_sla_elapsed_mins(...)
calculate_sla_minutes_common(...)
```

Nguyên tắc:

```text
- calc_real_elapsed_mins() dùng WORK calendar.
- calc_sla_elapsed_mins() dùng SLA calendar.
- calculate_sla_minutes_common() dùng SLA calendar cho sla_minutes.
- LC/BL vẫn dùng LC_SLA/BL_SLA theo cấu hình.
- O1/O2 vẫn là cap SLA theo cấu hình.
```

### 4.2. Cấu hình calendar

Default:

```text
WORK: 08:00-12:00, 13:00-19:30
SLA : 08:00-12:00, 13:00-19:30
```

Key đọc từ `sla_config`:

```text
WORK_MORNING_START
WORK_MORNING_END
WORK_AFTERNOON_START
WORK_AFTERNOON_END
SLA_MORNING_START
SLA_MORNING_END
SLA_AFTERNOON_START
SLA_AFTERNOON_END
```

### 4.3. Deadline qua ngày

Quy tắc đã xử lý:

```text
Nếu sla_deadline.date > sla_start_date:
    effective_deadline_date = sla_start_date + 1 ngày
```

Giữ nguyên giờ/phút của `sla_deadline`. Không thêm xử lý ngày nghỉ/lễ.

### 4.4. Fallback `sla_minutes`

Đã sửa trong:

```text
backend/modules/smartvcoms/store/config_admin.py
```

Fallback khi `sla_minutes` thiếu đã gọi:

```text
calculate_sla_minutes_common(arrival_time, sla_deadline, flow_type, sla_cfg_map)
```

Không còn dùng công thức raw:

```text
(sla_deadline - arrival_time).total_seconds() / 60
```

### 4.5. Kanban và Stats

Đã xử lý:

```text
- Kanban dùng SLA calendar cho thời gian còn/vượt SLA.
- Kanban dùng WORK calendar cho thời gian chờ/trạng thái.
- Stats load sla_config và dùng WORK calendar cho thống kê thời gian giải ngân.
```

---

## 5. Quy định lại `arrival_time`

Trạng thái: `DONE`

Đã xử lý:

```text
- Thêm helper _set_wait_accept_arrival_time(...) trong state_machine.py.
- Chỉ set arrival_time khi hồ sơ thật sự chuyển sang WAIT_ACCEPT / Chờ T.Nhận.
- ARRIVAL đầu tiên của hồ sơ online chưa đủ điều kiện WAIT_ACCEPT thì arrival_time để rỗng.
- ARRIVAL thứ 2/gom nhóm đủ điều kiện chuyển WAIT_ACCEPT thì mới set arrival_time.
- Hồ sơ thường chuyển thẳng WAIT_ACCEPT thì set arrival_time tại thời điểm chuyển đó.
- LC_REQUEST giữ nguyên logic cũ: vẫn set arrival_time theo LC_REQUEST nếu chưa có.
- Khi tạo case mới, chỉ set arrival_time nếu stage_code == WAIT_ACCEPT hoặc event_type == LC_REQUEST.
- sqlite_reader.py map Hồ sơ đến = arrival_time, Thời gian nhận email = created_at.
- _backfill_missing_arrival_from_family(...) chỉ còn relink vcoms_email_events.case_key và cập nhật dedupe_reason, không còn set arrival_time hoặc arrival_event_count.
```

File đã sửa:

```text
backend/modules/smartvcoms/pipeline/state_machine.py
backend/modules/smartvcoms/store/sqlite_reader.py
```

Những nơi còn được phép set `arrival_time`:

```text
- _set_wait_accept_arrival_time(...) khi case chuyển WAIT_ACCEPT.
- Nhánh LC_REQUEST theo logic cũ.
- Khi tạo case mới nếu stage_code == WAIT_ACCEPT hoặc event_type == LC_REQUEST.
```

Test nhanh:

```text
Online ARRIVAL đầu tiên:
- case còn ở ARRIVAL
- arrival_time rỗng

Online ARRIVAL thứ 2:
- case chuyển WAIT_ACCEPT
- arrival_time = thời điểm email thứ 2 làm case chuyển WAIT_ACCEPT

Hồ sơ thường:
- ARRIVAL đầu tiên vào WAIT_ACCEPT
- arrival_time = thời điểm chuyển WAIT_ACCEPT

LC_REQUEST:
- arrival_time giữ nguyên như trước
```

Lưu ý restart:

```text
- Cần restart backend.
- Không cần restart frontend; chỉ refresh trang nếu đang mở UI.
```

---

## 6. Tối ưu hiển thị Bàn điều phối

Trạng thái: `TODO`

Chỉ chỉnh spacing/density hiển thị, không thay đổi logic:

```text
- lọc
- sort
- màu cảnh báo SLA
- thao tác click chi tiết hồ sơ
- dữ liệu hồ sơ
```

Gợi ý CSS:

```css
.main-table,
.sub-table {
  font-size: 13px;
}

.main-table th,
.sub-table th {
  padding: 4px 5px;
  font-size: 13px;
  line-height: 1.15;
}

.main-table td,
.sub-table td {
  padding: 4px 5px;
  line-height: 1.15;
}

.kb-header {
  font-size: 16px;
  margin-bottom: 4px;
}

.kb-title-sub {
  font-size: 13px;
  margin-top: 3px;
  margin-bottom: 4px;
  padding: 3px 8px;
}

.kanban-col {
  padding: 8px 10px;
}
```

---

## 7. Những gì không sửa ngoài phạm vi

```text
- Không thay đổi logic LC nếu code hiện tại không yêu cầu.
- Không thêm xử lý ngày nghỉ/lễ.
- Không thay đổi rule nghiệp vụ đóng/mở hồ sơ.
- Không thay đổi cách tách case nếu không liên quan ID_CB/SLA/arrival_time.
- Không thay đổi logic ACCEPTED ngoài việc normalize tên đọc được thành ID_CB.
- Không thay đổi giao diện Kanban ngoài phần hiển thị tên CB từ ID_CB nếu cần và giảm spacing dòng hồ sơ.
- Không thay đổi logic lọc/sort/màu SLA trên Bàn điều phối khi giảm giãn cách dòng.
```

---

## 8. Tiêu chí nghiệm thu tổng hợp

### Test 1: `arrival_time`

```text
DONE

Hồ sơ chưa chuyển Chờ T.Nhận:
arrival_time chưa được dùng làm mốc SLA mới.

Khi hồ sơ chuyển Chờ T.Nhận:
arrival_time = thời điểm chuyển Chờ T.Nhận.
```

### Test 2: `sla_minutes`

```text
DONE

Không có fallback nào tính sla_minutes bằng raw deadline - arrival_time.
Tất cả đều loại trừ thời gian nghỉ theo cấu hình.
```

### Test 3: cấu hình thời gian

```text
DONE

Thời gian làm việc và Thời gian tính SLA khác nhau thì:
- thời gian chờ/trạng thái dùng Thời gian làm việc
- SLA/phân giao dùng Thời gian tính SLA
```

### Test 4: deadline qua ngày

```text
DONE

Nếu sla_deadline có ngày > ngày bắt đầu tính SLA:
hệ thống mặc định coi deadline là ngày hôm sau để tính sla_minutes.
Không xét ngày nghỉ/lễ.
```

### Test 5: ID_CB

```text
DONE

Email đọc ra tên CB -> map sang ID_CB.
assigned_officer lưu ID_CB.
Tổng SLA chỉ cộng theo ID_CB.
Đang xử lý chỉ đếm theo ID_CB.
Điểm Phân Giao chỉ tính theo ID_CB.
Tên CB chỉ dùng để hiển thị.
recalculate_config_load() hỗ trợ cả dashboard schema và internal case schema.
Filter Ready xử lý được khoảng trắng/chữ hoa-thường.
```

### Test 6: Rule Engine

```text
DONE

Tab Rule Engine / Bảng Assignment:
- Chọn được Loại luồng.
- Chọn được Phòng yêu cầu.
- Chọn được Cán bộ bằng select native.
- Cán bộ lưu xuống DB bằng ID_CB.
- Reload lại tab vẫn hiển thị rule đã lưu.
```

### Test 7: Bàn điều phối hiển thị dày hơn

```text
Các dòng hồ sơ trên Bàn điều phối có chiều cao nhỏ hơn hiện tại.
Màn hình hiển thị được nhiều hồ sơ hơn.
Không thay đổi dữ liệu, màu SLA, sort, filter, hoặc thao tác click chi tiết hồ sơ.
```

### Test 8: Phân bổ SLA tự có dữ liệu mặc định

```text
DONE

Vào tab Quản trị.
Bảng Phân bổ SLA tự hiển thị các tiêu chí mặc định.
Không cần nút Thêm.
Người dùng có thể chỉnh Giá trị và bấm Lưu.
Reload lại trang vẫn còn các tiêu chí đã lưu.
Các key cũ O1/O2/O3/O5/O6 không bị mất.
```

---

## 9. Ghi chú triển khai

Thứ tự thực hiện tiếp theo:

```text
1. Giảm giãn cách dòng Bàn điều phối.
2. Chạy nghiệm thu tổng hợp.
```

Lưu ý khi test frontend:

```text
- Nếu xem qua Vite dev server: mở đúng http://localhost:5173 và hard refresh.
- Nếu xem bản static build qua backend: chạy npm run build lại frontend, restart backend, rồi hard refresh.
```
