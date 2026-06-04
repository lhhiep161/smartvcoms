# SmartVCOMS - Tổng hợp các điểm cần chỉnh sửa

Ngày lập: 04/06/2026  
Phạm vi: SmartVCOMS trong repository `lhhiep161/smartvcoms`

Tài liệu này tổng hợp các nội dung cần chỉnh sửa đã chốt. Mục tiêu là sửa đúng phạm vi yêu cầu, không mở rộng sang các logic nghiệp vụ khác nếu không cần thiết.

---

## 1. Quy định lại `arrival_time`

### 1.1. Yêu cầu

Hiện tại `arrival_time` đang lấy theo thời điểm Outlook nhận email `ARRIVAL` / `LC_REQUEST`.

Cần chỉnh lại:

```text
arrival_time = thời điểm hồ sơ chuyển sang trạng thái Chờ T.Nhận / WAIT_ACCEPT
```

### 1.2. Phạm vi áp dụng

Chỉ áp dụng cho hồ sơ có luồng chuyển sang trạng thái:

```text
Chờ T.Nhận / WAIT_ACCEPT
```

Không thay đổi xử lý riêng của các luồng khác nếu code hiện tại không đi qua `WAIT_ACCEPT`.

Cụ thể:

```text
- LC_REQUEST hiện đang xử lý thế nào thì giữ nguyên.
- Không ép LC phải đổi arrival_time theo logic mới.
- Không thay đổi cách đóng/mở hồ sơ hoặc tách case nếu không liên quan.
```

### 1.3. Ảnh hưởng cần xử lý

Sau khi đổi `arrival_time`, các phần đang dùng `arrival_time` để tính SLA/phân giao sẽ hiểu đây là mốc bắt đầu tính:

```text
- sla_minutes
- Tổng SLA
- Điểm phân giao
- tải phân giao cán bộ
```

Điểm cần sửa chính nằm ở `state_machine.py`, nơi hiện đang set `arrival_time` khi nhận event `ARRIVAL` / `LC_REQUEST`.

---

## 2. Đồng nhất cách tính `sla_minutes`

### 2.1. Vấn đề hiện tại

Luồng chính đã có hàm tính SLA loại trừ thời gian nghỉ, nhưng vẫn còn đoạn fallback tính thô:

```text
sla_deadline - arrival_time
```

Đoạn fallback này không loại trừ thời gian nghỉ.

### 2.2. Yêu cầu

Tất cả nơi tính hoặc fallback `sla_minutes` phải dùng cùng một logic tính phút SLA có loại trừ thời gian nghỉ theo cấu hình.

Không để tồn tại công thức raw:

```text
(sla_deadline - arrival_time).total_minutes
```

nếu công thức đó không loại trừ thời gian nghỉ.

### 2.3. Phạm vi sửa

Tập trung vào:

```text
- _calculate_sla_minutes(...)
- fallback khi sla_minutes bị thiếu
- các phần tính Tổng SLA / Điểm phân giao dựa trên sla_minutes
```

---

## 3. Không hardcode thời gian nghỉ, chuyển thành cấu hình Portal Admin

Hiện các hàm tính thời gian đang hardcode khung giờ làm việc/SLA. Cần chuyển thành cấu hình trên Portal Admin gồm 2 nhóm riêng.

### 3.1. Thời gian làm việc

Dùng để tính thời gian hồ sơ đang nằm ở trạng thái nào đó:

```text
- Hồ sơ đến bao lâu
- Chờ T.Nhận bao lâu
- Đang xử lý bao lâu
- Chờ ký số bao lâu
- Chờ giải ngân bao lâu
```

Ví dụ:

```text
Thời gian làm việc: 13:00-17:00
```

### 3.2. Thời gian tính SLA

Dùng cho các công thức liên quan SLA/phân giao:

```text
- sla_minutes
- Tổng SLA
- Điểm phân giao
- tải phân giao CB
- thời gian còn lại/vượt SLA nếu thuộc nhóm SLA
```

Ví dụ:

```text
Thời gian tính SLA: 13:30-15:30
```

Khi đó:

```text
- Thời gian hồ sơ đang xử lý vẫn tính đến 17:00.
- Thời gian SLA/phân giao chỉ tính trong 13:30-15:30.
```

### 3.3. Không xử lý ngày nghỉ/lễ

Theo quy định đã chốt:

```text
Một hồ sơ không thể có > 1 ngày làm việc.
Không cần khai báo ngày nghỉ/lễ.
```

