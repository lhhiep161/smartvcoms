from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from pathlib import Path
from typing import Any

import pandas as pd

from .assignment import assign_officer, recalculate_config_load, update_last_assigned
from ..store.config_admin import load_config_cb_from_sqlite
from ..store.sqlite_store import connect_sqlite, init_schema
from ..utils import calculate_sla_minutes_common


SUBJECT_EVENT_MAP = [
    ("vcoms_hồ sơ giải ngân đến", "ARRIVAL", "GN"),
    ("vcoms_tiếp nhận hồ sơ giải ngân", "ACCEPTED", "GN"),
    ("vcoms_thay đổi thời gian hoàn thành hồ sơ dự kiến", "SLA_CHANGED", "GN"),
    ("vcoms_chuyển trả hồ sơ giải ngân", "RETURNED", "GN"),
    ("vcoms_phê duyệt hồ sơ", "APPROVED", "GN"),
    ("vcoms_đã phê duyệt ký số", "SIGN_APPROVED", "GN"),
    ("vcoms_hồ sơ đã giải ngân", "DISBURSED", "GN"),
    ("vcoms_đã giải ngân", "DISBURSED", "GN"),
    ("vcoms_đề nghị phát hành l/c hạn mức online", "LC_REQUEST", "LC"),
]


@dataclass
class RebuildStats:
    raw_count: int = 0
    event_count: int = 0
    case_count: int = 0
    unmatched_count: int = 0
    parse_warning_count: int = 0
    lc_count: int = 0
    returned_count: int = 0
    sla_changed_count: int = 0


