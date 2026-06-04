"""SQLite read helpers for SmartVCOMS page data source switching."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
from ..pipeline.excel_io import WorkbookInputs

REQUIRED_SLA_KEYS = {"O1", "O2", "O3", "O5", "O6"}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def sqlite_db_is_ready(db_path: str | Path, v2_strict: bool = False) -> tuple[bool, str]:
    """Check DB usability for SmartVCOMS reads (independent from latest sync status)."""
    db_file = Path(db_path)
    if not db_file.exists():
        return False, "db_file_missing"

    try:
        conn = sqlite3.connect(str(db_file))
        try:
            required_main = "vcoms_case_state" if v2_strict else "dashboard_records_processed"
            if not _table_exists(conn, required_main):
                return False, f"missing_table_{required_main}"
            has_cfg_cb_full = _table_exists(conn, "config_cb_full")
            if not has_cfg_cb_full:
                return False, "missing_table_config_cb_full"
            if not _table_exists(conn, "config_ld"):
                return False, "missing_table_config_ld"
            if not _table_exists(conn, "sla_config"):
                return False, "missing_table_sla_config"

            main_count = int(conn.execute(f"SELECT COUNT(*) FROM {required_main}").fetchone()[0])
            if main_count <= 0:
                return False, f"empty_{required_main}"

            cfg_full_count = int(conn.execute("SELECT COUNT(*) FROM config_cb_full").fetchone()[0])
            if cfg_full_count <= 0:
                return False, "empty_config_cb_full"

            ld_count = int(conn.execute("SELECT COUNT(*) FROM config_ld").fetchone()[0])
            if ld_count <= 0:
                return False, "empty_config_ld"

            sla_count = int(conn.execute("SELECT COUNT(*) FROM sla_config").fetchone()[0])
            if sla_count <= 0:
                return False, "empty_sla_config"

            sla_keys = {
                str(r[0]).strip().upper()
                for r in conn.execute("SELECT key FROM sla_config").fetchall()
            }
            missing_keys = REQUIRED_SLA_KEYS - sla_keys
            if missing_keys:
                return False, f"missing_sla_keys:{','.join(sorted(missing_keys))}"

            return True, "ready"
        finally:
            conn.close()
    except Exception as exc:
        return False, f"db_open_error:{exc}"


def get_sqlite_sync_health(db_path: str | Path) -> dict[str, Any]:
    """Return sync health (OK/WARN/FAILED) without deciding read fallback."""
    ready, reason = sqlite_db_is_ready(db_path)
    info: dict[str, Any] = {
        "latest_status": None,
        "latest_error": None,
        "latest_finished_at": None,
        "last_success_at": None,
        "is_healthy": False,
        "health_level": "FAILED",
        "message": reason if not ready else "",
    }
    if not ready:
        info["message"] = f"sqlite_unusable:{reason}"
        return info

    conn = sqlite3.connect(str(db_path))
    try:
        has_sync_runs = _table_exists(conn, "sync_runs")
        if not has_sync_runs:
            info.update(
                {
                    "is_healthy": True,
                    "health_level": "WARN",
                    "message": "sync_runs_missing_but_db_readable",
                }
            )
            return info

        latest = conn.execute(
            "SELECT status, finished_at, error_message FROM sync_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        last_success = conn.execute(
            "SELECT finished_at FROM sync_runs WHERE status='SUCCESS' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        info["last_success_at"] = last_success[0] if last_success else None
        if latest:
            latest_status = str(latest[0] or "").upper().strip()
            info["latest_status"] = latest_status
            info["latest_finished_at"] = latest[1]
            info["latest_error"] = latest[2]

            if latest_status == "SUCCESS":
                info.update({"is_healthy": True, "health_level": "OK", "message": "latest_success"})
            elif latest_status in {"SKIPPED", "SKIPPED_NO_CHANGE"}:
                if info["last_success_at"]:
                    info.update({"is_healthy": True, "health_level": "OK", "message": "latest_skipped_no_change"})
                else:
                    info.update({"is_healthy": False, "health_level": "FAILED", "message": "skipped_without_success_history"})
            elif latest_status in {"SKIPPED_CONFIG_NOT_READY", "CONFIG_NOT_READY"}:
                info.update({"is_healthy": False, "health_level": "FAILED", "message": "config_not_ready"})
            elif latest_status == "FAILED":
                if info["last_success_at"]:
                    info.update({"is_healthy": True, "health_level": "WARN", "message": "latest_failed_using_last_snapshot"})
                else:
                    info.update({"is_healthy": False, "health_level": "FAILED", "message": "failed_without_success_history"})
            else:
                if info["last_success_at"]:
                    info.update({"is_healthy": True, "health_level": "WARN", "message": f"unknown_latest_status:{latest_status}"})
                else:
                    info.update({"is_healthy": False, "health_level": "FAILED", "message": f"unknown_latest_status_no_success:{latest_status}"})
        else:
            info.update({"is_healthy": False, "health_level": "FAILED", "message": "sync_runs_empty"})
    finally:
        conn.close()
    return info


def load_data_from_sqlite(db_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load dashboard/config dataframes from sqlite with Excel-compatible columns."""
    conn = sqlite3.connect(str(db_path))
    try:
        df_db = pd.read_sql_query(
            """
            SELECT
                "STT",
                "Mã hồ sơ",
                "Phòng",
                "CIF",
                "Tên KH",
                "Số tiền GN",
                "Luồng GN",
                "CB HTTD",
                "LĐP/KSV HTTD",
                "SLA",
                "Hồ sơ đến",
                "Tiếp nhận",
                "Phê duyệt",
                "Ký số",
                "Giải ngân",
                "Tiến độ HS",
                "Số tài khoản",
                "Trạng thái Luồng",
                "Thời gian nhận email",
                "Cập nhật cuối",
                "EntryID",
                "Thời gian SLA",
                "Thời gian SLA HTTD",
                "Thời gian SLA BGĐ"
            FROM dashboard_records
            ORDER BY CAST("STT" AS INTEGER), id
            """,
            conn,
        )

        df_cfg_raw = pd.read_sql_query(
            """
            SELECT
                id_cb,
                ten_can_bo,
                thu_tu_uu_tien,
                trang_thai,
                dang_xu_ly,
                lan_giao_cuoi,
                tong_phut_sla,
                phut_bu_tru,
                diem_phan_giao
            FROM config_cb
            ORDER BY source_row, id
            """,
            conn,
        )
    finally:
        conn.close()

    # Build Config_CB-compatible shape/headers used by current page logic.
    n = len(df_cfg_raw)
    df_cfg = pd.DataFrame(
        {
            "ID_CB": df_cfg_raw.get("id_cb", pd.Series([None] * n)),
            "Tên Cán bộ": df_cfg_raw.get("ten_can_bo", pd.Series([None] * n)),
            "Thứ tự ưu tiên": df_cfg_raw.get("thu_tu_uu_tien", pd.Series([None] * n)),
            "Trạng thái": df_cfg_raw.get("trang_thai", pd.Series([None] * n)),
            "Đang xử lý": df_cfg_raw.get("dang_xu_ly", pd.Series([None] * n)),
            "Lần giao cuối": df_cfg_raw.get("lan_giao_cuoi", pd.Series([None] * n)),
            "Cột 7": [None] * n,
            "Cột 8": [None] * n,
            "Tổng phút SLA": pd.to_numeric(df_cfg_raw.get("tong_phut_sla"), errors="coerce"),
            "Phút Bù Trừ": pd.to_numeric(df_cfg_raw.get("phut_bu_tru"), errors="coerce"),
            "Điểm Phân Giao": pd.to_numeric(df_cfg_raw.get("diem_phan_giao"), errors="coerce"),
            "Cột 12": [None] * n,
            "Cột 13": [None] * n,
            "SLA_Config_N": [None] * n,
            "SLA_Config_O": [None] * n,
        }
    )

    for df in (df_db, df_cfg):
        df.columns = df.columns.astype(str).str.strip()
    return df_db, df_cfg