Nếu `sla_deadline` có ngày lớn hơn ngày bắt đầu tính SLA thì mặc định coi là ngày hôm sau.

Quy tắc:

```text
Nếu sla_deadline.date > sla_start_date:
    effective_deadline_date = sla_start_date + 1 ngày
```

Giữ nguyên giờ/phút của `sla_deadline`.

---

## 4. Chuẩn hóa ID CB và Tên CB

### 4.1. Nguyên tắc mới

```text
Email có thể đọc ra tên cán bộ.

Nhưng ngay khi đưa vào hệ thống:
Tên cán bộ -> map sang ID_CB.

Từ đó trở đi:
mọi tính toán/phân giao/cộng tải chỉ dùng ID_CB.

Tên cán bộ chỉ dùng để hiển thị nếu cần.
```

### 4.2. Khi đọc email

Nếu email có:

```text
Hồ sơ được xử lý bởi cán bộ: Nguyễn Văn A
```

hệ thống phải map sang `ID_CB` tương ứng trong `config_cb_full`.

Sau đó xử lý bằng `ID_CB`.

### 4.3. Khi phân giao tự động

Hàm phân giao phải trả về `ID_CB`, không trả về tên cán bộ.

Cần đổi sang:

```text
- Chọn theo Điểm Phân Giao
- Nếu bằng nhau thì theo Lần giao cuối
- Kết quả trả về ID_CB
```

### 4.4. Khi tính tải CB

Các chỉ tiêu sau chỉ tính theo `ID_CB`:

```text
- Đang xử lý
- Tổng phút SLA
- Điểm Phân Giao
- Lần giao cuối
```

Không cộng kiểu:

```text
ID_CB + Tên Cán bộ
```

### 4.5. Khi hiển thị

Web có thể hiển thị tên cán bộ, nhưng phải map từ:

```text
ID_CB -> Tên Cán bộ
```

Không dùng tên cán bộ làm khóa xử lý nội bộ.

---

## 5. Sửa lỗi tab Rule Engine không chọn được Cán bộ

### 5.1. Vấn đề

Trên tab Rule Engine, bảng:

```text
2. QUY TẮC PHÂN GIAO CB (ASSIGNMENT)
```

Loại luồng và Phòng yêu cầu chọn được, nhưng Cán bộ không chọn được.

Cột Cán bộ hiện đang dùng custom dropdown bằng `<div>`, lấy dữ liệu từ:

```text
adminConfig.cb_config
```

và khi click thì set:

```text
rule.assigned_officers = cb.ID_CB
```

Về mặt dữ liệu là đúng vì assignment rule nên lưu `ID_CB`, nhưng UI custom dropdown dễ lỗi thao tác hơn `<select>` native.

### 5.2. Yêu cầu sửa frontend

Đổi cột Cán bộ trong Assignment Rule sang `<select>` native.

Logic mong muốn:

```vue
<select v-model="rule.assigned_officers" class="table-input">
    <option value="">-- Chọn cán bộ --</option>
    <option
        v-for="cb in adminConfig.cb_config"
        :key="cb.ID_CB"
        :value="cb.ID_CB"
    >
        {{ cb.ID_CB }} - {{ cb['Tên Cán bộ'] }}
    </option>
</select>
```

### 5.3. Quy tắc dữ liệu

```text
rule.assigned_officers = ID_CB
```

Không lưu tên cán bộ vào rule.

### 5.4. Load dữ liệu

Cần đảm bảo:

```text
- loadAdminConfig xong trước khi cho chọn CB
- loadRules xong để hiển thị rule hiện có
```

### 5.5. Bổ sung API GET rules

Frontend đang cần load rules từ:

```text
GET /api/vcoms/admin/rules
```

Cần bổ sung endpoint này để đọc dữ liệu từ:

```text
- vcoms_routing_rules
- vcoms_assignment_rules
```

Response mong muốn:

```json
{
  "status": "success",
  "data": {
    "routing": [],
    "assignment": []
  }
}
```

---

## 6. Tối ưu hiển thị Bàn điều phối

### 6.1. Yêu cầu

Giảm giãn cách dòng các hồ sơ trên Bàn điều phối để tăng số lượng hồ sơ hiển thị trên màn hình.

### 6.2. Phạm vi sửa

Chỉ chỉnh spacing/density hiển thị, không thay đổi logic:

```text
- lọc
- sort
- màu cảnh báo SLA
- thao tác click chi tiết hồ sơ
- dữ liệu hồ sơ
```

### 6.3. Gợi ý chỉnh CSS

