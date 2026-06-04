from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def _print_sqlite_counts(db_path: str) -> None:
    print("[DB COUNT]")
    count_cmd = [
        sys.executable,
        "-c",
        (
            "import sqlite3; "
            f"c=sqlite3.connect(r'{db_path}'); "
            "raw=c.execute('SELECT COUNT(*) FROM outlook_raw_emails').fetchone()[0]; "
            "evt=c.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vcoms_email_events'\").fetchone()[0]; "
            "cas=c.execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='vcoms_case_state'\").fetchone()[0]; "
            "evc=c.execute('SELECT COUNT(*) FROM vcoms_email_events').fetchone()[0] if evt else -1; "
            "cac=c.execute('SELECT COUNT(*) FROM vcoms_case_state').fetchone()[0] if cas else -1; "
            "print(f'outlook_raw_emails={raw} vcoms_email_events={evc} vcoms_case_state={cac}'); c.close()"
        ),
    ]
    subprocess.run(count_cmd, cwd=ROOT)


def run_once(args: argparse.Namespace) -> int:
    print("[START RAW SYNC]")
    reader_cmd = [
        sys.executable,
        str(ROOT / "backend/modules/smartvcoms/runner/read_vcoms_outlook_to_sqlite.py"),
        "--db",
        args.db,
        "--folder",
        args.folder,
        "--max-items",
        str(args.max_items),
        "--overlap-minutes",
        str(args.overlap_minutes),
    ]
    if args.reader_today_only:
        reader_cmd.append("--today-only")
    if args.verbose:
        reader_cmd.append("--verbose")
    if args.once:
        reader_cmd.append("--once")
    rc = subprocess.run(reader_cmd, cwd=ROOT).returncode
    if rc != 0:
        print(f"[RAW SYNC FAILED] rc={rc}")
        return rc
    print("[RAW SYNC OK]")

    print("[START LEGACY PROCESS]")
    process_cmd = [
        sys.executable,
        str(ROOT / "backend/modules/smartvcoms/runner/process_vcoms_raw_to_sqlite.py"),
        "--db",
        args.db,
        "--config-source",
        "sqlite",
        "--target-table",
        args.target_table,
    ]
    if args.process_scope == "today":
        process_cmd.append("--today-only")
    process_rc = subprocess.run(process_cmd, cwd=ROOT).returncode
    if process_rc != 0:
        print(f"[LEGACY PROCESS FAILED] rc={process_rc}")
    else:
        print("[LEGACY PROCESS OK]")

    rebuild_rc = 0
    if args.rebuild_case_state_v2:
        print("[START REBUILD CASE_STATE V2]")
        rebuild_cmd = [
            sys.executable,
            str(ROOT / "backend/modules/smartvcoms/runner/rebuild_vcoms_case_state.py"),
            "--db",
            args.db,
            "--reset",
        ]
        if args.verbose:
            rebuild_cmd.append("--verbose")
        rebuild_rc = subprocess.run(rebuild_cmd, cwd=ROOT).returncode
        if rebuild_rc != 0:
            print(f"[REBUILD CASE_STATE V2 FAILED] rc={rebuild_rc}")
        else:
            print("[REBUILD CASE_STATE V2 OK]")

    _print_sqlite_counts(args.db)

    if process_rc != 0:
        # Keep compatibility with legacy pipeline status while allowing V2 rebuild to continue.
        return process_rc
    if rebuild_rc != 0:
        return rebuild_rc

    count_cmd = [
        sys.executable,
        "-c",
        (
            "import sqlite3; "
            f"c=sqlite3.connect(r'{args.db}'); "
            "raw=c.execute('SELECT COUNT(*) FROM outlook_raw_emails').fetchone()[0]; "
            f"proc=c.execute('SELECT COUNT(*) FROM {args.target_table}').fetchone()[0]; "
            "print(f'raw_count={raw} processed_count={proc}'); c.close()"
        ),
    ]
    subprocess.run(count_cmd, cwd=ROOT)
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="runtime_data/smartvcoms/vcoms.db")
    p.add_argument("--folder", default=os.getenv("VCOMS_OUTLOOK_FOLDER", "VCOMS"))
    p.add_argument("--target-table", default="dashboard_records_processed")
    p.add_argument("--excel-config", default="package_config/mock/VCOMS_Data.xlsm")
    p.add_argument("--interval", type=int, default=15)
    p.add_argument("--max-items", type=int, default=300)
    p.add_argument("--overlap-minutes", type=int, default=5)
    p.add_argument("--today-only", action="store_true")
    p.add_argument("--no-today-only", action="store_true")
    p.add_argument("--reader-today-only", action="store_true")
    p.add_argument("--no-reader-today-only", action="store_true")
    p.add_argument("--process-scope", choices=["history", "today"], default="history")
    p.add_argument("--once", action="store_true")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--list-folders", action="store_true")
    p.add_argument("--folder-depth", type=int, default=2)
    p.add_argument("--rebuild-case-state-v2", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    # Backward-compat: --today-only aliases reader today-only only.
    if args.no_reader_today_only:
        args.reader_today_only = False
    elif args.reader_today_only:
        args.reader_today_only = True
    elif args.no_today_only:
        args.reader_today_only = False
    else:
        args.reader_today_only = True
    if args.today_only:
        args.reader_today_only = True
    print(f"[INFO] reader_today_only={args.reader_today_only}")
    print(f"[INFO] process_scope={args.process_scope}")
    print(f"[INFO] rebuild_case_state_v2={args.rebuild_case_state_v2}")
    if args.list_folders:
        cmd = [
            sys.executable,
            str(ROOT / "backend/modules/smartvcoms/runner/read_vcoms_outlook_to_sqlite.py"),
            "--list-folders",
            "--folder-depth",
            str(args.folder_depth),
        ]
        if args.verbose:
            cmd.append("--verbose")
        return subprocess.run(cmd, cwd=ROOT).returncode

    if not args.once and not args.watch:
        args.once = True

    if args.watch:
        while True:
            rc = run_once(args)
            if rc != 0:
                print(f"[WARN] cycle failed rc={rc}")
            sleep_s = max(2, args.interval)
            print(f"[SLEEP {sleep_s}s]")
            time.sleep(sleep_s)
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
