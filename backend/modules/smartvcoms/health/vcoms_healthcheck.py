"""Healthcheck for SmartVCOMS SQLite + watch runtime status."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sqlite3
from ..store.sqlite_reader import get_sqlite_sync_health, sqlite_db_is_ready


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime_data/smartvcoms/vcoms.db")
    parser.add_argument("--status", default="runtime_data/smartvcoms/status/vcoms_sync_status.json")
    parser.add_argument("--max-age-seconds", type=int, default=120)
    return parser.parse_args()


def _iso_to_dt(v: str | None):
    if not v:
        return None
    try:
        return datetime.fromisoformat(v)
    except Exception:
        return None


def _print(msg: str) -> None:
    print(msg)


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    status_path = Path(args.status)

    errors: list[str] = []
    warns: list[str] = []

    if not db_path.exists():
        errors.append(f"DB missing: {db_path}")
    else:
        try:
            db_ready, db_reason = sqlite_db_is_ready(db_path)
            if not db_ready:
                errors.append(f"SQLite not ready: {db_reason}")
            conn = sqlite3.connect(str(db_path))
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                for table in ["dashboard_records", "config_cb_full", "config_ld", "sla_config", "sync_runs"]:
                    if table not in tables:
                        errors.append(f"Missing table: {table}")

                if not errors:
                    dashboard_count = int(conn.execute("SELECT COUNT(*) FROM dashboard_records").fetchone()[0])
                    cb_count = int(conn.execute("SELECT COUNT(*) FROM config_cb_full").fetchone()[0])
                    ld_count = int(conn.execute("SELECT COUNT(*) FROM config_ld").fetchone()[0])
                    sla_count = int(conn.execute("SELECT COUNT(*) FROM sla_config").fetchone()[0])

                    if dashboard_count <= 0:
                        errors.append("dashboard_records is empty")
                    if cb_count <= 0:
                        errors.append("config_cb_full is empty")
                    if ld_count <= 0:
                        errors.append("config_ld is empty")
                    if sla_count <= 0:
                        errors.append("sla_config is empty")

                    sync_health = get_sqlite_sync_health(db_path)
                    if sync_health.get("health_level") == "FAILED":
                        errors.append(f"Sync health failed: {sync_health.get('message')}")
                    elif sync_health.get("health_level") == "WARN":
                        warns.append(
                            f"Sync health warn: {sync_health.get('message')} "
                            f"(latest={sync_health.get('latest_status')}, last_success={sync_health.get('last_success_at')})"
                        )

                    open_closed = pd.read_sql_query(
                        'SELECT "Trạng thái Luồng" as status, COUNT(*) as cnt FROM dashboard_records GROUP BY "Trạng thái Luồng"',
                        conn,
                    )
                    _print("Dashboard status counts:")
                    if open_closed.empty:
                        _print("- none")
                    else:
                        _print(open_closed.to_string(index=False))
            finally:
                conn.close()
        except Exception as exc:
            errors.append(f"DB open/query error: {exc}")

    if not status_path.exists():
        warns.append(f"Status file missing: {status_path}")
    else:
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            last_success = _iso_to_dt(status.get("last_success_at"))
            if last_success is None:
                warns.append("status.last_success_at missing")
            else:
                age = datetime.now() - last_success
                if age > timedelta(seconds=args.max_age_seconds):
                    warns.append(f"last_success_at too old: {int(age.total_seconds())}s")
            _print("Status JSON:")
            _print(json.dumps(status, ensure_ascii=False, indent=2))
        except Exception as exc:
            warns.append(f"Cannot parse status JSON: {exc}")

    if errors:
        _print("HEALTH FAILED")
        for e in errors:
            _print(f"- ERROR: {e}")
        for w in warns:
            _print(f"- WARN: {w}")
        return 1

    if warns:
        _print("HEALTH WARN")
        for w in warns:
            _print(f"- WARN: {w}")
        return 2

    _print("HEALTH OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
