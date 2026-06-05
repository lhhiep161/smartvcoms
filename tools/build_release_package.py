import hashlib
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build"
STAGING_ROOT = BUILD_ROOT / "release" / "SmartVCOMS_Package"
OUTPUT_ROOT = BUILD_ROOT / "release_output"
FRONTEND_DIST = ROOT / "frontend" / "dist"

COPY_TARGETS = [
    ("backend", "backend"),
    ("launchers", "launchers"),
    ("package_config/seed", "package_config/seed"),
    ("package_config/app.env.example", "package_config/app.env.example"),
    ("requirements.txt", "requirements.txt"),
    ("tools/generate_emergency_password_hash.py", "tools/generate_emergency_password_hash.py"),
    ("docs/DEPLOY_GUIDE.md", "docs/DEPLOY_GUIDE.md"),
    ("docs/RELEASE_PACKAGING.md", "docs/RELEASE_PACKAGING.md"),
]

EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".github",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "src",
    "runtime_data",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    "app.env",
}
EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".tmp",
    ".cache",
}
OPTIONAL_PACKAGE_DIRS = ["wheelhouse", "offline_packages"]


def ensure_frontend_dist() -> None:
    index_file = FRONTEND_DIST / "index.html"
    if not FRONTEND_DIST.exists() or not index_file.exists():
        raise SystemExit("Chưa build frontend. Hãy chạy cd frontend && npm install && npm run build trước.")


