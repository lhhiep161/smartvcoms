# SYSTEM PACKAGING RULES

## 1. Mục đích tài liệu

Tài liệu này là nguồn quy tắc gốc để:

- thống nhất cách xây dựng hệ thống mới
- thống nhất cách đóng gói cập nhật
- lưu cấu trúc của từng bản đóng gói
- giảm rủi ro kéo nhầm code legacy vào package runtime
- làm chuẩn tham chiếu khi tiếp tục ghép thêm `SmartContract`, `SmartVCOMS` hoặc các phân hệ mới

Mọi lần thay đổi kiến trúc, đóng gói, thêm module, đổi launcher hoặc đổi cấu trúc package phải cập nhật lại tài liệu này.

---

## 2. Phạm vi hệ thống mới

Hệ thống mới được hiểu là hệ thống runtime chính thức dùng để đóng gói và triển khai.

Nguyên tắc:

- `backend/` chứa API, service, business logic backend, auth, permission, cấu hình runtime backend
- `frontend/` chứa UI, route, store, composable, component, asset frontend
- không để runtime của hệ thống mới phụ thuộc ngầm vào code legacy nằm ngoài phạm vi package đích
- mọi phụ thuộc ngoài `backend/` và `frontend/` phải được ghi nhận rõ trong tài liệu đóng gói

Khuyến nghị cấu trúc package đích khi triển khai nội bộ:

- `backend/`
- `frontend/`
- `runtime_data/`
- `launchers/`
- `package_config/`
- `docs/`

Giải thích:

- `runtime_data/` dùng cho SQLite DB, file seed, file cấu hình runtime, log trạng thái
- `launchers/` dùng cho `.bat`, `.ps1`, script chạy backend/frontend/watch pipeline
- `package_config/` dùng cho config theo môi trường triển khai nội bộ

---

## 3. Quy tắc xây dựng hệ thống

### 3.1. Quy tắc phân thư mục

#### `backend/`

Chỉ chứa:

- router/API
- service
- business rule
- auth backend
- permission engine backend
- schema/model cần cho backend
- adapter đọc/ghi dữ liệu nếu adapter này phục vụ runtime backend

Không để trong `backend/`:

- file test ad hoc
- script debug một lần
- package update tạm
- backup dữ liệu
- notebook hoặc file so sánh thủ công

#### `frontend/`

Chỉ chứa:

- route
- page
- component
- composable
- store
- asset
- cấu hình build frontend

Không để trong `frontend/`:

- dữ liệu runtime
- script backend
- file backup UI
- code của module đã loại khỏi package đích

#### `runtime_data/`

Chứa:

- database runtime như `portal.db`, `vcoms.db`
- seed file runtime nếu package còn cần
- status file
- cache runtime

Không để:

- source code chính

#### `launchers/`

Chứa:

- file `.bat`
- file `.ps1`
- script start/stop/check health

Không để:

- business logic chính

#### `package_config/`

Chứa:

- biến cấu hình theo package
- map path runtime
- polling interval
- cấu hình bật/tắt module

---

### 3.2. Quy tắc module

Mỗi phân hệ phải có ranh giới rõ:

- backend route riêng
- backend service riêng
- frontend page riêng
- frontend component riêng
- data runtime riêng nếu cần

Không để:

- module A import trực tiếp code legacy của module B mà không qua adapter rõ ràng
- module mới kéo router/module cũ chỉ vì tiện reuse

Khi cần dùng chung logic:

- tách ra lớp dùng chung có tên rõ
- đặt ở vị trí trung lập theo vai trò, không đặt trong module không liên quan

---

### 3.3. Quy tắc kích thước và tổ chức file

Không dồn quá nhiều code vào một file.

Nguyên tắc:

- file router chỉ nên tập trung vào route và gọi service
- file service chỉ nên tập trung vào một nhóm chức năng liên quan
- component frontend lớn phải tách nhỏ nếu có nhiều tab hoặc nhiều khối nghiệp vụ
- không nhồi cả auth, permission, business, view formatting vào cùng một file

Dấu hiệu cần tách file:

- một file xử lý từ 2 domain nghiệp vụ trở lên
- một file frontend vừa gọi API, vừa chứa logic lớn, vừa render nhiều màn hình con
- một file backend vừa parse dữ liệu, vừa xử lý business, vừa ghi DB, vừa format response

Khuyến nghị:

- router mỏng
- service rõ trách nhiệm
- helper tách riêng
- config tách riêng

---

### 3.4. Quy tắc import và phụ thuộc

Không được để runtime chính phụ thuộc ngầm vào code nằm ngoài package đích.

Mọi import từ thư mục ngoài phạm vi package phải:

- được xem là dependency phải nội bộ hóa
- hoặc phải được loại bỏ khỏi package

Ví dụ vi phạm:

- `backend/...` import trực tiếp từ thư mục ngoài `backend/`
- `frontend/...` phụ thuộc route/module không nằm trong package đích

Trước mỗi lần đóng gói phải rà:

- import ngoài phạm vi
- path file cứng
- DB path cứng
- seed path cứng

---

### 3.5. Quy tắc dữ liệu theo ngày

Đối với package runtime chính thức:

- dữ liệu hiển thị phải đúng theo ngày hiện tại nếu yêu cầu package quy định như vậy
- không được fallback sang ngày gần nhất nếu business rule không cho phép
- mọi hành vi fallback phải được ghi rõ bằng cấu hình hoặc tài liệu

Nếu package yêu cầu `today-only strict`:

- không fallback ngày gần nhất
- nếu không có dữ liệu hôm nay thì trả về rỗng hoặc trạng thái cảnh báo phù hợp

