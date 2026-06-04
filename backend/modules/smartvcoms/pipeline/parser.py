"""Email parser utilities for VCOMS rows."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd


EXTRA_KEYWORDS = {
    # Fallback aliases when VN sheet text variant does not match exact mail text.
    "money_loan": "tiền vay",
    "money_disburse": "tiền giải ngân",
    "hoa_so_den_alias": "giải ngân đến",
}


def normalize_text(text: Any) -> str:
    """Return normalized lower text for matching while preserving original values elsewhere."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    s = str(text).replace("_x000D_", "\n")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def extract_value_after_keyword(text: str, keyword: str) -> str | None:
    """Extract value following keyword in a line-oriented body text."""
    if not text or not keyword:
        return None
    body = str(text).replace("_x000D_", "\n").replace("\r", "")
    for line in body.split("\n"):
        line = line.replace("\xa0", " ")
        lk = line.lower()
        kk = keyword.lower()
        pos = lk.find(kk)
        if pos >= 0:
            pos_colon = line.find(":", pos)
            if pos_colon >= 0:
                return line[pos_colon + 1 :].strip()
            return line[pos + len(keyword) :].strip()
    return None


def extract_money(text: str) -> str | None:
    """Extract money literal like 1,500,000,000.00 VND from text."""
    if not text:
        return None
    m = re.search(r"([\d\.,]+)\s*(VND)?", text, flags=re.IGNORECASE)
    if not m:
        return None
    number = m.group(1)
    suffix = " VND" if m.group(2) else ""
    return f"{number}{suffix}".strip()


def extract_account_number(text: str) -> str | None:
    """Extract account number digits from text."""
    if not text:
        return None
    digits = "".join(ch for ch in str(text) if ch.isdigit())
    if not digits:
        return None
    return digits[:12]