Các bảng hồ sơ đang dùng chung class:

```text
.main-table
.sub-table
```

Có thể giảm padding/font như sau:

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
```

Có thể giảm thêm khoảng cách phụ:

```css
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

## 7. Tab Quản trị tự động load mặc định bảng Phân bổ SLA

### 7.1. Vấn đề

Trên tab Quản trị, bảng PHÂN BỔ SLA hiện không có thông tin nếu `sla_config` rỗng và cũng không có nút thêm dòng.

Bảng đang render theo:

```vue
<tr v-for="(sla, idx) in adminConfig.sla_config" :key="'sla'+idx">
```

Nếu `adminConfig.sla_config` rỗng thì người dùng không có gì để nhập.

### 7.2. Yêu cầu

Hệ thống phải tự động hiển thị sẵn các tiêu chí mặc định trong bảng Phân bổ SLA, tương tự các cấu hình nền như cán bộ/phòng ban/LĐP-KSV, để người dùng không cần tự thêm thủ công.

Không cần thêm nút Thêm nếu backend tự tạo đủ tiêu chí mặc định.

### 7.3. Danh sách tiêu chí mặc định

Giữ các tiêu chí SLA hiện tại đang dùng:

```text
O1
O2
LC_SLA
BL_SLA
DN_PREFIX
```

Bổ sung nhóm cấu hình thời gian mới:

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

Giá trị mặc định đề xuất để tương thích hành vi hiện tại:

```text
WORK_MORNING_START      = 08:00
WORK_MORNING_END        = 12:00
WORK_AFTERNOON_START    = 13:00
WORK_AFTERNOON_END      = 19:30

SLA_MORNING_START       = 08:00
SLA_MORNING_END         = 12:00
SLA_AFTERNOON_START     = 13:00
SLA_AFTERNOON_END       = 19:30
```

### 7.4. Cách xử lý mong muốn

Trong backend, khi gọi:

```text
GET /api/vcoms/admin/config
```

thì `sla_config` trả về luôn có đầy đủ tiêu chí mặc định.

Cần mở rộng logic hiện tại thành hàm chuẩn, ví dụ:

```text
ensure_default_sla_config()
```

Chức năng:

```text
- Kiểm tra các key SLA mặc định.
- Nếu thiếu thì tạo dòng mặc định.
- Trả về đầy đủ cho frontend.
- Nên ghi luôn vào SQLite để lần sau load không bị rỗng.
```

---

## 8. Danh sách file/khu vực cần sửa

### 8.1. Backend

```text
backend/modules/smartvcoms/pipeline/state_machine.py
```

Cần sửa:

```text
- logic set arrival_time khi hồ sơ chuyển Chờ T.Nhận
- _calculate_sla_minutes(...)
- normalize cán bộ từ email sang ID_CB
- gán assigned_officer bằng ID_CB
- giữ nguyên logic LC nếu không liên quan yêu cầu trên
```

```text
backend/modules/smartvcoms/pipeline/assignment.py
```

Cần sửa:

```text
- assign_officer() trả về ID_CB
- recalculate_config_load() tính tải theo ID_CB
- update_last_assigned() cập nhật theo ID_CB
```

```text
backend/modules/smartvcoms/store/config_admin.py
```

Cần sửa:

```text
- fallback sla_minutes không được tính thô
- sync_config_cb_load_from_case_state() chỉ tính theo ID_CB
- không cộng name + cb_id
- bổ sung ensure_default_sla_config() hoặc logic tương đương
```

```text
backend/modules/smartvcoms/services/admin_service.py
```

Cần sửa:

```text
- Đang xử lý chỉ tính theo ID_CB
- Tổng SLA chỉ tính theo ID_CB
- Điểm Phân Giao = Tổng SLA theo ID_CB + Phút Bù Trừ
- trả về sla_config mặc định nếu thiếu/rỗng
```

```text
backend/modules/smartvcoms/utils.py
```

Cần sửa:

```text
- bỏ hardcode khung giờ
- thêm hàm tính theo cấu hình Thời gian làm việc
- thêm hàm tính theo cấu hình Thời gian tính SLA
```

```text
backend/modules/smartvcoms/services/actions_service.py
```

Cần sửa/thêm:

```text
- load_rule_engine_config()
- GET rules đọc từ vcoms_routing_rules và vcoms_assignment_rules
- manual override CB nếu nhập tên hoặc ID thì normalize về ID_CB
```

```text
backend/modules/smartvcoms/router.py
```

Cần thêm:

