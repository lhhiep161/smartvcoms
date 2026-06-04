"""SQLite storage helpers for SmartVCOMS sync."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

DASHBOARD_COLUMNS = [
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
    "Thời gian SLA BGĐ",
]


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def connect_sqlite(db_path: str | Path) -> sqlite3.Connection:
    """Open sqlite connection and apply pragmas for concurrent read/write."""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create required schema objects for VCOMS sync."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_row INTEGER,
            stt TEXT,
            subject TEXT,
            body TEXT,
            received_time TEXT,
            entry_id TEXT,
            status TEXT,
            assigned_to TEXT,
            recipients TEXT,
            row_hash TEXT NOT NULL,
            source_file TEXT,
            source_file_mtime REAL,
            imported_at TEXT,
            UNIQUE(entry_id),
            UNIQUE(row_hash)
        );

        CREATE TABLE IF NOT EXISTS dashboard_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "STT" TEXT,
            "Mã hồ sơ" TEXT,
            "Phòng" TEXT,
            "CIF" TEXT,
            "Tên KH" TEXT,
            "Số tiền GN" TEXT,
            "Luồng GN" TEXT,
            "CB HTTD" TEXT,
            "LĐP/KSV HTTD" TEXT,
            "SLA" TEXT,
            "Hồ sơ đến" TEXT,
            "Tiếp nhận" TEXT,
            "Phê duyệt" TEXT,
            "Ký số" TEXT,
            "Giải ngân" TEXT,
            "Tiến độ HS" TEXT,
            "Số tài khoản" TEXT,
            "Trạng thái Luồng" TEXT,
            "Thời gian nhận email" TEXT,
            "Cập nhật cuối" TEXT,
            "EntryID" TEXT,
            "Thời gian SLA" REAL,
            "Thời gian SLA HTTD" REAL,
            "Thời gian SLA BGĐ" REAL,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS dashboard_records_staging (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "STT" TEXT,
            "Mã hồ sơ" TEXT,
            "Phòng" TEXT,
            "CIF" TEXT,
            "Tên KH" TEXT,
            "Số tiền GN" TEXT,
            "Luồng GN" TEXT,
            "CB HTTD" TEXT,
            "LĐP/KSV HTTD" TEXT,
            "SLA" TEXT,
            "Hồ sơ đến" TEXT,
            "Tiếp nhận" TEXT,
            "Phê duyệt" TEXT,
            "Ký số" TEXT,
            "Giải ngân" TEXT,
            "Tiến độ HS" TEXT,
            "Số tài khoản" TEXT,
            "Trạng thái Luồng" TEXT,
            "Thời gian nhận email" TEXT,
            "Cập nhật cuối" TEXT,
            "EntryID" TEXT,
            "Thời gian SLA" REAL,
            "Thời gian SLA HTTD" REAL,
            "Thời gian SLA BGĐ" REAL,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS dashboard_records_processed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            "STT" TEXT,
            "Mã hồ sơ" TEXT,
            "Phòng" TEXT,
            "CIF" TEXT,
            "Tên KH" TEXT,
            "Số tiền GN" TEXT,
            "Luồng GN" TEXT,
            "CB HTTD" TEXT,
            "LĐP/KSV HTTD" TEXT,
            "SLA" TEXT,
            "Hồ sơ đến" TEXT,
            "Tiếp nhận" TEXT,
            "Phê duyệt" TEXT,
            "Ký số" TEXT,
            "Giải ngân" TEXT,
            "Tiến độ HS" TEXT,
            "Số tài khoản" TEXT,
            "Trạng thái Luồng" TEXT,
            "Thời gian nhận email" TEXT,
            "Cập nhật cuối" TEXT,
            "EntryID" TEXT,
            "Thời gian SLA" REAL,
            "Thời gian SLA HTTD" REAL,
            "Thời gian SLA BGĐ" REAL,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS vcoms_email_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id INTEGER,
            entry_id TEXT,
            received_time TEXT,
            sender TEXT,
            recipients TEXT,
            subject TEXT,
            subject_norm TEXT,
            event_type TEXT,
            product_type TEXT,
            case_key TEXT,
            block_index INTEGER,
            arrival_seq_in_block INTEGER,
            sender_arrival_count INTEGER,
            ma_ho_so TEXT,
            cif TEXT,
            customer_name TEXT,
            amount REAL,
            currency TEXT,
            flow_type TEXT,
            account_number TEXT,
            officer_name TEXT,
            supervisor_name TEXT,
            sla_deadline TEXT,
            sla_old TEXT,
            return_reason TEXT,
            external_ref_type TEXT,
            external_ref_code TEXT,
            parse_status TEXT,
            parse_warning TEXT,
            field_json TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_vcoms_email_events_case_key ON vcoms_email_events(case_key);
        CREATE INDEX IF NOT EXISTS idx_vcoms_email_events_received ON vcoms_email_events(received_time);
        CREATE INDEX IF NOT EXISTS idx_vcoms_email_events_entry_id ON vcoms_email_events(entry_id);

        CREATE TABLE IF NOT EXISTS vcoms_case_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_key TEXT UNIQUE,
            business_date TEXT,
            block_index INTEGER,
            product_type TEXT,
            ma_ho_so TEXT,
            cif TEXT,
            customer_name TEXT,
            room TEXT,
            amount REAL,
            currency TEXT,
            flow_type TEXT,
            assigned_officer TEXT,
            supervisor_name TEXT,
            current_stage_code TEXT,
            current_stage_label TEXT,
            current_status TEXT,
            completion_type TEXT,
            arrival_time TEXT,
            accepted_time TEXT,
            sla_changed_time TEXT,
            returned_time TEXT,
            approved_time TEXT,
            sign_time TEXT,
            disbursed_time TEXT,
            manual_completed_time TEXT,
            completed_time TEXT,
            sla_deadline TEXT,
            sla_minutes REAL,
            vcoms_sla_finish_time TEXT,
            manual_finish_time TEXT,
            sla_result TEXT,
            manual_sla_result TEXT,
            arrival_event_count INTEGER DEFAULT 0,
            required_arrival_count INTEGER DEFAULT 0,
            ready_to_accept INTEGER DEFAULT 0,
            missing_info_flag INTEGER DEFAULT 0,
            missing_info_note TEXT,
            note TEXT,
            last_event_time TEXT,
            last_event_type TEXT,
            is_open INTEGER DEFAULT 1,
            entry_id_last TEXT,
            stt INTEGER,
            progress_text TEXT,
            created_at TEXT,
            updated_at TEXT,
            updated_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_vcoms_case_state_biz ON vcoms_case_state(business_date);
        CREATE INDEX IF NOT EXISTS idx_vcoms_case_state_open ON vcoms_case_state(is_open);

        CREATE TABLE IF NOT EXISTS vcoms_case_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_key TEXT,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS vcoms_manual_case_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_key TEXT,
            business_date TEXT,
            cif TEXT,
            ma_ho_so TEXT,
            amount REAL,
            flow_type TEXT,
            action_type TEXT,
            action_time TEXT,
            action_by TEXT,
            note TEXT,
            created_at TEXT,
            is_active INTEGER DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_vcoms_manual_actions_case_key ON vcoms_manual_case_actions(case_key);
        CREATE INDEX IF NOT EXISTS idx_vcoms_manual_actions_active ON vcoms_manual_case_actions(is_active);

        CREATE TABLE IF NOT EXISTS config_cb (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_cb TEXT,
            ten_can_bo TEXT,
            thu_tu_uu_tien TEXT,
            trang_thai TEXT,
            dang_xu_ly TEXT,
            lan_giao_cuoi TEXT,
            tong_phut_sla REAL,
            phut_bu_tru REAL,
            diem_phan_giao REAL,
            raw_json TEXT,
            source_row INTEGER,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS config_ld (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            display_name TEXT,
            lookup_key TEXT,
            email TEXT,
            role TEXT,
            sort_order INTEGER,
            is_active INTEGER DEFAULT 1,
            source_row INTEGER,
            imported_at TEXT,
            updated_at TEXT,
            updated_by TEXT
        );

        CREATE TABLE IF NOT EXISTS config_cb_full (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_row INTEGER,
            id_cb TEXT,
            ten_can_bo TEXT,
            thu_tu_uu_tien INTEGER,
            trang_thai TEXT,
            dang_xu_ly REAL,
            lan_giao_cuoi TEXT,
            tong_phut_sla REAL,
            phut_bu_tru REAL,
            diem_phan_giao REAL,
            raw_json TEXT,
            is_active INTEGER DEFAULT 1,
            imported_at TEXT,
            updated_at TEXT,
            updated_by TEXT
        );

        CREATE TABLE IF NOT EXISTS sla_config (
            key TEXT PRIMARY KEY,
            label TEXT,
            value TEXT,
            value_type TEXT,
            source_cell TEXT,
            sort_order INTEGER,
            imported_at TEXT,
            updated_at TEXT,
            updated_by TEXT
        );

        CREATE TABLE IF NOT EXISTS config_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            record_key TEXT,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_at TEXT,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS room_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cif TEXT,
            room_code TEXT,
            room_name TEXT,
            source_row INTEGER,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS keyword_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            value TEXT,
            source_row INTEGER,
            imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            finished_at TEXT,
            status TEXT,
            mode TEXT,
            source_file TEXT,
            source_file_mtime REAL,
            source_file_size INTEGER,
            data_row_count INTEGER,
            dashboard_row_count INTEGER,
            raw_inserted INTEGER,
            raw_updated INTEGER,
            error_message TEXT,
            duration_ms INTEGER
        );

        CREATE TABLE IF NOT EXISTS processing_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sync_run_id INTEGER,
            source_row INTEGER,
            entry_id TEXT,
            subject TEXT,
            level TEXT,
            action TEXT,
            message TEXT,
            created_at TEXT,
            FOREIGN KEY(sync_run_id) REFERENCES sync_runs(id)
        );
        """
    )
    _ensure_table_columns(
        conn,
        "config_ld",
        {
            "role": "TEXT",
            "sort_order": "INTEGER",
            "is_active": "INTEGER DEFAULT 1",
            "updated_at": "TEXT",
            "updated_by": "TEXT",
        },
    )


