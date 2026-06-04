from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.modules.smartvcoms.pipeline.state_machine import rebuild_from_raw
from backend.modules.smartvcoms.store.config_admin import sync_config_cb_load_from_case_state


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="runtime_data/smartvcoms/vcoms.db")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--today-only", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    stats = rebuild_from_raw(
        db_path=args.db,
        reset=args.reset,
        today_only=args.today_only,
        verbose=args.verbose,
    )
    sync_config_cb_load_from_case_state(args.db)
    print(
        f"raw_count={stats.raw_count} event_count={stats.event_count} case_count={stats.case_count} "
        f"unmatched_count={stats.unmatched_count} parse_warning_count={stats.parse_warning_count} "
        f"LC_count={stats.lc_count} returned_count={stats.returned_count} sla_changed_count={stats.sla_changed_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