def load_case_state_as_dashboard(db_path: str | Path) -> pd.DataFrame:
    """Load SQLite V2 case state and map to dashboard-like columns for existing UI."""
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql_query(
            """
            SELECT
                stt AS "STT",
                ma_ho_so AS "Mã hồ sơ",
                room AS "Phòng",
                cif AS "CIF",
                customer_name AS "Tên KH",
                amount AS "Số tiền GN",
                flow_type AS "Luồng GN",
                assigned_officer AS "CB HTTD",
                supervisor_name AS "LĐP/KSV HTTD",
                sla_deadline AS "SLA",
                arrival_time AS "Hồ sơ đến",
                accepted_time AS "Tiếp nhận",
                approved_time AS "Phê duyệt",
                sign_time AS "Ký số",
                disbursed_time AS "Giải ngân",
                current_stage_label AS "Tiến độ HS",
                account_number AS "Số tài khoản",
                current_status AS "Trạng thái Luồng",
                created_at AS "Thời gian nhận email",
                updated_at AS "Cập nhật cuối",
                entry_id_last AS "EntryID",
                sla_minutes AS "Thời gian SLA",
                NULL AS "Thời gian SLA HTTD",
                NULL AS "Thời gian SLA BGĐ",
                id AS case_id,
                case_key,
                business_date,
                current_stage_code,
                current_stage_label,
                product_type,
                completion_type,
                missing_info_flag,
                missing_info_note,
                note,
                currency,
                manual_completed_time,
                completed_time,
                returned_time,
                sla_changed_time
            FROM vcoms_case_state
            ORDER BY business_date DESC, stt ASC, id ASC
            """,
            conn,
        )
    finally:
        conn.close()
    return df