def reset_build_dirs() -> None:
    if STAGING_ROOT.exists():
        shutil.rmtree(STAGING_ROOT)
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def should_skip_file(path: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return True
    if path.name in EXCLUDED_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree_filtered(src: Path, dst: Path) -> None:
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if should_skip_file(rel):
            continue
        if item.is_dir():
            continue
        copy_file(item, dst / rel)


def copy_runtime_files() -> list[str]:
    copied_roots = []
    for src_rel, dst_rel in COPY_TARGETS:
        src = ROOT / src_rel
        dst = STAGING_ROOT / dst_rel
        if not src.exists():
            raise SystemExit(f"Thiếu file/thư mục bắt buộc để đóng gói: {src_rel}")
        if src.is_dir():
            copy_tree_filtered(src, dst)
        else:
            copy_file(src, dst)
        copied_roots.append(dst_rel.split("/", 1)[0])

    frontend_dst = STAGING_ROOT / "frontend" / "dist"
    copy_tree_filtered(FRONTEND_DIST, frontend_dst)
    copied_roots.append("frontend")

    for folder_name in OPTIONAL_PACKAGE_DIRS:
        src = ROOT / folder_name
        if src.exists() and src.is_dir():
            copy_tree_filtered(src, STAGING_ROOT / folder_name)
            copied_roots.append(folder_name)

    return sorted(set(copied_roots))


def write_readme_deploy(has_wheelhouse: bool) -> None:
    target = STAGING_ROOT / "README_DEPLOY.txt"
    lines = [
        "SMARTVCOMS PACKAGE - RUN FIRST",
        "",
        "1) Copy package_config\\app.env.example thanh package_config\\app.env",
        "2) Chinh cau hinh AD trong package_config\\app.env",
        "3) Sinh emergency password hash bang:",
        "   python tools\\generate_emergency_password_hash.py",
        "4) Dan PORTAL_EMERGENCY_PASSWORD_HASH vao package_config\\app.env",
    ]
    if has_wheelhouse:
        lines.extend(
            [
                "5) Cai dependency offline bang:",
                "   launchers\\install_requirements_offline.bat",
            ]
        )
    else:
        lines.extend(
            [
                "5) Chua co wheelhouse/offline_packages trong goi.",
                "   Can chuan bi cac file .whl phu hop va dat vao wheelhouse hoac offline_packages,",
                "   sau do chay: launchers\\install_requirements_offline.bat",
            ]
        )
    lines.extend(
        [
            "6) Chay:",
            "   launchers\\start_smartvcoms.bat",
            "7) Mo trinh duyet tai:",
            "   http://localhost:8000",
            "   hoac http://<IP-may-chu>:8000",
            "",
            "Luu y:",
            "- Khong commit package_config\\app.env that.",
            "- Frontend da duoc build san trong frontend\\dist, may chu khong can npm.",
            "- Tat ca lenh Python runtime trong goi deu dung python, khong dung py.",
        ]
    )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checksums() -> None:
    out = STAGING_ROOT / "CHECKSUMS.txt"
    rows = []
    for file_path in sorted(p for p in STAGING_ROOT.rglob("*") if p.is_file()):
        digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {file_path.relative_to(STAGING_ROOT).as_posix()}")
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")


def find_rar_cli() -> Path | None:
    candidates = [
        shutil.which("rar"),
        shutil.which("Rar"),
        r"C:\Program Files\WinRAR\Rar.exe",
        r"C:\Program Files\WinRAR\WinRAR.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def create_archive(timestamp: str) -> tuple[Path, str]:
    base_name = f"SmartVCOMS_Package_Production_{timestamp}"
    rar_cli = find_rar_cli()
    if rar_cli:
        archive_path = OUTPUT_ROOT / f"{base_name}.rar"
        subprocess.run(
            [str(rar_cli), "a", "-ep1", str(archive_path), str(STAGING_ROOT)],
            check=True,
            cwd=OUTPUT_ROOT,
        )
        return archive_path, "rar"

    archive_base = OUTPUT_ROOT / base_name
    archive_file = shutil.make_archive(str(archive_base), "zip", root_dir=STAGING_ROOT.parent, base_dir=STAGING_ROOT.name)
    return Path(archive_file), "zip"


def validate_package() -> None:
    forbidden = [
        "package_config/app.env",
        "frontend/src",
        "frontend/node_modules",
        "runtime_data",
    ]
    for rel in forbidden:
        if (STAGING_ROOT / rel).exists():
            raise SystemExit(f"Package chứa thành phần không được phép: {rel}")
    required = [
        "frontend/dist/index.html",
        "requirements.txt",
        "launchers/start_smartvcoms.bat",
        "README_DEPLOY.txt",
    ]
    for rel in required:
        if not (STAGING_ROOT / rel).exists():
            raise SystemExit(f"Package thiếu thành phần bắt buộc: {rel}")


def print_summary(archive_path: Path, archive_kind: str, copied_roots: list[str], has_wheelhouse: bool) -> None:
    top_level = sorted(path.name for path in STAGING_ROOT.iterdir())
    print(f"ARCHIVE_PATH={archive_path}")
    print(f"ARCHIVE_TYPE={archive_kind}")
    print(f"ARCHIVE_SIZE_BYTES={archive_path.stat().st_size}")
    print(f"TOP_LEVEL={','.join(top_level)}")
    print(f"COPIED_ROOTS={','.join(copied_roots)}")
    print(f"WHEELHOUSE_INCLUDED={int(has_wheelhouse)}")
    print(f"HAS_REAL_APP_ENV={int((STAGING_ROOT / 'package_config/app.env').exists())}")
    print(f"HAS_FRONTEND_SRC={int((STAGING_ROOT / 'frontend/src').exists())}")
    print(f"HAS_NODE_MODULES={int((STAGING_ROOT / 'frontend/node_modules').exists())}")
    if archive_kind != "rar":
        print("WARNING=Không tìm thấy WinRAR/rar CLI nên đã tạo .zip thay thế. Muốn có .rar cần cài WinRAR hoặc thêm rar.exe vào PATH.")
    if not has_wheelhouse:
        print("WARNING=Chưa có wheelhouse/offline_packages trong repo, cần chuẩn bị .whl riêng trước khi mang sang máy chủ offline.")


def main() -> int:
    ensure_frontend_dist()
    reset_build_dirs()
    copied_roots = copy_runtime_files()
    has_wheelhouse = any((STAGING_ROOT / name).exists() for name in OPTIONAL_PACKAGE_DIRS)
    write_readme_deploy(has_wheelhouse)
    write_checksums()
    validate_package()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    archive_path, archive_kind = create_archive(timestamp)
    print_summary(archive_path, archive_kind, copied_roots, has_wheelhouse)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
