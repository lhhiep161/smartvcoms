"""Admin config read/write helpers for SQLite-backed SmartVCOMS."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import numpy as np

from .sqlite_store import connect_sqlite, init_schema
from ..utils import calculate_sla_minutes_common


DEFAULT_DN_PREFIX = (
    "CÔNG TY TNHH MTV, CONG TY TNHH MTV, CTY TNHH MTV, CT TNHH MTV, "
    "CÔNG TY TNHH, CONG TY TNHH, CTY TNHH, CT TNHH, "
    "CÔNG TY CỔ PHẦN, CONG TY CO PHAN, CTCP, CÔNG TY CP, CONG TY CP, "
    "CÔNG TY, CONG TY, CTY, CT, DNTN, DOANH NGHIEP"
)

DEFAULT_SLA_CONFIG_ROWS = [
    {"key": "O1", "label": "SLA mặc định rút gọn", "value": "45", "value_type": "text", "source_cell": "O1", "sort_order": 10},
    {"key": "O2", "label": "SLA tối đa", "value": "180", "value_type": "text", "source_cell": "O2", "sort_order": 20},
    {"key": "O3", "label": "Hệ số hồ sơ trả lại", "value": "1", "value_type": "text", "source_cell": "O3", "sort_order": 30},
    {"key": "O5", "label": "Tỷ lệ SLA HTTD", "value": "0.8", "value_type": "text", "source_cell": "O5", "sort_order": 40},
    {"key": "O6", "label": "Tỷ lệ SLA BGĐ", "value": "0.2", "value_type": "text", "source_cell": "O6", "sort_order": 50},
    {"key": "LC_SLA", "label": "SLA LC", "value": "60", "value_type": "text", "source_cell": "", "sort_order": 60},
    {"key": "BL_SLA", "label": "SLA Bảo lãnh", "value": "60", "value_type": "text", "source_cell": "", "sort_order": 70},
    {"key": "DN_PREFIX", "label": "Tiền tố tên doanh nghiệp", "value": DEFAULT_DN_PREFIX, "value_type": "text", "source_cell": "", "sort_order": 80},
    {"key": "WORK_MORNING_START", "label": "Giờ làm việc sáng bắt đầu", "value": "08:00", "value_type": "text", "source_cell": "", "sort_order": 90},
    {"key": "WORK_MORNING_END", "label": "Giờ làm việc sáng kết thúc", "value": "12:00", "value_type": "text", "source_cell": "", "sort_order": 100},
    {"key": "WORK_AFTERNOON_START", "label": "Giờ làm việc chiều bắt đầu", "value": "13:00", "value_type": "text", "source_cell": "", "sort_order": 110},
    {"key": "WORK_AFTERNOON_END", "label": "Giờ làm việc chiều kết thúc", "value": "19:30", "value_type": "text", "source_cell": "", "sort_order": 120},
    {"key": "SLA_MORNING_START", "label": "Giờ SLA sáng bắt đầu", "value": "08:00", "value_type": "text", "source_cell": "", "sort_order": 130},
    {"key": "SLA_MORNING_END", "label": "Giờ SLA sáng kết thúc", "value": "12:00", "value_type": "text", "source_cell": "", "sort_order": 140},
    {"key": "SLA_AFTERNOON_START", "label": "Giờ SLA chiều bắt đầu", "value": "13:00", "value_type": "text", "source_cell": "", "sort_order": 150},
    {"key": "SLA_AFTERNOON_END", "label": "Giờ SLA chiều kết thúc", "value": "19:30", "value_type": "text", "source_cell": "", "sort_order": 160},
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_runtime_state_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS vcoms_runtime_state (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
        """
    )


