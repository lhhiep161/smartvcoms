"""Build SmartVCOMS SQLite state from Outlook raw emails."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.smartvcoms.store.config_admin import ensure_assignment_day_state, sync_config_cb_load_from_case_state
from backend.modules.smartvcoms.pipeline.state_machine import rebuild_from_raw


def _safe_console_setup() -> None:
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _sync_processed_snapshot_from_case_state(db_path: str, target_table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        df = conn.execute(
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
                arrival_time AS "Thời gian nhận email",
                updated_at AS "Cập nhật cuối",
                entry_id_last AS "EntryID",
                sla_minutes AS "Thời gian SLA",
                NULL AS "Thời gian SLA HTTD",
                NULL AS "Thời gian SLA BGĐ"
            FROM vcoms_case_state
            ORDER BY business_date DESC, stt ASC, id ASC
            """
        ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT stt FROM vcoms_case_state LIMIT 0").description] if False else None
        # Use pandas for easier write with quoted headers.
        import pandas as pd

        snap = pd.read_sql_query(
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
                arrival_time AS "Thời gian nhận email",
                updated_at AS "Cập nhật cuối",
                entry_id_last AS "EntryID",
                sla_minutes AS "Thời gian SLA",
                NULL AS "Thời gian SLA HTTD",
                NULL AS "Thời gian SLA BGĐ"
            FROM vcoms_case_state
            ORDER BY business_date DESC, stt ASC, id ASC
            """,
            conn,
        )
        snap.to_sql(target_table, conn, if_exists="replace", index=False)
        return len(snap)
    finally:
        conn.close()


def main() -> int:
    _safe_console_setup()
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime_data/smartvcoms/vcoms.db")
    parser.add_argument("--target-table", default="dashboard_records_processed")
    parser.add_argument("--config-source", choices=["sqlite", "excel"], default="sqlite")
    parser.add_argument("--today-only", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.config_source != "sqlite":
        raise RuntimeError("sqlite_only_pipeline: config_source must be sqlite")

    reset_done, assignment_date = ensure_assignment_day_state(args.db)
    print(f"[PROCESS] db={args.db} config_source=sqlite target_table={args.target_table}")
    print(f"[PROCESS] assignment_date={assignment_date}")
    print(f"[PROCESS] assignment_daily_reset={reset_done}")

    stats = rebuild_from_raw(
        db_path=args.db,
        reset=args.reset,
        today_only=args.today_only,
        verbose=args.verbose,
    )
    output_count = _sync_processed_snapshot_from_case_state(args.db, args.target_table)
    sync_config_cb_load_from_case_state(args.db)

    print(
        "[PROCESS] "
        f"raw_count={stats.raw_count} event_count={stats.event_count} "
        f"case_count={stats.case_count} output_count={output_count} "
        f"target_table={args.target_table}"
    )
    print(
        "[PROCESS] "
        f"unmatched_count={stats.unmatched_count} parse_warning_count={stats.parse_warning_count} "
        f"LC_count={stats.lc_count} returned_count={stats.returned_count} sla_changed_count={stats.sla_changed_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