def load_ldp_mapping_from_sqlite(db_path: str | Path) -> dict[str, str]:
    """Load LĐP/KSV mapping from config_ld table."""
    conn = sqlite3.connect(str(db_path))
    try:
        df_ld = pd.read_sql_query(
            "SELECT display_name, lookup_key, email FROM config_ld ORDER BY source_row, id",
            conn,
        )
    finally:
        conn.close()

    mapping: dict[str, str] = {}
    for _, row in df_ld.iterrows():
        display_name = str(row.get("display_name") or "").strip()
        if not display_name:
            continue
        for key in (row.get("lookup_key"), row.get("email")):
            norm = str(key or "").strip()
            if norm:
                mapping[norm] = display_name
    return mapping


def _num_or_blank(value: Any) -> Any:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return ""
    return float(parsed)


def load_workbook_inputs_config_from_sqlite(db_path: str | Path, data_df: pd.DataFrame) -> WorkbookInputs:
    """Load processor runtime config from sqlite in Excel-compatible shape."""
    conn = sqlite3.connect(str(db_path))
    try:
        has_cb_full = _table_exists(conn, "config_cb_full")
        if has_cb_full:
            cfg_cb = pd.read_sql_query(
                """
                SELECT
                    id_cb AS "ID_CB",
                    ten_can_bo AS "Tên Cán bộ",
                    thu_tu_uu_tien AS "Thứ tự ưu tiên",
                    trang_thai AS "Trạng thái",
                    dang_xu_ly AS "Đang xử lý",
                    lan_giao_cuoi AS "Lần giao cuối",
                    tong_phut_sla AS "Tổng phút SLA",
                    phut_bu_tru AS "Phút Bù Trừ",
                    diem_phan_giao AS "Điểm Phân Giao"
                FROM config_cb_full
                WHERE COALESCE(is_active, 1) = 1
                ORDER BY COALESCE(thu_tu_uu_tien, 9999), id
                """,
                conn,
            )
        else:
            cfg_cb = pd.read_sql_query(
                """
                SELECT
                    id_cb AS "ID_CB",
                    ten_can_bo AS "Tên Cán bộ",
                    thu_tu_uu_tien AS "Thứ tự ưu tiên",
                    trang_thai AS "Trạng thái",
                    dang_xu_ly AS "Đang xử lý",
                    lan_giao_cuoi AS "Lần giao cuối",
                    tong_phut_sla AS "Tổng phút SLA",
                    phut_bu_tru AS "Phút Bù Trừ",
                    diem_phan_giao AS "Điểm Phân Giao"
                FROM config_cb
                ORDER BY source_row, id
                """,
                conn,
            )

        n = len(cfg_cb)
        cfg_cb_excel = pd.DataFrame(
            {
                "ID_CB": cfg_cb.get("ID_CB", pd.Series([""] * n)).astype(str),
                "Tên Cán bộ": cfg_cb.get("Tên Cán bộ", pd.Series([""] * n)).astype(str),
                "Thứ tự ưu tiên": cfg_cb.get("Thứ tự ưu tiên", pd.Series([""] * n)),
                "Trạng thái": cfg_cb.get("Trạng thái", pd.Series([""] * n)).astype(str),
                "Đang xử lý": cfg_cb.get("Đang xử lý", pd.Series([""] * n)),
                "Lần giao cuối": cfg_cb.get("Lần giao cuối", pd.Series([""] * n)).astype(str),
                "Cột 7": [""] * n,
                "Cột 8": [""] * n,
                "Tổng phút SLA": cfg_cb.get("Tổng phút SLA", pd.Series([""] * n)).apply(_num_or_blank),
                "Phút Bù Trừ": cfg_cb.get("Phút Bù Trừ", pd.Series([""] * n)).apply(_num_or_blank),
                "Điểm Phân Giao": cfg_cb.get("Điểm Phân Giao", pd.Series([""] * n)).apply(_num_or_blank),
                "Cột 12": [""] * n,
                "Cột 13": [""] * n,
                "SLA_Config_N": [""] * n,
                "SLA_Config_O": [""] * n,
            }
        )

        cfg_ld = pd.read_sql_query(
            """
            SELECT
                display_name AS "Tên LĐP/KSV",
                lookup_key AS "ID_LĐP",
                email AS "Email"
            FROM config_ld
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY COALESCE(sort_order, 9999), id
            """,
            conn,
        )
        vn = pd.read_sql_query("SELECT key as ID, value as VAL FROM keyword_config ORDER BY id", conn)
        phongban = pd.read_sql_query(
            """
            SELECT
                cif AS "CIF",
                room_code AS "MA PHONG",
                room_name AS "TEN PHONG"
            FROM room_mapping
            ORDER BY id
            """,
            conn,
        )
        kw = {str(r["ID"]).strip(): str(r["VAL"]).strip() for _, r in vn.iterrows()}

        sla_df = pd.read_sql_query("SELECT key, value FROM sla_config", conn)
        sla_values = {str(r["key"]).strip().upper(): str(r["value"]).strip() for _, r in sla_df.iterrows()}

        def _sla(k: str, default: float) -> float:
            raw = sla_values.get(k, "")
            try:
                return float(raw)
            except Exception:
                return default

        sla_config = {
            "sla_default": _sla("O1", 45.0),
            "sla_max": _sla("O2", 180.0),
            "return_factor": _sla("O3", 1.0),
            "alloc_httd": _sla("O5", 0.8),
            "alloc_bgd": _sla("O6", 0.2),
        }

        return WorkbookInputs(
            data=data_df,
            dashboard=pd.DataFrame(),
            config_cb=cfg_cb_excel,
            config_ld=cfg_ld,
            vn=vn,
            phongban=phongban,
            keywords=kw,
            sla_config=sla_config,
        )
    finally:
        conn.close()