def ensure_assignment_day_state(db_path: str | Path, business_date: date | None = None) -> tuple[bool, str]:
    if business_date is None:
        business_date = date.today()
    business_date_str = business_date.isoformat()
    conn = connect_sqlite(db_path)
    init_schema(conn)
    _ensure_runtime_state_table(conn)
    with conn:
        row = conn.execute(
            "SELECT value FROM vcoms_runtime_state WHERE key='assignment_business_date'"
        ).fetchone()
        prev_date = str(row[0]) if row else ""
        if prev_date == business_date_str:
            return False, business_date_str
        conn.execute(
            """
            UPDATE config_cb_full
               SET dang_xu_ly = 0,
                   lan_giao_cuoi = NULL,
                   tong_phut_sla = 0,
                   phut_bu_tru = 0,
                   diem_phan_giao = 0,
                   updated_at = ?,
                   updated_by = COALESCE(updated_by, 'system')
            """,
            (_now_iso(),),
        )
        conn.execute(
            """
            INSERT INTO vcoms_runtime_state(key, value, updated_at)
            VALUES('assignment_business_date', ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """,
            (business_date_str, _now_iso()),
        )
    conn.close()
    return True, business_date_str


def _safe(v):
    if pd.isna(v):
        return None
    return v


def _to_json_safe(value):
    """Convert pandas/numpy/datetime values to JSON-serializable Python types."""
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if np.isnan(value):
            return None
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        try:
            return raw.decode("utf-8")
        except Exception:
            return raw.hex()
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]
    return value


def _json_dumps_safe(value) -> str:
    return json.dumps(_to_json_safe(value), ensure_ascii=False, sort_keys=True)


def load_config_cb_from_sqlite(db_path: str | Path, active_only: bool = True) -> pd.DataFrame:
    """Load full HTTD officer config from sqlite."""
    conn = sqlite3.connect(str(db_path))
    try:
        where = "WHERE is_active = 1" if active_only else ""
        return pd.read_sql_query(
            f"""
            SELECT
                id_cb AS "ID_CB",
                ten_can_bo AS "Tên Cán bộ",
                thu_tu_uu_tien AS "Thứ tự ưu tiên",
                trang_thai AS "Trạng thái",
                dang_xu_ly AS "Đang xử lý",
                lan_giao_cuoi AS "Lần giao cuối",
                tong_phut_sla AS "Tổng phút SLA",
                phut_bu_tru AS "Phút Bù Trừ",
                diem_phan_giao AS "Điểm Phân Giao",
                is_active AS "is_active"
            FROM config_cb_full
            {where}
            ORDER BY COALESCE(thu_tu_uu_tien, 9999), id
            """,
            conn,
        )
    finally:
        conn.close()


def load_config_ld_from_sqlite(db_path: str | Path, active_only: bool = True) -> pd.DataFrame:
    """Load LĐP/KSV config from sqlite."""
    conn = sqlite3.connect(str(db_path))
    try:
        where = "WHERE is_active = 1" if active_only else ""
        return pd.read_sql_query(
            f"""
            SELECT
                display_name,
                lookup_key,
                email,
                role,
                sort_order,
                is_active
            FROM config_ld
            {where}
            ORDER BY COALESCE(sort_order, 9999), id
            """,
            conn,
        )
    finally:
        conn.close()


def load_sla_config_from_sqlite(db_path: str | Path) -> pd.DataFrame:
    """Load SLA parameter config from sqlite."""
    conn = sqlite3.connect(str(db_path))
    try:
        return pd.read_sql_query(
            """
            SELECT key, label, value, value_type, source_cell, sort_order
            FROM sla_config
            ORDER BY COALESCE(sort_order, 9999), key
            """,
            conn,
        )
    finally:
        conn.close()


