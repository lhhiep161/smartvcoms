"""SLA calculation helpers with working-hours calendar."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

import pandas as pd


WORK_WINDOWS = [(time(8, 0), time(11, 30)), (time(13, 30), time(15, 30))]


def _is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5


def working_minutes_between(start: datetime | pd.Timestamp, end: datetime | pd.Timestamp) -> int:
    """Calculate working minutes between timestamps with minute-by-minute VBA-compatible loop."""
    if pd.isna(start) or pd.isna(end):
        return 0
    if end <= start:
        return 0

    cur = pd.Timestamp(start).to_pydatetime()
    end_dt = pd.Timestamp(end).to_pydatetime()
    total = 0

    while cur < end_dt:
        wd = cur.weekday()
        t = cur.time()
        is_work = wd < 5 and ((time(8, 0) <= t < time(11, 30)) or (time(13, 30) <= t < time(15, 30)))
        if is_work:
            total += 1
        cur = cur + timedelta(minutes=1)
    return int(total)


def calculate_sla(record: dict[str, Any], sla_config: dict[str, float]) -> tuple[float, float, float]:
    """Calculate total/HTTD/BGĐ SLA minutes for one dashboard row."""
    hs_den = record.get("Hồ sơ đến")
    sla_deadline = record.get("SLA")
    progress = str(record.get("Tiến độ HS") or "").lower()
    is_ky_so_progress = ("ký số" in progress) or ("kí số" in progress)
    is_return = bool(record.get("_is_return_case", False))

    if pd.isna(hs_den) or str(hs_den).strip() == "":
        # VBA-aligned: rút gọn ký số dùng O1, còn HS-den-only chưa có SLA giữ 60.
        if is_ky_so_progress or is_return:
            total = float(sla_config.get("sla_default", 45.0))
        else:
            total = 60.0
    else:
        if pd.isna(sla_deadline) or str(sla_deadline).strip() == "":
            total = 60.0
        else:
            total = float(working_minutes_between(hs_den, sla_deadline))

    total = min(total, float(sla_config.get("sla_max", 180.0)))

    if is_return:
        factor = float(sla_config.get("return_factor", 1.0))
        if factor > 1:
            factor = factor / 100.0
        total = total * factor

    total = float(int(total))  # VBA-like truncation
    httd = total * float(sla_config.get("alloc_httd", 0.8))
    bgd = total * float(sla_config.get("alloc_bgd", 0.2))
    return float(total), round(httd, 2), round(bgd, 2)