def get_latest_sync_info(db_path: str | Path) -> dict[str, Any]:
    """Return latest sync run metadata for lightweight UI/debug display."""
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "sync_runs" not in tables:
            return {}
        row = conn.execute(
            """
            SELECT status, finished_at, dashboard_row_count, data_row_count, raw_inserted, raw_updated
            FROM sync_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return {}
        return {
            "status": row[0],
            "finished_at": row[1],
            "dashboard_row_count": row[2],
            "data_row_count": row[3],
            "raw_inserted": row[4],
            "raw_updated": row[5],
        }
    finally:
        conn.close()


def load_dashboard_records_outlook_shadow(
    db_path: str | Path, latest_only: bool = True
) -> tuple[pd.DataFrame, str]:
    """Load dashboard snapshot from outlook shadow table."""
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dashboard_records_outlook_shadow"):
            return pd.DataFrame(), "missing_table_dashboard_records_outlook_shadow"
        c = int(conn.execute("SELECT COUNT(*) FROM dashboard_records_outlook_shadow").fetchone()[0])
        if c <= 0:
            return pd.DataFrame(), "shadow_empty"

        where_sql = ""
        params: list[Any] = []
        if latest_only:
            row = conn.execute(
                "SELECT shadow_run_id FROM dashboard_records_outlook_shadow ORDER BY id DESC LIMIT 1"
            ).fetchone()
            run_id = row[0] if row else None
            if run_id is not None:
                where_sql = "WHERE shadow_run_id = ?"
                params.append(run_id)

        sql = f"""
            SELECT
                "STT",
                "Mã hồ sơ",
                "Phòng",
                "CIF",
                "Tên KH",
                "Số tiền GN",
                "Luồng GN",
                "CB HTTD",
                "LĐP/KSV HTTD",
                "SLA",
                "Hồ sơ đến",
                "Tiếp nhận",
                "Phê duyệt",
                "Ký số",
                "Giải ngân",
                "Tiến độ HS",
                "Số tài khoản",
                "Trạng thái Luồng",
                "Thời gian nhận email",
                "Cập nhật cuối",
                "EntryID",
                "Thời gian SLA",
                "Thời gian SLA HTTD",
                "Thời gian SLA BGĐ"
            FROM dashboard_records_outlook_shadow
            {where_sql}
            ORDER BY CAST("STT" AS INTEGER), id
        """
        df = pd.read_sql_query(sql, conn, params=params)
        return df, "ok"
    finally:
        conn.close()


def load_dashboard_records_processed(
    db_path: str | Path, latest_only: bool = True
) -> tuple[pd.DataFrame, str]:
    """Load processed dashboard snapshot from dashboard_records_processed table."""
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "dashboard_records_processed"):
            return pd.DataFrame(), "missing_table_dashboard_records_processed"
        count = int(conn.execute("SELECT COUNT(*) FROM dashboard_records_processed").fetchone()[0])
        if count <= 0:
            return pd.DataFrame(), "processed_empty"
        sql = """
            SELECT
                "STT","Mã hồ sơ","Phòng","CIF","Tên KH","Số tiền GN","Luồng GN","CB HTTD",
                "LĐP/KSV HTTD","SLA","Hồ sơ đến","Tiếp nhận","Phê duyệt","Ký số","Giải ngân",
                "Tiến độ HS","Số tài khoản","Trạng thái Luồng","Thời gian nhận email","Cập nhật cuối",
                "EntryID","Thời gian SLA","Thời gian SLA HTTD","Thời gian SLA BGĐ"
            FROM dashboard_records_processed
            ORDER BY CAST("STT" AS INTEGER), rowid
        """
        return pd.read_sql_query(sql, conn), "ok"
    finally:
        conn.close()


def get_latest_processed_status(db_path: str | Path) -> dict[str, Any]:
    """Return summary for processed table and optional sync metadata."""
    conn = sqlite3.connect(str(db_path))
    try:
        out = {
            "processed_count": 0,
            "open_count": 0,
            "closed_count": 0,
            "latest_sync_status": None,
            "latest_sync_finished_at": None,
            "message": "",
        }
        if not _table_exists(conn, "dashboard_records_processed"):
            out["message"] = "missing_table_dashboard_records_processed"
            return out
        out["processed_count"] = int(conn.execute("SELECT COUNT(*) FROM dashboard_records_processed").fetchone()[0])
        out["open_count"] = int(
            conn.execute('SELECT COUNT(*) FROM dashboard_records_processed WHERE "Trạng thái Luồng" = ?', ("OPEN",)).fetchone()[0]
        )
        out["closed_count"] = int(
            conn.execute('SELECT COUNT(*) FROM dashboard_records_processed WHERE "Trạng thái Luồng" = ?', ("CLOSED",)).fetchone()[0]
        )
        if _table_exists(conn, "sync_runs"):
            row = conn.execute("SELECT status, finished_at FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                out["latest_sync_status"] = row[0]
                out["latest_sync_finished_at"] = row[1]
        out["message"] = "ok" if out["processed_count"] > 0 else "processed_empty"
        return out
    finally:
        conn.close()


def get_latest_outlook_shadow_status(db_path: str | Path) -> dict[str, Any]:
    """Return latest shadow status summary for UI/check scripts."""
    conn = sqlite3.connect(str(db_path))
    try:
        out = {
            "latest_shadow_run_id": None,
            "latest_reader_run_status": None,
            "latest_reader_finished_at": None,
            "outlook_raw_emails_count": 0,
            "dashboard_records_outlook_shadow_count": 0,
            "open_count": 0,
            "closed_count": 0,
            "message": "",
        }
        if _table_exists(conn, "outlook_raw_emails"):
            out["outlook_raw_emails_count"] = int(
                conn.execute("SELECT COUNT(*) FROM outlook_raw_emails").fetchone()[0]
            )
        if _table_exists(conn, "dashboard_records_outlook_shadow"):
            out["dashboard_records_outlook_shadow_count"] = int(
                conn.execute("SELECT COUNT(*) FROM dashboard_records_outlook_shadow").fetchone()[0]
            )
            row = conn.execute(
                "SELECT shadow_run_id FROM dashboard_records_outlook_shadow ORDER BY id DESC LIMIT 1"
            ).fetchone()
            out["latest_shadow_run_id"] = row[0] if row else None
            if out["latest_shadow_run_id"] is not None:
                counts = conn.execute(
                    """
                    SELECT "Trạng thái Luồng", COUNT(*)
                    FROM dashboard_records_outlook_shadow
                    WHERE shadow_run_id = ?
                    GROUP BY "Trạng thái Luồng"
                    """,
                    (out["latest_shadow_run_id"],),
                ).fetchall()
                for k, v in counts:
                    if str(k).upper() == "OPEN":
                        out["open_count"] = int(v)
                    if str(k).upper() == "CLOSED":
                        out["closed_count"] = int(v)
        if _table_exists(conn, "outlook_reader_runs"):
            row = conn.execute(
                "SELECT status, finished_at FROM outlook_reader_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                out["latest_reader_run_status"] = row[0]
                out["latest_reader_finished_at"] = row[1]
        out["message"] = (
            "Chưa có dữ liệu Outlook Shadow. Hãy chạy reader trước."
            if out["dashboard_records_outlook_shadow_count"] <= 0
            else "ok"
        )
        return out
    finally:
        conn.close()