def extract_progress_from_subject(subject: str) -> str | None:
    """Extract progress segment after VCOMS_ in subject."""
    if not subject:
        return None
    m = re.search(r"vcoms[_:\-\s]*(.+)$", str(subject), flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def detect_event_type(subject: str, keywords: dict[str, str]) -> str | None:
    """Detect event type in subject."""
    s = normalize_text(subject)
    if not s:
        return None
    if normalize_text(keywords.get("HS_Den", "giải ngân đến")) in s:
        return "HS_Den"
    if normalize_text(keywords.get("Tiep_Nhan", "Tiếp nhận")) in s:
        return "Tiep_Nhan"
    if normalize_text(keywords.get("Da_GN", "đã giải ngân")) in s:
        return "Da_GN"
    ky_so = normalize_text(keywords.get("Ky_So", "ký số"))
    ky_so2 = normalize_text(keywords.get("Ky_So2", "kí số"))
    if ky_so in s or ky_so2 in s:
        return "Ky_So"
    if normalize_text(keywords.get("Phe_Duyet", "phê duyệt")) in s:
        return "Phe_Duyet"
    return None


def detect_return_case(progress: str, subject: str, body: str) -> bool:
    """Detect hồ sơ chuyển trả signals from progress/subject/body."""
    joined = f"{normalize_text(progress)} {normalize_text(subject)} {normalize_text(body)}"
    return "chuyển trả" in joined


def get_room_from_body_or_cif(body: str, cif: str | None, phongban_df: pd.DataFrame) -> str | None:
    """Resolve room from mail text first, then from CIF lookup in PhongBan."""
    b = str(body).replace("_x000D_", "\n").replace("\r", "") if body else ""
    for line in b.split("\n"):
        low = line.lower()
        for kw in [" vừa chuyển", "vừa chuyển"]:
            pos = low.find(kw)
            if pos > 0:
                return line[:pos].strip()

    if not cif:
        return None
    map_df = phongban_df.copy()
    map_df["_cif"] = map_df.iloc[:, 0].astype(str).str.strip()
    m = map_df[map_df["_cif"] == str(cif).strip()]
    if m.empty:
        return None
    room_col = "TEN PHONG" if "TEN PHONG" in m.columns else m.columns[-1]
    v = m.iloc[0].get(room_col)
    return str(v).strip() if pd.notna(v) else None


def get_ldp_ksv(body: str, recipients: str, config_ld_df: pd.DataFrame) -> str | None:
    """Map LĐP/KSV by matching configured email/key against body or recipient list."""
    haystack = str(body or "")
    for _, row in config_ld_df.iterrows():
        name = row.get("Tên LĐP/KSV")
        email = row.get("Email")
        key = row.get("ID_LĐP")
        hs = haystack.lower()
        tokens = [str(email or "").strip().lower(), str(key or "").strip().lower()]
        if any(tok and tok in hs for tok in tokens):
            return str(name) if pd.notna(name) else None
    return None


def parse_email_row(row: pd.Series, keywords: dict[str, str], config_ld: pd.DataFrame, phongban: pd.DataFrame) -> dict[str, Any]:
    """Parse one Data row into extracted business fields."""
    subject = row.get("Tiêu đề")
    body = row.get("Nội dung")
    recipients = row.get("Người nhận")

    body_text = str(body) if pd.notna(body) else ""
    subject_text = str(subject) if pd.notna(subject) else ""

    if "online" in subject_text.lower():
        return {"skip": True, "reason": "subject_online"}

    ma_hs = extract_value_after_keyword(body_text, keywords.get("MaHS_M", "Mã hồ sơ:"))
    if ma_hs and " " in ma_hs:
        ma_hs = ma_hs.split(" ", 1)[0].strip()
    cif = extract_value_after_keyword(body_text, keywords.get("CIF_M", "CIF:"))
    if cif and " -" in cif:
        cif = cif.split(" -", 1)[0].strip()

    kh_line = extract_value_after_keyword(body_text, keywords.get("Khach_M", "Khách hàng:"))
    ten_kh = None
    if kh_line:
        if "- CIF" in kh_line:
            ten_kh = kh_line.split("- CIF", 1)[0].strip()
        else:
            ten_kh = kh_line.strip()
    if not ten_kh:
        return {"skip": True, "reason": "missing_customer"}

    money_line = extract_value_after_keyword(body_text, keywords.get("Tien_M", EXTRA_KEYWORDS["money_disburse"]))
    if not money_line:
        money_line = extract_value_after_keyword(body_text, keywords.get("TienVay_M", EXTRA_KEYWORDS["money_loan"]))
    so_tien = extract_money(money_line or "")

    luong = extract_value_after_keyword(body_text, keywords.get("Luong_M", "Luồng giải ngân:"))
    sla_raw = extract_value_after_keyword(body_text, keywords.get("SLA_New", "chuẩn SLA mới:"))
    if not sla_raw:
        sla_raw = extract_value_after_keyword(body_text, keywords.get("SLA_M", "chuẩn SLA:"))

    sla_dt = pd.to_datetime(sla_raw, errors="coerce", dayfirst=True)
    if pd.isna(sla_dt):
        sla_dt = pd.to_datetime(sla_raw, errors="coerce")

    stk_raw = extract_value_after_keyword(body_text, keywords.get("STK_M", "tài khoản"))
    so_tk = extract_account_number(stk_raw or "")

    cb_thuc_te = extract_value_after_keyword(body_text, keywords.get("CB_ThucTe", "bởi cán bộ:"))
    progress = extract_progress_from_subject(subject_text)
    event_type = detect_event_type(subject_text, keywords)
    is_return = detect_return_case(progress or "", subject_text, body_text)

    return {
        "skip": False,
        "subject": subject_text,
        "body": body_text,
        "recipients": str(recipients) if pd.notna(recipients) else "",
        "ma_ho_so": ma_hs,
        "cif": cif,
        "ten_kh": ten_kh,
        "so_tien_gn": so_tien,
        "luong_gn": luong,
        "sla": sla_dt if pd.notna(sla_dt) else pd.NaT,
        "so_tai_khoan": so_tk,
        "cb_thuc_te": cb_thuc_te,
        "ldp_ksv": get_ldp_ksv(body_text, str(recipients) if pd.notna(recipients) else "", config_ld),
        "phong": get_room_from_body_or_cif(body_text, cif, phongban),
        "progress": progress,
        "event_type": event_type,
        "is_return_case": is_return,
        "entry_id": row.get("EntryID"),
        "receive_time": pd.to_datetime(row.get("Thời gian nhận email"), errors="coerce"),
    }
