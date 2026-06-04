"""SQLite storage layer for SmartVCOMS Outlook shadow reader."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .sqlite_store import connect_sqlite


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return str(value)


def to_sqlite_safe(value: Any) -> Any:
    """Normalize common pandas/numpy/datetime values for SQLite bindings."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        if pd.isna(value):
            return None
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (dict, list)):
        return json.dumps(_json_safe(value), ensure_ascii=False)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def create_outlook_tables(db_path: str | Path) -> None:
    """Create Outlook shadow tables without touching production dashboard tables."""
    conn = connect_sqlite(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS outlook_raw_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id TEXT,
                internet_message_id TEXT,
                conversation_id TEXT,
                subject TEXT,
                body TEXT,
                received_time TEXT,
                sender_email TEXT,
                sender_name TEXT,
                to_recipients TEXT,
                cc_recipients TEXT,
                recipients_text TEXT,
                folder_path TEXT,
                subject_matched INTEGER DEFAULT 0,
                sender_matched INTEGER DEFAULT 0,
                body_hash TEXT,
                row_hash TEXT,
                imported_at TEXT,
                updated_at TEXT,
                source TEXT,
                is_valid INTEGER DEFAULT 1,
                parse_warning TEXT,
                UNIQUE(entry_id),
                UNIQUE(row_hash)
            );

            CREATE TABLE IF NOT EXISTS outlook_reader_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_path TEXT UNIQUE,
                last_received_time TEXT,
                last_entry_id TEXT,
                last_success_at TEXT,
                last_error TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS outlook_reader_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                finished_at TEXT,
                mode TEXT,
                status TEXT,
                folder_path TEXT,
                since TEXT,
                overlap_minutes INTEGER,
                max_items INTEGER,
                scanned_count INTEGER,
                matched_count INTEGER,
                inserted_count INTEGER,
                updated_count INTEGER,
                skipped_count INTEGER,
                error_message TEXT,
                duration_ms INTEGER
            );

            CREATE TABLE IF NOT EXISTS outlook_reader_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                level TEXT,
                entry_id TEXT,
                subject TEXT,
                action TEXT,
                message TEXT,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dashboard_records_outlook_shadow (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shadow_run_id INTEGER,
                source TEXT,
                created_at TEXT,
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
                "Thời gian SLA BGĐ" REAL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_outlook_reader_run(
    db_path: str | Path,
    *,
    mode: str,
    folder_path: str,
    since: str | None,
    overlap_minutes: int,
    max_items: int,
) -> int:
    """Create a reader run row with RUNNING state."""
    conn = connect_sqlite(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO outlook_reader_runs
            (started_at, mode, status, folder_path, since, overlap_minutes, max_items)
            VALUES (?, ?, 'RUNNING', ?, ?, ?, ?)
            """,
            tuple(
                to_sqlite_safe(v)
                for v in (_now_iso(), mode, folder_path, since, overlap_minutes, max_items)
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def finish_outlook_reader_run(
    db_path: str | Path,
    run_id: int,
    *,
    status: str,
    scanned_count: int = 0,
    matched_count: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    skipped_count: int = 0,
    error_message: str | None = None,
    duration_ms: int | None = None,
) -> None:
    """Finalize a reader run."""
    conn = connect_sqlite(db_path)
    try:
        conn.execute(
            """
            UPDATE outlook_reader_runs
            SET finished_at=?, status=?, scanned_count=?, matched_count=?, inserted_count=?, updated_count=?,
                skipped_count=?, error_message=?, duration_ms=?
            WHERE id=?
            """,
            tuple(
                to_sqlite_safe(v)
                for v in (
                    _now_iso(),
                    status,
                    scanned_count,
                    matched_count,
                    inserted_count,
                    updated_count,
                    skipped_count,
                    error_message,
                    duration_ms,
                    run_id,
                )
            ),
        )
        conn.commit()
    finally:
        conn.close()


def insert_outlook_reader_log(
    db_path: str | Path,
    *,
    run_id: int | None,
    level: str,
    action: str,
    message: str,
    entry_id: str | None = None,
    subject: str | None = None,
) -> None:
    """Insert one reader log row."""
    conn = connect_sqlite(db_path)
    try:
        conn.execute(
            """
            INSERT INTO outlook_reader_log
            (run_id, level, entry_id, subject, action, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(
                to_sqlite_safe(v)
                for v in (run_id, level, entry_id, subject, action, message, _now_iso())
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_outlook_reader_state(db_path: str | Path, folder_path: str) -> dict[str, Any]:
    """Read reader state for one folder path."""
    conn = connect_sqlite(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM outlook_reader_state WHERE folder_path = ? LIMIT 1",
            (folder_path,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def update_outlook_reader_state(
    db_path: str | Path,
    *,
    folder_path: str,
    last_received_time: str | None,
    last_entry_id: str | None,
    last_success_at: str | None = None,
    last_error: str | None = None,
) -> None:
    """Upsert reader state."""
    conn = connect_sqlite(db_path)
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO outlook_reader_state
            (folder_path, last_received_time, last_entry_id, last_success_at, last_error, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(folder_path) DO UPDATE SET
              last_received_time=excluded.last_received_time,
              last_entry_id=excluded.last_entry_id,
              last_success_at=excluded.last_success_at,
              last_error=excluded.last_error,
              updated_at=excluded.updated_at
            """,
            tuple(
                to_sqlite_safe(v)
                for v in (
                    folder_path,
                    last_received_time,
                    last_entry_id,
                    last_success_at,
                    last_error,
                    now,
                )
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _prepare_outlook_row(rec: dict[str, Any]) -> dict[str, Any]:
    entry_id = str(rec.get("entry_id") or "").strip()
    subject = str(rec.get("subject") or "").strip()
    body = str(rec.get("body") or "")
    received_time = str(rec.get("received_time") or "")
    sender_email = str(rec.get("sender_email") or "").strip()
    recipients_text = str(rec.get("recipients_text") or "").strip()
    body_hash = rec.get("body_hash") or _hash_text(body)
    row_hash = rec.get("row_hash") or _hash_text(
        "|".join([entry_id, subject, received_time, body_hash, recipients_text])
    )
    prepared = {
        "entry_id": entry_id or None,
        "internet_message_id": rec.get("internet_message_id"),
        "conversation_id": rec.get("conversation_id"),
        "subject": subject,
        "body": body,
        "received_time": received_time,
        "sender_email": sender_email,
        "sender_name": rec.get("sender_name"),
        "to_recipients": rec.get("to_recipients"),
        "cc_recipients": rec.get("cc_recipients"),
        "recipients_text": recipients_text,
        "folder_path": rec.get("folder_path"),
        "subject_matched": int(bool(rec.get("subject_matched"))),
        "sender_matched": int(bool(rec.get("sender_matched"))),
        "body_hash": body_hash,
        "row_hash": row_hash,
        "imported_at": rec.get("imported_at") or _now_iso(),
        "updated_at": _now_iso(),
        "source": rec.get("source") or "outlook",
        "is_valid": int(rec.get("is_valid", 1)),
        "parse_warning": rec.get("parse_warning"),
    }
    return {k: to_sqlite_safe(v) for k, v in prepared.items()}


def upsert_outlook_raw_emails(
    db_path: str | Path, records: list[dict[str, Any]], run_id: int | None = None
) -> tuple[int, int]:
    """Upsert Outlook raw records by entry_id, fallback row_hash."""
    conn = connect_sqlite(db_path)
    inserted = 0
    updated = 0
    try:
        for rec in records:
            row = _prepare_outlook_row(rec)
            existing = None
            if row["entry_id"]:
                existing = conn.execute(
                    "SELECT id FROM outlook_raw_emails WHERE entry_id = ?",
                    (row["entry_id"],),
                ).fetchone()
            if existing is None:
                existing = conn.execute(
                    "SELECT id FROM outlook_raw_emails WHERE row_hash = ?",
                    (row["row_hash"],),
                ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE outlook_raw_emails
                    SET internet_message_id=?, conversation_id=?, subject=?, body=?, received_time=?, sender_email=?,
                        sender_name=?, to_recipients=?, cc_recipients=?, recipients_text=?, folder_path=?,
                        subject_matched=?, sender_matched=?, body_hash=?, row_hash=?, updated_at=?, source=?,
                        is_valid=?, parse_warning=?
                    WHERE id=?
                    """,
                    tuple(
                        to_sqlite_safe(v)
                        for v in (
                            row["internet_message_id"],
                            row["conversation_id"],
                            row["subject"],
                            row["body"],
                            row["received_time"],
                            row["sender_email"],
                            row["sender_name"],
                            row["to_recipients"],
                            row["cc_recipients"],
                            row["recipients_text"],
                            row["folder_path"],
                            row["subject_matched"],
                            row["sender_matched"],
                            row["body_hash"],
                            row["row_hash"],
                            row["updated_at"],
                            row["source"],
                            row["is_valid"],
                            row["parse_warning"],
                            existing["id"],
                        )
                    ),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO outlook_raw_emails
                    (entry_id, internet_message_id, conversation_id, subject, body, received_time, sender_email,
                     sender_name, to_recipients, cc_recipients, recipients_text, folder_path, subject_matched,
                     sender_matched, body_hash, row_hash, imported_at, updated_at, source, is_valid, parse_warning)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    tuple(
                        to_sqlite_safe(v)
                        for v in (
                            row["entry_id"],
                            row["internet_message_id"],
                            row["conversation_id"],
                            row["subject"],
                            row["body"],
                            row["received_time"],
                            row["sender_email"],
                            row["sender_name"],
                            row["to_recipients"],
                            row["cc_recipients"],
                            row["recipients_text"],
                            row["folder_path"],
                            row["subject_matched"],
                            row["sender_matched"],
                            row["body_hash"],
                            row["row_hash"],
                            row["imported_at"],
                            row["updated_at"],
                            row["source"],
                            row["is_valid"],
                            row["parse_warning"],
                        )
                    ),
                )
                inserted += 1
        conn.commit()
        if run_id:
            insert_outlook_reader_log(
                db_path,
                run_id=run_id,
                level="INFO",
                action="UPSERT_RAW",
                message=f"inserted={inserted}, updated={updated}",
            )
        return inserted, updated
    finally:
        conn.close()


def load_outlook_raw_emails_as_dataframe(
    db_path: str | Path,
    *,
    folder_path: str | None = None,
    since: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """Load raw outlook records for adapter/compare."""
    conn = connect_sqlite(db_path)
    try:
        sql = "SELECT * FROM outlook_raw_emails"
        where = []
        params: list[Any] = []
        if folder_path:
            where.append("folder_path = ?")
            params.append(folder_path)
        if since:
            where.append("received_time >= ?")
            params.append(since)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY datetime(received_time) ASC, id ASC"
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def write_dashboard_records_outlook_shadow(
    db_path: str | Path,
    dashboard_df: pd.DataFrame,
    *,
    shadow_run_id: int | None,
    source: str = "outlook_shadow",
) -> int:
    """Write one shadow snapshot into dashboard_records_outlook_shadow."""
    conn = connect_sqlite(db_path)
    try:
        cols = [
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
        now = _now_iso()
        conn.execute("DELETE FROM dashboard_records_outlook_shadow WHERE source = ?", (source,))
        for _, row in dashboard_df.iterrows():
            values = []
            for c in cols:
                values.append(to_sqlite_safe(row.get(c)))
            conn.execute(
                f"""
                INSERT INTO dashboard_records_outlook_shadow
                (shadow_run_id, source, created_at, {', '.join('\"'+c+'\"' for c in cols)})
                VALUES (?, ?, ?, {', '.join('?' for _ in cols)})
                """,
                [to_sqlite_safe(shadow_run_id), to_sqlite_safe(source), to_sqlite_safe(now), *values],
            )
        conn.commit()
        return len(dashboard_df)
    finally:
        conn.close()


def build_data_like_dataframe_from_outlook(outlook_df: pd.DataFrame) -> pd.DataFrame:
    """Adapter: convert outlook_raw_emails dataframe to Data-sheet-like schema."""
    if outlook_df is None or outlook_df.empty:
        return pd.DataFrame(
            columns=["STT", "Tiêu đề", "Nội dung", "Thời gian nhận email", "EntryID", "Status", "Giao cho", "Người nhận"]
        )
    df = outlook_df.copy()
    for col in ["subject", "body", "received_time", "entry_id", "recipients_text"]:
        if col not in df.columns:
            df[col] = ""
    df["received_time"] = pd.to_datetime(df["received_time"], errors="coerce")
    df = df.sort_values(by=["received_time", "entry_id"], na_position="last").reset_index(drop=True)
    out = pd.DataFrame(
        {
            "STT": range(1, len(df) + 1),
            "Tiêu đề": df["subject"].fillna(""),
            "Nội dung": df["body"].fillna(""),
            "Thời gian nhận email": df["received_time"],
            "EntryID": df["entry_id"].fillna(""),
            "Status": "",
            "Giao cho": "",
            "Người nhận": df["recipients_text"].fillna(""),
        }
    )
    return out


def hash_outlook_like_row(subject: str, body: str, received_time: str, recipients_text: str) -> tuple[str, str]:
    """Return (body_hash, row_hash) for dedupe fallback."""
    body_hash = _hash_text(body or "")
    row_hash = _hash_text("|".join([subject or "", received_time or "", body_hash, recipients_text or ""]))
    return body_hash, row_hash


def to_json_text(payload: Any) -> str:
    """Serialize payload safely to JSON string for lightweight reports/logs."""
    return json.dumps(_json_safe(payload), ensure_ascii=False)