def _ensure_table_columns(conn: sqlite3.Connection, table: str, cols: dict[str, str]) -> None:
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({_q(table)})").fetchall()}
    for col, col_type in cols.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {_q(table)} ADD COLUMN {_q(col)} {col_type}")


def clear_table(conn: sqlite3.Connection, table: str) -> None:
    """Delete all rows from table."""
    conn.execute(f"DELETE FROM {_q(table)}")


def replace_table_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    """Replace table rows with provided row dict list."""
    clear_table(conn, table)
    if not rows:
        return 0
    cols = list(rows[0].keys())
    col_sql = ", ".join(_q(c) for c in cols)
    val_sql = ", ".join("?" for _ in cols)
    sql = f"INSERT INTO {_q(table)} ({col_sql}) VALUES ({val_sql})"
    conn.executemany(sql, [[row.get(c) for c in cols] for row in rows])
    return len(rows)


def upsert_raw_emails(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Upsert raw email rows by entry_id or row_hash."""
    if not rows:
        return 0, 0

    inserted = 0
    updated = 0
    for row in rows:
        entry_id = row.get("entry_id")
        if entry_id:
            existing = conn.execute("SELECT id FROM raw_emails WHERE entry_id = ?", (entry_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE raw_emails
                    SET source_row=?, stt=?, subject=?, body=?, received_time=?, status=?, assigned_to=?, recipients=?,
                        row_hash=?, source_file=?, source_file_mtime=?, imported_at=?
                    WHERE id=?
                    """,
                    (
                        row.get("source_row"),
                        row.get("stt"),
                        row.get("subject"),
                        row.get("body"),
                        row.get("received_time"),
                        row.get("status"),
                        row.get("assigned_to"),
                        row.get("recipients"),
                        row.get("row_hash"),
                        row.get("source_file"),
                        row.get("source_file_mtime"),
                        row.get("imported_at"),
                        existing["id"],
                    ),
                )
                updated += 1
                continue

        existing_hash = conn.execute("SELECT id FROM raw_emails WHERE row_hash = ?", (row.get("row_hash"),)).fetchone()
        if existing_hash:
            conn.execute(
                """
                UPDATE raw_emails
                SET source_row=?, stt=?, subject=?, body=?, received_time=?, entry_id=?, status=?, assigned_to=?, recipients=?,
                    source_file=?, source_file_mtime=?, imported_at=?
                WHERE id=?
                """,
                (
                    row.get("source_row"),
                    row.get("stt"),
                    row.get("subject"),
                    row.get("body"),
                    row.get("received_time"),
                    row.get("entry_id"),
                    row.get("status"),
                    row.get("assigned_to"),
                    row.get("recipients"),
                    row.get("source_file"),
                    row.get("source_file_mtime"),
                    row.get("imported_at"),
                    existing_hash["id"],
                ),
            )
            updated += 1
        else:
            conn.execute(
                """
                INSERT INTO raw_emails (
                    source_row, stt, subject, body, received_time, entry_id, status, assigned_to, recipients,
                    row_hash, source_file, source_file_mtime, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.get("source_row"),
                    row.get("stt"),
                    row.get("subject"),
                    row.get("body"),
                    row.get("received_time"),
                    row.get("entry_id"),
                    row.get("status"),
                    row.get("assigned_to"),
                    row.get("recipients"),
                    row.get("row_hash"),
                    row.get("source_file"),
                    row.get("source_file_mtime"),
                    row.get("imported_at"),
                ),
            )
            inserted += 1

    return inserted, updated


def write_dashboard_snapshot(conn: sqlite3.Connection, dashboard_df: pd.DataFrame, imported_at: str) -> int:
    """Atomically replace current dashboard snapshot via staging table."""
    df = dashboard_df.copy()
    for col in DASHBOARD_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    df = df[DASHBOARD_COLUMNS].copy()
    for col in df.columns:
        if col in {"Thời gian SLA", "Thời gian SLA HTTD", "Thời gian SLA BGĐ"}:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = df[col].map(lambda v: None if pd.isna(v) else str(v))
    df["imported_at"] = imported_at
    cols = list(df.columns)

    clear_table(conn, "dashboard_records_staging")
    if not df.empty:
        col_sql = ", ".join(_q(c) for c in cols)
        val_sql = ", ".join("?" for _ in cols)
        conn.executemany(
            f"INSERT INTO dashboard_records_staging ({col_sql}) VALUES ({val_sql})",
            df.where(pd.notna(df), None).values.tolist(),
        )

    clear_table(conn, "dashboard_records")
    conn.execute(
        f"INSERT INTO dashboard_records ({', '.join(_q(c) for c in cols)}) "
        f"SELECT {', '.join(_q(c) for c in cols)} FROM dashboard_records_staging"
    )
    return len(df)


def insert_sync_run_start(
    conn: sqlite3.Connection,
    started_at: str,
    mode: str,
    source_file: str,
    source_file_mtime: float,
    source_file_size: int,
) -> int:
    """Insert sync run start row and return run id."""
    cur = conn.execute(
        """
        INSERT INTO sync_runs (started_at, status, mode, source_file, source_file_mtime, source_file_size)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (started_at, "RUNNING", mode, source_file, source_file_mtime, source_file_size),
    )
    return int(cur.lastrowid)