def ensure_default_sla_config(db_path: str | Path, user: str | None = None) -> int:
    """Ensure required SLA config keys exist in SQLite without overwriting existing rows."""
    conn = connect_sqlite(db_path)
    init_schema(conn)
    now = _now_iso()
    changed = 0
    with conn:
        existing_rows = pd.read_sql_query(
            """
            SELECT key, label, value, value_type, source_cell, sort_order
            FROM sla_config
            """,
            conn,
        )
        existing_keys = {
            str(row.get("key") or "").strip().upper()
            for _, row in existing_rows.iterrows()
            if str(row.get("key") or "").strip()
        }

        for default_row in DEFAULT_SLA_CONFIG_ROWS:
            key = str(default_row["key"]).strip().upper()
            if key in existing_keys:
                continue
            payload = {
                "key": default_row["key"],
                "label": default_row["label"],
                "value": default_row["value"],
                "value_type": default_row["value_type"],
                "source_cell": default_row["source_cell"],
                "sort_order": default_row["sort_order"],
            }
            conn.execute(
                """
                INSERT INTO sla_config (key, label, value, value_type, source_cell, sort_order, imported_at, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["key"],
                    payload["label"],
                    payload["value"],
                    payload["value_type"],
                    payload["source_cell"],
                    payload["sort_order"],
                    now,
                    now,
                    user or "system",
                ),
            )
            write_config_audit_log(conn, "sla_config", payload["key"], "UPSERT", None, payload, user)
            changed += 1
    conn.close()
    return changed


def load_config_for_admin(db_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all admin config frames from sqlite."""
    ensure_default_sla_config(db_path)
    return (
        load_config_cb_from_sqlite(db_path, active_only=False),
        load_config_ld_from_sqlite(db_path, active_only=False),
        load_sla_config_from_sqlite(db_path),
    )


def _normalize_assigned_officer_series(values: pd.Series, cfg: pd.DataFrame) -> pd.Series:
    if values.empty or cfg.empty:
        return values.astype(str).str.strip()
    id_map = {}
    name_map = {}
    for _, row in cfg.iterrows():
        cb_id = str(row.get("id_cb") or row.get("ID_CB") or "").strip()
        cb_name = str(row.get("ten_can_bo") or row.get("Tên Cán bộ") or "").strip()
        if cb_id:
            id_map[cb_id.upper()] = cb_id
        if cb_name and cb_id:
            name_map[cb_name.upper()] = cb_id
    def _normalize_one(value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        upper = raw.upper()
        if upper in id_map:
            return id_map[upper]
        if upper in name_map:
            return name_map[upper]
        return raw
    return values.map(_normalize_one)


def _load_sla_cfg_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM sla_config").fetchall()
    return {str(key).strip().upper(): str(value).strip() for key, value in rows}


def sync_config_cb_load_from_case_state(
    db_path: str | Path,
    business_date: date | None = None,
    user: str | None = None,
) -> int:
    """Recalculate officer load metrics from vcoms_case_state for one business date."""
    if business_date is None:
        business_date = date.today()
    biz = business_date.isoformat()
    conn = connect_sqlite(db_path)
    init_schema(conn)
    changed = 0
    now = _now_iso()
    try:
        with conn:
            if not {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }.issuperset({"config_cb_full", "vcoms_case_state"}):
                return 0

            case_df = pd.read_sql_query(
                """
                SELECT assigned_officer, current_status, sla_minutes, sla_deadline, arrival_time, last_event_time, business_date, flow_type
                FROM vcoms_case_state
                WHERE business_date = ?
                """,
                conn,
                params=(biz,),
            )
            if case_df.empty:
                conn.execute(
                    """
                    UPDATE config_cb_full
                       SET dang_xu_ly = 0,
                           tong_phut_sla = 0,
                           diem_phan_giao = COALESCE(phut_bu_tru, 0),
                           lan_giao_cuoi = NULL,
                           updated_at = ?,
                           updated_by = ?
                    """,
                    (now, user or "system"),
                )
                return int(conn.total_changes)

            case_df["assigned_officer"] = case_df["assigned_officer"].astype(str).str.strip()
            case_df = case_df[case_df["assigned_officer"] != ""].copy()
            case_df["sla_minutes"] = pd.to_numeric(case_df["sla_minutes"], errors="coerce")
            missing_sla = case_df["sla_minutes"].isna()
            if missing_sla.any():
                sla_cfg_map = _load_sla_cfg_map(conn)
                case_df.loc[missing_sla, "sla_minutes"] = case_df.loc[missing_sla].apply(
                    lambda row: calculate_sla_minutes_common(
                        row.get("arrival_time"),
                        row.get("sla_deadline"),
                        row.get("flow_type"),
                        sla_cfg_map,
                    ),
                    axis=1,
                )
            case_df["sla_minutes"] = case_df["sla_minutes"].fillna(0.0)
            case_df["last_event_time"] = pd.to_datetime(case_df["last_event_time"], errors="coerce")

            cfg = pd.read_sql_query(
                "SELECT id, id_cb, ten_can_bo, phut_bu_tru FROM config_cb_full",
                conn,
            )
            original_assigned = case_df["assigned_officer"].copy()
            case_df["assigned_officer"] = _normalize_assigned_officer_series(case_df["assigned_officer"], cfg)
            normalized_mask = original_assigned != case_df["assigned_officer"]
            if normalized_mask.any():
                normalized_rows = case_df.loc[normalized_mask].copy()
                for _, row in normalized_rows.iterrows():
                    conn.execute(
                        """
                        UPDATE vcoms_case_state
                           SET assigned_officer = ?,
                               updated_at = ?,
                               updated_by = ?
                         WHERE business_date = ?
                           AND COALESCE(assigned_officer, '') = ?
                        """,
                        (
                            str(row["assigned_officer"]).strip(),
                            now,
                            user or "system",
                            biz,
                            str(original_assigned.loc[row.name]).strip(),
                        ),
                    )
            open_counts = (
                case_df[case_df["current_status"].astype(str).str.upper() == "OPEN"]
                .groupby("assigned_officer")
                .size()
                .to_dict()
            )
            sla_totals = case_df.groupby("assigned_officer")["sla_minutes"].sum().to_dict()
            last_times = case_df.groupby("assigned_officer")["last_event_time"].max().to_dict()
            for _, r in cfg.iterrows():
                cb_id = str(r.get("id_cb") or "").strip()
                load_open = int(open_counts.get(cb_id, 0))
                load_sla = float(sla_totals.get(cb_id, 0.0))
                offset = float(pd.to_numeric(r.get("phut_bu_tru"), errors="coerce") or 0.0)
                score = load_sla + offset
                last_ts = last_times.get(cb_id)
                conn.execute(
                    """
                    UPDATE config_cb_full
                       SET dang_xu_ly = ?,
                           tong_phut_sla = ?,
                           diem_phan_giao = ?,
                           lan_giao_cuoi = ?,
                           updated_at = ?,
                           updated_by = ?
                     WHERE id = ?
                    """,
                    (
                        load_open,
                        load_sla,
                        score,
                        last_ts.isoformat() if pd.notna(last_ts) else None,
                        now,
                        user or "system",
                        int(r["id"]),
                    ),
                )
                changed += 1
    finally:
        conn.close()
    return changed


def write_config_audit_log(
    conn: sqlite3.Connection,
    table_name: str,
    record_key: str,
    action: str,
    old_value: dict | None,
    new_value: dict | None,
    changed_by: str | None,
    note: str = "",
) -> None:
    """Write one config audit record."""
    conn.execute(
        """
        INSERT INTO config_audit_log (table_name, record_key, action, old_value, new_value, changed_by, changed_at, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            table_name,
            record_key,
            action,
            _json_dumps_safe(old_value) if old_value is not None else None,
            _json_dumps_safe(new_value) if new_value is not None else None,
            changed_by or "system",
            _now_iso(),
            note,
        ),
    )


def upsert_config_cb(db_path: str | Path, df: pd.DataFrame, user: str | None = None) -> int:
    """Replace config_cb_full from edited dataframe and append audit logs."""
    reset_done, assignment_date = ensure_assignment_day_state(db_path, date.today())
    conn = connect_sqlite(db_path)
    init_schema(conn)
    _ensure_runtime_state_table(conn)
    now = _now_iso()
    changed = 0
    with conn:
        prev = pd.read_sql_query("SELECT * FROM config_cb_full", conn)
        prev_by_key = {
            str(r.get("id_cb") or "").strip(): r.to_dict()
            for _, r in prev.iterrows()
            if str(r.get("id_cb") or "").strip()
        }

        normalized_rows: list[tuple[int, pd.Series, dict, dict | None]] = []
        payloads: list[dict] = []
        for idx, row in df.reset_index(drop=True).iterrows():
            id_cb = str(row.get("ID_CB") or "").strip()
            if not id_cb:
                continue
            payload = {
                "id_cb": id_cb,
                "ten_can_bo": str(row.get("Tên Cán bộ") or "").strip(),
                "thu_tu_uu_tien": pd.to_numeric(row.get("Thứ tự ưu tiên"), errors="coerce"),
                "trang_thai": str(row.get("Trạng thái") or "").strip(),
                "dang_xu_ly": pd.to_numeric(row.get("Đang xử lý"), errors="coerce"),
                "lan_giao_cuoi": str(row.get("Lần giao cuối") or "").strip(),
                "tong_phut_sla": pd.to_numeric(row.get("Tổng phút SLA"), errors="coerce"),
                "phut_bu_tru": pd.to_numeric(row.get("Phút Bù Trừ"), errors="coerce"),
                "diem_phan_giao": pd.to_numeric(row.get("Điểm Phân Giao"), errors="coerce"),
                "is_active": int(pd.to_numeric(row.get("is_active"), errors="coerce")) if pd.notna(pd.to_numeric(row.get("is_active"), errors="coerce")) else 1,
            }
            payloads.append(payload)
            normalized_rows.append((idx, row, payload, prev_by_key.get(id_cb)))

        payloads_by_id = {str(p.get("id_cb") or "").strip(): p for p in payloads}
        for idx, row, payload, old in normalized_rows:
            old_status = str((old or {}).get("trang_thai") or "").strip().lower()
            new_status = str(payload.get("trang_thai") or "").strip().lower()
            if old_status != "ready" and new_status == "ready" and payload["is_active"] == 1:
                target_total_sla = pd.to_numeric(payload.get("tong_phut_sla"), errors="coerce")
                today_sla = float(target_total_sla) if pd.notna(target_total_sla) else 0.0
                current_offset_val = pd.to_numeric(payload.get("phut_bu_tru"), errors="coerce")
                current_score_val = pd.to_numeric(payload.get("diem_phan_giao"), errors="coerce")
                current_offset = float(current_offset_val) if pd.notna(current_offset_val) else 0.0
                current_score = float(current_score_val) if pd.notna(current_score_val) else today_sla + current_offset
                other_scores: list[float] = []
                for other_id, item in payloads_by_id.items():
                    if other_id == payload["id_cb"]:
                        continue
                    if str(item.get("trang_thai") or "").strip().lower() != "ready":
                        continue
                    if int(item.get("is_active") or 1) != 1:
                        continue
                    score_val = pd.to_numeric(item.get("diem_phan_giao"), errors="coerce")
                    other_scores.append(float(score_val) if pd.notna(score_val) else 0.0)
                if other_scores:
                    min_ready_score = min(other_scores)
                    if current_score <= min_ready_score:
                        new_offset = float(min_ready_score - 1 - today_sla)
                        if new_offset >= 0:
                            old_offset = payload.get("phut_bu_tru")
                            payload["phut_bu_tru"] = new_offset
                            payload["tong_phut_sla"] = today_sla
                            payload["diem_phan_giao"] = today_sla + new_offset
                            write_config_audit_log(
                                conn,
                                "config_cb_full",
                                payload["id_cb"],
                                "AUTO_COMPENSATE_READY",
                                {
                                    "old_status": old_status,
                                    "old_phut_bu_tru": old_offset,
                                    "old_diem_phan_giao": current_score,
                                },
                                {
                                    "new_status": new_status,
                                    "new_phut_bu_tru": new_offset,
                                    "today_sla": today_sla,
                                    "min_ready_score_others": min_ready_score,
                                    "new_diem_phan_giao": payload["diem_phan_giao"],
                                },
                                user,
                                note="auto_ready_compensation",
                            )
            payloads_by_id[payload["id_cb"]] = payload

        conn.execute("DELETE FROM config_cb_full")
        for idx, row, payload, old in normalized_rows:
            raw_json = _json_dumps_safe({k: (_safe(v)) for k, v in row.to_dict().items()})
            conn.execute(
                """
                INSERT INTO config_cb_full (
                    source_row, id_cb, ten_can_bo, thu_tu_uu_tien, trang_thai, dang_xu_ly, lan_giao_cuoi,
                    tong_phut_sla, phut_bu_tru, diem_phan_giao, raw_json, is_active, imported_at, updated_at, updated_by
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    idx + 2,
                    payload["id_cb"],
                    payload["ten_can_bo"],
                    payload["thu_tu_uu_tien"],
                    payload["trang_thai"],
                    payload["dang_xu_ly"],
                    payload["lan_giao_cuoi"],
                    payload["tong_phut_sla"],
                    payload["phut_bu_tru"],
                    payload["diem_phan_giao"],
                    raw_json,
                    payload["is_active"],
                    now,
                    now,
                    user or "system",
                ),
            )
            if old is None or _json_dumps_safe(old) != _json_dumps_safe(payload):
                changed += 1
                write_config_audit_log(conn, "config_cb_full", payload["id_cb"], "UPSERT", old, payload, user)
    conn.close()
    return changed


def upsert_config_ld(db_path: str | Path, df: pd.DataFrame, user: str | None = None) -> int:
    """Replace config_ld from edited dataframe and append audit logs."""
    conn = connect_sqlite(db_path)
    init_schema(conn)
    now = _now_iso()
    changed = 0
    with conn:
        prev = pd.read_sql_query("SELECT * FROM config_ld", conn)
        prev_by_key = {
            str(r.get("lookup_key") or "").strip(): r.to_dict()
            for _, r in prev.iterrows()
            if str(r.get("lookup_key") or "").strip()
        }
        conn.execute("DELETE FROM config_ld")
        for idx, row in df.reset_index(drop=True).iterrows():
            lookup_key = str(row.get("lookup_key") or "").strip()
            display_name = str(row.get("display_name") or "").strip()
            if not display_name or not lookup_key:
                continue
            payload = {
                "display_name": display_name,
                "lookup_key": lookup_key,
                "email": str(row.get("email") or "").strip(),
                "role": str(row.get("role") or "").strip(),
                "sort_order": pd.to_numeric(row.get("sort_order"), errors="coerce"),
                "is_active": int(pd.to_numeric(row.get("is_active"), errors="coerce")) if pd.notna(pd.to_numeric(row.get("is_active"), errors="coerce")) else 1,
            }
            conn.execute(
                """
                INSERT INTO config_ld (display_name, lookup_key, email, role, sort_order, is_active, source_row, imported_at, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["display_name"],
                    payload["lookup_key"],
                    payload["email"],
                    payload["role"],
                    payload["sort_order"],
                    payload["is_active"],
                    idx + 2,
                    now,
                    now,
                    user or "system",
                ),
            )
            old = prev_by_key.get(lookup_key)
            if old is None or _json_dumps_safe(old) != _json_dumps_safe(payload):
                changed += 1
                write_config_audit_log(conn, "config_ld", lookup_key, "UPSERT", old, payload, user)
    conn.close()
    return changed


def upsert_sla_config(db_path: str | Path, df: pd.DataFrame, user: str | None = None) -> int:
    """Replace sla_config from edited dataframe and append audit logs."""
    conn = connect_sqlite(db_path)
    init_schema(conn)
    now = _now_iso()
    changed = 0
    with conn:
        prev = pd.read_sql_query("SELECT * FROM sla_config", conn)
        prev_by_key = {str(r.get("key") or "").strip(): r.to_dict() for _, r in prev.iterrows()}
        conn.execute("DELETE FROM sla_config")
        for idx, row in df.reset_index(drop=True).iterrows():
            key = str(row.get("key") or "").strip()
            if not key:
                continue
            payload = {
                "key": key,
                "label": str(row.get("label") or "").strip(),
                "value": str(row.get("value") or "").strip(),
                "value_type": str(row.get("value_type") or "text").strip(),
                "source_cell": str(row.get("source_cell") or "").strip(),
                "sort_order": pd.to_numeric(row.get("sort_order"), errors="coerce"),
            }
            conn.execute(
                """
                INSERT INTO sla_config (key, label, value, value_type, source_cell, sort_order, imported_at, updated_at, updated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["key"],
                    payload["label"],
                    payload["value"],
                    payload["value_type"],
                    payload["source_cell"],
                    payload["sort_order"],
                    now,
                    now,
                    user or "system",
                ),
            )
            old = prev_by_key.get(key)
            if old is None or _json_dumps_safe(old) != _json_dumps_safe(payload):
                changed += 1
                write_config_audit_log(conn, "sla_config", key, "UPSERT", old, payload, user)
    conn.close()
    return changed
