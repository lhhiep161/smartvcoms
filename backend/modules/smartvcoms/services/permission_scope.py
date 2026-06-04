from __future__ import annotations

from typing import Any
import unicodedata

import pandas as pd

DEFAULT_RESTRICTED_ROOM_MAP = {
    "PHONG KHDN": "Phòng KHDN",
    "KHDN": "Phòng KHDN",
    "PHONG BAN LE": "Phòng Bán lẻ",
    "BAN LE": "Phòng Bán lẻ",
    "BAN LẺ": "Phòng Bán lẻ",
    "PHONG BÁN LẺ": "Phòng Bán lẻ",
    "PGD CAY TRAM": "PGD Cây Trâm",
    "PGD HIEP THANH": "PGD Hiệp Thành",
    "HIEP THANH": "PGD Hiệp Thành",
    "PGD HANH THONG TAY": "PGD Hạnh Thông Tây",
    "HANH THONG TAY": "PGD Hạnh Thông Tây",
    "PGD GO VAP": "PGD Gò Vấp",
    "GO VAP": "PGD Gò Vấp",
    "PGD AN NHON": "PGD An Nhơn",
    "AN NHON": "PGD An Nhơn",
    "CAY TRAM": "PGD Cây Trâm",
}

DEFAULT_ALL_ACCESS_DEPARTMENTS = {
    "BGD",
    "BAN GIAM DOC",
    "BAN GIÁM ĐỐC",
    "ADMIN",
    "PHONG HTTD",
    "HTTD",
    "PHONG KE TOAN",
    "PHONG KẾ TOÁN",
    "PHONG TONG HOP",
    "PHONG TỔNG HỢP",
    "PHONG DVKH",
    "DVKH",
    "PHONG TCTH",
    "TCTH",
}

DEFAULT_ADMIN_ROLES = {"ADMIN", "BGD", "BAN GIAM DOC", "BAN GIÁM ĐỐC", "A", "G"}


def _norm_text(value: Any) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.upper()


def _canonical_department(user_context: dict[str, Any]) -> str | None:
    department = user_context.get("firstGroup") or user_context.get("departmentName") or user_context.get("department")
    ma_phong = _norm_text(user_context.get("maPhong") or user_context.get("departmentCode"))
    dept_norm = _norm_text(department)

    if not dept_norm:
        if ma_phong == "18":
            return "Phòng HTTD"
        if ma_phong == "05":
            return "Phòng KHDN"
        if ma_phong == "09":
            return "Phòng Bán lẻ"
        return None

    alias = DEFAULT_RESTRICTED_ROOM_MAP.get(dept_norm)
    if alias:
        return alias

    if dept_norm.startswith("PGD "):
        return " ".join(str(department).strip().split())

    return str(department).strip()


def canonical_room_label(value: Any) -> str:
    raw = str(value or "").strip()
    norm = _norm_text(raw)
    if not norm:
        return ""
    alias = DEFAULT_RESTRICTED_ROOM_MAP.get(norm)
    if alias:
        return alias
    if norm.startswith("PGD "):
        return " ".join(raw.split())
    return raw


def resolve_vcoms_scope(current_user: dict) -> dict:
    role_norm = _norm_text(current_user.get("viTri"))
    dept_canonical = _canonical_department(current_user)
    dept_norm = _norm_text(dept_canonical)

    is_admin = bool(current_user.get("isAdmin")) or role_norm in DEFAULT_ADMIN_ROLES
    if not is_admin and dept_norm in DEFAULT_ALL_ACCESS_DEPARTMENTS:
        is_admin = True

    if is_admin:
        return {
            "scope": "ALL",
            "allowed_rooms": [],
            "message": "Phạm vi dữ liệu: Toàn chi nhánh",
            "department": dept_canonical,
        }

    if not dept_canonical:
        return {
            "scope": "DENY",
            "allowed_rooms": [],
            "message": "Không xác định được phòng ban người dùng.",
            "department": None,
        }

    restricted = DEFAULT_RESTRICTED_ROOM_MAP.get(_norm_text(dept_canonical))
    if restricted:
        allowed = [restricted]
    elif _norm_text(dept_canonical).startswith("PGD "):
        allowed = [dept_canonical]
    else:
        return {
            "scope": "ALL",
            "allowed_rooms": [],
            "message": "Phạm vi dữ liệu: Toàn chi nhánh",
            "department": dept_canonical,
        }

    return {
        "scope": "ROOM_ONLY",
        "allowed_rooms": allowed,
        "message": f"Phạm vi dữ liệu: {allowed[0]}",
        "department": dept_canonical,
    }


def apply_vcoms_scope(df: pd.DataFrame, current_user: dict, room_col: str = "Phòng") -> tuple[pd.DataFrame, dict]:
    scope = resolve_vcoms_scope(current_user)
    meta = {
        "scope": scope["scope"],
        "allowed_rooms": scope["allowed_rooms"],
        "message": scope["message"],
        "department": scope["department"],
        "total_before": len(df),
        "total_after": 0,
    }

    if scope["scope"] == "ALL":
        meta["total_after"] = len(df)
        return df.copy(), meta

    if scope["scope"] == "DENY" or room_col not in df.columns:
        meta["scope"] = "DENY"
        meta["message"] = "Không xác định được phạm vi dữ liệu SmartVCOMS."
        return df.iloc[0:0].copy(), meta

    allowed_norm = {_norm_text(x) for x in scope["allowed_rooms"]}
    scoped = df[df[room_col].apply(lambda v: _norm_text(v) in allowed_norm)].copy()
    meta["total_after"] = len(scoped)
    return scoped, meta


def room_allowed_for_user(room_value: Any, current_user: dict) -> bool:
    scope = resolve_vcoms_scope(current_user)
    if scope["scope"] == "ALL":
        return True
    if scope["scope"] == "DENY":
        return False
    canonical = _norm_text(canonical_room_label(room_value))
    allowed_norm = {_norm_text(canonical_room_label(item)) for item in scope["allowed_rooms"]}
    return canonical in allowed_norm
