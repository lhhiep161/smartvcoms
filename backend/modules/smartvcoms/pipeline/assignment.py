"""Officer assignment logic for VCOMS dashboard records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def recalculate_config_load(config_cb: pd.DataFrame, dashboard_df: pd.DataFrame) -> pd.DataFrame:
    """Recompute workload score columns from current dashboard snapshot."""
    cb = config_cb.copy()

    name_col = "Tên Cán bộ"
    status_col = "Trạng thái"
    total_col = "Tổng phút SLA"
    offset_col = "Phút Bù Trừ"
    score_col = "Điểm Phân Giao"

    totals = (
        dashboard_df.groupby("CB HTTD", dropna=True)["Thời gian SLA"].sum(min_count=1).fillna(0).to_dict()
        if "CB HTTD" in dashboard_df.columns and "Thời gian SLA" in dashboard_df.columns
        else {}
    )

    cb[total_col] = cb[name_col].map(lambda n: totals.get(n, 0.0) if pd.notna(n) else 0.0)
    if offset_col not in cb.columns:
        cb[offset_col] = 0.0
    cb[offset_col] = pd.to_numeric(cb[offset_col], errors="coerce").fillna(0.0)
    cb[score_col] = pd.to_numeric(cb[total_col], errors="coerce").fillna(0.0) + cb[offset_col]

    if "Lần giao cuối" not in cb.columns:
        cb["Lần giao cuối"] = pd.NaT
    if status_col not in cb.columns:
        cb[status_col] = "Ready"

    return cb


def assign_officer(record: dict[str, Any], dashboard_df: pd.DataFrame, config_cb: pd.DataFrame, suggested_cb: str = "") -> str | None:
    """Assign officer using VBA rule: suggested Ready first, else lowest score and oldest assign time."""
    if config_cb.empty:
        return None

    name_col = "Tên Cán bộ"
    status_col = "Trạng thái"

    ready = config_cb[config_cb[status_col].astype(str).str.lower() == "ready"].copy()
    if ready.empty:
        first = config_cb[name_col].dropna()
        return str(first.iloc[0]) if not first.empty else None

    if suggested_cb:
        m = ready[ready[name_col].astype(str).str.strip() == str(suggested_cb).strip()]
        if not m.empty:
            return str(suggested_cb).strip()

    ready["Điểm Phân Giao"] = pd.to_numeric(ready.get("Điểm Phân Giao", 0), errors="coerce").fillna(0)
    ready["Lần giao cuối"] = pd.to_datetime(ready.get("Lần giao cuối"), errors="coerce")
    ready = ready.sort_values(by=["Điểm Phân Giao", "Lần giao cuối"], ascending=[True, True], na_position="first")

    chosen = ready.iloc[0].get(name_col)
    return str(chosen) if pd.notna(chosen) else None


def update_last_assigned(config_cb: pd.DataFrame, officer: str, timestamp: datetime | pd.Timestamp | None) -> pd.DataFrame:
    """Update in-memory last-assigned timestamp for selected officer."""
    if not officer:
        return config_cb
    cb = config_cb.copy()
    if "Tên Cán bộ" not in cb.columns:
        return cb
    if "Lần giao cuối" not in cb.columns:
        cb["Lần giao cuối"] = pd.NaT
    cb["Lần giao cuối"] = pd.to_datetime(cb["Lần giao cuối"], errors="coerce").dt.floor("s")
    ts = pd.to_datetime(timestamp, errors="coerce")
    if pd.isna(ts):
        ts = pd.Timestamp.now()
    ts = pd.Timestamp(ts).floor("s")
    mask = cb["Tên Cán bộ"].astype(str) == str(officer)
    if not mask.any():
        return cb
    # Assign through series to avoid pandas datetime64[s] precision conversion errors.
    series = cb["Lần giao cuối"].astype("object")
    series.loc[mask] = ts
    cb["Lần giao cuối"] = pd.to_datetime(series, errors="coerce")
    return cb