```text
GET /api/vcoms/admin/rules
```

### 8.2. Frontend

```text
frontend/src/modules/smart-vcoms/components/TabRuleEngine.vue
```

Cần sửa:

```text
- đổi custom dropdown cán bộ sang select native
- option value = ID_CB
- label = ID_CB - Tên Cán bộ
- nếu chưa có cb_config thì hiển thị trạng thái chưa có dữ liệu hoặc đang tải
```

```text
frontend/src/modules/smart-vcoms/pages/SmartVCOMSPage.vue
```

Cần sửa:

```text
- đảm bảo khi vào tab RULE_ENGINE thì loadAdminConfig xong trước hoặc song song an toàn
- loadRules phải hoạt động với GET endpoint mới
- giảm giãn cách dòng hồ sơ trên Bàn điều phối
```

```text
frontend/src/modules/smart-vcoms/components/TabAdminConfig.vue
```

Cần sửa:

```text
- bảng Phân bổ SLA luôn có tiêu chí mặc định từ backend
- nếu vẫn rỗng do lỗi thì hiển thị empty-state phù hợp
- không bắt buộc thêm nút Thêm nếu backend tự tạo đủ tiêu chí
```

---

## 9. Những gì không sửa trong phạm vi này

Không sửa các nội dung ngoài yêu cầu:

```text
- Không thay đổi logic LC nếu code hiện tại không yêu cầu.
- Không thêm xử lý ngày nghỉ/lễ.
- Không thay đổi rule nghiệp vụ đóng/mở hồ sơ.
- Không thay đổi cách tách case nếu không liên quan ID_CB/SLA/arrival_time.
- Không thay đổi logic ACCEPTED ghi nhận cán bộ xử lý, chỉ chuẩn hóa tên đọc được thành ID_CB.
- Không thay đổi giao diện Kanban ngoài phần hiển thị tên CB từ ID_CB nếu cần và giảm spacing dòng hồ sơ.
- Không thay đổi logic lọc/sort/màu SLA trên Bàn điều phối khi giảm giãn cách dòng.
```

---

## 10. Tiêu chí nghiệm thu

### Test 1: `arrival_time`

```text
Hồ sơ chưa chuyển Chờ T.Nhận:
arrival_time chưa được dùng làm mốc SLA mới.

Khi hồ sơ chuyển Chờ T.Nhận:
arrival_time = thời điểm chuyển Chờ T.Nhận.
```

### Test 2: `sla_minutes`

```text
Không có fallback nào tính sla_minutes bằng raw deadline - arrival_time.
Tất cả đều loại trừ thời gian nghỉ theo cấu hình.
```

### Test 3: cấu hình thời gian

```text
Thời gian làm việc và Thời gian tính SLA khác nhau thì:
- thời gian chờ/trạng thái dùng Thời gian làm việc
- SLA/phân giao dùng Thời gian tính SLA
```

### Test 4: deadline qua ngày

```text
Nếu sla_deadline có ngày > ngày bắt đầu tính SLA:
hệ thống mặc định coi deadline là ngày hôm sau để tính sla_minutes.
Không xét ngày nghỉ/lễ.
```

### Test 5: ID_CB

```text
Email đọc ra tên CB -> map sang ID_CB.
assigned_officer lưu ID_CB.
Tổng SLA chỉ cộng theo ID_CB.
Đang xử lý chỉ đếm theo ID_CB.
Điểm Phân Giao chỉ tính theo ID_CB.
Tên CB chỉ dùng để hiển thị.
```

### Test 6: Rule Engine

```text
Tab Rule Engine / Bảng Assignment:
- Chọn được Loại luồng.
- Chọn được Phòng yêu cầu.
- Chọn được Cán bộ bằng dropdown/select.
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
Vào tab Quản trị.
Bảng Phân bổ SLA tự hiển thị các tiêu chí mặc định.
Không cần nút Thêm.
Người dùng có thể chỉnh Giá trị và bấm Lưu.
Reload lại trang vẫn còn các tiêu chí đã lưu.
```

---

## 11. Ghi chú triển khai

Nên thực hiện theo thứ tự:

```text
1. Bổ sung default SLA config và GET rules để ổn định dữ liệu cấu hình.
2. Chuẩn hóa ID_CB trong assignment/admin/config/manual override.
3. Sửa arrival_time và tính sla_minutes theo calendar cấu hình.
4. Cập nhật frontend Rule Engine, Admin Config và density Bàn điều phối.
5. Chạy lại toàn bộ test nghiệm thu ở mục 10.
```
