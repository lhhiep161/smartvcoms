# DEPLOY GUIDE - SMARTVCOMS PACKAGE

## 1. Mục tiêu

Tài liệu này hướng dẫn chạy `SmartVCOMS_Package` trên máy nội bộ theo chế độ production:

- `AD`

Hiện tại package đã được chuẩn hóa để:

- không cần Node.js trên máy triển khai
- frontend được serve trực tiếp từ backend
- watcher Outlook chạy riêng theo chu kỳ cấu hình

## 2. Yêu cầu máy triển khai

- Windows
- Python đã cài và gọi được bằng `python`
- Outlook desktop đã đăng nhập nếu muốn đọc mail thật

Không bắt buộc:

- Node.js

## 3. Cài thư viện Python

Tại thư mục `SmartVCOMS_Package`, chạy:

```bat
python -m pip install -r requirements.txt
```

## 4. Cấu hình chính

File cấu hình runtime:

- `package_config/app.env`

Các biến quan trọng:

- `PORTAL_SQLITE_PATH`
- `VCOMS_DB_PATH`
- `VCOMS_STATUS_PATH`
- `VCOMS_OUTLOOK_FOLDER`
- `VCOMS_WATCH_INTERVAL_SECONDS`
- `PORTAL_AUTH_MODE`
- `PORTAL_DEV_LOGIN_ENABLED`
- `PORTAL_EMERGENCY_LOGIN_ENABLED`
- `PORTAL_EMERGENCY_USER`
- `PORTAL_EMERGENCY_PASSWORD_HASH`
- `TODAY_ONLY_STRICT`

File seed AD mapping:

- `package_config/seed/ad_group_mappings.json`
- `package_config/seed/page_permissions.json`
- `package_config/seed/portal_admin_bootstrap.json`
- `package_config/seed/auth_policy.json`
- `package_config/seed/dev_users.json`

Ghi chú:

- file này chỉ dùng để seed lần đầu khi bảng `portal_ad_group_mappings` đang rỗng
- sau đó chỉnh sửa dữ liệu qua `Portal Admin > AD Group Mappings`
- `page_permissions.json` dùng để bootstrap page permissions nền
- `portal_admin_bootstrap.json` dùng để bootstrap `portal admin cấp 1/cấp 2` và grant theo section
- `auth_policy.json` dùng để bootstrap auth settings nền cho các policy runtime được phép quản trị qua Portal Admin
- `dev_users.json` chỉ dùng cho source/dev test, không dùng cho package production AD-only

## 4.1. Bootstrap Portal Admin

`Portal Admin` hiện dùng mô hình:

- `portal_admin_roles`
- `portal_admin_grants`

Bootstrap ban đầu lấy từ:

- `package_config/seed/portal_admin_bootstrap.json`

Nguyên tắc:

- `portal admin cấp 1` có toàn quyền `Portal Admin`
- `portal admin cấp 2` chỉ có quyền theo grant từng section
- `Portal Admin` không còn mở chỉ bằng cờ `isAdmin`
- seed mặc định hiện bootstrap `lh.hiep` là `portal admin cấp 1`

Nếu DB đang trống, cần đảm bảo seed bootstrap này được áp dụng trước khi kỳ vọng user nhìn thấy `Portal Admin`.

## 5. Cách chạy package

### Chạy toàn hệ thống

```bat
launchers\start_smartvcoms.bat
```

Launcher này sẽ:

- chạy backend tại `http://localhost:8000`
- serve frontend build sẵn từ backend
- chạy watcher Outlook theo chu kỳ cấu hình

### Chạy riêng backend

```bat
launchers\start_backend.bat
```

### Kiểm tra health

```bat
launchers\healthcheck.bat
```

## 6. Chốt mode triển khai

### Cách cấu hình

Sửa file:

- `package_config/app.env`

Giá trị production:

```env
PORTAL_AUTH_MODE=AD
PORTAL_DEV_LOGIN_ENABLED=0
PORTAL_EMERGENCY_LOGIN_ENABLED=1
PORTAL_EMERGENCY_USER=lh.hiep
PORTAL_EMERGENCY_PASSWORD_HASH=
```

Tạo hash emergency password bằng:

```bat
python tools\generate_emergency_password_hash.py
```

Script sẽ:

- yêu cầu nhập password 2 lần bằng `getpass`
- bắt buộc password tối thiểu `12` ký tự
- chỉ in ra đúng một dòng:

```env
PORTAL_EMERGENCY_PASSWORD_HASH=pbkdf2_sha256$...
```

Sao chép dòng này vào `package_config/app.env`.

Sau khi sửa, chạy lại:

```bat
launchers\start_smartvcoms.bat
```

### Quy tắc ưu tiên mode

Trong package hiện tại:

- `PORTAL_AUTH_MODE` chỉ đọc từ `package_config/app.env`
- `PORTAL_DEV_LOGIN_ENABLED` chỉ đọc từ `package_config/app.env`
- `Portal Admin` không còn được sửa 2 giá trị này

## 7. Trạng thái thực tế của xác thực

### `AD`

Đã được chuyển logic từ `login_standalone` vào `backend/core/auth_providers/`.

hệ thống sẽ dùng:

- `backend/core/auth_providers/ad_runtime.py`
- `package_config/seed/ad_group_mappings.json` cho lần seed đầu nếu DB mapping đang rỗng

Các biến cần khai báo thêm trong `package_config/app.env`:

```env
AD_DOMAIN=icbv.com
AD_NETBIOS_DOMAIN=ICBV
AD_AUTH_MODE=SIMPLE
AD_UPN_SUFFIX=icbv.com
AD_SERVER=ldap://icbv.com
BASE_DN=DC=icbv,DC=com
AD_SERVICE_USER=
AD_SERVICE_PASS=
MA_CB_AD_ATTRIBUTE=employeeID
AD_DEBUG=0
```

Ghi chú:

- nếu có `AD_SERVICE_USER` và `AD_SERVICE_PASS`, package sẽ bind bằng service account để đọc group/attribute
- nếu để trống service account, package sẽ bind bằng chính user đăng nhập
- `AD_AUTH_MODE` hỗ trợ `SIMPLE` và `NTLM`
- nếu xác thực `AD` lỗi, package chỉ cho phép fallback emergency với đúng user `lh.hiep` và đúng password khớp `PORTAL_EMERGENCY_PASSWORD_HASH`

## 7.1. Lưu ý bảo mật emergency login

- Không commit `package_config/app.env` thật vào Git.
- Dùng `package_config/app.env.example` làm file mẫu cấu hình.
- `PORTAL_EMERGENCY_PASSWORD_HASH` là hash một chiều PBKDF2-SHA256 có salt, không lưu plaintext password.
- Vì emergency password cũ từng tồn tại ở dạng plaintext trong Git, cần đổi emergency password hiện tại trước khi triển khai tiếp.

## 8. Kết luận triển khai

- package production hiện được chốt theo `AD-only`
- cần điền đúng biến AD trong `package_config/app.env` và kiểm tra kết nối LDAP/AD thực tế của máy triển khai
- nếu muốn thấy và dùng `Portal Admin`, cần seed đúng:
  - `portal_admin_bootstrap.json`
  - `page_permissions.json`