---

### 3.6. Quy tắc homepage, menu, route

Homepage, sidebar và route không được hardcode theo cách gây khó mở rộng.

Mỗi lần thêm module mới phải kiểm tra:

- homepage
- sidebar
- router
- permission map
- portal admin permission store

Mục tiêu:

- thêm module mới với ít điểm sửa nhất
- tránh sửa rải rác nhiều nơi

Nếu còn hardcode thì phải ghi rõ trong tài liệu package để tránh bỏ sót.

---

## 4. Quy tắc đóng gói cập nhật

### 4.1. Mục tiêu của mỗi bản đóng gói

Mỗi package cập nhật phải trả lời rõ:

- package này dành cho module nào
- package này chạy độc lập hay ghép cùng package khác
- package này có thay đổi schema/data không
- package này có thay đổi launcher không
- package này có cần seed/config mới không

---

### 4.2. Các bước chuẩn khi đóng gói

1. xác định phạm vi module/package đích
2. rà import/path phụ thuộc ra ngoài phạm vi package
3. xác định danh sách file runtime bắt buộc
4. loại bỏ file test/debug/backup/legacy không cần
5. kiểm tra launcher
6. kiểm tra DB path, config path, log path
7. kiểm tra homepage/sidebar/router nếu package có thay đổi module hiển thị
8. kiểm tra business rule đặc biệt của package
9. ghi cấu trúc package vào mục lịch sử bên dưới

---

### 4.3. Quy tắc launcher

Launcher phải:

- chạy đúng entrypoint của package mới
- không gọi nhầm entrypoint của hệ cũ
- có log hoặc status rõ
- có polling interval cấu hình được nếu có watch job

Nếu package có Outlook watch:

- phải ghi rõ interval
- phải ghi rõ folder nguồn
- phải ghi rõ DB đích
- phải ghi rõ có strict today hay không

---

### 4.4. Quy tắc package update

Không đóng gói kèm:

- `__pycache__`
- `.pyc`
- `.DS_Store`
- file backup
- file report debug
- package cũ trong `updates/`, `release/`, `releases/`
- DB test
- script test không dùng runtime

Chỉ mang theo:

- source runtime
- config cần thiết
- data runtime cần thiết
- launcher cần thiết
- tài liệu vận hành cần thiết

---

### 4.5. Quy tắc kiểm tra trước khi xuất package

Tối thiểu phải kiểm tra:

- backend import được
- frontend build được hoặc có thể chạy bằng chế độ deploy đã chọn
- route module đích hoạt động
- DB path đúng
- launcher đúng
- không còn phụ thuộc nhầm vào module đã loại
- business rule đặc biệt của package đã được giữ đúng

---

## 5. Cấu trúc chuẩn của một bản đóng gói

Mẫu khuyến nghị:

```text
PackageName/
  backend/
  frontend/
  runtime_data/
    smartvcoms/
    portal/
  launchers/
  package_config/
  docs/
```

Nếu package là gói đơn module:

```text
SmartVCOMS_Package/
  backend/
  frontend/
  runtime_data/
    portal/
    smartvcoms/
  launchers/
  package_config/
  docs/
```

Nếu package là gói đa module:

```text
PortalCN9_Package/
  backend/
  frontend/
  runtime_data/
    portal/
    smartvcoms/
    smartcontract/
  launchers/
  package_config/
  docs/
```

---

## 6. Nhật ký cấu trúc các bản đóng gói

Mỗi lần tạo package mới phải thêm một mục mới ở đây.

Mẫu ghi:

```text
### [PACKAGE_CODE]
- Date:
- Scope:
- Modules:
- Runtime entrypoints:
- Launcher files:
- Runtime data:
- External dependencies removed:
- External dependencies still allowed:
- Special business rules:
- Notes:
```

### [TEMPLATE_ONLY]

- Date: YYYY-MM-DD
- Scope: Template khởi tạo quy tắc
- Modules: N/A
- Runtime entrypoints: N/A
- Launcher files: N/A
- Runtime data: N/A
- External dependencies removed: N/A
- External dependencies still allowed: N/A
- Special business rules: N/A
- Notes: Mục này chỉ là mẫu, không phải package thực tế

---

## 7. Danh sách kiểm tra khi thêm module mới

Khi thêm module như `SmartContract` hoặc module mới khác, phải kiểm tra:

- backend route đã tách riêng chưa
- frontend page đã tách riêng chưa
- homepage có cần hiển thị thêm không
- sidebar có cần hiển thị thêm không
- router có cần thêm route không
- permission store có row riêng chưa
- portal admin có cần cấu hình riêng không
- runtime data có namespace riêng chưa
- launcher có cần bản ghép module không

---

## 8. Danh sách kiểm tra khi loại module khỏi package

Khi package chỉ giữ một số module:

- bỏ route của module không dùng
- bỏ menu/home card của module không dùng
- bỏ permission seed của module không dùng
- bỏ portal admin config riêng của module không dùng
- bỏ DB path và healthcheck của module không dùng
- bỏ import và dependency ngầm

---

## 9. Quy tắc cập nhật tài liệu này

Phải cập nhật tài liệu này khi có một trong các thay đổi sau:

- đổi cấu trúc package
- đổi launcher
- đổi nơi đặt DB/config/runtime data
- thêm hoặc bỏ module
- thay đổi rule business đặc biệt của package
- đổi tiêu chuẩn đóng gói

Không được đóng gói bản mới mà không cập nhật lại mục:

- `Cấu trúc chuẩn của một bản đóng gói`
- `Nhật ký cấu trúc các bản đóng gói`
- các rule mới phát sinh nếu có