def _norm(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    txt = re.sub(r"\s+", " ", str(s)).strip().lower()
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode("ascii")
    return txt


def _to_dt(v: Any) -> datetime | None:
    if isinstance(v, str):
        txt = v.strip()
        if "/" in txt and "-" not in txt:
            ts = pd.to_datetime(txt, errors="coerce", dayfirst=True)
        else:
            ts = pd.to_datetime(txt, errors="coerce")
    else:
        ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()


def _parse_datetime_mixed(v: Any, fallback_date: datetime = None) -> pd.Timestamp:
    if v is None:
        return pd.NaT
    txt = str(v).strip()
    if not txt:
        return pd.NaT

    # 1. Tìm chuỗi có dạng HH:MM DD/MM/YYYY (Ví dụ: 10:07 08/04/2026)
    m = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s+(\d{1,2}/\d{1,2}/\d{4})", txt)
    if m:
        time_str, date_str = m.group(1), m.group(2)
        fmt = "%H:%M %d/%m/%Y" if len(time_str.split(":")) == 2 else "%H:%M:%S %d/%m/%Y"
        try:
            return pd.to_datetime(f"{time_str} {date_str}", format=fmt)
        except Exception:
            pass
            
    # 2. Tìm chuỗi có dạng DD/MM/YYYY HH:MM (Ví dụ: 08/04/2026 10:07)
    m2 = re.search(r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}(?::\d{2})?)", txt)
    if m2:
        date_str, time_str = m2.group(1), m2.group(2)
        fmt = "%d/%m/%Y %H:%M" if len(time_str.split(":")) == 2 else "%d/%m/%Y %H:%M:%S"
        try:
            return pd.to_datetime(f"{date_str} {time_str}", format=fmt)
        except Exception:
            pass

    if re.fullmatch(r"\d{1,2}:\d{2}", txt) and fallback_date:
        try:
            t = datetime.strptime(txt, "%H:%M").time()
            return pd.Timestamp(datetime.combine(fallback_date.date(), t))
        except Exception: pass

    # ISO first (stable, no locale ambiguity)
    iso = _to_dt(txt)
    if iso is not None:
        return pd.Timestamp(iso)
    fmts = [
        "%H:%M %d/%m/%Y",
        "%H:%M:%S %d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in fmts:
        try:
            return pd.to_datetime(txt, format=fmt, errors="raise")
        except Exception:
            continue
    return pd.to_datetime(txt, errors="coerce", dayfirst=True)


def _extract(body: str, patterns: list[str]) -> str:
    for p in patterns:
        m = re.search(p, body, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _parse_money(v: str) -> float:
    if not v:
        return 0.0
    s = str(v).strip().upper()
    s = s.replace("VND", "").replace("VNĐ", "").replace("USD", "").replace("US$", "").strip()
    s = re.sub(r"[^\d\.,-]", "", s)
    if not s:
        return 0.0
    # 1.000.000 or 1,000,000 -> 1000000
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    else:
        # fallback: remove thousands separators heuristically
        if s.count(",") > 1 and "." not in s:
            s = s.replace(",", "")
        elif s.count(".") > 1 and "," not in s:
            s = s.replace(".", "")
        elif "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s and "." not in s:
            s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_currency(text: str) -> str:
    t = _norm(text)
    if "usd" in t:
        return "USD"
    if "eur" in t:
        return "EUR"
    return "VNĐ"

def _calculate_sla_minutes(arrival_time, sla_deadline, flow_type, sla_cfg_map):
    return calculate_sla_minutes_common(arrival_time, sla_deadline, flow_type, sla_cfg_map)


def normalize_subject_for_classify(subject: str) -> str:
    s = str(subject or "").strip()
    if not s:
        return ""
    # Strip repeated mail prefixes: FW:/RE:/C.tiếp:/...
    prefixes = [
        "c.tiếp:",
        "c.tiep:",
        "fw:",
        "fwd:",
        "re:",
        "trả lời:",
        "tra loi:",
        "chuyển tiếp:",
        "chuyen tiep:",
    ]
    changed = True
    while changed and s:
        changed = False
        low = _norm(s)
        for p in prefixes:
            pn = _norm(p)
            if low.startswith(pn):
                s = s[len(s.split(":", 1)[0]) + 1 :].strip() if ":" in s else s
                changed = True
                break
    return s


def classify_event(subject: str) -> tuple[str, str, str, str]:
    sn = _norm(normalize_subject_for_classify(subject))
    if "vcoms" not in sn:
        return "UNKNOWN", "", "skip_non_vcoms", "subject_non_vcoms"
    s = sn.replace("_", " ")

    # LC first
    if "phat hanh l/c" in s or "lc han muc online" in s or "de nghi phat hanh" in s:
        return "LC_REQUEST", "LC", "ok", ""

    # Returned / changed SLA
    if "chuyen tra" in s:
        return "RETURNED", "GN", "ok", ""
    if "thay doi thoi gian hoan thanh" in s or "thay oi thoi gian hoan thanh" in s:
        return "SLA_CHANGED", "GN", "ok", ""

    # Sign approved / disbursed - tolerant for missing 'đ' after accent stripping glitches
    if "phe duyet ky so" in s or "phe duyet ki so" in s or "a phe duyet ky so" in s:
        return "SIGN_APPROVED", "GN", "ok", ""
    if ("giai ngan" in s and "ho so" in s and ("da giai ngan" in s or "ho so a giai ngan" in s or "ho so da giai ngan" in s)) or s.strip().endswith("da giai ngan"):
        return "DISBURSED", "GN", "ok", ""

    # Approved / accepted
    if "phe duyet ho so" in s:
        return "APPROVED", "GN", "ok", ""
    if "tiep nhan" in s:
        return "ACCEPTED", "GN", "ok", ""

    # Arrival tolerant: e.g. "ho so giai ngan en" when 'đ' is mangled
    if "ho so" in s and "giai ngan" in s and (" den" in s or " en" in s or s.endswith("den") or s.endswith("en")):
        return "ARRIVAL", "GN", "ok", ""

    return "UNKNOWN", "", "unmatched", "subject_not_mapped"


def _load_routing_rules(conn: sqlite3.Connection) -> list[dict]:
    try:
        rows = conn.execute("SELECT keyword, flow_type, auto_close_at_stage FROM vcoms_routing_rules WHERE is_active=1").fetchall()
        return [{"keyword": r[0], "flow_type": r[1], "auto_close": r[2]} for r in rows]
    except Exception: return []

def _load_assignment_rules(conn: sqlite3.Connection) -> list[dict]:
    try:
        rows = conn.execute("SELECT flow_type, room_name, assigned_officers FROM vcoms_assignment_rules WHERE is_active=1").fetchall()
        return [{"flow_type": r[0], "room_name": r[1], "assigned_officers": r[2]} for r in rows]
    except Exception: return []

def _evaluate_flow_type(body: str, subject: str, rules: list[dict]) -> str:
    text = f"{_norm(subject)} {_norm(body)}"
    for r in rules:
        kw = _norm(r.get("keyword", ""))
        if kw and kw in text:
            return str(r.get("flow_type", "GN_THONG_THUONG")).upper()
    if "online" in text: return "GN_ONLINE_KHDN"
    if "l/c" in text or "lc " in text: return "LC_ONLINE"
    if "bảo lãnh" in text or "bao lanh" in text: return "BL"
    return "GN_THONG_THUONG"

def _evaluate_assignment(flow: str, room: str, rules: list[dict], cb_cfg: pd.DataFrame) -> str:
    room_norm = _norm(room)
    specific_rules, default_rules = [], []
    for r in rules:
        if str(r.get("flow_type", "")).upper() == str(flow).upper():
            r_room = _norm(r.get("room_name", ""))
            if r_room and (r_room in room_norm or room_norm in r_room): specific_rules.append(r)
            elif not r_room: default_rules.append(r)
    
    for r in specific_rules + default_rules:
        cb_id = str(r.get("assigned_officers", "")).strip()
        if not cb_id: continue
        if not cb_cfg.empty and "ID_CB" in cb_cfg.columns:
            hit = cb_cfg[cb_cfg["ID_CB"].astype(str).str.strip() == cb_id]
            if not hit.empty and str(hit.iloc[0].get("Trạng thái", "Ready")).strip().lower() == "ready":
                return cb_id
    return ""


def _required_arrival_count(flow_type: str, ldp_count: int) -> int:
    if ldp_count <= 0:
        ldp_count = 1
    return ldp_count * 2 if "ONLINE" in str(flow_type).upper() else ldp_count


def _normalize_officer_id(officer_value: str, cb_cfg: pd.DataFrame) -> str:
    val = str(officer_value or "").strip()
    if not val or cb_cfg is None or cb_cfg.empty:
        return val
    if "ID_CB" in cb_cfg.columns and "Tên Cán bộ" in cb_cfg.columns:
        cb = cb_cfg.copy()
        cb["ID_CB"] = cb["ID_CB"].astype(str).str.strip()
        cb["Tên Cán bộ"] = cb["Tên Cán bộ"].astype(str).str.strip()
        hit = cb[cb["ID_CB"].str.upper() == val.upper()]
        if not hit.empty:
            return str(hit.iloc[0].get("ID_CB") or "").strip() or val
        hit = cb[cb["Tên Cán bộ"].str.upper() == val.upper()]
        if not hit.empty:
            return str(hit.iloc[0].get("ID_CB") or "").strip() or val
    return val


def _is_business_customer(customer_name: str, dn_prefixes: list[str]) -> bool:
    name = _norm(customer_name)
    if not name:
        return False
    for p in dn_prefixes:
        if name.startswith(_norm(p)):
            return True
    return False


def _load_sla_config_map(conn: sqlite3.Connection) -> dict:
    try:
        rows = conn.execute("SELECT key, value FROM sla_config").fetchall()
        return {str(k).strip().upper(): str(v).strip() for k, v in rows}
    except Exception: return {}


def _resolve_room_for_case(
    room_current: str,
    room_from_body: str,
    cif: str,
    room_mapping_by_cif: dict[str, str],
    old_processed_room_by_cif: dict[str, str],
    latest_room_by_cif: dict[str, str],
) -> tuple[str, str]:
    def _valid_room(val: Any) -> str:
        txt = str(val or "").strip()
        if not txt:
            return ""
        # Never use HTTD department labels as customer room.
        if "HTTD" in _norm(txt):
            return ""
        return txt

    room0 = _valid_room(room_current)
    if room0:
        return room0, "existing"
    room1 = _valid_room(room_from_body)
    if room1:
        return room1, "body"
    c = str(cif or "").strip()
    if not c:
        return "", "missing"
    for src, mp in (
        ("room_mapping", room_mapping_by_cif),
        ("dashboard_records_processed", old_processed_room_by_cif),
        ("history", latest_room_by_cif),
    ):
        val = _valid_room((mp or {}).get(c))
        if val:
            return val, src
    return "", "missing"


def _resolve_customer_for_case(
    customer_current: str,
    customer_parsed: str,
    cif: str,
    old_processed_customer_by_cif: dict[str, str],
    latest_customer_by_cif: dict[str, str],
) -> tuple[str, str]:
    c0 = str(customer_current or "").strip()
    if c0:
        return c0, "existing"
    c1 = str(customer_parsed or "").strip()
    if c1:
        return c1, "parsed"
    k = str(cif or "").strip()
    if not k:
        return "", "missing"
    for src, mp in (
        ("dashboard_records_processed", old_processed_customer_by_cif),
        ("history", latest_customer_by_cif),
    ):
        v = str((mp or {}).get(k) or "").strip()
        if v:
            return v, src
    return "", "missing"


def _stage_for_event(event_type: str, flow_type: str) -> tuple[str, str, str, int]:
    # stage_code, stage_label, current_status, is_open
    if event_type == "ARRIVAL":
        if "ONLINE" in str(flow_type).upper():
            return "ARRIVAL", "Hồ sơ đến", "OPEN", 1
        return "WAIT_ACCEPT", "Chờ tiếp nhận", "OPEN", 1
    if event_type == "ACCEPTED":
        return "PROCESSING", "Đang xử lý", "OPEN", 1
    if event_type == "APPROVED":
        if "ONLINE" in str(flow_type).upper():
            return "WAIT_SIGN", "Chờ BGĐ ký số", "OPEN", 1
        return "WAIT_MANUAL_DONE", "Chờ hoàn tất thủ công", "OPEN", 1
    if event_type == "SIGN_APPROVED":
        return "WAIT_DISBURSE", "Chờ giải ngân", "OPEN", 1
    if event_type == "DISBURSED":
        return "DONE", "Hoàn thành", "CLOSED", 0
    if event_type == "RETURNED":
        return "DONE", "Hoàn thành", "CLOSED", 0
    if event_type == "LC_REQUEST":
        return "PROCESSING", "Đang xử lý", "OPEN", 1
    return "PROCESSING", "Đang xử lý", "OPEN", 1


def _load_raw(conn: sqlite3.Connection, today_only: bool = False, target_date: str = None) -> pd.DataFrame:
    sql = "SELECT * FROM outlook_raw_emails ORDER BY received_time, id"
    df = pd.read_sql_query(sql, conn)
    if target_date and not df.empty:
        df["date_only"] = pd.to_datetime(df["received_time"], errors="coerce").dt.date.astype(str)
        df = df[df["date_only"] == target_date].copy()
        df = df.drop(columns=["date_only"])
    elif today_only and not df.empty:
        start = datetime.combine(datetime.today().date(), datetime.min.time())
        end = start + timedelta(days=1)
        rt = pd.to_datetime(df.get("received_time"), errors="coerce")
        df = df[(rt >= start) & (rt < end)].copy()
    return df


def _next_case_key(biz: str, cif: str, amount: float, flow: str, product: str, block_index: int) -> str:
    cif_key = cif or "NO_CIF"
    amt_key = int(amount) if amount else 0
    return f"{biz}|{product}|{flow}|{cif_key}|{amt_key}|B{block_index}"


def _ensure_event_dedupe_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vcoms_email_events)").fetchall()}
    add_cols = []
    if "is_canonical" not in cols:
        add_cols.append('ALTER TABLE vcoms_email_events ADD COLUMN is_canonical INTEGER DEFAULT 1')
    if "canonical_event_key" not in cols:
        add_cols.append('ALTER TABLE vcoms_email_events ADD COLUMN canonical_event_key TEXT')
    if "duplicate_of_event_id" not in cols:
        add_cols.append('ALTER TABLE vcoms_email_events ADD COLUMN duplicate_of_event_id INTEGER')
    if "dedupe_reason" not in cols:
        add_cols.append('ALTER TABLE vcoms_email_events ADD COLUMN dedupe_reason TEXT')
    for sql in add_cols:
        conn.execute(sql)


def _ensure_case_state_extra_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(vcoms_case_state)").fetchall()}
    if "room_lookup_source" not in cols:
        conn.execute("ALTER TABLE vcoms_case_state ADD COLUMN room_lookup_source TEXT")
    if "account_number" not in cols:
        conn.execute("ALTER TABLE vcoms_case_state ADD COLUMN account_number TEXT")


def _backfill_missing_arrival_from_family(
    conn: sqlite3.Connection,
    cases: dict[str, dict[str, Any]],
) -> None:
    """Backfill ARRIVAL for progressed cases when ARRIVAL was deduped to sibling case."""
    if not cases:
        return
    for case_key, case in cases.items():
        if str(case.get("arrival_time") or "").strip():
            continue
        if not (
            case.get("accepted_time")
            or case.get("approved_time")
            or case.get("sign_time")
            or case.get("disbursed_time")
        ):
            continue

        biz = str(case.get("business_date") or "").strip()
        product = str(case.get("product_type") or "").strip()
        flow = str(case.get("flow_type") or "").strip()
        ma_hs = str(case.get("ma_ho_so") or "").strip()
        cif = str(case.get("cif") or "").strip()
        amount = float(case.get("amount") or 0.0)
        target_ts = pd.to_datetime(
            case.get("accepted_time")
            or case.get("approved_time")
            or case.get("sign_time")
            or case.get("disbursed_time")
            or case.get("last_event_time"),
            errors="coerce",
        )

        if not biz or not product or not flow:
            continue

        sql = """
        SELECT id, received_time, case_key, dedupe_reason
        FROM vcoms_email_events
        WHERE event_type='ARRIVAL'
          AND date(received_time)=?
          AND COALESCE(product_type,'')=?
          AND COALESCE(flow_type,'')=?
          AND (
            (COALESCE(ma_ho_so,'')<>'' AND ma_ho_so=?)
            OR (COALESCE(cif,'')<>'' AND cif=? AND ABS(COALESCE(amount,0)-?)<=1.0)
          )
        ORDER BY datetime(received_time) ASC, id ASC
        """
        cand = pd.read_sql_query(sql, conn, params=[biz, product, flow, ma_hs, cif, amount])
        if cand.empty:
            continue
        cand["received_ts"] = pd.to_datetime(cand["received_time"], errors="coerce")
        cand = cand.dropna(subset=["received_ts"])
        if cand.empty:
            continue

        chosen = None
        if pd.notna(target_ts):
            prior = cand[cand["received_ts"] <= target_ts]
            if not prior.empty:
                chosen = prior.iloc[-1]
        if chosen is None:
            chosen = cand.iloc[0]

        arr_ts = pd.to_datetime(chosen["received_time"], errors="coerce")
        if pd.isna(arr_ts):
            continue
        case["arrival_time"] = arr_ts.isoformat()
        case["arrival_event_count"] = max(int(case.get("arrival_event_count") or 0), 1)

        ev_id = int(chosen["id"])
        src_case = str(chosen.get("case_key") or "").strip()
        if src_case != case_key:
            conn.execute("UPDATE vcoms_email_events SET case_key=? WHERE id=?", (case_key, ev_id))
        old_reason = str(chosen.get("dedupe_reason") or "").strip()
        if "relinked_missing_arrival_case" not in old_reason:
            new_reason = (old_reason + ";" if old_reason else "") + "relinked_missing_arrival_case"
            conn.execute("UPDATE vcoms_email_events SET dedupe_reason=? WHERE id=?", (new_reason, ev_id))


def _backfill_missing_room_from_case_raw(
    conn: sqlite3.Connection,
    cases: dict[str, dict[str, Any]],
) -> None:
    room_patterns = [
        r"(Phòng[^\n\r]+)\s+vừa\s+chuyển",
        r"(PGD[^\n\r]+)\s+vừa\s+chuyển",
    ]
    for case_key, case in cases.items():
        if str(case.get("room") or "").strip():
            continue
        raw_rows = pd.read_sql_query(
            """
            SELECT r.body
            FROM vcoms_email_events e
            JOIN outlook_raw_emails r ON r.id = e.raw_id
            WHERE e.case_key = ?
            ORDER BY datetime(e.received_time), e.id
            """,
            conn,
            params=[case_key],
        )
        if raw_rows.empty:
            continue
        room_found = ""
        for _, rr in raw_rows.iterrows():
            room_found = _extract(str(rr.get("body") or ""), room_patterns)
            if str(room_found or "").strip():
                break
        if room_found:
            case["room"] = str(room_found).strip()
            case["room_lookup_source"] = "raw_event_body"


def _load_active_manual_actions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    try:
        cursor = conn.execute(
            """
            SELECT id, case_key, business_date, cif, ma_ho_so, amount, flow_type, action_type, action_time, action_by, note
            FROM vcoms_manual_case_actions
            WHERE COALESCE(is_active, 1) = 1
              AND UPPER(COALESCE(action_type,'')) IN ('MANUAL_DONE', 'MANUAL_WAIT_DISBURSE')
            ORDER BY id
            """
        )
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(dict(zip(cols, r)))
    return out


def _apply_manual_actions_to_cases(cases: dict[str, dict[str, Any]], actions: list[dict[str, Any]]) -> int:
    if not cases or not actions:
        return 0
    applied = 0

    def _match_score(case: dict[str, Any], act: dict[str, Any]) -> int:
        score = 0
        if str(case.get("business_date") or "") == str(act.get("business_date") or ""):
            score += 2
        if str(case.get("flow_type") or "") == str(act.get("flow_type") or ""):
            score += 2
        if str(case.get("cif") or "") and str(case.get("cif") or "") == str(act.get("cif") or ""):
            score += 2
        if str(case.get("ma_ho_so") or "") and str(case.get("ma_ho_so") or "") == str(act.get("ma_ho_so") or ""):
            score += 3
        try:
            if int(float(case.get("amount") or 0)) == int(float(act.get("amount") or 0)):
                score += 2
        except Exception:
            pass
        if str(case.get("completion_type") or "").upper() == "RETURNED":
            score -= 3
        if int(case.get("is_open") or 0) == 1:
            score += 1
        return score

    actions_sorted = sorted(
        actions,
        key=lambda a: (
            pd.to_datetime(a.get("action_time"), errors="coerce") if a.get("action_time") else pd.Timestamp.min,
            int(a.get("id") or 0),
        ),
    )

    for act in actions_sorted:
        action_time = str(act.get("action_time") or datetime.now().isoformat(timespec="seconds"))
        action_dt = pd.to_datetime(action_time, errors="coerce")
        action_by = str(act.get("action_by") or "manual")
        action_note = str(act.get("note") or "").strip()
        action_type = str(act.get("action_type") or "").upper()
        target_key = str(act.get("case_key") or "").strip()

        target_case = None
        if target_key and target_key in cases:
            target_case = cases[target_key]
        else:
            candidates = [
                c for c in cases.values()
                if str(c.get("current_stage_code") or "").upper() in {"WAIT_MANUAL_DONE", "PROCESSING", "WAIT_SIGN", "WAIT_DISBURSE"}
                or int(c.get("is_open") or 0) == 1
            ]
            if not candidates:
                candidates = list(cases.values())
            ranked = sorted(candidates, key=lambda c: _match_score(c, act), reverse=True)
            if ranked and _match_score(ranked[0], act) >= 5:
                target_case = ranked[0]

        if target_case is None:
            continue

        # Auto events after action time win over MANUAL_WAIT_DISBURSE.
        case_last_event_dt = pd.to_datetime(target_case.get("last_event_time"), errors="coerce")
        last_event_type = str(target_case.get("last_event_type") or "").upper()
        has_later_auto_close = (
            pd.notna(case_last_event_dt)
            and pd.notna(action_dt)
            and case_last_event_dt > action_dt
            and last_event_type in {"DISBURSED", "RETURNED"}
        )

        if action_type == "MANUAL_WAIT_DISBURSE":
            if has_later_auto_close:
                continue
            target_case["current_stage_code"] = "WAIT_DISBURSE"
            target_case["current_stage_label"] = "Chờ giải ngân"
            target_case["current_status"] = "OPEN"
            target_case["is_open"] = 1
            target_case["completion_type"] = ""
        else:
            target_case["current_stage_code"] = "DONE"
            target_case["current_stage_label"] = "Hoàn thành"
            target_case["current_status"] = "CLOSED"
            target_case["is_open"] = 0
            target_case["completion_type"] = "MANUAL_DONE"
            target_case["manual_completed_time"] = action_time
            target_case["manual_finish_time"] = action_time
            target_case["completed_time"] = action_time
        target_case["updated_by"] = action_by
        if action_note:
            old_note = str(target_case.get("note") or "").strip()
            target_case["note"] = (old_note + " | " if old_note else "") + f"{action_type.lower()}:{action_note}"
        target_case["updated_at"] = datetime.now().isoformat(timespec="seconds")
        applied += 1
    return applied


def _build_event_group_key(
    biz: str,
    product_type: str,
    flow: str,
    cif: str,
    amount: float,
    ma_hs: str,
) -> str:
    return "|".join(
        [
            biz,
            product_type or "GN",
            flow or "",
            (cif or "").strip(),
            str(int(amount or 0)),
            (ma_hs or "").strip(),
        ]
    )


def _build_canonical_event_key(
    event_type: str,
    biz: str,
    product_type: str,
    flow: str,
    ma_hs: str,
    cif: str,
    amount: float,
    body_hash: str,
    conversation_id: str,
    subject_norm: str,
) -> str:
    anchor = (ma_hs or "").strip() or (cif or "").strip() or "NO_ANCHOR"
    signal = (body_hash or "").strip() or (conversation_id or "").strip() or (subject_norm or "")
    return "::".join(
        [
            (event_type or "").upper(),
            biz,
            product_type or "GN",
            flow or "",
            anchor,
            str(int(amount or 0)),
            signal,
        ]
    )


def _find_or_create_case(
    cases: dict[str, dict[str, Any]],
    group_open_keys: dict[tuple[str, str, str, str, int], list[str]],
    by_ma_hs: dict[str, str],
    biz: str,
    ma_hs: str,
    cif: str,
    amount: float,
    flow_type: str,
    product_type: str,
    block_size: int,
    event_type: str = "",
) -> str:
    event_up = str(event_type or "").upper()
    gk = (biz, product_type, flow_type, cif or "", int(amount or 0))
    keys = group_open_keys[gk]

    def _latest_open_key() -> str:
        for k in reversed(keys):
            c_latest = cases.get(k)
            if c_latest is not None and int(c_latest.get("is_open") or 0) == 1:
                return k
        return ""

    if ma_hs and ma_hs in by_ma_hs:
        key = by_ma_hs[ma_hs]
        c = cases.get(key)
        completion_up = str((c or {}).get("completion_type") or "").upper()
        is_closed = bool(c is not None and int(c.get("is_open") or 0) == 0)
        is_returned_closed = bool(is_closed and completion_up == "RETURNED")

        if c is not None and str(c.get("business_date") or "") == str(biz or ""):
            # Case đã CLOSED thì không cập nhật tiếp bằng event tiến trình mới.
            # Nếu có cycle OPEN cùng nhóm, reroute event sang cycle OPEN đó.
            if is_closed:
                if is_returned_closed and event_up in {"ARRIVAL", "LC_REQUEST", "ACCEPTED"}:
                    # Hồ sơ bị chuyển trả rồi gửi lại: cho phép tạo hoặc dùng cycle mới.
                    pass
                else:
                    open_key = _latest_open_key()
                    if open_key:
                        by_ma_hs[ma_hs] = open_key
                        return open_key
                    return key
            else:
                return key

        if c is not None and int(c.get("is_open") or 0) == 1:
            return key

        # Với event tiến trình không phải mở hồ sơ, ưu tiên case OPEN mới nhất cùng nhóm.
        if c is not None and event_up not in {"ARRIVAL", "LC_REQUEST", "ACCEPTED"}:
            open_key = _latest_open_key()
            if open_key:
                by_ma_hs[ma_hs] = open_key
                return open_key
            return key

    if keys:
        last_key = keys[-1]
        c = cases[last_key]

        if int(c.get("is_open") or 0) == 1:
            # Event tiến trình sau ARRIVAL/ACCEPTED phải bám vào case OPEN hiện tại.
            # Không tạo block mới và không quay lại block CLOSED.
            if event_up not in {"ARRIVAL", "LC_REQUEST"}:
                if ma_hs:
                    by_ma_hs[ma_hs] = last_key
                return last_key

            # ARRIVAL/LC_REQUEST vẫn gom vào block hiện tại nếu chưa đủ số arrival cần thiết.
            if int(c.get("arrival_event_count") or 0) < block_size:
                if ma_hs:
                    by_ma_hs[ma_hs] = last_key
                return last_key

    block_index = len(keys) + 1
    case_key = _next_case_key(biz, cif, amount, flow_type, product_type, block_index)
    group_open_keys[gk].append(case_key)
    if ma_hs:
        by_ma_hs[ma_hs] = case_key
    return case_key

def rebuild_from_raw(
    db_path: str | Path,
    reset: bool = False,
    today_only: bool = False,
    verbose: bool = False,
    target_date: str = None,
    interactive: bool = False,
) -> RebuildStats:
    conn = connect_sqlite(db_path)
    init_schema(conn)
    _ensure_event_dedupe_columns(conn)
    _ensure_case_state_extra_columns(conn)
    stats = RebuildStats()

    with conn:
        if reset:
            conn.execute("DELETE FROM vcoms_email_events")
            conn.execute("DELETE FROM vcoms_case_state")
        raw_df = _load_raw(conn, today_only=today_only, target_date=target_date)
        stats.raw_count = len(raw_df)

        cb_cfg = load_config_cb_from_sqlite(db_path, active_only=True)
        routing_rules = _load_routing_rules(conn)
        assignment_rules = _load_assignment_rules(conn)

        sla_cfg_map = _load_sla_config_map(conn)
        prefix_str = sla_cfg_map.get("DN_PREFIX", "CÔNG TY TNHH MTV, CONG TY TNHH MTV, CTY TNHH MTV, CT TNHH MTV, CÔNG TY TNHH, CONG TY TNHH, CTY TNHH, CT TNHH, CÔNG TY CỔ PHẦN, CONG TY CO PHAN, CTCP, CÔNG TY CP, CONG TY CP, CÔNG TY, CONG TY, CTY, CT, DNTN, DOANH NGHIEP")
        dn_prefixes = [p.strip() for p in prefix_str.split(",") if p.strip()]

        room_mapping_by_cif: dict[str, str] = {}
        old_processed_room_by_cif: dict[str, str] = {}
        old_processed_customer_by_cif: dict[str, str] = {}
        latest_room_by_cif: dict[str, str] = {}
        latest_customer_by_cif: dict[str, str] = {}
        try:
            rm_df = pd.read_sql_query(
                "SELECT cif, COALESCE(room_name, room_code, '') AS room FROM room_mapping",
                conn,
            )
            if not rm_df.empty:
                for _, rr in rm_df.iterrows():
                    c = str(rr.get("cif") or "").strip()
                    r = str(rr.get("room") or "").strip()
                    if c and r and c not in room_mapping_by_cif:
                        room_mapping_by_cif[c] = r
        except Exception:
            pass
        try:
            old_df = pd.read_sql_query(
                'SELECT "CIF" AS cif, "Phòng" AS room, "Tên KH" AS customer_name FROM dashboard_records_processed',
                conn,
            )
            if not old_df.empty:
                for _, rr in old_df.iterrows():
                    c = str(rr.get("cif") or "").strip()
                    r = str(rr.get("room") or "").strip()
                    n = str(rr.get("customer_name") or "").strip()
                    if c and r and c not in old_processed_room_by_cif:
                        old_processed_room_by_cif[c] = r
                    if c and n and c not in old_processed_customer_by_cif:
                        old_processed_customer_by_cif[c] = n
        except Exception:
            pass
        ldp_count = int(conn.execute("SELECT COUNT(*) FROM config_ld WHERE COALESCE(is_active,1)=1").fetchone()[0])
        if ldp_count <= 0:
            ldp_count = 1

        cases: dict[str, dict[str, Any]] = {}
        group_open_keys: dict[tuple[str, str, str, str, int], list[str]] = defaultdict(list)
        by_ma_hs: dict[str, str] = {}
        sender_arrival_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        seen_opening_keys: dict[str, int] = {}
        latest_event_id_by_case_key: dict[str, int] = {}
        stt_counter = 1

        for _, r in raw_df.iterrows():
            subject = str(r.get("subject") or "")
            body = str(r.get("body") or "")
            event_type, product_type, parse_status, parse_warning = classify_event(subject)
            received_dt = _to_dt(r.get("received_time")) or datetime.now()
            biz = received_dt.date().isoformat()

            import html
            clean_body = html.unescape(str(body)).replace('\xa0', ' ')
            clean_body = re.sub(r'<[^>]+>', ' ', clean_body)
            
            ma_hs_raw = _extract(clean_body, [r"Mã hồ sơ\s*:\s*([^\n\r]+)"])
            ma_hs = ma_hs_raw.split()[0] if ma_hs_raw else ""
            cif = _extract(clean_body, [r"CIF\s*:\s*([0-9]+)"])
            cust = _extract(clean_body, [r"Khách hàng\s*:\s*([^\n\r]+)", r"Khách hàng yêu cầu\s*:\s*([^\n\r]+)"])
            if "- CIF" in cust:
                cust = cust.split("- CIF", 1)[0].strip()
            amount_raw = _extract(clean_body, [r"Số tiền giải ngân\s*:\s*([^\n\r]+)", r"Số tiền vay\s*:\s*([^\n\r]+)", r"Số tiền\s*:\s*([^\n\r]+)", r"tiền giải ngân\s*:\s*([^\n\r]+)", r"tiền vay\s*:\s*([^\n\r]+)"])
            amount = _parse_money(amount_raw)
            currency = _parse_currency(amount_raw)
            flow = _evaluate_flow_type(clean_body, subject, routing_rules)
            
            body_norm = _norm(clean_body)
            acc_match = re.search(r"tai khoan vay[^\d]*(\d{9,15})", body_norm)
            if not acc_match:
                acc_match = re.search(r"tai khoan[^\d]*(\d{9,15})", body_norm)
            account = acc_match.group(1) if acc_match else ""
            
            officer = _normalize_officer_id(
                _extract(clean_body, [r"Hồ sơ được xử lý bởi cán bộ\s*:\s*([^\n\r]+)", r"bởi cán bộ\s*:\s*([^\n\r]+)", r"cán bộ\s*:\s*([^\n\r]+)"]),
                cb_cfg,
            )
            supervisor = _extract(clean_body, [r"LĐP/KSV\s*:\s*([^\n\r]+)"])
            return_reason = _extract(clean_body, [r"Lý do chuyển trả\s*:\s*([^\n\r]+)", r"lý do\s*:\s*([^\n\r]+)"])
            external_ref = _extract(clean_body, [r"Mã eFAST/ERP\s*:\s*([^\n\r]+)", r"Mã IPAY\s*:\s*([^\n\r]+)"])
            external_ref_type = "EFAST_ERP" if "efast" in _norm(clean_body) or "erp" in _norm(clean_body) else ("IPAY" if "ipay" in _norm(clean_body) else "")
            sla_deadline_raw = _extract(clean_body, [r"Thời điểm hoàn thành theo chuẩn SLA mới\s*:\s*([^\n\r]+)", r"Thời điểm hoàn thành theo chuẩn SLA ban đầu\s*:\s*([^\n\r]+)", r"Thời điểm hoàn thành dự kiến theo chuẩn SLA\s*:\s*([^\n\r]+)", r"SLA mới\s*:\s*([^\n\r]+)", r"chuẩn SLA\s*:\s*([^\n\r]+)"])
            sla_deadline = _parse_datetime_mixed(sla_deadline_raw, fallback_date=received_dt)

            normalized_subject = normalize_subject_for_classify(subject)
            prefixed_subject = _norm(normalized_subject) != _norm(subject)
            conversation_id = str(r.get("conversation_id") or "").strip()
            body_hash = str(r.get("body_hash") or "").strip()
            canonical_event_key = _build_canonical_event_key(
                event_type,
                biz,
                product_type or "GN",
                flow,
                ma_hs,
                cif,
                amount,
                body_hash,
                conversation_id,
                _norm(normalized_subject),
            )
            event_group_key = _build_event_group_key(biz, product_type or "GN", flow, cif, amount, ma_hs)

            is_canonical = 1
            dedupe_reason = ""
            duplicate_of_event_id = None

            case_key = ""
            block_index = 0
            arrival_seq = 0
            sender_arrival_count = 0
            # LC lookup from nearest historical case by CIF
            if (not cust or not str(cust).strip()) and cif:
                hist = [c for c in cases.values() if str(c.get("cif") or "").strip() == cif and str(c.get("customer_name") or "").strip()]
                if hist:
                    hist_sorted = sorted(hist, key=lambda c: (str(c.get("business_date") or ""), str(c.get("last_event_time") or "")), reverse=True)
                    cust = str(hist_sorted[0].get("customer_name") or "").strip()
            room_detected = _extract(
                clean_body,
                [
                    r"(Phòng[^\n\r]+)\s+vừa\s+chuyển",
                    r"(PGD[^\n\r]+)\s+vừa\s+chuyển",
                ],
            )
            if (not room_detected or not str(room_detected).strip()) and cif:
                hist_room = [c for c in cases.values() if str(c.get("cif") or "").strip() == cif and str(c.get("room") or "").strip()]
                if hist_room:
                    hist_sorted = sorted(hist_room, key=lambda c: (str(c.get("business_date") or ""), str(c.get("last_event_time") or "")), reverse=True)
                    room_detected = str(hist_sorted[0].get("room") or "").strip()
                    
            room_resolved = room_detected or ""
            cust_resolved = cust or ""

            if parse_status in {"ok", "partial"}:
                missing_fields = []
                if not cif:
                    missing_fields.append("cif")
                if not cust:
                    missing_fields.append("customer_name")
                if not amount:
                    missing_fields.append("amount")
                if missing_fields:
                    parse_status = "partial"
                    parse_warning = f"missing:{','.join(missing_fields)}"

            if parse_status in {"ok", "partial"}:
                gk_pref = (biz, product_type or "GN", flow, cif or "", int(amount or 0))
                existing_group_keys = group_open_keys.get(gk_pref) or []
                
                # --- NEW FALLBACK TO PREVENT ORPHAN EVENTS ---
                if not (ma_hs and ma_hs in by_ma_hs) and not existing_group_keys and cif and event_type not in {"ARRIVAL", "LC_REQUEST", "ACCEPTED"}:
                    fallback_keys = [
                        k for k, c_item in cases.items()
                        if c_item.get("business_date") == biz and str(c_item.get("cif", "")).strip() == cif and int(c_item.get("is_open", 0)) == 1
                    ]
                    if fallback_keys:
                        existing_group_keys = [fallback_keys[-1]]

                has_existing_ref = bool((ma_hs and ma_hs in by_ma_hs) or existing_group_keys)
                is_reopen_after_returned = False
                if event_type in {"ARRIVAL", "LC_REQUEST", "ACCEPTED"}:
                    candidate_keys = []
                    if ma_hs and ma_hs in by_ma_hs:
                        candidate_keys.append(by_ma_hs.get(ma_hs, ""))
                    if existing_group_keys:
                        candidate_keys.append(existing_group_keys[-1])
                    for ck in candidate_keys:
                        c_prev = cases.get(ck or "")
                        if c_prev is None:
                            continue
                        if (
                            int(c_prev.get("is_open") or 0) == 0
                            and str(c_prev.get("completion_type") or "").upper() == "RETURNED"
                        ):
                            is_reopen_after_returned = True
                            break

                if event_type in {"ARRIVAL", "LC_REQUEST"}:
                    if canonical_event_key in seen_opening_keys:
                        is_canonical = 0
                        dedupe_reason = "duplicate_opening_event_key"
                        duplicate_of_event_id = seen_opening_keys.get(canonical_event_key)
                    elif prefixed_subject and (ma_hs and ma_hs in by_ma_hs) and not is_reopen_after_returned:
                        is_canonical = 0
                        dedupe_reason = "prefixed_secondary_same_ma_hs"
                        duplicate_of_event_id = latest_event_id_by_case_key.get(by_ma_hs.get(ma_hs, ""))
                    elif prefixed_subject and event_group_key and existing_group_keys and not is_reopen_after_returned:
                        is_canonical = 0
                        dedupe_reason = "prefixed_secondary_same_group"
                        duplicate_of_event_id = latest_event_id_by_case_key.get(existing_group_keys[-1])

                # Non-opening events are not allowed to create brand new business case.
                # They must attach to an existing case reference (by ma_hs/group), except ACCEPTED
                # which may arrive before ARRIVAL and should still create case.
                opening_or_primary_events = {"ARRIVAL", "ACCEPTED", "APPROVED", "LC_REQUEST"}
                if event_type not in opening_or_primary_events and not has_existing_ref:
                    is_canonical = 0
                    if not dedupe_reason:
                        dedupe_reason = "orphan_non_opening_event_without_case"

                if is_canonical == 0:
                    if ma_hs and ma_hs in by_ma_hs:
                        case_key = by_ma_hs.get(ma_hs, "")
                    else:
                        if existing_group_keys:
                            case_key = existing_group_keys[-1]

                    # For ARRIVAL duplicates, still backfill arrival on target case if missing.
                    if event_type == "ARRIVAL" and case_key and case_key in cases:
                        tgt = cases[case_key]
                        if not str(tgt.get("arrival_time") or "").strip():
                            tgt["arrival_time"] = received_dt.isoformat()
                            
                        # Luôn luôn cộng bộ đếm và check Sender cho dù là email gom nhóm
                        tgt["arrival_event_count"] = int(tgt.get("arrival_event_count") or 0) + 1
                        sender_key = (case_key, str(r.get("sender_email") or r.get("sender_name") or "").strip().lower())
                        sender_arrival_counts[sender_key] += 1
                        sender_arrival_count = sender_arrival_counts[sender_key]
                        
                        flow_tgt = str(tgt.get("flow_type") or "")
                        if "ONLINE" in flow_tgt.upper() and sender_arrival_count >= 2 and tgt.get("current_stage_code") in {"ARRIVAL", "WAIT_ACCEPT"}:
                            tgt["current_stage_code"] = "WAIT_ACCEPT"
                            tgt["current_stage_label"] = "Chờ tiếp nhận"
                        elif "ONLINE" not in flow_tgt.upper() and tgt.get("current_stage_code") == "ARRIVAL":
                            tgt["current_stage_code"] = "WAIT_ACCEPT"
                            tgt["current_stage_label"] = "Chờ tiếp nhận"
                            
                        tgt["last_event_time"] = received_dt.isoformat()
                        tgt["last_event_type"] = event_type
                        tgt["updated_at"] = datetime.now().isoformat(timespec="seconds")
                        if not dedupe_reason:
                            dedupe_reason = "duplicate_arrival_backfilled"
                elif is_reopen_after_returned and event_type in {"ARRIVAL", "LC_REQUEST", "ACCEPTED"}:
                    # Explicit marker for new business cycle after a returned closure.
                    dedupe_reason = "new_cycle_after_returned"

            if parse_status in {"ok", "partial"} and is_canonical == 1:
                req_count = _required_arrival_count(flow, ldp_count)
                case_key = _find_or_create_case(
                    cases,
                    group_open_keys,
                    by_ma_hs,
                    biz,
                    ma_hs,
                    cif,
                    amount,
                    flow,
                    product_type or "GN",
                    req_count,
                    event_type,
                )
                block_index = int(case_key.rsplit("|B", 1)[-1]) if "|B" in case_key else 1

                case = cases.get(case_key)
                if case is None:
                    stage_code, stage_label, curr_status, is_open = _stage_for_event(event_type, flow)
                    assigned = officer.strip()
                    if not assigned:
                        rule_assigned = _evaluate_assignment(flow, room_detected or "", assignment_rules, cb_cfg)
                        if rule_assigned:
                            assigned = _normalize_officer_id(rule_assigned, cb_cfg)
                        else:
                            cb_cfg = recalculate_config_load(cb_cfg, pd.DataFrame([c for c in cases.values()]))
                            suggested = ""
                            if cif:
                                same_cif = [c for c in cases.values() if c.get("business_date") == biz and str(c.get("cif") or "").strip() == cif]
                                if same_cif:
                                    suggested = str(same_cif[-1].get("assigned_officer") or "")
                            assigned = assign_officer({"cif": cif, "so_tien_gn": amount}, pd.DataFrame([c for c in cases.values()]), cb_cfg, suggested_cb=suggested) or ""
                            assigned = _normalize_officer_id(assigned, cb_cfg)
                        cb_cfg = update_last_assigned(cb_cfg, assigned, received_dt)

                    case = {
                        "case_key": case_key,
                        "business_date": biz,
                        "block_index": block_index,
                        "product_type": product_type or "GN",
                        "ma_ho_so": ma_hs,
                        "cif": cif,
                        "customer_name": cust,
                        "room": room_detected or "",
                        "amount": amount,
                        "currency": currency,
                        "flow_type": flow,
                        "account_number": account,
                        "assigned_officer": assigned,
                        "supervisor_name": supervisor,
                        "current_stage_code": stage_code,
                        "current_stage_label": stage_label,
                        "current_status": curr_status,
                        "completion_type": "",
                        "arrival_time": received_dt.isoformat() if event_type in {"ARRIVAL", "LC_REQUEST"} else None,
                        "accepted_time": received_dt.isoformat() if event_type == "ACCEPTED" else None,
                        "sla_changed_time": None,
                        "returned_time": received_dt.isoformat() if event_type == "RETURNED" else None,
                        "approved_time": received_dt.isoformat() if event_type == "APPROVED" else None,
                        "sign_time": received_dt.isoformat() if event_type == "SIGN_APPROVED" else None,
                        "disbursed_time": received_dt.isoformat() if event_type == "DISBURSED" else None,
                        "manual_completed_time": None,
                        "completed_time": received_dt.isoformat() if event_type in {"RETURNED", "DISBURSED"} else None,
                        "sla_deadline": sla_deadline.isoformat() if pd.notna(sla_deadline) else None,
                        "sla_minutes": _calculate_sla_minutes(
                            received_dt if event_type in {"ARRIVAL", "LC_REQUEST"} else None,
                            sla_deadline,
                            flow,
                            sla_cfg_map
                        ),
                        "vcoms_sla_finish_time": None,
                        "manual_finish_time": None,
                        "sla_result": "",
                        "manual_sla_result": "",
                        "arrival_event_count": 0,
                        "required_arrival_count": req_count,
                        "ready_to_accept": 0,
                        "missing_info_flag": 0,
                        "missing_info_note": "",
                        "room_lookup_source": "",
                        "note": "",
                        "last_event_time": received_dt.isoformat(),
                        "last_event_type": event_type,
                        "is_open": 0 if event_type in {"RETURNED", "DISBURSED"} else 1,
                        "entry_id_last": str(r.get("entry_id") or ""),
                        "stt": stt_counter,
                        "progress_text": stage_label,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "updated_at": datetime.now().isoformat(timespec="seconds"),
                        "updated_by": "system",
                    }
                    if str(case.get("product_type") or "").upper() == "LC":
                        missing = []
                        if not str(case.get("customer_name") or "").strip():
                            missing.append("Tên KH")
                        if not str(case.get("room") or "").strip():
                            missing.append("Phòng")
                        if not str(case.get("assigned_officer") or "").strip():
                            missing.append("CB")
                        if missing:
                            case["missing_info_flag"] = 1
                            case["missing_info_note"] = "Thiếu " + ", ".join(missing)
                    stt_counter += 1

                    room_resolved, room_src = _resolve_room_for_case(
                        case.get("room"),
                        room_detected,
                        case.get("cif"),
                        room_mapping_by_cif,
                        old_processed_room_by_cif,
                        latest_room_by_cif,
                    )
                    case["room"] = room_resolved
                    case["room_lookup_source"] = room_src
                    cust_resolved, _cust_src = _resolve_customer_for_case(
                        case.get("customer_name"),
                        cust,
                        case.get("cif"),
                        old_processed_customer_by_cif,
                        latest_customer_by_cif,
                    )
                    case["customer_name"] = cust_resolved
                    cases[case_key] = case

                if event_type == "ARRIVAL":
                    case["arrival_event_count"] = int(case.get("arrival_event_count") or 0) + 1
                    sender_key = (case_key, str(r.get("sender_email") or r.get("sender_name") or "").strip().lower())
                    sender_arrival_counts[sender_key] += 1
                    sender_arrival_count = sender_arrival_counts[sender_key]
                    arrival_seq = int(case.get("arrival_event_count") or 0)
                    if "ONLINE" in str(flow).upper() and sender_arrival_count >= 2 and case.get("current_stage_code") in {"ARRIVAL", "WAIT_ACCEPT"}:
                        case["current_stage_code"] = "WAIT_ACCEPT"
                        case["current_stage_label"] = "Chờ tiếp nhận"
                    elif "ONLINE" not in str(flow).upper():
                        case["current_stage_code"] = "WAIT_ACCEPT"
                        case["current_stage_label"] = "Chờ tiếp nhận"
                elif event_type == "ACCEPTED":
                    case["accepted_time"] = received_dt.isoformat()
                    case["current_stage_code"] = "PROCESSING"
                    case["current_stage_label"] = "Đang xử lý"
                    if officer:
                        case["assigned_officer"] = _normalize_officer_id(officer, cb_cfg)
                    if pd.notna(sla_deadline):
                        case["sla_deadline"] = sla_deadline.isoformat()
                        case["sla_minutes"] = _calculate_sla_minutes(
                            case.get("arrival_time") or case.get("accepted_time"), 
                            sla_deadline, 
                            case.get("flow_type") or flow, 
                            sla_cfg_map
                        )
                elif event_type == "APPROVED":
                    case["approved_time"] = received_dt.isoformat()
                    
                    sender_val = str(r.get("sender_email") or r.get("sender_name") or "").strip()
                    if sender_val:
                        case["supervisor_name"] = sender_val
                        
                    if "ONLINE" in str(flow).upper():
                        case["current_stage_code"] = "WAIT_SIGN"
                        case["current_stage_label"] = "Chờ BGĐ ký số"
                    else:
                        case["current_stage_code"] = "WAIT_MANUAL_DONE"
                        case["current_stage_label"] = "Chờ hoàn tất thủ công"
                        
                    if pd.notna(sla_deadline):
                        case["sla_deadline"] = sla_deadline.isoformat()
                        case["sla_minutes"] = _calculate_sla_minutes(
                            case.get("arrival_time") or case.get("accepted_time") or case.get("approved_time"),
                            sla_deadline,
                            case.get("flow_type") or flow,
                            sla_cfg_map
                        )
                elif event_type == "SIGN_APPROVED":
                    case["sign_time"] = received_dt.isoformat()
                    case["current_stage_code"] = "WAIT_DISBURSE"
                    case["current_stage_label"] = "Chờ giải ngân"
                elif event_type == "DISBURSED":
                    case["disbursed_time"] = received_dt.isoformat()
                    case["completed_time"] = received_dt.isoformat()
                    case["current_stage_code"] = "DONE"
                    case["current_stage_label"] = "Hoàn thành"
                    case["current_status"] = "CLOSED"
                    case["is_open"] = 0
                elif event_type == "RETURNED":
                    case["returned_time"] = received_dt.isoformat()
                    case["completed_time"] = received_dt.isoformat()
                    case["completion_type"] = "RETURNED"
                    case["current_stage_code"] = "DONE"
                    case["current_stage_label"] = "Hoàn thành"
                    case["current_status"] = "CLOSED"
                    case["is_open"] = 0
                    if return_reason:
                        case["note"] = return_reason
                elif event_type == "SLA_CHANGED":
                    case["sla_changed_time"] = received_dt.isoformat()
                    if pd.notna(sla_deadline):
                        case["sla_deadline"] = sla_deadline.isoformat()
                        case["sla_minutes"] = _calculate_sla_minutes(
                            case.get("arrival_time"), 
                            sla_deadline, 
                            case.get("flow_type") or flow, 
                            sla_cfg_map
                        )
                elif event_type == "LC_REQUEST":
                    case["current_stage_code"] = "PROCESSING"
                    case["current_stage_label"] = "Đang xử lý"
                    case["sla_minutes"] = 60.0
                    if not str(case.get("arrival_time") or "").strip():
                        case["arrival_time"] = received_dt.isoformat()
                    case["sla_deadline"] = (received_dt + timedelta(minutes=60)).isoformat()

                # Enforce final state for RETURNED regardless of out-of-order events.
                if str(case.get("completion_type") or "").upper() == "RETURNED":
                    case["current_stage_code"] = "DONE"
                    case["current_stage_label"] = "Hoàn thành"
                    case["current_status"] = "CLOSED"
                    case["is_open"] = 0

                case["last_event_time"] = received_dt.isoformat()
                case["last_event_type"] = event_type
                case["updated_at"] = datetime.now().isoformat(timespec="seconds")
                case["ma_ho_so"] = case.get("ma_ho_so") or ma_hs
                case["cif"] = case.get("cif") or cif
                case["customer_name"] = case.get("customer_name") or cust
                case["amount"] = case.get("amount") or amount
                case["flow_type"] = case.get("flow_type") or flow
                if account:
                    case["account_number"] = account
                case["entry_id_last"] = str(r.get("entry_id") or "")
                case["progress_text"] = case.get("current_stage_label")

                # Resolve room with fallback sources for empty room.
                room_resolved, room_src = _resolve_room_for_case(
                    case.get("room"),
                    room_detected,
                    case.get("cif"),
                    room_mapping_by_cif,
                    old_processed_room_by_cif,
                    latest_room_by_cif,
                )
                case["room"] = room_resolved
                case["room_lookup_source"] = room_src
                cust_resolved, _cust_src = _resolve_customer_for_case(
                    case.get("customer_name"),
                    cust,
                    case.get("cif"),
                    old_processed_customer_by_cif,
                    latest_customer_by_cif,
                )
                case["customer_name"] = cust_resolved

                # Auto-close GN online KHCN short-flow at SIGN_APPROVED stage.
                if (
                    str(case.get("product_type") or "").upper() == "GN"
                    and (str(case.get("flow_type") or "").upper() == "GN_ONLINE_KHCN" or (
                        "ONLINE" in str(case.get("flow_type") or "").upper() and not _is_business_customer(str(case.get("customer_name") or ""), dn_prefixes)
                    ))
                    and str(case.get("sign_time") or "").strip()
                    and not str(case.get("arrival_time") or "").strip()
                    and not str(case.get("disbursed_time") or "").strip()
                ):
                    case["current_stage_code"] = "DONE"
                    case["current_stage_label"] = "Hoàn thành"
                    case["current_status"] = "CLOSED"
                    case["is_open"] = 0
                    case["completion_type"] = "SIGNED_ONLINE_KHCN"
                    if not str(case.get("completed_time") or "").strip():
                        case["completed_time"] = case.get("sign_time")

                # Build latest-room history map for next cases.
                c_key = str(case.get("cif") or "").strip()
                r_val = str(case.get("room") or "").strip()
                if c_key and r_val:
                    latest_room_by_cif[c_key] = r_val
                cst_val = str(case.get("customer_name") or "").strip()
                if c_key and cst_val:
                    latest_customer_by_cif[c_key] = cst_val
                if str(case.get("product_type") or "").upper() == "LC":
                    missing = []
                    if not str(case.get("customer_name") or "").strip():
                        missing.append("Tên KH")
                    if not str(case.get("room") or "").strip():
                        missing.append("Phòng")
                    if not str(case.get("assigned_officer") or "").strip():
                        missing.append("CB")
                    if missing:
                        case["missing_info_flag"] = 1
                        case["missing_info_note"] = "Thiếu " + ", ".join(missing)
                    else:
                        case["missing_info_flag"] = 0
                        case["missing_info_note"] = ""
                if ma_hs and ma_hs not in by_ma_hs:
                    by_ma_hs[ma_hs] = case_key
                if event_type in {"ARRIVAL", "LC_REQUEST"} and canonical_event_key:
                    seen_opening_keys[canonical_event_key] = int(r.get("id") or 0)
            elif parse_status == "unmatched":
                stats.unmatched_count += 1

            conn.execute(
                """
                INSERT INTO vcoms_email_events (
                    raw_id, entry_id, received_time, sender, recipients, subject, subject_norm,
                    event_type, product_type, case_key, block_index, arrival_seq_in_block, sender_arrival_count,
                    ma_ho_so, cif, customer_name, amount, currency, flow_type, account_number,
                    officer_name, supervisor_name, sla_deadline, sla_old, return_reason, external_ref_type, external_ref_code,
                    parse_status, parse_warning, field_json, is_canonical, canonical_event_key, duplicate_of_event_id, dedupe_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r.get("id"),
                    str(r.get("entry_id") or ""),
                    received_dt.isoformat(),
                    str(r.get("sender_email") or r.get("sender_name") or ""),
                    str(r.get("recipients_text") or ""),
                    subject,
                    _norm(subject),
                    event_type,
                    product_type,
                    case_key,
                    block_index,
                    arrival_seq,
                    sender_arrival_count,
                    ma_hs,
                    cif,
                    cust,
                    amount,
                    currency,
                    flow,
                    account,
                    officer,
                    supervisor,
                    sla_deadline.isoformat() if pd.notna(sla_deadline) else None,
                    None,
                    return_reason,
                    external_ref_type,
                    external_ref,
                    parse_status,
                    parse_warning,
                    json.dumps(
                        {
                            "internet_message_id": r.get("internet_message_id"),
                            "conversation_id": r.get("conversation_id"),
                            "folder_path": r.get("folder_path"),
                        },
                        ensure_ascii=False,
                    ),
                    is_canonical,
                    canonical_event_key,
                    duplicate_of_event_id,
                    dedupe_reason,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            ev_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if case_key:
                latest_event_id_by_case_key[case_key] = int(ev_id)
            stats.event_count += 1
            if parse_warning:
                stats.parse_warning_count += 1
            if event_type == "LC_REQUEST":
                stats.lc_count += 1
            if event_type == "RETURNED":
                stats.returned_count += 1
            if event_type == "SLA_CHANGED":
                stats.sla_changed_count += 1
                
            # ==========================================
            # CHẾ ĐỘ MÔ PHỎNG (INTERACTIVE MODE)
            # ==========================================
            if interactive:
                # Dùng connection mới để bắt được các thay đổi từ Web UI (Ghi đè thủ công, Sửa Rule)
                conn_tmp = sqlite3.connect(db_path)
                manual_actions_sim = _load_active_manual_actions(conn_tmp)
                routing_rules = _load_routing_rules(conn_tmp)
                assignment_rules = _load_assignment_rules(conn_tmp)
                conn_tmp.close()
                
                _apply_manual_actions_to_cases(cases, manual_actions_sim)

                # Ghi tạm ra DB để Web đọc
                conn.execute("DELETE FROM vcoms_case_state")
                for c_val in cases.values():
                    c_copy = dict(c_val)
                    if str(c_copy.get("completion_type") or "").upper() == "RETURNED":
                        c_copy["current_stage_code"] = "DONE"
                        c_copy["current_stage_label"] = "Hoàn thành"
                        c_copy["current_status"] = "CLOSED"
                        c_copy["is_open"] = 0
                    c_cols = list(c_copy.keys())
                    c_plh = ",".join(["?"] * len(c_cols))
                    conn.execute(f"INSERT INTO vcoms_case_state ({','.join(c_cols)}) VALUES ({c_plh})", [c_copy.get(c) for c in c_cols])
                conn.commit()

                print("\n" + "="*80)
                print(f"📧 EMAIL VỪA XỬ LÝ : {subject}")
                print(f"   Thời gian nhận  : {received_dt.strftime('%H:%M:%S %d/%m/%Y')}")
                print(f"   Nhận diện Luồng : {flow} | Event: {event_type} | Ghi vào thẻ: {case_key.split('|')[-1] if case_key else 'None'}")
                print(f"   Dữ liệu bóc tách: Khách hàng: [{cust_resolved}] | Tiền: [{amount:,}] | STK: [{account}] | Phòng: [{room_resolved}]")
                if case_key and case_key in cases:
                    c_curr = cases[case_key]
                    print(f"   CB Phân giao    : {c_curr.get('assigned_officer')} | Tiến độ: {c_curr.get('current_stage_label')}")
                print("="*80)
                cmd = input("▶ Bật Web xem thẻ nhảy. Nhấn Enter để đọc email tiếp (hoặc 'q' để thoát): ")
                if cmd.strip().lower() == 'q': return stats

        _backfill_missing_arrival_from_family(conn, cases)
        _backfill_missing_room_from_case_raw(conn, cases)
        manual_actions = _load_active_manual_actions(conn)
        _apply_manual_actions_to_cases(cases, manual_actions)

        conn.execute("DELETE FROM vcoms_case_state")
        for case in sorted(cases.values(), key=lambda x: (x.get("business_date") or "", int(x.get("stt") or 0))):
            if str(case.get("completion_type") or "").upper() == "RETURNED":
                case["current_stage_code"] = "DONE"
                case["current_stage_label"] = "Hoàn thành"
                case["current_status"] = "CLOSED"
                case["is_open"] = 0
            cols = list(case.keys())
            placeholders = ",".join(["?"] * len(cols))
            conn.execute(
                f"INSERT INTO vcoms_case_state ({','.join(cols)}) VALUES ({placeholders})",
                [case.get(c) for c in cols],
            )
        stats.case_count = len(cases)

    conn.close()
    if verbose:
        print(
            "[REBUILD] "
            f"raw_count={stats.raw_count} event_count={stats.event_count} case_count={stats.case_count} "
            f"unmatched_count={stats.unmatched_count} parse_warning_count={stats.parse_warning_count} "
            f"LC_count={stats.lc_count} returned_count={stats.returned_count} sla_changed_count={stats.sla_changed_count}"
        )
    return stats
