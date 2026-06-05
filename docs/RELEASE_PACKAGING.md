# SMARTVCOMS RELEASE PACKAGING

## 1. Mục tiêu

Đóng gói bản triển khai offline cho máy chủ Windows:

- không cần internet
- không cần npm trên máy chủ
- frontend đã build sẵn và được serve từ `frontend/dist`
- toàn bộ lệnh Python runtime dùng `python`, không dùng `py`

## 2. Chuẩn bị trên máy dev

Nếu frontend source có thay đổi, chạy:

```bat
cd frontend
npm install
npm run build
cd ..
```

Nếu frontend source không đổi nhưng `frontend/dist/index.html` đã tồn tại hợp lệ, có thể dùng lại bản build hiện có.

## 3. Tạo package runtime

```bat
python tools\build_release_package.py
```

Script sẽ:

- kiểm tra `frontend/dist/index.html`
- tạo thư mục staging trong `build/release/SmartVCOMS_Package`
- copy đúng runtime cần thiết
- loại bỏ `frontend/src`, `frontend/node_modules`, `runtime_data`, DB/cache/log
- sinh `README_DEPLOY.txt`
- sinh `CHECKSUMS.txt`
- cố gắng tạo `.rar` nếu có `rar.exe` / `Rar.exe`
- nếu không có WinRAR CLI, tự động tạo `.zip`

## 4. Gói đầu ra

Gói cuối cùng nằm trong:

```text
build/release_output/
```

Tên dự kiến:

```text
SmartVCOMS_Package_Production_YYYYMMDD_HHMM.rar
```

hoặc fallback:

```text
SmartVCOMS_Package_Production_YYYYMMDD_HHMM.zip
```

## 5. Wheelhouse offline

Nếu đã chuẩn bị sẵn `wheelhouse/` hoặc `offline_packages/` ở root repo, script sẽ copy vào gói.

Nếu chưa có, package vẫn được tạo nhưng cần chuẩn bị `.whl` riêng trước khi mang sang máy chủ offline.
