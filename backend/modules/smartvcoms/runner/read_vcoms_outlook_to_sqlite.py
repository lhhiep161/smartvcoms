"""Read Outlook raw emails into SQLite and build SmartVCOMS shadow dashboard."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.smartvcoms.pipeline.excel_io import WorkbookInputs, read_workbook_inputs
from backend.modules.smartvcoms.pipeline.outlook_reader import (
    compute_since_from_state,
    list_outlook_folders,
    poll_outlook_folder,
)
from backend.modules.smartvcoms.store.outlook_store import (
    build_data_like_dataframe_from_outlook,
    create_outlook_reader_run,
    create_outlook_tables,
    finish_outlook_reader_run,
    get_outlook_reader_state,
    hash_outlook_like_row,
    load_outlook_raw_emails_as_dataframe,
    update_outlook_reader_state,
    upsert_outlook_raw_emails,
    write_dashboard_records_outlook_shadow,
)
from backend.modules.smartvcoms.store.sqlite_reader import load_workbook_inputs_config_from_sqlite
from backend.modules.smartvcoms.pipeline.transform import process_data_to_dashboard


LOGGER = logging.getLogger("vcoms_outlook_reader")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _normalize_dashboard_df_for_sqlite(df: pd.DataFrame) -> pd.DataFrame:
    def _cell(v):
        if isinstance(v, pd.Timestamp):
            return v.isoformat()
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v
    return df.copy().apply(lambda col: col.map(_cell))


def _build_inputs_for_processing(args, data_df: pd.DataFrame) -> WorkbookInputs:
    if args.config_source == "sqlite":
        try:
            return load_workbook_inputs_config_from_sqlite(args.db, data_df)
        except Exception:
            if args.mock_from_excel:
                wb = read_workbook_inputs(args.mock_from_excel)
                wb.data = data_df
                wb.dashboard = pd.DataFrame(columns=wb.dashboard.columns)
                return wb
            raise
    wb = read_workbook_inputs(args.mock_from_excel or "package_config/mock/VCOMS_Data.xlsm")
    wb.data = data_df
    wb.dashboard = pd.DataFrame(columns=wb.dashboard.columns)
    return wb


def _records_from_excel_data(path: str, folder_path: str) -> list[dict[str, Any]]:
    wb = read_workbook_inputs(path)
    data = wb.data.copy()
    records = []
    for _, r in data.iterrows():
        subject = str(r.get("Tiêu đề") or "")
        body = str(r.get("Nội dung") or "")
        received = pd.to_datetime(r.get("Thời gian nhận email"), errors="coerce")
        entry_id = str(r.get("EntryID") or "")
        recipients = str(r.get("Người nhận") or "")
        b_hash, row_hash = hash_outlook_like_row(subject, body, received.isoformat() if pd.notna(received) else "", recipients)
        records.append(
            {
                "entry_id": entry_id,
                "subject": subject,
                "body": body,
                "received_time": received.isoformat() if pd.notna(received) else "",
                "sender_email": "vcoms@vietinbank.vn",
                "sender_name": "VCOMS",
                "to_recipients": recipients,
                "cc_recipients": "",
                "recipients_text": recipients,
                "folder_path": folder_path,
                "subject_matched": "vcoms_" in subject.lower(),
                "sender_matched": True,
                "body_hash": b_hash,
                "row_hash": row_hash,
                "source": "mock_from_excel",
                "is_valid": 1 if subject and body and entry_id else 0,
                "parse_warning": "",
            }
        )
    return records


def _run_once(args) -> int:
    create_outlook_tables(args.db)
    state = get_outlook_reader_state(args.db, args.folder)
    since_dt = compute_since_from_state(state, days_back=args.days_back, overlap_minutes=args.overlap_minutes)
    today_start = None
    today_end = None
    if args.since_date:
        try:
            since_dt = datetime.strptime(args.since_date, "%Y-%m-%d")
        except ValueError:
            raise RuntimeError("--since-date must be YYYY-MM-DD")
    if args.today_only:
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = today_start + timedelta(days=1)
        if state and state.get("last_received_time"):
            last = pd.to_datetime(state.get("last_received_time"), errors="coerce")
            if pd.notna(last):
                incremental_since = last.to_pydatetime() - timedelta(minutes=args.overlap_minutes)
                since_dt = max(today_start, incremental_since)
            else:
                since_dt = today_start
        else:
            since_dt = today_start
    since = since_dt.isoformat()

    run_id = create_outlook_reader_run(
        args.db,
        mode="watch" if args.watch else "once",
        folder_path=args.folder,
        since=since,
        overlap_minutes=args.overlap_minutes,
        max_items=args.max_items,
    )
    started = time.time()
    scanned = matched = inserted = updated = skipped = 0
    try:
        if args.mock_from_excel:
            records = _records_from_excel_data(args.mock_from_excel, args.folder)
            scanned = matched = len(records)
        else:
            LOGGER.info("Outlook folder requested: %s", args.folder)
            LOGGER.info("Since: %s", since_dt.isoformat())
            LOGGER.info("Subject keyword: %s", args.subject_keyword)
            records, meta = poll_outlook_folder(
                folder_path=args.folder,
                since=since_dt,
                max_items=args.max_items,
                subject_keyword=args.subject_keyword,
            )
            scanned = int(meta.get("scanned_count", 0))
            matched = int(meta.get("matched_count", 0))
            LOGGER.info("Outlook folder resolved: %s", meta.get("resolved_folder_path", ""))
            if args.today_only and today_start and today_end:
                records = [
                    r for r in records
                    if pd.notna(pd.to_datetime(r.get("received_time"), errors="coerce"))
                    and today_start <= pd.to_datetime(r.get("received_time"), errors="coerce").to_pydatetime() < today_end
                ]
                matched = len(records)
                LOGGER.info("today_only=True today_start=%s today_end=%s", today_start.isoformat(), today_end.isoformat())

        if args.dry_run:
            LOGGER.info("dry-run scanned=%s matched=%s", scanned, matched)
            if args.export:
                pd.DataFrame(records).to_excel(args.export, index=False)
            finish_outlook_reader_run(
                args.db,
                run_id,
                status="SUCCESS",
                scanned_count=scanned,
                matched_count=matched,
                skipped_count=0,
                duration_ms=int((time.time() - started) * 1000),
            )
            return 0

        inserted, updated = upsert_outlook_raw_emails(args.db, records, run_id=run_id)
        skipped = max(0, matched - inserted - updated)

        if args.process_shadow:
            raw_df = load_outlook_raw_emails_as_dataframe(
                args.db,
                folder_path=args.folder,
                since=(today_start.isoformat() if (args.today_only and today_start) else None),
            )
            if args.today_only and today_start and today_end and not raw_df.empty:
                rt = pd.to_datetime(raw_df.get("received_time"), errors="coerce")
                raw_df = raw_df[(rt >= today_start) & (rt < today_end)].copy()
            data_like = build_data_like_dataframe_from_outlook(raw_df)
            inputs = _build_inputs_for_processing(args, data_like)
            dashboard_df = process_data_to_dashboard(inputs, skip_done=False)
            if isinstance(dashboard_df, tuple):
                dashboard_df = dashboard_df[0]
            dashboard_df = _normalize_dashboard_df_for_sqlite(dashboard_df)
            if args.process_target_table == "dashboard_records_outlook_shadow":
                write_dashboard_records_outlook_shadow(
                    args.db, dashboard_df, shadow_run_id=run_id, source="outlook_shadow"
                )
            else:
                import sqlite3

                conn = sqlite3.connect(args.db)
                try:
                    dashboard_df.to_sql(args.process_target_table, conn, if_exists="replace", index=False)
                finally:
                    conn.close()

        if matched > 0:
            latest = sorted(
                [r for r in records if r.get("received_time")],
                key=lambda x: x.get("received_time", ""),
            )[-1]
            update_outlook_reader_state(
                args.db,
                folder_path=args.folder,
                last_received_time=latest.get("received_time"),
                last_entry_id=latest.get("entry_id"),
                last_success_at=datetime.now().isoformat(timespec="seconds"),
                last_error=None,
            )
        finish_outlook_reader_run(
            args.db,
            run_id,
            status="SUCCESS",
            scanned_count=scanned,
            matched_count=matched,
            inserted_count=inserted,
            updated_count=updated,
            skipped_count=skipped,
            duration_ms=int((time.time() - started) * 1000),
        )
        LOGGER.info(
            "reader success scanned=%s matched=%s inserted=%s updated=%s skipped=%s",
            scanned,
            matched,
            inserted,
            updated,
            skipped,
        )
        if args.today_only:
            LOGGER.info(
                "today_only summary: since=%s matched_today=%s inserted=%s updated=%s",
                since_dt.isoformat(),
                matched,
                inserted,
                updated,
            )
        return 0
    except Exception as exc:
        msg = str(exc)
        if "Cannot find Outlook folder token" in msg or "top-level mailbox/store" in msg:
            LOGGER.error("Folder VCOMS theo ảnh Outlook đang nằm cùng cấp Inbox.")
            LOGGER.error('Hãy thử: --folder "VCOMS"')
            LOGGER.error('Hoặc: --folder "cn9@vietinbank.vn/VCOMS"')
        update_outlook_reader_state(
            args.db,
            folder_path=args.folder,
            last_received_time=state.get("last_received_time"),
            last_entry_id=state.get("last_entry_id"),
            last_success_at=state.get("last_success_at"),
            last_error=str(exc),
        )
        finish_outlook_reader_run(
            args.db,
            run_id,
            status="FAILED",
            scanned_count=scanned,
            matched_count=matched,
            inserted_count=inserted,
            updated_count=updated,
            skipped_count=skipped,
            error_message=str(exc),
            duration_ms=int((time.time() - started) * 1000),
        )
        LOGGER.error("reader failed: %s", exc)
        return 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="runtime_data/smartvcoms/vcoms.db")
    p.add_argument("--folder", default=os.getenv("VCOMS_OUTLOOK_FOLDER", "VCOMS"))
    p.add_argument("--list-folders", action="store_true")
    p.add_argument("--folder-depth", type=int, default=3)
    p.add_argument("--subject-keyword", default="VCOMS_")
    p.add_argument("--days-back", type=int, default=1)
    p.add_argument("--today-only", action="store_true")
    p.add_argument("--since-date", default="")
    p.add_argument("--overlap-minutes", type=int, default=5)
    p.add_argument("--max-items", type=int, default=300)
    p.add_argument("--interval", type=int, default=10)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--process-shadow", action="store_true")
    p.add_argument("--process-target-table", default="dashboard_records_processed")
    p.add_argument("--config-source", choices=["sqlite", "excel"], default="sqlite")
    p.add_argument("--mock-from-excel")
    p.add_argument("--export")
    p.add_argument("--write-dashboard-production", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    _setup_logging(args.verbose)
    LOGGER.info(
        "reader args db=%s folder=%s today_only=%s since_date=%s max_items=%s overlap=%s",
        args.db,
        args.folder,
        args.today_only,
        args.since_date or "-",
        args.max_items,
        args.overlap_minutes,
    )
    if args.list_folders:
        for line in list_outlook_folders(max_depth=args.folder_depth):
            print(line)
        return 0
    if args.write_dashboard_production:
        raise RuntimeError(
            "Production write is intentionally disabled in this package. Use shadow mode only."
        )
    if not args.once and not args.watch and not args.dry_run:
        args.once = True
    if args.watch:
        while True:
            code = _run_once(args)
            if code != 0:
                LOGGER.warning("watch cycle failed, continue next loop")
            time.sleep(max(2, args.interval))
    return _run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