def update_sync_run_end(
    conn: sqlite3.Connection,
    run_id: int,
    finished_at: str,
    status: str,
    data_row_count: int,
    dashboard_row_count: int,
    raw_inserted: int,
    raw_updated: int,
    duration_ms: int,
    error_message: str | None,
) -> None:
    """Finalize sync run row."""
    conn.execute(
        """
        UPDATE sync_runs
        SET finished_at=?, status=?, data_row_count=?, dashboard_row_count=?, raw_inserted=?, raw_updated=?, duration_ms=?, error_message=?
        WHERE id=?
        """,
        (
            finished_at,
            status,
            data_row_count,
            dashboard_row_count,
            raw_inserted,
            raw_updated,
            duration_ms,
            error_message,
            run_id,
        ),
    )


def create_sync_run_with_status(
    conn: sqlite3.Connection,
    *,
    started_at: str,
    finished_at: str,
    mode: str,
    source_file: str,
    source_file_mtime: float,
    source_file_size: int,
    status: str,
    data_row_count: int = 0,
    dashboard_row_count: int = 0,
    raw_inserted: int = 0,
    raw_updated: int = 0,
    duration_ms: int = 0,
    error_message: str | None = None,
) -> int:
    """Insert a non-running sync row (for SKIPPED/FAILED watch-loop events)."""
    cur = conn.execute(
        """
        INSERT INTO sync_runs (
            started_at, finished_at, status, mode, source_file, source_file_mtime, source_file_size,
            data_row_count, dashboard_row_count, raw_inserted, raw_updated, error_message, duration_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            started_at,
            finished_at,
            status,
            mode,
            source_file,
            source_file_mtime,
            source_file_size,
            data_row_count,
            dashboard_row_count,
            raw_inserted,
            raw_updated,
            error_message,
            duration_ms,
        ),
    )
    return int(cur.lastrowid)


def insert_processing_logs(conn: sqlite3.Connection, logs: list[dict[str, Any]]) -> int:
    """Insert processing log entries."""
    if not logs:
        return 0
    conn.executemany(
        """
        INSERT INTO processing_log (sync_run_id, source_row, entry_id, subject, level, action, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row.get("sync_run_id"),
                row.get("source_row"),
                row.get("entry_id"),
                row.get("subject"),
                row.get("level"),
                row.get("action"),
                row.get("message"),
                row.get("created_at"),
            )
            for row in logs
        ],
    )
    return len(logs)
